"""
Node settings dialog utilities.
Provides a generic dialog to edit full properties for any node.
"""

from typing import Any, Dict

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDialogButtonBox,
    QScrollArea,
    QWidget,
    QFormLayout,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QCheckBox,
    QPushButton,
    QFileDialog,
)


from core.properties import get_node_property_definitions


class _SettingsDialog(QDialog):
    def __init__(self, node):
        super().__init__()
        self.setWindowTitle(f"Settings - {node.title}")
        self._node = node
        self._editors: dict[str, QWidget] = {}

        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_host = QWidget()
        self.form = QFormLayout(form_host)
        self.form.setContentsMargins(10, 10, 10, 10)
        scroll.setWidget(form_host)
        layout.addWidget(scroll)

        # Build editors from shared property definitions per node type
        try:
            defs = get_node_property_definitions(getattr(node, 'node_type', ''))
        except Exception:
            defs = []
        # Ensure existing properties still editable even if not in defs
        seen = set()
        for prop in defs:
            name = str(prop.get('name'))
            label = str(prop.get('label', name))
            editor = self._create_editor_for_definition(prop)
            # Seed with current value or default
            value = node.get_property(name, prop.get('default'))
            self._set_editor_value(editor, value)
            self.form.addRow(QLabel(label), editor)
            self._editors[name] = editor
            seen.add(name)
        # Add any remaining node.properties not covered by defs
        for key, value in sorted((node.properties or {}).items()):
            if key in seen:
                continue
            editor = self._create_editor_for_value(value)
            self._set_editor_value(editor, value)
            self.form.addRow(QLabel(key), editor)
            self._editors[key] = editor

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_editor_for_value(self, value: Any) -> QWidget:
        if isinstance(value, bool):
            editor = QCheckBox()
            return editor
        if isinstance(value, int) and not isinstance(value, bool):
            sb = QSpinBox()
            sb.setRange(-999999, 999999)
            return sb
        if isinstance(value, float):
            dsb = QDoubleSpinBox()
            dsb.setRange(-1e9, 1e9)
            dsb.setDecimals(6)
            return dsb
        # Fallback to line edit for strings/others
        return QLineEdit()

    def _create_editor_for_definition(self, prop: Dict[str, Any]) -> QWidget:
        ptype = str(prop.get('type', 'string'))
        if ptype == 'bool':
            return QCheckBox()
        if ptype == 'int':
            sb = QSpinBox()
            sb.setRange(int(prop.get('min', -999999)), int(prop.get('max', 999999)))
            return sb
        if ptype == 'float':
            dsb = QDoubleSpinBox()
            dsb.setRange(float(prop.get('min', -1e9)), float(prop.get('max', 1e9)))
            dsb.setDecimals(int(prop.get('decimals', 6)))
            return dsb
        if ptype == 'choice':
            cmb = QComboBox()
            for item in prop.get('choices', []) or []:
                cmb.addItem(str(item))
            return cmb
        if ptype in ('file', 'multifile'):
            # Composite: QLineEdit + Browse button
            from PySide6.QtWidgets import QWidget, QHBoxLayout
            container = QWidget()
            hl = QHBoxLayout(container)
            hl.setContentsMargins(0, 0, 0, 0)
            le = QLineEdit()
            btn = QPushButton('Browse…')
            def _browse():
                if ptype == 'file':
                    filename, _ = QFileDialog.getOpenFileName(self, 'Select File', '', str(prop.get('filter', 'All Files (*)')))
                    if filename:
                        le.setText(filename)
                else:
                    filenames, _ = QFileDialog.getOpenFileNames(self, 'Select Files', '', str(prop.get('filter', 'All Files (*)')))
                    if filenames:
                        le.setText(';'.join(filenames))
            btn.clicked.connect(_browse)
            hl.addWidget(le)
            hl.addWidget(btn)
            # Store a reference so we can read value later
            container._line_edit = le  # type: ignore[attr-defined]
            return container
        # default: string/text
        return QLineEdit()

    def _set_editor_value(self, editor: QWidget, value: Any):
        if isinstance(editor, QCheckBox):
            editor.setChecked(bool(value))
        elif isinstance(editor, QSpinBox):
            editor.setValue(int(value))
        elif isinstance(editor, QDoubleSpinBox):
            editor.setValue(float(value))
        elif isinstance(editor, QLineEdit):
            editor.setText(str(value))
        else:
            # Composite file/multifile container
            le = getattr(editor, '_line_edit', None)
            if le is not None:
                try:
                    le.setText(str(value))
                except Exception:
                    pass

    def _get_editor_value(self, editor: QWidget) -> Any:
        if isinstance(editor, QCheckBox):
            return editor.isChecked()
        if isinstance(editor, QSpinBox):
            return editor.value()
        if isinstance(editor, QDoubleSpinBox):
            return editor.value()
        if isinstance(editor, QComboBox):
            return editor.currentText()
        if isinstance(editor, QLineEdit):
            return editor.text()
        # Composite file/multifile container
        le = getattr(editor, '_line_edit', None)
        if le is not None:
            try:
                return le.text()
            except Exception:
                return ''
        return None

    def values(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        for key, editor in self._editors.items():
            data[key] = self._get_editor_value(editor)
        return data


def open_settings_dialog(node) -> bool:
    """Open the settings dialog for a node. Returns True if any change applied."""
    dlg = _SettingsDialog(node)
    if dlg.exec() == QDialog.Accepted:
        vals = dlg.values()
        changed = False
        for k, v in vals.items():
            if node.get_property(k) != v:
                node.set_property(k, v)
                changed = True
        # Apply auxiliary toggles for nodes that require it
        try:
            if getattr(node, 'node_type', '') == 'grid_search':
                cx = vals.get('center_x')
                cy = vals.get('center_y')
                cz = vals.get('center_z')
                sx = vals.get('size_x')
                sy = vals.get('size_y')
                sz = vals.get('size_z')
                if any(val is not None for val in (cx, cy, cz)):
                    node.set_property('override_center', True)
                    changed = True
                if any(val is not None for val in (sx, sy, sz)):
                    node.set_property('override_size', True)
                    changed = True
        except Exception:
            pass
        return changed
    return False


