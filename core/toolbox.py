"""
Node toolbox widget for dragging nodes to canvas.
Accordion-style, dock-friendly, with circular icon items and hover tooltips.
Enhanced with smooth animations and modern visual effects.
"""

from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QPushButton,
    QFrame,
    QGridLayout,
    QGraphicsOpacityEffect,
    QLineEdit,
    QSizePolicy,
    QToolButton,
)
from PySide6.QtCore import Qt, Signal, QMimeData, QPoint, QSize, QPropertyAnimation, QEasingCurve, QParallelAnimationGroup, Property, QEvent, QSettings
from PySide6.QtGui import QDrag, QPixmap, QPainter, QColor, QFont, QIcon, QPen, QBrush

def _get_text_colors(theme_id=None):
    if theme_id is None:
        try:
            theme_id = str(QSettings().value("ui/theme_id", "") or "").lower()
        except Exception:
            theme_id = ""
    theme_id = (theme_id or "").lower()
    dark_themes = ["amoled_dark", "dracula", "nord", "win11_dark"]
    is_dark = any(dt in theme_id for dt in dark_themes)
    if is_dark:
        return "#e0e0e0", "#ffffff", "#d0d0d0"
    else:
        return "#000000", "#000000", "#000000"


# Use resource system with fallback
try:
    from backend.resource_access import load_node_icon
except ImportError:
    # Fallback implementation if resource system not available
    _ICONS_DIR = Path(__file__).resolve().parent.parent / "theme" / "icons"
    
    def load_node_icon(node_type: str, display_name: str) -> QIcon:
        """Return an icon for the node type using theme icons with graceful fallback.

        Exposed as a module helper so other modules (e.g., canvas) can reuse identical
        logic without needing a NodeToolbox instance.
        """
        # Try exact PNG by node type, else by display name slug
        try:
            candidates = [f"{node_type}.png", f"{display_name.lower().replace(' ', '_')}.png"]
            for name in candidates:
                path = _ICONS_DIR / name
                if path.exists():
                    # Compose the provided transparent icon over a colored circular background
                    size = 48
                    pix = QPixmap(size, size)
                    pix.fill(Qt.transparent)
                    painter = QPainter(pix)
                    painter.setRenderHint(QPainter.Antialiasing)
                    try:
                        hue = (abs(hash(node_type)) % 360) / 360.0
                        base_color = QColor.fromHsvF(hue, 0.6, 0.9)
                        dark_color = QColor.fromHsvF(hue, 0.7, 0.6)
                        painter.setBrush(QBrush(base_color))
                        painter.setPen(QPen(dark_color, 2))
                        painter.drawEllipse(2, 2, size - 4, size - 4)
                        # Subtle inner highlight to match fallback look
                        highlight_color = QColor.fromHsvF(hue, 0.3, 1.0, 0.6)
                        painter.setBrush(QBrush(highlight_color))
                        painter.setPen(Qt.NoPen)
                        painter.drawEllipse(6, 6, 12, 12)

                        # Draw the source icon centered, scaled to fit within the circle
                        src_pix = QPixmap(str(path))
                        if not src_pix.isNull():
                            target = QSize(int(size * 0.58), int(size * 0.58))  # ~28px inside 48px circle
                            src_scaled = src_pix.scaled(target, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            x = (size - src_scaled.width()) // 2
                            y = (size - src_scaled.height()) // 2
                            painter.drawPixmap(x, y, src_scaled)
                    finally:
                        painter.end()
                    return QIcon(pix)
        except Exception:
            # Fallback: generate a colored circle with the first letter
            size = 48
            pix = QPixmap(size, size)
            pix.fill(Qt.transparent)
            painter = QPainter(pix)
            painter.setRenderHint(QPainter.Antialiasing)
            try:
                hue = (abs(hash(node_type)) % 360) / 360.0
                base_color = QColor.fromHsvF(hue, 0.6, 0.9)
                dark_color = QColor.fromHsvF(hue, 0.7, 0.6)
                painter.setBrush(QBrush(base_color))
                painter.setPen(QPen(dark_color, 2))
                painter.drawEllipse(2, 2, size - 4, size - 4)
                # Inner highlight
                highlight_color = QColor.fromHsvF(hue, 0.3, 1.0, 0.6)
                painter.setBrush(QBrush(highlight_color))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(6, 6, 12, 12)
                # Letter with shadow
                painter.setPen(QPen(QColor(0, 0, 0, 100)))
                font = QFont()
                font.setBold(True)
                font.setPointSize(20)
                painter.setFont(font)
                letter = (display_name[0] if display_name else node_type[0]).upper()
                painter.drawText(pix.rect().adjusted(2, 2, 2, 2), Qt.AlignCenter, letter)
                painter.setPen(QPen(QColor(255, 255, 255)))
                painter.drawText(pix.rect(), Qt.AlignCenter, letter)
            finally:
                painter.end()
            
            return QIcon(pix)


class CollapsibleSection(QWidget):
    """A collapsible accordion section with a header and a content area."""

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self._title = title
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(8, 4, 8, 8)
        self._content_layout.setSpacing(6)

        self._header_btn = QPushButton(f"▶ {self._title}")
        self._header_btn.setCheckable(True)
        self._header_btn.setChecked(False)
        self.apply_styles()
        self._header_btn.clicked.connect(self._toggle)



        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)
        layout.addWidget(self._header_btn)

        # Enhanced separator with gradient effect
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(2)
        separator.setStyleSheet(
            """
            QFrame {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 transparent, stop:0.2 #555555, stop:0.8 #555555, stop:1 transparent);
                border: none;
            }
            """
        )
        layout.addWidget(separator)

        layout.addWidget(self._content_widget)
        self._content_widget.setVisible(False)
        
        # Animation setup
        self._animation = QPropertyAnimation(self._content_widget, b"maximumHeight")
        self._animation.setDuration(300)
        self._animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Opacity animation
        self._opacity_effect = QGraphicsOpacityEffect()
        self._content_widget.setGraphicsEffect(self._opacity_effect)
        self._opacity_animation = QPropertyAnimation(self._opacity_effect, b"opacity")
        self._opacity_animation.setDuration(250)
        self._opacity_animation.setEasingCurve(QEasingCurve.OutCubic)
        
        # Animation group for coordinated effects
        self._animation_group = QParallelAnimationGroup()
        self._animation_group.addAnimation(self._animation)
        self._animation_group.addAnimation(self._opacity_animation)
        self._is_collapsing = False
        self._animation_group.finished.connect(self._on_animation_finished)

    def apply_styles(self, theme_id=None):
        base_color, hover_color, _ = _get_text_colors(theme_id)
        self._header_btn.setStyleSheet(f"""
            QPushButton {{ 
                text-align: left; 
                padding: 10px 12px; 
                border: none; 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #3a3a3a, stop:1 #2f2f2f);
                color: {base_color};
                font-weight: bold;
                border-radius: 6px;
                margin: 2px;
            }}
            QPushButton:hover {{ 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4a4a4a, stop:1 #3f3f3f);
                color: {hover_color};
            }}
            QPushButton:checked {{ 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4a9eff, stop:1 #3a8eef);
                color: {hover_color};
            }}
            QPushButton:checked:hover {{ 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #5aafff, stop:1 #4a9eff);
            }}
        """)

    def content_layout(self) -> QVBoxLayout:
        return self._content_layout

    def set_content_widget(self, widget: QWidget):
        # Replace content widget with provided one
        layout = self.layout()
        layout.removeWidget(self._content_widget)
        self._content_widget.setParent(None)
        
        self._content_widget = widget
        
        # Reapply effects and animations to new widget
        self._opacity_effect = QGraphicsOpacityEffect()
        self._content_widget.setGraphicsEffect(self._opacity_effect)
        
        # Update animations
        self._animation.setTargetObject(self._content_widget)
        self._opacity_animation.setTargetObject(self._opacity_effect)
        
        layout.addWidget(self._content_widget)
        self._content_widget.setVisible(False)

    def _toggle(self):
        expanded = self._header_btn.isChecked()
        
        # Update header button text with animated arrow
        arrow = "▼" if expanded else "▶"
        self._header_btn.setText(f"{arrow} {self._title}")
        
        if expanded:
            self._is_collapsing = False
            # Expanding
            self._content_widget.setVisible(True)
            
            # Calculate target height
            self._content_widget.setMaximumHeight(16777215)  # Remove height constraint temporarily
            target_height = self._content_widget.sizeHint().height()
            
            # Set up animations
            self._animation.setStartValue(0)
            self._animation.setEndValue(target_height)
            self._opacity_animation.setStartValue(0.0)
            self._opacity_animation.setEndValue(1.0)
            
            self._content_widget.setMaximumHeight(0)  # Start from 0
            self._animation_group.start()
            
        else:
            # Collapsing
            self._is_collapsing = True
            current_height = self._content_widget.height()
            
            # Set up animations
            self._animation.setStartValue(current_height)
            self._animation.setEndValue(0)
            self._opacity_animation.setStartValue(1.0)
            self._opacity_animation.setEndValue(0.0)
            
            self._animation_group.start()

    def _on_animation_finished(self):
        # Handle visibility and constraints after animations
        if self._is_collapsing:
            self._content_widget.setVisible(False)
        else:
            # Remove height constraint after expanding so layout can adjust naturally
            self._content_widget.setMaximumHeight(16777215)

    # Public API to control expanded state programmatically
    def set_expanded(self, expanded: bool) -> None:
        try:
            if bool(expanded) != bool(self._header_btn.isChecked()):
                self._header_btn.setChecked(bool(expanded))
                self._toggle()
        except Exception:
            pass

    def title(self) -> str:
        """Return the raw title without arrow prefix."""
        return self._title


class NodeIconButton(QPushButton):
    """Circular icon-only button that starts a drag with the node type."""

    node_type: str

    def __init__(self, node_type: str, icon: QIcon, tooltip: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.node_type = node_type
        self.setToolTip(tooltip)
        self.setIcon(icon)
        icon_size = 40
        size = 56
        self.setIconSize(QSize(icon_size, icon_size))
        self.setFixedSize(QSize(size, size))
        self.setCursor(Qt.OpenHandCursor)
        self.setFlat(True)
        
        # Enhanced styling with gradients and shadows
        self.setStyleSheet(
            """
            QPushButton { 
                border-radius: 28px; 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #4a4a4a, stop:1 #3c3c3c);
                border: 2px solid #555555;
                padding: 2px;
            }
            QPushButton:hover { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #6a6a6a, stop:1 #505050);
                border: 2px solid #777777;
            }
            QPushButton:pressed { 
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #2a2a2a, stop:1 #2f2f2f);
                border: 2px solid #333333;
            }
            """
        )
        self._press_pos: QPoint | None = None

        # Add subtle hover animation
        self._hover_animation = QPropertyAnimation(self, b"geometry")
        self._hover_animation.setDuration(150)
        self._hover_animation.setEasingCurve(QEasingCurve.OutCubic)

    def enterEvent(self, event):
        # Subtle scale effect on hover
        super().enterEvent(event)

    def leaveEvent(self, event):
        # Reset scale on leave
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._press_pos = event.pos()
            self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_pos is not None:
            if (event.pos() - self._press_pos).manhattanLength() > 8:
                self._start_drag()
                self._press_pos = None
                self.setCursor(Qt.OpenHandCursor)
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press_pos = None
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # On double click, we can emit a synthetic drag-add by sending signal via parent hierarchy
        # Simpler: start a drag as well; canvas can handle a drop at cursor position
        self._start_drag()
        super().mouseDoubleClickEvent(event)

    def _start_drag(self):
        mime = QMimeData()
        mime.setText(self.node_type)
        drag = QDrag(self)
        drag.setMimeData(mime)
        
        # Enhanced preview with shadow effect
        preview = QPixmap(self.size() + QSize(8, 8))  # Slightly larger for shadow
        preview.fill(Qt.transparent)
        painter = QPainter(preview)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Draw shadow
        shadow_offset = 4
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(QColor(0, 0, 0, 80)))
        radius = min(self.width(), self.height()) // 2
        center = preview.rect().center()
        painter.drawEllipse(center.x() - radius + shadow_offset, 
                          center.y() - radius + shadow_offset, 
                          radius * 2, radius * 2)
        
        # Draw main circle with gradient
        gradient_brush = QBrush(QColor(80, 80, 80))
        painter.setBrush(gradient_brush)
        painter.setPen(QPen(QColor(120, 120, 120), 2))
        painter.drawEllipse(center.x() - radius, center.y() - radius, radius * 2, radius * 2)
        
        # Draw icon
        icon_pix = self.icon().pixmap(self.iconSize())
        x = (preview.width() - icon_pix.width()) // 2
        y = (preview.height() - icon_pix.height()) // 2
        painter.drawPixmap(x, y, icon_pix)
        painter.end()
        
        drag.setPixmap(preview)
        drag.exec(Qt.MoveAction)


class NodeCategoryWidget(QWidget):
    """Grid of circular node icon buttons for a category."""

    node_requested = Signal(str)  # Emits node type

    def __init__(self, category_name: str, icon_loader, columns: int = 3, parent: QWidget | None = None):
        super().__init__(parent)
        self.category_name = category_name
        self._icon_loader = icon_loader
        self._columns = max(1, columns)

        # Enhanced styling for the category widget
        self.setStyleSheet(
            """
            NodeCategoryWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 rgba(45, 45, 45, 50), stop:1 rgba(35, 35, 35, 50));
                border-radius: 8px;
                margin: 4px;
            }
            """
        )

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(12, 12, 12, 12)
        self._grid.setHorizontalSpacing(12)
        self._grid.setVerticalSpacing(12)
        self._count = 0
        # Track items for efficient filtering
        self._items: list[dict] = []

    def add_node(self, node_type: str, display_name: str, description: str = ""):
        """Add a node tool item with an icon and a label beneath it."""
        icon = self._icon_loader(node_type, display_name)
        # Build a small vertical widget: [circle button]
        #                                  display name
        container = QWidget(self)
        v = QVBoxLayout(container)
        v.setContentsMargins(2, 2, 2, 2)
        v.setSpacing(4)

        btn = NodeIconButton(node_type, icon, tooltip=description)
        btn.clicked.connect(lambda: self.node_requested.emit(node_type))
        v.addWidget(btn, alignment=Qt.AlignHCenter)

        label = QLabel(display_name)
        label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        label.setWordWrap(True)
        _, _, label_color = _get_text_colors()
        label.setStyleSheet(
            f"""
            QLabel {{ color: {label_color}; font-size: 10px; padding: 0; margin: 0; }}
            """
        )
        # Tooltip mirrors description
        if description:
            label.setToolTip(description)
        v.addWidget(label)

        row = self._count // self._columns
        col = self._count % self._columns
        self._grid.addWidget(container, row, col, alignment=Qt.AlignCenter)
        self._count += 1

        # Store for filtering
        try:
            searchable = f"{node_type} {display_name} {description}".lower()
        except Exception:
            searchable = f"{node_type} {display_name}".lower()
        self._items.append({
            "node_type": node_type,
            "display_name": display_name,
            "container": container,
            "search": searchable,
        })

    def apply_styles(self, theme_id=None):
        _, _, label_color = _get_text_colors(theme_id)
        for it in self._items:
            container = it["container"]
            for child in container.children():
                if isinstance(child, QLabel):
                    child.setStyleSheet(f"QLabel {{ color: {label_color}; font-size: 10px; padding: 0; margin: 0; }}")

    def sort_items_by_display_name(self) -> None:
        """Sort all items alphabetically by display name and reflow the grid."""
        try:
            self._items.sort(key=lambda it: str(it.get("display_name", "")).lower())
            # Remove all widgets from the grid first
            for it in self._items:
                try:
                    self._grid.removeWidget(it["container"])
                except Exception:
                    pass
            # Re-add in sorted order, ensure visible
            columns = max(1, self._columns)
            for idx, it in enumerate(self._items):
                row = idx // columns
                col = idx % columns
                self._grid.addWidget(it["container"], row, col, alignment=Qt.AlignCenter)
                try:
                    it["container"].setVisible(True)
                except Exception:
                    pass
        except Exception:
            pass

    def apply_filter(self, text: str) -> bool:
        """Filter contained items by case-insensitive substring.

        Returns True if any item remains visible after filtering.
        """
        q = (text or "").strip().lower()
        any_visible = False
        # Determine visibility for each item
        visible_items: list[dict] = []
        if not q:
            for it in self._items:
                visible_items.append(it)
                any_visible = True
        else:
            for it in self._items:
                if q in it.get("search", ""):
                    visible_items.append(it)
                    any_visible = True
        # Reflow grid to pack visible items tightly (no gaps)
        try:
            # Remove all widgets from the grid first
            for it in self._items:
                try:
                    self._grid.removeWidget(it["container"])
                except Exception:
                    pass
            # Add back only visible ones in order
            columns = max(1, self._columns)
            for idx, it in enumerate(visible_items):
                row = idx // columns
                col = idx % columns
                self._grid.addWidget(it["container"], row, col, alignment=Qt.AlignCenter)
                try:
                    it["container"].setVisible(True)
                except Exception:
                    pass
            # Hide the rest
            hidden_set = set(id(v["container"]) for v in visible_items)
            for it in self._items:
                if id(it["container"]) not in hidden_set:
                    try:
                        it["container"].setVisible(False)
                    except Exception:
                        pass
        except Exception:
            # Fallback: at least toggle visibility if reflow fails
            for it in self._items:
                try:
                    it["container"].setVisible(it in visible_items)
                except Exception:
                    pass
        return any_visible


class NodeToolbox(QWidget):
    """Main toolbox widget containing all node categories as an accordion."""

    node_requested = Signal(str)  # Emits node type

    def __init__(self):
        super().__init__()

        self._setup_ui()
        self._populate_nodes()

    def _setup_ui(self):
        """Setup the toolbox UI."""
        # Enhanced main widget styling
        self.setStyleSheet(
            """
            NodeToolbox {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1, 
                    stop:0 #2a2a2a, stop:1 #1f1f1f);
                border: 1px solid #555555;
                border-radius: 8px;
            }
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #2f2f2f;
                width: 12px;
                border-radius: 6px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #5a5a5a, stop:1 #4a4a4a);
                border-radius: 6px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, 
                    stop:0 #6a6a6a, stop:1 #5a5a5a);
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Search bar (replaces title)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search nodes…")
        try:
            self._search_edit.setClearButtonEnabled(True)
        except Exception:
            pass
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        self.apply_styles()
        layout.addWidget(self._search_edit)

        # Scroll area to contain accordion sections
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(scroll, 1)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._accordion_layout = QVBoxLayout(container)
        self._accordion_layout.setContentsMargins(4, 4, 4, 4)
        self._accordion_layout.setSpacing(6)
        scroll.setWidget(container)

        # Track sections for filtering
        self._sections: list[tuple[CollapsibleSection, NodeCategoryWidget]] = []

        # Set preferred width for dock
        self.setMinimumWidth(260)
        self.setMaximumWidth(380)

    def apply_styles(self, theme_id=None):
        base_color, _, _ = _get_text_colors(theme_id)
        self._search_edit.setStyleSheet(f"""
            QLineEdit {{
                color: {base_color};
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px 8px;
            }}
            QLineEdit:focus {{ border-color: #4a9eff; }}
        """)
        for section, category in getattr(self, '_sections', []):
            try:
                section.apply_styles(theme_id)
                category.apply_styles(theme_id)
            except Exception:
                pass

    # Icon loading with fallback (enhanced with better gradients)
    def _load_icon(self, node_type: str, display_name: str) -> QIcon:
        return load_node_icon(node_type, display_name)

    def _add_category(self, title: str, add_nodes_callback):
        section = CollapsibleSection(title)
        # Category grid
        category = NodeCategoryWidget(title, icon_loader=self._load_icon, columns=3)
        category.node_requested.connect(self.node_requested.emit)
        section.set_content_widget(category)
        # Populate via callback
        add_nodes_callback(category)
        # Sort items alphabetically in this category
        try:
            category.sort_items_by_display_name()
        except Exception:
            pass
        self._accordion_layout.addWidget(section)
        self._sections.append((section, category))

    def _on_search_text_changed(self, text: str) -> None:
        """Filter categories and items by the search text (case-insensitive)."""
        q = (text or "").strip()
        any_visible = False
        for section, category in self._sections:
            try:
                visible = category.apply_filter(q)
                section.setVisible(bool(visible))
                # Auto-expand on search when visible
                if q:
                    try:
                        section.set_expanded(True)
                    except Exception:
                        pass
                any_visible = any_visible or bool(visible)
            except Exception:
                pass
        # If nothing visible and search not empty, keep all hidden (no-op)

    def _populate_nodes(self):
        """Populate the toolbox with node categories and types (accordion sections)."""

        # Molecular Docking
        def add_docking(cat: NodeCategoryWidget):
            cat.add_node("autodock_vina", "AutoDock Vina", "Molecular docking with AutoDock Vina")
            cat.add_node("autodock_vina_gpu", "AutoDock Vina GPU", "GPU-accelerated AutoDock Vina")
            cat.add_node("autodock_vina_batch", "AutoDock Vina Batch", "Batch docking from SMILES with automatic ligand preparation")
            cat.add_node("docking_analysis", "Docking Analysis", "Analyze docking results")
            cat.add_node("vina_split", "Vina Split", "Split molecules list into single-molecule output pins")
            cat.add_node("grid_search", "Grid Box Search", "Estimate docking grid from molecules")
            cat.add_node("manual_grid_box", "Manual Grid Box", "Manually input grid box parameters for docking")
            cat.add_node("merge_molecule", "Merge Molecule", "Merge 2+ molecules into a complex")
            cat.add_node("receptor_preparation", "Receptor Preparation", "Prepare protein: remove waters/ligands, add H, charges")
            cat.add_node("ligand_preparation", "Ligand Preparation", "Prepare ligand: de-salt, neutralize, H, 3D, minimize, charges")

        self._add_category("Molecular Docking", add_docking)

        # Minimization
        def add_min(cat: NodeCategoryWidget):
            cat.add_node("rdkit_minimize", "RDKit Minimize", "Minimize molecules using RDKit")
            cat.add_node("openbabel_minimize", "OpenBabel Minimize", "Minimize molecules using OpenBabel")
            cat.add_node("conformer_gen", "Conformer Generation", "Generate molecular conformers")

        self._add_category("Molecular Minimization", add_min)

        # Molecular Dynamics
        def add_md(cat: NodeCategoryWidget):
            cat.add_node("charmm_gui_input", "CHARMM-GUI Input", "Verify and load CHARMM-GUI output files")
            cat.add_node("gromacs_input_editor", "GROMACS Input Editor", "Edit MDP parameters before simulation")
            cat.add_node("gromacs_prep", "GROMACS Preparation", "Prepare system for MD simulation")
            cat.add_node("gromacs_minimize", "GROMACS Minimisation", "Energy minimization with GROMACS")
            cat.add_node("gromacs_equilibrate", "GROMACS Equilibration", "Equilibration with GROMACS")
            cat.add_node("gromacs_production", "GROMACS Production", "Production MD with GROMACS")
            cat.add_node("xtc_extractor", "XTC Extractor", "Extract and process XTC trajectories")
            cat.add_node("gromacs_analysis", "GROMACS Analysis", "Analyze MD trajectories")
            cat.add_node("gromacs_ploting", "Gromacs Ploting", "Plot results from GROMACS Analysis")
            cat.add_node("gromacs_viewer", "GROMACS Viewer", "Visualize MD trajectories")
        self._add_category("Molecular Dynamics", add_md)

        # Visualization
        def add_viz(cat: NodeCategoryWidget):
            cat.add_node("structure_draw_2d", "2D Structure Draw", "Render 2D molecule structures from molecules or SMILES")
            cat.add_node("prolif_interaction", "ProLIF Interaction", "Visualize protein-ligand interactions")
            cat.add_node("web3d_viewer", "3D Web Viewer", "Interactive 3D visualization (NGL.js)")

        self._add_category("Chemical Visualization", add_viz)

        # Plotting category with common plot nodes
        def add_plotting(cat: NodeCategoryWidget):
            cat.add_node("plot_histogram", "Histogram", "Histogram of numeric values or a numeric column from a table")
            cat.add_node("plot_scatter", "Scatter", "Scatter plot from x/y arrays or columns")
            cat.add_node("plot_line", "Line Plot", "Line plot from x/y arrays or columns")
            cat.add_node("plot_bar", "Bar Plot", "Bar chart from categories + values or columns")
            cat.add_node("plot_pie", "Pie Chart", "Pie chart from labels + values or columns")
            cat.add_node("plot_donut", "Donut Chart", "Donut chart variant of pie chart")
            cat.add_node("plot_heatmap", "Heatmap", "Heatmap from matrix or table (e.g., ProLIF interactions)")
            # New plotting nodes
            cat.add_node("plot_venn", "Venn Diagram", "2-set Venn diagram from two lists or table columns")
            cat.add_node("plot_volcano", "Volcano Plot", "log2FC vs -log10(p) with thresholds and labels")
            cat.add_node("plot_box", "Box Plot", "Box plot of values; optional grouping by category")
            cat.add_node("plot_violin", "Violin Plot", "Violin plot of values; optional grouping by category")
            cat.add_node("plot_kde", "KDE Plot", "Kernel density estimate curve for a numeric series")
            cat.add_node("plot_hexbin", "Hexbin Plot", "Hexagonal binning for dense scatter data")
            cat.add_node("plot_area", "Area Plot", "Filled area under curve for x/y series")
            cat.add_node("plot_ecdf", "ECDF Plot", "Empirical cumulative distribution of a numeric series")
            cat.add_node("plot_radar", "Radar Chart", "Radar/spider chart for categories and values")
            cat.add_node("plot_bubble", "Bubble Plot", "Scatter with variable marker sizes")
            cat.add_node("plot_stacked_bar", "Stacked Bar", "Stacked categories per series from a table")
            cat.add_node("plot_hist2d", "2D Histogram", "2D histogram heatmap for x vs y")
            cat.add_node("plot_pairplot", "Pair Plot", "Scatter matrix for numeric columns (seaborn)")

        self._add_category("Ploting", add_plotting)

        # Data
        def add_data(cat: NodeCategoryWidget):
            cat.add_node("pubchem_search", "PubChem Search", "Search and download from PubChem")
            cat.add_node("rcsb_pdb", "RCSB PDB", "Fetch PDB structure by code → molecule")

        self._add_category("Chemical Data Scraping", add_data)

        # Data Modification
        def add_data_mod(cat: NodeCategoryWidget):
            cat.add_node("select_columns", "Select Columns", "Select specific columns from a table")
            cat.add_node("filter_rows", "Filter Rows", "Select rows based on conditions (equals, contains, <, >, etc)")
            cat.add_node("slice_rows", "Slice Rows", "Select a subset of rows based on start:end:step")
            cat.add_node("drop_duplicates", "Drop Duplicates", "Remove duplicate rows, optionally subset by columns")
            cat.add_node("sort_rows", "Sort Rows", "Sort rows based on one or more columns")
            cat.add_node("merge_dataframes", "Dataframe Merge", "Merge two dataframes based on key columns")

        self._add_category("Dataframe Modification", add_data_mod)


        # I/O - General (non-molecular)
        def add_io_general(cat: NodeCategoryWidget):
            cat.add_node("file_input", "File Input", "Select (multi/single), output path only")
            cat.add_node("folder_input", "Folder Input", "Select folder path for input")
            cat.add_node("file_output", "File Output", "Save results to file")
            cat.add_node("save_dataframe", "Save DataFrame", "Save DataFrame/list-of-dicts → CSV/TSV/Excel")
            cat.add_node("save_text", "Save Text", "Save text/log → TXT/LOG")
            cat.add_node("save_json", "Save JSON", "Save data → JSON")
            cat.add_node("save_image", "Save Image", "Simpan bytes gambar → PNG/JPG")
            cat.add_node("save_file", "Save File (Sink)", "Save incoming data to disk")
            cat.add_node("table_view", "Table View", "Display list-of-dicts as a table")
            cat.add_node("text_view", "Text View", "Display text or JSON")
            cat.add_node("image_view", "Image View", "Display image bytes (PNG/JPG)")
            cat.add_node("text_input", "Text Input", "Input single-line text")
            # General data readers
            cat.add_node("csv_reader", "CSV/TSV Reader", "Read CSV/TSV → data (list-of-dicts)")
            cat.add_node("excel_reader", "Excel Reader", "Read Excel → data (list-of-dicts)")
            cat.add_node("txt_reader", "TXT Reader", "Read TXT → string/lines data")

        self._add_category("General Input/Output", add_io_general)

        # I/O - Molecular readers
        def add_io_molecular(cat: NodeCategoryWidget):
            cat.add_node("smiles_input", "SMILES Input", "Type SMILES strings to generate molecules")
            cat.add_node("mol_reader_auto", "Auto Mol Reader", "Read SDF/MOL/MOL2/PDB/PDBQT/XYZ automatically")
            cat.add_node("sdf_reader", "SDF Reader", "Read SDF file → molecules")
            cat.add_node("mol_reader", "MOL Reader", "Read MOL file → molecules")
            cat.add_node("mol2_reader", "MOL2 Reader", "Read MOL2 file → molecules")
            cat.add_node("pdb_reader", "PDB Reader", "Read PDB file → molecules")
            cat.add_node("pdbqt_reader", "PDBQT Reader", "Read PDBQT file → molecules (fallback)")
            cat.add_node("xyz_reader", "XYZ Reader", "Read XYZ file → molecules")
            cat.add_node("save_molecule", "Save Molecule", "Save molecule → SDF/MOL/MOL2/PDB/PDBQT/XYZ")

        self._add_category("Molecular Input/Output", add_io_molecular)

        # Machine Learning
        def add_ml(cat: NodeCategoryWidget):
            cat.add_node("ml_train_test_split", "Train/Test Split", "Split dataset into train/test with optional stratify")
            # Classifiers
            cat.add_node("ml_logistic_regression", "Logistic Regression", "Logistic regression classifier")
            cat.add_node("ml_random_forest_classifier", "Random Forest (Classifier)", "Ensemble tree-based classifier")
            cat.add_node("ml_svm_classifier", "SVM (Classifier)", "Support Vector Machine classifier")
            cat.add_node("ml_knn_classifier", "KNN (Classifier)", "K-Nearest Neighbors classifier")
            # Regressors
            cat.add_node("ml_linear_regression", "Linear Regression", "Linear regression model")
            cat.add_node("ml_random_forest_regressor", "Random Forest (Regressor)", "Ensemble tree-based regressor")
            cat.add_node("ml_svr", "SVR", "Support Vector Regression")

        self._add_category("Machine Learning", add_ml)

        # Model Evaluation
        def add_eval(cat: NodeCategoryWidget):
            cat.add_node("eval_confusion_matrix", "Confusion Matrix", "Compute confusion matrix and optional heatmap")
            cat.add_node("eval_classification_report", "Classification Report", "Precision/Recall/F1 report table and text")
            cat.add_node("eval_regression_metrics", "Regression Metrics", "MAE/MSE/R2 for regression")

        self._add_category("Model Evaluation", add_eval)

        # Clustering & Dimensionality Reduction
        def add_cluster(cat: NodeCategoryWidget):
            cat.add_node("cluster_kmeans", "KMeans Clustering", "Partition data into K clusters")
            cat.add_node("cluster_agglomerative", "Agglomerative Clustering", "Hierarchical clustering")
            cat.add_node("dim_pca", "PCA", "Principal Component Analysis (projection)")

        self._add_category("Clustering and Dimensionality Reduction", add_cluster)

        # Chromatography & Spectroscopy
        def add_chrom(cat: NodeCategoryWidget):
            cat.add_node("chrom_reader", "Chromatography Reader", "Read time-series (HPLC/IR/others) into a table")
            cat.add_node("chrom_smoothing", "Chrom Smoothing", "Savitzky–Golay or moving average smoothing")
            cat.add_node("chrom_baseline", "Chrom Baseline", "Baseline correction (rolling quantile/min)")
            cat.add_node("chrom_peak_detect", "Chrom Peak Detect", "find_peaks with prominence/width filters")
            cat.add_node("chrom_integrate", "Chrom Integrate", "Integrate peak areas or whole curve")
            cat.add_node("chrom_viewer", "Chrom Viewer", "Plot series and optional peaks → PNG")

        self._add_category("Chromatography and Spectroscopy", add_chrom)

        # Response Surface Analysis
        def add_rsa(cat: NodeCategoryWidget):
            cat.add_node("rsa_prep", "RSA Prepare Dataset", "Filter/clean data, choose response")
            cat.add_node("rsa_fit", "RSA Fit", "Fit linear/quadratic/cubic/GPR response surface")
            cat.add_node("rsa_surface", "RSA Surface", "Generate X1/X2/Z grid for plotting")

        self._add_category("Response Surface Analysis", add_rsa)

        # ML Model Management
        def add_ml_models(cat: NodeCategoryWidget):
            cat.add_node("ml_model_load", "Model Load (.pkl)", "Load saved model from disk")
            cat.add_node("ml_model_save", "Model Save (.pkl)", "Save model to disk")
            cat.add_node("ml_model_test", "Model Test", "Evaluate on dataset with target column")
            cat.add_node("ml_model_predict", "Model Predict", "Batch prediction for dataset")

        self._add_category("ML Model Management", add_ml_models)

        # Cheminformatics
        def add_chem(cat: NodeCategoryWidget):
            cat.add_node("mol_descriptor", "Mol Descriptor", "Calculate RDKit molecular descriptors (Lipinski, all, etc.)")
            cat.add_node("mol_fingerprint", "Mol Fingerprint", "Generate molecular fingerprints (Morgan, MACCS, RDKit, etc.)")
            cat.add_node("smarts_filter", "SMARTS Filter", "Filter molecules by SMARTS substructure pattern")

        self._add_category("Cheminformatics", add_chem)

        # Scripting
        def add_script(cat: NodeCategoryWidget):
            cat.add_node("python_script", "Python Script", "Execute custom Python code in the workflow")

        self._add_category("Scripting", add_script)

        # Utilities
        def add_utils(cat: NodeCategoryWidget):
            cat.add_node("note", "Note", "Sticky note / comment on the canvas")

        self._add_category("Utilities", add_utils)

        # Plugin-provided categories
        try:
            from backend.plugin_manager import get_loaded_toolbox_categories
            plugin_cats = get_loaded_toolbox_categories()
        except Exception:
            plugin_cats = []
        for category_name, nodes in plugin_cats:
            def _make_adder(items):
                def add_plugin_nodes(cat: NodeCategoryWidget):
                    for it in items:
                        # If plugin provided a custom icon path, load it as a QIcon; else use theme fallback
                        if getattr(it, "icon_path", None):
                            try:
                                icon = QIcon(str(it.icon_path))
                                # Manual add using internal widget builder to force icon
                                # Build container similar to add_node()
                                container = QWidget(cat)
                                v = QVBoxLayout(container)
                                v.setContentsMargins(2, 2, 2, 2)
                                v.setSpacing(4)
                                btn = NodeIconButton(it.node_type, icon, tooltip=it.description)
                                btn.clicked.connect(lambda checked=False, nt=it.node_type: cat.node_requested.emit(nt))
                                v.addWidget(btn, alignment=Qt.AlignHCenter)
                                label = QLabel(it.display_name)
                                label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
                                label.setWordWrap(True)
                                label.setStyleSheet("QLabel { color: #d0d0d0; font-size: 10px; padding: 0; margin: 0; }")
                                if it.description:
                                    label.setToolTip(it.description)
                                v.addWidget(label)
                                row = cat._count // cat._columns
                                col = cat._count % cat._columns
                                cat._grid.addWidget(container, row, col, alignment=Qt.AlignCenter)
                                cat._count += 1
                                try:
                                    searchable = f"{it.node_type} {it.display_name} {it.description}".lower()
                                except Exception:
                                    searchable = f"{it.node_type} {it.display_name}".lower()
                                cat._items.append({
                                    "node_type": it.node_type,
                                    "display_name": it.display_name,
                                    "container": container,
                                    "search": searchable,
                                })
                            except Exception:
                                # Fallback to theme icon
                                cat.add_node(it.node_type, it.display_name, it.description)
                        else:
                            cat.add_node(it.node_type, it.display_name, it.description)
                return add_plugin_nodes
            self._add_category(str(category_name), _make_adder(list(nodes)))

        # After all categories added: sort categories alphabetically and expand all
        try:
            # Sort the internal list first
            self._sections.sort(key=lambda pair: pair[0].title().lower())
            # Remove existing widgets from layout in current order
            for section, _category in self._sections:
                try:
                    self._accordion_layout.removeWidget(section)
                except Exception:
                    pass
            # Add back in sorted order and expand them
            for section, _category in self._sections:
                self._accordion_layout.addWidget(section)
                try:
                    section.set_expanded(True)
                except Exception:
                    pass
        except Exception:
            pass

class FloatingNodePicker(QFrame):
    """Floating toolbox with search and a flat list of nodes.

    Emits node_chosen(node_type: str) when a node is selected.
    """

    node_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("FloatingNodePicker")
        self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        self.setFrameShape(QFrame.StyledPanel)
        self.setFrameShadow(QFrame.Raised)

        self._items: list[dict] = []
        self._drag_active: bool = False
        self._drag_offset: QPoint | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # Header row with search and a close button
        header = QWidget(self)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(6)
        # Save header reference and install event filter for dragging
        self._header = header
        try:
            self._header.installEventFilter(self)
        except Exception:
            pass

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search nodes…")
        try:
            self.search.setClearButtonEnabled(True)
        except Exception:
            pass
        self.search.textChanged.connect(self._on_search_text_changed)
        self.search.setStyleSheet(
            """
            QLineEdit {
                color: #e0e0e0;
                background-color: #3a3a3a;
                border: 1px solid #555;
                border-radius: 6px;
                padding: 6px 8px;
            }
            QLineEdit:focus { border-color: #4a9eff; }
            """
        )
        header_layout.addWidget(self.search, 1)

        self.btn_close = QToolButton(header)
        self.btn_close.setText("✖")
        self.btn_close.setToolTip("Close")
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.clicked.connect(self.hide)
        header_layout.addWidget(self.btn_close, 0)

        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        layout.addWidget(scroll, 1)

        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self._grid = QGridLayout(container)
        self._grid.setContentsMargins(6, 6, 6, 6)
        self._grid.setHorizontalSpacing(10)
        self._grid.setVerticalSpacing(10)
        scroll.setWidget(container)

        # Styling
        self.setStyleSheet(
            """
            QFrame#FloatingNodePicker {
                background-color: #242424;
                border: 1px solid #555;
                border-radius: 10px;
            }
            """
        )

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        # Ensure reasonable default/minimum size so it doesn't collapse to a tiny box
        try:
            self.setMinimumSize(360, 280)
            scroll.setMinimumSize(340, 220)
        except Exception:
            pass

    def populate(self, items: list[tuple[str, str, QIcon]]):
        """Populate with a list of (node_type, display_name, icon)."""
        # Clear existing
        try:
            while self._grid.count():
                it = self._grid.takeAt(0)
                w = it.widget()
                if w is not None:
                    w.setParent(None)
        except Exception:
            pass
        self._items.clear()

        columns = 3
        for idx, (node_type, display_name, icon) in enumerate(items):
            container = QWidget(self)
            v = QVBoxLayout(container)
            v.setContentsMargins(2, 2, 2, 2)
            v.setSpacing(4)

            btn = NodeIconButton(node_type, icon, tooltip=display_name)
            btn.clicked.connect(lambda checked=False, nt=node_type: self.node_chosen.emit(nt))
            v.addWidget(btn, alignment=Qt.AlignHCenter)

            label = QLabel(display_name)
            label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            label.setWordWrap(True)
            label.setStyleSheet("QLabel { color: #d0d0d0; font-size: 10px; padding: 0; margin: 0; }")
            v.addWidget(label)

            row = idx // columns
            col = idx % columns
            self._grid.addWidget(container, row, col, alignment=Qt.AlignCenter)

            self._items.append({
                "node_type": node_type,
                "display_name": display_name,
                "container": container,
                "search": f"{node_type} {display_name}".lower(),
            })

        self.adjustSize()

    def _on_search_text_changed(self, text: str) -> None:
        q = (text or "").strip().lower()
        # Build visible list first
        visible_items: list[dict] = []
        for it in self._items:
            if (not q) or (q in it.get("search", "")):
                visible_items.append(it)
        # Reflow grid to eliminate gaps
        try:
            # Remove all widgets from grid
            while self._grid.count():
                item = self._grid.takeAt(0)
                _w = item.widget()  # keep reference
            # Add back visible ones in order
            columns = 3
            for idx, it in enumerate(visible_items):
                row = idx // columns
                col = idx % columns
                self._grid.addWidget(it["container"], row, col, alignment=Qt.AlignCenter)
                try:
                    it["container"].setVisible(True)
                except Exception:
                    pass
            # Hide the rest not in visible set
            visible_ids = set(id(v["container"]) for v in visible_items)
            for it in self._items:
                if id(it["container"]) not in visible_ids:
                    try:
                        it["container"].setVisible(False)
                    except Exception:
                        pass
            self.adjustSize()
        except Exception:
            # Fallback: toggle visibility only
            for it in self._items:
                show = it in visible_items
                try:
                    it["container"].setVisible(bool(show))
                except Exception:
                    pass

    def showEvent(self, event):
        # Always reset the search bar when the picker is shown
        try:
            self.search.setText("")
        except Exception:
            pass
        try:
            # Ensure all items visible on open
            self._on_search_text_changed("")
        except Exception:
            pass
        return super().showEvent(event)

    def eventFilter(self, obj, event):
        # Enable dragging the floating picker by its header area
        try:
            if obj is getattr(self, "_header", None):
                if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                    self._drag_active = True
                    try:
                        self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
                    except Exception:
                        # Fallback for older Qt
                        self._drag_offset = event.globalPos() - self.frameGeometry().topLeft()
                    return True
                if event.type() == QEvent.MouseMove and self._drag_active:
                    gp = None
                    try:
                        gp = event.globalPosition().toPoint()
                    except Exception:
                        gp = event.globalPos()
                    if self._drag_offset is not None and gp is not None:
                        self.move(gp - self._drag_offset)
                    return True
                if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                    self._drag_active = False
                    self._drag_offset = None
                    return True
        except Exception:
            pass
        return super().eventFilter(obj, event)

    # (methods specific to NodeToolbox were removed from this class)