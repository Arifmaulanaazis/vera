"""
Properties panel for displaying and editing node properties.
"""

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox,
                               QCheckBox, QPushButton, QTextEdit, QFormLayout,
                               QScrollArea, QFrame, QFileDialog, QGroupBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class PropertyWidget(QWidget):
    """Base class for property widgets."""
    
    value_changed = Signal(str, object)  # property_name, value
    
    def __init__(self, property_name, label_text):
        super().__init__()
        self.property_name = property_name
        self.label_text = label_text
        
    def get_value(self):
        """Get the current value. Override in subclasses."""
        raise NotImplementedError
        
    def set_value(self, value):
        """Set the value. Override in subclasses."""
        raise NotImplementedError


class StringPropertyWidget(PropertyWidget):
    """Widget for string properties."""
    
    def __init__(self, property_name, label_text, default_value=""):
        super().__init__(property_name, label_text)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(label_text)
        label.setFixedWidth(100)
        layout.addWidget(label)
        
        # Line edit
        self.line_edit = QLineEdit(default_value)
        self.line_edit.textChanged.connect(self._on_value_changed)
        layout.addWidget(self.line_edit)
        
    def get_value(self):
        return self.line_edit.text()
        
    def set_value(self, value):
        self.line_edit.setText(str(value))
        
    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())


class FilePropertyWidget(PropertyWidget):
    """Widget for file path properties."""
    
    def __init__(self, property_name, label_text, file_filter="All Files (*)", default_value=""):
        super().__init__(property_name, label_text)
        self.file_filter = file_filter
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(label_text)
        label.setFixedWidth(100)
        layout.addWidget(label)
        
        # Line edit
        self.line_edit = QLineEdit(default_value)
        self.line_edit.textChanged.connect(self._on_value_changed)
        layout.addWidget(self.line_edit)
        
        # Browse button
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_file)
        layout.addWidget(browse_btn)
        
    def get_value(self):
        return self.line_edit.text()
        
    def set_value(self, value):
        self.line_edit.setText(str(value))
        
    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())
        
    def _browse_file(self):
        # Use save dialog for output-like properties
        label = (self.label_text or "").lower()
        is_output = any(k in label for k in ("output", "save", "path"))
        if is_output:
            filename, _ = QFileDialog.getSaveFileName(
                self, f"Select {self.label_text}", self.line_edit.text(), self.file_filter
            )
        else:
            filename, _ = QFileDialog.getOpenFileName(
                self, f"Select {self.label_text}", "", self.file_filter
            )
        if filename:
            self.set_value(filename)


class MultiFilePropertyWidget(PropertyWidget):
    """Widget for multi-file path properties (semicolon-separated in line edit)."""

    def __init__(self, property_name, label_text, file_filter="All Files (*)", default_value=""):
        super().__init__(property_name, label_text)
        self.file_filter = file_filter

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel(label_text)
        label.setFixedWidth(100)
        layout.addWidget(label)

        self.line_edit = QLineEdit(default_value)
        self.line_edit.setPlaceholderText("path1; path2; path3 …")
        self.line_edit.textChanged.connect(self._on_value_changed)
        layout.addWidget(self.line_edit)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse_files)
        layout.addWidget(browse_btn)

    def get_value(self):
        return self.line_edit.text()

    def set_value(self, value):
        self.line_edit.setText(str(value))

    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())

    def _browse_files(self):
        filenames, _ = QFileDialog.getOpenFileNames(
            self, f"Select {self.label_text}", "", self.file_filter
        )
        if filenames:
            # Join with semicolon as requested UX
            self.set_value(";".join(filenames))


class IntPropertyWidget(PropertyWidget):
    """Widget for integer properties."""
    
    def __init__(self, property_name, label_text, default_value=0, min_val=-999999, max_val=999999):
        super().__init__(property_name, label_text)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(label_text)
        label.setFixedWidth(100)
        layout.addWidget(label)
        
        # Spin box
        self.spin_box = QSpinBox()
        self.spin_box.setRange(min_val, max_val)
        self.spin_box.setValue(default_value)
        self.spin_box.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.spin_box)
        
    def get_value(self):
        return self.spin_box.value()
        
    def set_value(self, value):
        self.spin_box.setValue(int(value))
        
    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())


class FloatPropertyWidget(PropertyWidget):
    """Widget for float properties."""
    
    def __init__(self, property_name, label_text, default_value=0.0, min_val=-999999.0, max_val=999999.0, decimals=3):
        super().__init__(property_name, label_text)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(label_text)
        label.setFixedWidth(100)
        layout.addWidget(label)
        
        # Double spin box
        self.spin_box = QDoubleSpinBox()
        self.spin_box.setRange(min_val, max_val)
        self.spin_box.setDecimals(decimals)
        self.spin_box.setValue(default_value)
        self.spin_box.valueChanged.connect(self._on_value_changed)
        layout.addWidget(self.spin_box)
        
    def get_value(self):
        return self.spin_box.value()
        
    def set_value(self, value):
        self.spin_box.setValue(float(value))
        
    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())


class ComboPropertyWidget(PropertyWidget):
    """Widget for choice properties."""
    
    def __init__(self, property_name, label_text, choices, default_index=0):
        super().__init__(property_name, label_text)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(label_text)
        label.setFixedWidth(100)
        layout.addWidget(label)
        
        # Combo box
        self.combo_box = QComboBox()
        self.combo_box.addItems(choices)
        self.combo_box.setCurrentIndex(default_index)
        self.combo_box.currentTextChanged.connect(self._on_value_changed)
        layout.addWidget(self.combo_box)
        
    def get_value(self):
        return self.combo_box.currentText()
        
    def set_value(self, value):
        index = self.combo_box.findText(str(value))
        if index >= 0:
            self.combo_box.setCurrentIndex(index)
        
    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())


class BoolPropertyWidget(PropertyWidget):
    """Widget for boolean properties."""
    
    def __init__(self, property_name, label_text, default_value=False):
        super().__init__(property_name, label_text)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Checkbox
        self.checkbox = QCheckBox(label_text)
        self.checkbox.setChecked(default_value)
        self.checkbox.toggled.connect(self._on_value_changed)
        layout.addWidget(self.checkbox)
        
    def get_value(self):
        return self.checkbox.isChecked()
        
    def set_value(self, value):
        self.checkbox.setChecked(bool(value))
        
    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())


class TextPropertyWidget(PropertyWidget):
    """Widget for multi-line text properties."""
    
    def __init__(self, property_name, label_text, default_value=""):
        super().__init__(property_name, label_text)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Label
        label = QLabel(label_text)
        layout.addWidget(label)
        
        # Text edit
        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(default_value)
        self.text_edit.setMaximumHeight(100)
        self.text_edit.textChanged.connect(self._on_value_changed)
        layout.addWidget(self.text_edit)
        
    def get_value(self):
        return self.text_edit.toPlainText()
        
    def set_value(self, value):
        self.text_edit.setPlainText(str(value))
        
    def _on_value_changed(self):
        self.value_changed.emit(self.property_name, self.get_value())


def get_node_property_definitions(node_type: str):
    """Public API: return property definitions for a node type.

    Shared by the old side panel and the settings dialog shown on double-click.
    """
    # This would normally come from a configuration file or node registry
    # For now, return some common properties based on node type
    common_props = [
        {'name': 'name', 'type': 'string', 'label': 'Name', 'default': ''},
        {'name': 'description', 'type': 'text', 'label': 'Description', 'default': ''},
    ]

    if node_type == 'vina_split':
        return common_props + [
            {'name': 'start_index_1based', 'type': 'int', 'label': 'Start Index (1-based)', 'default': 1, 'min': 1, 'max': 999999},
            {'name': 'num_outputs', 'type': 'int', 'label': 'Number of Outputs', 'default': 3, 'min': 1, 'max': 999999},
        ]
    elif 'vina' in node_type:
        return common_props + [
            {'name': 'center_x', 'type': 'float', 'label': 'Center X', 'default': 0.0},
            {'name': 'center_y', 'type': 'float', 'label': 'Center Y', 'default': 0.0},
            {'name': 'center_z', 'type': 'float', 'label': 'Center Z', 'default': 0.0},
            {'name': 'size_x', 'type': 'float', 'label': 'Size X', 'default': 20.0},
            {'name': 'size_y', 'type': 'float', 'label': 'Size Y', 'default': 20.0},
            {'name': 'size_z', 'type': 'float', 'label': 'Size Z', 'default': 20.0},
            {'name': 'exhaustiveness', 'type': 'int', 'label': 'Exhaustiveness', 'default': 8, 'min': 1, 'max': 100},
            {'name': 'num_modes', 'type': 'int', 'label': 'Number of Modes', 'default': 9, 'min': 1, 'max': 20},
        ]
    elif 'rdkit' in node_type:
        return common_props + [
            {'name': 'input_file', 'type': 'file', 'label': 'Input File', 'filter': 'SDF Files (*.sdf)', 'default': ''},
            {'name': 'output_file', 'type': 'file', 'label': 'Output File', 'filter': 'SDF Files (*.sdf)', 'default': ''},
            {'name': 'max_iterations', 'type': 'int', 'label': 'Max Iterations', 'default': 1000, 'min': 1, 'max': 10000},
            {'name': 'force_field', 'type': 'choice', 'label': 'Force Field', 'choices': ['MMFF94', 'UFF'], 'default': 'MMFF94'},
            {'name': 'optimize_conformers', 'type': 'bool', 'label': 'Optimize Multiple Conformers', 'default': True},
            {'name': 'num_conformers', 'type': 'int', 'label': 'Number of Conformers', 'default': 50, 'min': 1, 'max': 200},
            {'name': 'add_hydrogens', 'type': 'bool', 'label': 'Add Hydrogens', 'default': True},
        ]
    elif 'openbabel' in node_type:
        return common_props + [
            {'name': 'force_field', 'type': 'choice', 'label': 'Force Field', 'choices': ['MMFF94', 'UFF'], 'default': 'MMFF94'},
            {'name': 'steps', 'type': 'int', 'label': 'Steps', 'default': 1000, 'min': 1, 'max': 1000000},
            {'name': 'convergence', 'type': 'float', 'label': 'Convergence', 'default': 1e-6, 'min': 0.0, 'max': 1.0, 'decimals': 9},
            {'name': 'steepest_descent', 'type': 'bool', 'label': 'Use Steepest Descent', 'default': True},
            {'name': 'conjugate_gradient', 'type': 'bool', 'label': 'Use Conjugate Gradient', 'default': True},
            {'name': 'add_hydrogens', 'type': 'bool', 'label': 'Add Hydrogens', 'default': True},
        ]
    elif 'gromacs' in node_type:
        return common_props + [
            {'name': 'input_file', 'type': 'file', 'label': 'Input File', 'filter': 'GRO Files (*.gro)', 'default': ''},
            {'name': 'topology_file', 'type': 'file', 'label': 'Topology', 'filter': 'TOP Files (*.top)', 'default': ''},
            {'name': 'mdp_file', 'type': 'file', 'label': 'MDP File', 'filter': 'MDP Files (*.mdp)', 'default': ''},
            {'name': 'gromacs_version', 'type': 'choice', 'label': 'GROMACS Version', 'choices': ['2025.2', '2025.1'], 'default': '2025.2'},
            {'name': 'use_gpu', 'type': 'bool', 'label': 'Use GPU', 'default': False},
            {'name': 'threads', 'type': 'int', 'label': 'Threads', 'default': 0, 'min': 0, 'max': 128},
            {'name': 'deffnm', 'type': 'string', 'label': 'Name stem', 'default': 'run'},
        ]
    elif node_type == 'prolif_interaction':
        return common_props + [
            {'name': 'protein_index', 'type': 'int', 'label': 'Protein Index', 'default': 0, 'min': 0, 'max': 99999},
            {'name': 'ligand_index', 'type': 'int', 'label': 'Ligand Index', 'default': 0, 'min': 0, 'max': 99999},
        ]
    elif node_type == 'pubchem_search':
        return common_props + [
            {'name': 'query', 'type': 'string', 'label': 'Query', 'default': ''},
            {'name': 'selected_column', 'type': 'string', 'label': 'Selected Column', 'default': ''},
            {'name': 'max_workers', 'type': 'int', 'label': 'Workers', 'default': 4, 'min': 1, 'max': 16},
        ]
    elif node_type == 'text_input':
        return common_props + [
            {'name': 'text', 'type': 'string', 'label': 'Text', 'default': ''},
            {'name': 'placeholder', 'type': 'string', 'label': 'Placeholder', 'default': 'Type here…'},
        ]
    elif node_type in ('plot_histogram', 'plot_scatter', 'plot_line', 'plot_bar', 'plot_pie', 'plot_donut'):
        base = [
            {'name': 'title', 'type': 'string', 'label': 'Title', 'default': ''},
        ]
        if node_type == 'plot_histogram':
            base += [
                {'name': 'value_key', 'type': 'string', 'label': 'Value Column', 'default': ''},
                {'name': 'bins', 'type': 'int', 'label': 'Bins', 'default': 20, 'min': 1, 'max': 200},
            ]
        elif node_type in ('plot_scatter', 'plot_line'):
            base += [
                {'name': 'x_key', 'type': 'string', 'label': 'X Column', 'default': ''},
                {'name': 'y_key', 'type': 'string', 'label': 'Y Column', 'default': ''},
            ]
        elif node_type in ('plot_bar',):
            base += [
                {'name': 'label_key', 'type': 'string', 'label': 'Label Column', 'default': ''},
                {'name': 'value_key', 'type': 'string', 'label': 'Value Column', 'default': ''},
            ]
        elif node_type in ('plot_pie', 'plot_donut'):
            base += [
                {'name': 'label_key', 'type': 'string', 'label': 'Label Column', 'default': ''},
                {'name': 'value_key', 'type': 'string', 'label': 'Value Column', 'default': ''},
            ]
            if node_type == 'plot_donut':
                base += [
                    {'name': 'hole', 'type': 'float', 'label': 'Hole Radius (0-1)', 'default': 0.5, 'min': 0.0, 'max': 0.9, 'decimals': 2},
                ]
        return common_props + base
    elif node_type in (
        'ml_train_test_split',
        'ml_logistic_regression', 'ml_random_forest_classifier', 'ml_svm_classifier', 'ml_knn_classifier',
        'ml_linear_regression', 'ml_random_forest_regressor', 'ml_svr',
        'eval_confusion_matrix', 'eval_classification_report', 'eval_regression_metrics',
        'cluster_kmeans', 'cluster_agglomerative', 'dim_pca',
    ):
        # ML-related properties
        base: list[dict] = []
        if node_type == 'ml_train_test_split':
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'test_size', 'type': 'float', 'label': 'Test Size (0-1)', 'default': 0.2, 'min': 0.01, 'max': 0.99, 'decimals': 2},
                {'name': 'random_state', 'type': 'int', 'label': 'Random State', 'default': 42, 'min': 0, 'max': 999999},
                {'name': 'shuffle', 'type': 'bool', 'label': 'Shuffle', 'default': True},
                {'name': 'stratify', 'type': 'bool', 'label': 'Stratify by Target', 'default': True},
            ]
        elif node_type in ('ml_logistic_regression',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Features', 'default': False},
                {'name': 'C', 'type': 'float', 'label': 'C (Inverse Regularization)', 'default': 1.0, 'min': 0.0001, 'max': 1e6, 'decimals': 4},
                {'name': 'max_iter', 'type': 'int', 'label': 'Max Iter', 'default': 200, 'min': 10, 'max': 10000},
                {'name': 'solver', 'type': 'choice', 'label': 'Solver', 'choices': ['lbfgs','liblinear','saga','newton-cg','sag'], 'default': 'lbfgs'},
                {'name': 'penalty', 'type': 'choice', 'label': 'Penalty', 'choices': ['l2','l1','elasticnet','none'], 'default': 'l2'},
            ]
        elif node_type in ('ml_random_forest_classifier',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Features', 'default': False},
                {'name': 'n_estimators', 'type': 'int', 'label': 'Trees', 'default': 200, 'min': 1, 'max': 2000},
                {'name': 'max_depth', 'type': 'int', 'label': 'Max Depth (0=None)', 'default': 0, 'min': 0, 'max': 200},
                {'name': 'min_samples_split', 'type': 'int', 'label': 'Min Samples Split', 'default': 2, 'min': 2, 'max': 20},
                {'name': 'random_state', 'type': 'int', 'label': 'Random State', 'default': 42, 'min': 0, 'max': 999999},
            ]
        elif node_type in ('ml_svm_classifier',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Features', 'default': True},
                {'name': 'kernel', 'type': 'choice', 'label': 'Kernel', 'choices': ['rbf','linear','poly','sigmoid'], 'default': 'rbf'},
                {'name': 'C', 'type': 'float', 'label': 'C', 'default': 1.0, 'min': 0.0001, 'max': 1e6, 'decimals': 4},
                {'name': 'gamma', 'type': 'choice', 'label': 'Gamma', 'choices': ['scale','auto'], 'default': 'scale'},
            ]
        elif node_type in ('ml_knn_classifier',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Features', 'default': True},
                {'name': 'n_neighbors', 'type': 'int', 'label': 'Neighbors', 'default': 5, 'min': 1, 'max': 200},
                {'name': 'weights', 'type': 'choice', 'label': 'Weights', 'choices': ['uniform','distance'], 'default': 'uniform'},
                {'name': 'metric', 'type': 'choice', 'label': 'Metric', 'choices': ['minkowski','euclidean','manhattan','chebyshev'], 'default': 'minkowski'},
            ]
        elif node_type in ('ml_linear_regression',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Features', 'default': False},
                {'name': 'fit_intercept', 'type': 'bool', 'label': 'Fit Intercept', 'default': True},
            ]
        elif node_type in ('ml_random_forest_regressor',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Features', 'default': False},
                {'name': 'n_estimators', 'type': 'int', 'label': 'Trees', 'default': 200, 'min': 1, 'max': 2000},
                {'name': 'max_depth', 'type': 'int', 'label': 'Max Depth (0=None)', 'default': 0, 'min': 0, 'max': 200},
                {'name': 'min_samples_split', 'type': 'int', 'label': 'Min Samples Split', 'default': 2, 'min': 2, 'max': 20},
                {'name': 'random_state', 'type': 'int', 'label': 'Random State', 'default': 42, 'min': 0, 'max': 999999},
            ]
        elif node_type in ('ml_svr',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Features', 'default': True},
                {'name': 'kernel', 'type': 'choice', 'label': 'Kernel', 'choices': ['rbf','linear','poly','sigmoid'], 'default': 'rbf'},
                {'name': 'C', 'type': 'float', 'label': 'C', 'default': 1.0, 'min': 0.0001, 'max': 1e6, 'decimals': 4},
                {'name': 'epsilon', 'type': 'float', 'label': 'Epsilon', 'default': 0.1, 'min': 0.0, 'max': 10.0, 'decimals': 3},
                {'name': 'gamma', 'type': 'choice', 'label': 'Gamma', 'choices': ['scale','auto'], 'default': 'scale'},
            ]
        elif node_type in ('eval_confusion_matrix',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
                {'name': 'normalize', 'type': 'choice', 'label': 'Normalize', 'choices': ['none','true','pred'], 'default': 'none'},
                {'name': 'title', 'type': 'string', 'label': 'Title', 'default': 'Confusion Matrix'},
            ]
        elif node_type in ('eval_classification_report',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
            ]
        elif node_type in ('eval_regression_metrics',):
            base = [
                {'name': 'target_column', 'type': 'string', 'label': 'Target Column', 'default': ''},
            ]
        elif node_type in ('cluster_kmeans',):
            base = [
                {'name': 'n_clusters', 'type': 'int', 'label': 'Clusters', 'default': 3, 'min': 1, 'max': 100},
                {'name': 'init', 'type': 'choice', 'label': 'Init', 'choices': ['k-means++','random'], 'default': 'k-means++'},
                {'name': 'n_init', 'type': 'int', 'label': 'n_init', 'default': 10, 'min': 1, 'max': 1000},
                {'name': 'random_state', 'type': 'int', 'label': 'Random State', 'default': 42, 'min': 0, 'max': 999999},
            ]
        elif node_type in ('cluster_agglomerative',):
            base = [
                {'name': 'n_clusters', 'type': 'int', 'label': 'Clusters', 'default': 3, 'min': 1, 'max': 100},
                {'name': 'linkage', 'type': 'choice', 'label': 'Linkage', 'choices': ['ward','complete','average','single'], 'default': 'ward'},
                {'name': 'affinity', 'type': 'choice', 'label': 'Affinity/Metric', 'choices': ['euclidean','l1','l2','manhattan','cosine'], 'default': 'euclidean'},
            ]
        elif node_type in ('dim_pca',):
            base = [
                {'name': 'n_components', 'type': 'int', 'label': 'Components', 'default': 2, 'min': 1, 'max': 50},
                {'name': 'standardize', 'type': 'bool', 'label': 'Standardize Before PCA', 'default': True},
            ]
        return common_props + base
    elif node_type in ('file_output', 'save_file'):
        return common_props + [
            {'name': 'output_path', 'type': 'file', 'label': 'Output Path', 'filter': 'All Files (*)', 'default': ''},
            # Include common molecule/data/model formats; 'auto' infers from extension
            {'name': 'file_type', 'type': 'choice', 'label': 'File Type', 'choices': [
                'auto',
                # Molecules
                'sdf', 'mol', 'mol2', 'pdb', 'pdbqt', 'xyz',
                # Tabular/Text
                'csv', 'tsv', 'xlsx', 'xls', 'json', 'txt', 'arw',
                # Models
                'pkl', 'joblib'
            ], 'default': 'auto'},
            {'name': 'overwrite', 'type': 'bool', 'label': 'Overwrite', 'default': True},
        ]
    elif node_type in ('file_input',):
        return common_props + [
            {'name': 'file_paths', 'type': 'multifile', 'label': 'Input Files', 'filter': 'All Files (*);;Chemistry (*.sdf *.mol *.mol2 *.pdb *.pdbqt *.xyz);;Data (*.csv *.tsv *.xlsx *.xls *.txt *.json *.arw)', 'default': ''},
        ]
    elif node_type in ('chrom_reader',):
        return common_props + [
            {'name': 'instrument', 'type': 'choice', 'label': 'Instrument', 'choices': ['generic','hplc','ir','ms'], 'default': 'generic'},
            {'name': 'x_label', 'type': 'string', 'label': 'X Label', 'default': 'x'},
            {'name': 'y_label', 'type': 'string', 'label': 'Y Label', 'default': 'y'},
            {'name': 'x_column', 'type': 'string', 'label': 'X Column Override', 'default': ''},
            {'name': 'y_column', 'type': 'string', 'label': 'Y Column Override', 'default': ''},
            {'name': 'separator', 'type': 'choice', 'label': 'Separator', 'choices': ['auto','comma','semicolon','tab','space'], 'default': 'auto'},
            {'name': 'encoding', 'type': 'string', 'label': 'Encoding', 'default': 'utf-8'},
        ]
    elif node_type in ('sdf_reader', 'mol_reader', 'mol2_reader', 'pdb_reader', 'pdbqt_reader', 'mol_reader_auto'):
        return common_props + [
            {'name': 'file_paths', 'type': 'multifile', 'label': 'Molecule Files', 'filter': 'Molecules (*.sdf *.mol *.mol2 *.pdb *.pdbqt)', 'default': ''},
        ]
    elif node_type in ('csv_reader',):
        return common_props + [
            {'name': 'file_paths', 'type': 'multifile', 'label': 'CSV/TSV Files', 'filter': 'CSV/TSV (*.csv *.tsv);;All Files (*)', 'default': ''},
            {'name': 'delimiter', 'type': 'choice', 'label': 'Delimiter', 'choices': ['auto', 'comma', 'semicolon', 'tab'], 'default': 'auto'},
            {'name': 'encoding', 'type': 'string', 'label': 'Encoding', 'default': 'utf-8'},
        ]
    elif node_type in ('excel_reader',):
        return common_props + [
            {'name': 'file_paths', 'type': 'multifile', 'label': 'Excel Files', 'filter': 'Excel (*.xlsx *.xls);;All Files (*)', 'default': ''},
            {'name': 'sheet', 'type': 'string', 'label': 'Sheet Name/Index', 'default': ''},
            {'name': 'header', 'type': 'bool', 'label': 'Use Header', 'default': True},
            {'name': 'engine', 'type': 'choice', 'label': 'Engine', 'choices': ['auto', 'openpyxl', 'xlrd'], 'default': 'auto'},
        ]
    elif node_type in ('txt_reader',):
        return common_props + [
            {'name': 'file_paths', 'type': 'multifile', 'label': 'Text Files', 'filter': 'Text (*.txt);;All Files (*)', 'default': ''},
            {'name': 'mode', 'type': 'choice', 'label': 'Mode', 'choices': ['lines', 'text'], 'default': 'lines'},
            {'name': 'encoding', 'type': 'string', 'label': 'Encoding', 'default': 'utf-8'},
        ]
    elif node_type in ('grid_search',):
        return common_props + [
            {'name': 'padding', 'type': 'float', 'label': 'Padding (Å)', 'default': 5.0},
            {'name': 'mode', 'type': 'choice', 'label': 'Mode', 'choices': ['ligand', 'protein', 'custom'], 'default': 'ligand'},
            {'name': 'pdb_code', 'type': 'string', 'label': 'PDB Code', 'default': ''},
            {'name': 'selected_residue', 'type': 'string', 'label': 'Ligand (RES:CHAIN:RESNUM)', 'default': ''},
            {'name': 'min_size', 'type': 'float', 'label': 'Min Size (Å)', 'default': 16.0, 'min': 4.0, 'max': 200.0, 'decimals': 2},
            {'name': 'max_size', 'type': 'float', 'label': 'Max Size (Å)', 'default': 60.0, 'min': 8.0, 'max': 400.0, 'decimals': 2},
            {'name': 'override_center', 'type': 'bool', 'label': 'Override Center', 'default': False},
            {'name': 'center_x', 'type': 'float', 'label': 'Center X', 'default': 0.0, 'decimals': 3},
            {'name': 'center_y', 'type': 'float', 'label': 'Center Y', 'default': 0.0, 'decimals': 3},
            {'name': 'center_z', 'type': 'float', 'label': 'Center Z', 'default': 0.0, 'decimals': 3},
            {'name': 'override_size', 'type': 'bool', 'label': 'Override Size', 'default': False},
            {'name': 'size_x', 'type': 'float', 'label': 'Size X', 'default': 20.0, 'decimals': 3},
            {'name': 'size_y', 'type': 'float', 'label': 'Size Y', 'default': 20.0, 'decimals': 3},
            {'name': 'size_z', 'type': 'float', 'label': 'Size Z', 'default': 20.0, 'decimals': 3},
        ]
    elif node_type == 'receptor_preparation':
        return common_props + [
            {'name': 'remove_waters', 'type': 'bool', 'label': 'Remove Waters', 'default': True},
            {'name': 'remove_ligands', 'type': 'bool', 'label': 'Remove Ligands (HETATM)', 'default': True},
            {'name': 'keep_metals', 'type': 'bool', 'label': 'Keep Metals/Ions', 'default': True},
            {'name': 'metal_elements', 'type': 'string', 'label': 'Metal Elements (CSV)', 'default': 'ZN,MG,FE,MN,CU,CO,NI,CA,NA,K,CD,HG'},
            {'name': 'keep_resnames', 'type': 'string', 'label': 'Keep RESNAMES (CSV)', 'default': ''},
            {'name': 'remove_nonstd_residues', 'type': 'bool', 'label': 'Remove Non-std Residues', 'default': False},
            {'name': 'add_hydrogens_mode', 'type': 'choice', 'label': 'Add Hydrogens', 'choices': ['polar_only', 'all', 'none'], 'default': 'polar_only'},
            {'name': 'compute_charges', 'type': 'choice', 'label': 'Charges', 'choices': ['kollman', 'gasteiger', 'none'], 'default': 'kollman'},
            {'name': 'unique_atom_names', 'type': 'bool', 'label': 'Unique Atom Names', 'default': False},
        ]
    elif node_type == 'ligand_preparation':
        return common_props + [
            {'name': 'remove_salts', 'type': 'bool', 'label': 'Remove Salts (Largest Fragment)', 'default': True},
            {'name': 'neutralize', 'type': 'bool', 'label': 'Neutralize (Uncharger)', 'default': True},
            {'name': 'add_hydrogens_mode', 'type': 'choice', 'label': 'Add Hydrogens', 'choices': ['all', 'polar_only', 'none'], 'default': 'all'},
            {'name': 'embed_3d', 'type': 'bool', 'label': 'Embed 3D', 'default': True},
            {'name': 'minimize', 'type': 'bool', 'label': 'Minimize Geometry', 'default': True},
            {'name': 'force_field', 'type': 'choice', 'label': 'Force Field', 'choices': ['MMFF94', 'UFF'], 'default': 'MMFF94'},
            {'name': 'max_iterations', 'type': 'int', 'label': 'Max Iterations', 'default': 200, 'min': 1, 'max': 10000},
            {'name': 'compute_charges', 'type': 'choice', 'label': 'Charges', 'choices': ['gasteiger', 'none'], 'default': 'gasteiger'},
        ]
    elif node_type == 'manual_grid_box':
        return common_props + [
            {'name': 'center_x', 'type': 'float', 'label': 'Center X (Å)', 'default': None, 'decimals': 3},
            {'name': 'center_y', 'type': 'float', 'label': 'Center Y (Å)', 'default': None, 'decimals': 3},
            {'name': 'center_z', 'type': 'float', 'label': 'Center Z (Å)', 'default': None, 'decimals': 3},
            {'name': 'size_x', 'type': 'float', 'label': 'Size X (Å)', 'default': None, 'min': 0.0, 'max': 1000.0, 'decimals': 3},
            {'name': 'size_y', 'type': 'float', 'label': 'Size Y (Å)', 'default': None, 'min': 0.0, 'max': 1000.0, 'decimals': 3},
            {'name': 'size_z', 'type': 'float', 'label': 'Size Z (Å)', 'default': None, 'min': 0.0, 'max': 1000.0, 'decimals': 3},
        ]
    else:
        return common_props


class PropertiesPanel(QWidget):
    """Panel for displaying and editing node properties."""
    
    def __init__(self):
        super().__init__()
        
        self.current_node = None
        self.property_widgets = {}
        
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the properties panel UI."""
        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Title
        title = QLabel("Properties")
        title.setAlignment(Qt.AlignCenter)
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        title.setFont(font)
        layout.addWidget(title)
        
        # Add separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        layout.addWidget(separator)
        
        # Scroll area for properties
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        layout.addWidget(scroll_area)
        
        # Properties widget
        self.properties_widget = QWidget()
        self.properties_layout = QVBoxLayout(self.properties_widget)
        self.properties_layout.setContentsMargins(5, 5, 5, 5)
        scroll_area.setWidget(self.properties_widget)
        
        # No selection label
        self.no_selection_label = QLabel("No node selected")
        self.no_selection_label.setAlignment(Qt.AlignCenter)
        self.properties_layout.addWidget(self.no_selection_label)
        
        # Set fixed width
        self.setFixedWidth(300)
        
    def show_node_properties(self, node):
        """Show properties for the given node."""
        self.current_node = node
        self._clear_properties()
        
        if not node:
            return
            
        # Hide no selection label
        self.no_selection_label.hide()
        
        # Node info group
        info_group = QGroupBox("Node Information")
        info_layout = QVBoxLayout(info_group)
        
        # Node type
        type_label = QLabel(f"Type: {node.node_type}")
        info_layout.addWidget(type_label)
        
        # Node title
        title_label = QLabel(f"Title: {node.title}")
        info_layout.addWidget(title_label)
        
        self.properties_layout.addWidget(info_group)
        
        # Node-specific properties
        self._create_node_properties(node)
        
        # Add stretch at the end
        self.properties_layout.addStretch()
        
    def clear_properties(self):
        """Clear the properties panel."""
        self.current_node = None
        self._clear_properties()
        self.no_selection_label.show()
        
    def _clear_properties(self):
        """Clear all property widgets."""
        # Remove all widgets except the no selection label
        for i in reversed(range(self.properties_layout.count())):
            item = self.properties_layout.itemAt(i)
            if item.widget() != self.no_selection_label:
                widget = item.widget()
                if widget:
                    widget.setParent(None)
        
        self.property_widgets.clear()
        
    def _create_node_properties(self, node):
        """Create property widgets for the node."""
        # Get node-specific property definitions
        property_defs = self._get_node_property_definitions(node.node_type)
        
        if not property_defs:
            return
            
        # Create properties group
        props_group = QGroupBox("Properties")
        props_layout = QVBoxLayout(props_group)
        
        # Create property widgets
        for prop_def in property_defs:
            prop_name = prop_def['name']
            prop_type = prop_def['type']
            prop_label = prop_def.get('label', prop_name)
            
            # Get current value
            current_value = node.get_property(prop_name, prop_def.get('default'))
            
            # Create appropriate widget
            widget = None
            if prop_type == 'string':
                widget = StringPropertyWidget(prop_name, prop_label, current_value)
            elif prop_type == 'file':
                file_filter = prop_def.get('filter', 'All Files (*)')
                widget = FilePropertyWidget(prop_name, prop_label, file_filter, current_value)
            elif prop_type == 'multifile':
                file_filter = prop_def.get('filter', 'All Files (*)')
                widget = MultiFilePropertyWidget(prop_name, prop_label, file_filter, current_value)
            elif prop_type == 'int':
                min_val = prop_def.get('min', -999999)
                max_val = prop_def.get('max', 999999)
                widget = IntPropertyWidget(prop_name, prop_label, current_value, min_val, max_val)
            elif prop_type == 'float':
                min_val = prop_def.get('min', -999999.0)
                max_val = prop_def.get('max', 999999.0)
                decimals = prop_def.get('decimals', 3)
                widget = FloatPropertyWidget(prop_name, prop_label, current_value, min_val, max_val, decimals)
            elif prop_type == 'choice':
                choices = prop_def.get('choices', [])
                default_index = choices.index(current_value) if current_value in choices else 0
                widget = ComboPropertyWidget(prop_name, prop_label, choices, default_index)
            elif prop_type == 'bool':
                widget = BoolPropertyWidget(prop_name, prop_label, current_value)
            elif prop_type == 'text':
                widget = TextPropertyWidget(prop_name, prop_label, current_value)
            
            if widget:
                widget.value_changed.connect(self._on_property_changed)
                props_layout.addWidget(widget)
                self.property_widgets[prop_name] = widget
        
        self.properties_layout.addWidget(props_group)
        
    def _get_node_property_definitions(self, node_type):
        """Back-compat wrapper used by the old side panel."""
        return get_node_property_definitions(node_type)
        
    def _on_property_changed(self, property_name, value):
        """Handle property value change."""
        if self.current_node:
            self.current_node.set_property(property_name, value)
            # For Grid Search node, toggling manual edits should enable overrides automatically
            try:
                if getattr(self.current_node, 'node_type', '') == 'grid_search':
                    if property_name in ('center_x', 'center_y', 'center_z'):
                        self.current_node.set_property('override_center', True)
                    if property_name in ('size_x', 'size_y', 'size_z'):
                        self.current_node.set_property('override_size', True)
            except Exception:
                pass
