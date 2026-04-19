"""
Base node classes for the workflow system.
Defines the fundamental node structure and behavior.
"""

from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsWidget,
    QGraphicsProxyWidget,
    QGraphicsTextItem,
    QLabel,
    QWidget,
    QGridLayout,
    QProgressBar,
    QFrame,
    QVBoxLayout,
    QPlainTextEdit,
)
from PySide6.QtCore import Qt, Signal, QRectF, QPointF, QTimer
from PySide6.QtGui import QPainter, QPen, QBrush, QColor, QFont

from .port_types import color_for_type, normalize_type
from utils.qt_utils import in_gui_thread
from utils.theme_colors import get_node_colors_for_state

class NodePort(QGraphicsItem):
    """Represents an input or output port on a node."""
    
    def __init__(self, parent_node, port_name, port_type, data_type="any"):
        super().__init__()
        self.parent_node = parent_node
        self.port_name = port_name
        self.port_type = port_type  # "input" or "output"
        self.data_type = normalize_type(data_type)
        self.radius = 8
        self.label_margin = 6
        # Ensure ports and their labels render above inline widgets
        self.setZValue(100)
        self.label_item = QGraphicsTextItem("")
        self.label_item.setDefaultTextColor(QColor(230, 230, 230))
        self.label_item.setZValue(101)
        self.label_item.setParentItem(self)
        self.setToolTip(f"{self.port_type.capitalize()} '{self.port_name}' : {self.data_type}")
        self.setAcceptHoverEvents(True)
        
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self._update_label_text()
        
    def boundingRect(self):
        """Return the bounding rectangle of the port."""
        return QRectF(-self.radius, -self.radius, 
                     self.radius * 2, self.radius * 2)
    
    def paint(self, painter, option, widget):
        """Paint the port."""
        # Colors by data type, subtle difference for input/output
        base_color = color_for_type(self.data_type)
        if self.port_type == "input":
            brush_color = QColor(
                min(255, int(base_color.red() * 0.85)),
                min(255, int(base_color.green() * 0.85)),
                min(255, int(base_color.blue() * 0.85)),
            )
        else:
            brush_color = base_color

        if self.isSelected():
            pen_color = QColor(255, 255, 255)
            pen_width = 2
        else:
            pen_color = QColor(50, 50, 50)
            pen_width = 1

        painter.setPen(QPen(pen_color, pen_width))
        painter.setBrush(QBrush(brush_color))
        painter.drawEllipse(self.boundingRect())
        # Keep label positioned relative to the current port position
        self._update_label_position()

    def hoverEnterEvent(self, event):
        self.update()
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.update()
        return super().hoverLeaveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press for connection creation."""
        if event.button() == Qt.LeftButton:
            # Emit connection request signal through parent node
            self.parent_node.connection_requested.emit(
                self.parent_node, self.port_name, self.port_type
            )
        super().mousePressEvent(event)

    def _update_label_text(self):
        text = f"{self.port_name} [{self.data_type}]"
        self.label_item.setPlainText(text)

    def _update_label_position(self):
        # Place text outside the node bounding box, near the port
        brect = self.label_item.boundingRect()
        if self.port_type == "input":
            # text to the left of the socket
            x = -self.radius - self.label_margin - brect.width()
            y = -brect.height() / 2
        else:
            # text to the right of the socket
            x = self.radius + self.label_margin
            y = -brect.height() / 2
        self.label_item.setPos(x, y)


class BaseNode(QGraphicsWidget):
    """Base class for all workflow nodes."""
    
    # When True, subclasses should avoid constructing heavy inline UI widgets
    # during temporary instantiation (e.g., for toolbox compatibility probing)
    _lightweight_construction: bool = False

    # Node execution states
    STATE_IDLE = "idle"
    STATE_VALIDATING = "validating"
    STATE_RUNNING = "running"
    STATE_PAUSED = "paused"
    STATE_COMPLETED = "completed"
    STATE_ERROR = "error"
    
    # Signals
    connection_requested = Signal(object, str, str)  # node, port_name, port_type
    position_changed = Signal(object)  # node
    # Fired by nodes that want to trigger a downstream partial re-run from themselves
    rerun_requested = Signal(object)  # node
    
    def __init__(self, node_type="base", title="Base Node"):
        super().__init__()
        
        self.node_type = node_type
        self.title = title
        self.width = 200
        self.height = 100
        # Minimum size constraints for interactive resizing
        self._min_width = 140
        self._min_height = 80
        # Extra margin around the painted content to accommodate glow/highlights
        # and ensure the scene invalidates those pixels to avoid trails.
        self._outer_margin = 10.0
        # Interactive resizing state
        self._resize_margin = 8.0
        self._resizing_active = False
        self._resize_zone: str | None = None  # e.g., 'left', 'right', 'top_left', ...
        self._drag_start_pos: QPointF | None = None
        self._drag_start_rect: QRectF | None = None
        
        # Node execution state
        self._execution_state = self.STATE_IDLE
        # Internal: temporarily block moving when press starts outside title
        self._move_blocked = False
        
        # Animation timer for running state (GUI thread only)
        self._created_in_gui_thread = in_gui_thread()
        self._animation_timer = None
        if self._created_in_gui_thread:
            self._animation_timer = QTimer(self)
            self._animation_timer.timeout.connect(self.update)
            self._animation_timer.setInterval(50)  # 20 FPS for smooth animation
        
        # Node properties
        self.properties = {}
        self._inline_widgets: dict[str, QGraphicsProxyWidget] = {}
        
        # Ports
        self.input_ports = {}
        self.output_ports = {}
        
        # Setup node
        self._setup_node()

        # Unified inline content area (embedded QWidget with a grid layout)
        # Subclasses should add child widgets to self.content_layout instead of
        # creating multiple QGraphicsProxyWidget floating elements.
        self._content_proxy: QGraphicsProxyWidget | None = None
        self._content_widget: QWidget | None = None
        self._content_layout: QGridLayout | None = None
        # Content margins inside the node body (left, top, right, bottom)
        # Increase top margin so inline widgets are visibly clear from title/ports
        self._content_margins = (16, 56, 16, 16)
        self._create_content_container()
        
        # Floating progress panel (below node) and error panel
        self._progress_proxy: QGraphicsProxyWidget | None = None
        self._progress_widget: QWidget | None = None
        self._progress_bar: QProgressBar | None = None
        
        # Error panel shown outside (below) the node body
        self._error_proxy: QGraphicsProxyWidget | None = None
        self._error_widget: QWidget | None = None
        
        # Floating log panel (below node) for streaming stdout/stderr
        self._log_proxy: QGraphicsProxyWidget | None = None
        self._log_widget: QWidget | None = None
        self._log_text: QPlainTextEdit | None = None
        
    def _setup_node(self):
        """Setup basic node properties."""
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setAcceptedMouseButtons(Qt.AllButtons)
        # Enable hover events so we can show resize cursors
        self.setAcceptHoverEvents(True)
        
        # Set initial size constraints (allow growth by default)
        try:
            self.setMinimumSize(self._min_width, self._min_height)
        except Exception:
            pass

    # --- Inline content container helpers ---------------------------------
    def _create_content_container(self) -> None:
        """Create the embedded QWidget that hosts all inline controls in a grid.

        We keep a single QGraphicsProxyWidget for the whole node body, so all
        child controls participate in Qt layouts (grid/box) and never float or
        overlap each other.
        """
        try:
            # Skip creating any inline QWidget/Proxy when probing in lightweight mode.
            # This keeps the UI thread responsive when the floating picker instantiates
            # many node classes just to inspect port signatures.
            from core.nodes import BaseNode as _BaseNode  # safe self-import
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._content_proxy = None
                self._content_widget = None
                self._content_layout = None
                return
            if self._content_proxy is not None:
                return
            self._content_widget = QWidget()
            # Transparent background so the node's painted body is visible
            try:
                self._content_widget.setAttribute(Qt.WA_TranslucentBackground, True)  # type: ignore[attr-defined]
            except Exception:
                pass
            self._content_layout = QGridLayout(self._content_widget)
            self._content_layout.setContentsMargins(0, 0, 0, 0)
            self._content_layout.setHorizontalSpacing(8)
            self._content_layout.setVerticalSpacing(6)

            self._content_proxy = QGraphicsProxyWidget(self)
            self._content_proxy.setWidget(self._content_widget)
            try:
                self._content_proxy.setZValue(5)
            except Exception:
                pass
            # Initial geometry
            self._update_content_geometry(force=True)
        except Exception:
            # In headless mode, this may fail silently. Nodes without inline
            # UI should still function.
            self._content_proxy = None
            self._content_widget = None
            self._content_layout = None

    @property
    def content_layout(self) -> QGridLayout | None:
        """Return the QGridLayout used for inline controls inside the node.

        Subclasses should check for None to remain robust in headless mode.
        """
        return self._content_layout

    def set_content_margins(self, left: int, top: int, right: int, bottom: int) -> None:
        """Customize margins of the content area inside the node body."""
        self._content_margins = (int(left), int(top), int(right), int(bottom))
        self._update_content_geometry(force=True)

    def _update_content_geometry(self, force: bool = False) -> None:
        """Position and resize the embedded content area to fit the node size."""
        if self._content_proxy is None:
            return
        try:
            l, t, r, b = self._content_margins
            new_x = float(l)
            new_y = float(t)
            new_w = float(max(0, self.width - (l + r)))
            new_h = float(max(0, self.height - (t + b)))

            # Only update when changed unless forced
            br = self._content_proxy.boundingRect()
            changed = (
                force
                or abs(self._content_proxy.pos().x() - new_x) > 0.5
                or abs(self._content_proxy.pos().y() - new_y) > 0.5
                or abs(br.width() - new_w) > 0.5
                or abs(br.height() - new_h) > 0.5
            )
            if changed:
                self._content_proxy.setPos(new_x, new_y)
                self._content_proxy.resize(new_w, new_h)
        except Exception:
            pass
        # Keep error panel positioned under the node if visible
        try:
            if self._error_proxy is not None:
                self._update_error_geometry()
        except Exception:
            pass
        # Keep progress panel positioned under the node if visible
        try:
            if self._progress_proxy is not None:
                self._update_progress_geometry()
        except Exception:
            pass
        # Keep log panel positioned under the node if visible
        try:
            if self._log_proxy is not None:
                self._update_log_geometry()
        except Exception:
            pass
        
    def add_input_port(self, name, data_type="any"):
        """Add an input port to the node."""
        port = NodePort(self, name, "input", data_type)
        self.input_ports[name] = port
        port.setParentItem(self)
        self._update_port_positions()
        
    def add_output_port(self, name, data_type="any"):
        """Add an output port to the node."""
        port = NodePort(self, name, "output", data_type)
        self.output_ports[name] = port
        port.setParentItem(self)
        self._update_port_positions()
        
    def _update_port_positions(self):
        """Update positions of all ports.
        Allows subclasses to override _get_output_port_anchor_x to shift pins (e.g., to the right of a floating panel).
        """
        # Position input ports on the left
        input_count = len(self.input_ports)
        if input_count > 0:
            spacing = self.height / (input_count + 1)
            for i, port in enumerate(self.input_ports.values()):
                port.setPos(-port.radius, spacing * (i + 1))
                if hasattr(port, "_update_label_position"):
                    port._update_label_position()
        
        # Position output ports, default at the node's right edge, but allow override
        output_count = len(self.output_ports)
        if output_count > 0:
            spacing = self.height / (output_count + 1)
            anchor_x = float(self.width)
            # If subclass provided an override (callable attribute), use it
            try:
                anchor_method = getattr(self, "_get_output_port_anchor_x", None)
                if callable(anchor_method):
                    anchor_x = float(anchor_method())
            except Exception:
                anchor_x = float(self.width)
            for i, port in enumerate(self.output_ports.values()):
                port.setPos(anchor_x + port.radius, spacing * (i + 1))
                if hasattr(port, "_update_label_position"):
                    port._update_label_position()

    def _get_output_port_anchor_x(self) -> float:
        """Return the X coordinate to anchor output ports.
        Subclasses can override to place ports beyond the node body (e.g., to the right of a floating panel).
        """
        return float(self.width)
    
    def boundingRect(self):
        """Return the bounding rectangle of the node including visual margins.

        Expanded to include outer glow/highlight, preventing paint artifacts when moving.
        """
        m = float(self._outer_margin)
        return QRectF(-m, -m, self.width + 2.0 * m, self.height + 2.0 * m)
    
    def paint(self, painter, option, widget):
        """Paint the node."""
        # Set colors based on execution state and selection
        border_color, border_width, background_color, title_color = self._get_state_colors()
        
        # Override with selection colors if selected
        if self.isSelected():
            border_color = QColor(255, 255, 255)
            border_width = 3
        
        # Draw node background strictly within the logical node rect (0..width/height)
        node_rect = QRectF(0, 0, self.width, self.height)
        painter.setPen(QPen(border_color, border_width))
        painter.setBrush(QBrush(background_color))
        painter.drawRoundedRect(node_rect, 5, 5)
        
        # Draw execution state indicator (glow effect for running/validating state)
        if self._execution_state in [self.STATE_RUNNING, self.STATE_VALIDATING]:
            self._draw_running_effect(painter)
        
        # Draw title bar
        title_rect = QRectF(0, 0, self.width, 30)
        painter.setBrush(QBrush(title_color))
        painter.drawRoundedRect(title_rect, 5, 5)
        
        # Draw title text
        painter.setPen(QPen(QColor(255, 255, 255)))
        font = QFont()
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(title_rect, Qt.AlignCenter, self.title)

        # Keep content area geometry in sync with current node size
        # (important when subclasses changed width/height after construction)
        self._update_content_geometry()

        # Draw essential inline properties in the body area (simple summary)
        body_rect = QRectF(10, 35, self.width - 20, self.height - 45)
        painter.setPen(QPen(QColor(200, 200, 200)))
        summary_lines = self._inline_summary()
        y = body_rect.top()
        line_height = 14
        for line in summary_lines[: int(body_rect.height() // line_height)]:
            painter.drawText(QRectF(body_rect.left(), y, body_rect.width(), line_height), Qt.AlignLeft | Qt.AlignVCenter, line)
            y += line_height
    
    def itemChange(self, change, value):
        """Handle item changes."""
        if change == QGraphicsItem.ItemPositionChange:
            # Emit position changed signal
            self.position_changed.emit(self)
        return super().itemChange(change, value)
    
    def get_property(self, key, default=None):
        """Get a node property value."""
        return self.properties.get(key, default)
    
    def set_property(self, key, value):
        """Set a node property value."""
        self.properties[key] = value
        # Avoid triggering paint/update from worker threads
        if self._created_in_gui_thread:
            self.update()
    
    def set_execution_state(self, state):
        """Set the node execution state."""
        if state in [self.STATE_IDLE, self.STATE_VALIDATING, self.STATE_RUNNING, self.STATE_PAUSED, self.STATE_COMPLETED, self.STATE_ERROR]:
            old_state = self._execution_state
            self._execution_state = state

            # Start/stop animation timer based on state
            if self._animation_timer is not None:
                if (state == self.STATE_RUNNING or state == self.STATE_VALIDATING) and old_state not in [self.STATE_RUNNING, self.STATE_VALIDATING]:
                    self._animation_timer.start()
                elif state not in [self.STATE_RUNNING, self.STATE_VALIDATING] and old_state in [self.STATE_RUNNING, self.STATE_VALIDATING]:
                    self._animation_timer.stop()

            # Hide progress bar when node is no longer running/validating
            if state in [self.STATE_IDLE, self.STATE_COMPLETED, self.STATE_ERROR] and old_state in [self.STATE_RUNNING, self.STATE_VALIDATING]:
                try:
                    if self._progress_proxy is not None:
                        self._progress_proxy.setVisible(False)
                except Exception:
                    pass

            if self._created_in_gui_thread:
                self.update()  # Trigger repaint to show new state

    # --- Resizing helpers ---------------------------------------------------
    def set_node_size(self, width: float, height: float) -> None:
        """Programmatically set node size with constraints and update layout."""
        try:
            w = max(self._min_width, float(width))
            h = max(self._min_height, float(height))
        except Exception:
            w, h = self.width, self.height
        if abs(w - self.width) < 0.5 and abs(h - self.height) < 0.5:
            return
        try:
            self.prepareGeometryChange()
        except Exception:
            pass
        self.width = w
        self.height = h
        # Keep Qt size hints roughly aligned (best-effort)
        try:
            self.setMinimumSize(self._min_width, self._min_height)
        except Exception:
            pass
        # Update ports and inline areas
        try:
            self._update_port_positions()
        except Exception:
            pass
        try:
            self._update_content_geometry(force=True)
        except Exception:
            pass
        # Update connections touching this node
        self._update_attached_connections()
        # Repaint
        try:
            if self._created_in_gui_thread:
                self.update()
        except Exception:
            pass

    def _hit_test_resize_zone(self, pos: QPointF) -> str | None:
        """Return which edge/corner is being hovered for resizing, if any."""
        x = float(pos.x())
        y = float(pos.y())
        w = float(self.width)
        h = float(self.height)
        m = float(self._resize_margin)
        in_left = 0.0 <= x <= m
        in_right = (w - m) <= x <= w
        in_top = 0.0 <= y <= m
        in_bottom = (h - m) <= y <= h
        if in_left and in_top:
            return "top_left"
        if in_right and in_top:
            return "top_right"
        if in_left and in_bottom:
            return "bottom_left"
        if in_right and in_bottom:
            return "bottom_right"
        if in_left:
            return "left"
        if in_right:
            return "right"
        if in_top:
            return "top"
        if in_bottom:
            return "bottom"
        return None

    def _cursor_for_zone(self, zone: str | None):
        if zone in ("left", "right"):
            return Qt.SizeHorCursor
        if zone in ("top", "bottom"):
            return Qt.SizeVerCursor
        if zone in ("top_left", "bottom_right"):
            return Qt.SizeFDiagCursor
        if zone in ("top_right", "bottom_left"):
            return Qt.SizeBDiagCursor
        return Qt.ArrowCursor

    def hoverMoveEvent(self, event):  # pragma: no cover - UI interaction
        try:
            if not self.isSelected():
                # Only show resize affordances when selected to reduce visual noise
                self.unsetCursor()
                return super().hoverMoveEvent(event)
            local = event.pos()
            zone = self._hit_test_resize_zone(local)
            self.setCursor(self._cursor_for_zone(zone))
        except Exception:
            pass
        return super().hoverMoveEvent(event)

    def mousePressEvent(self, event):  # pragma: no cover - UI interaction
        if event.button() == Qt.LeftButton:
            zone = self._hit_test_resize_zone(event.pos())
            if zone is not None:
                # Begin interactive resizing
                self._resizing_active = True
                self._resize_zone = zone
                self._drag_start_pos = event.scenePos()
                self._drag_start_rect = QRectF(self.pos().x(), self.pos().y(), self.width, self.height)
                event.accept()
                return
            # Restrict node dragging to title bar area only
            # Title bar height is 30 as painted in paint()
            try:
                local = event.pos()
                if not (0.0 <= float(local.x()) <= float(self.width) and 0.0 <= float(local.y()) <= 30.0):
                    # Clicked outside title: temporarily disable movable so drag won't move the node
                    if self.flags() & QGraphicsItem.ItemIsMovable:
                        self.setFlag(QGraphicsItem.ItemIsMovable, False)
                        self._move_blocked = True
            except Exception:
                pass
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):  # pragma: no cover - UI interaction
        if self._resizing_active and self._drag_start_pos is not None and self._drag_start_rect is not None:
            try:
                # Compute delta in scene coordinates
                scene_delta = event.scenePos() - self._drag_start_pos
                dx = float(scene_delta.x())
                dy = float(scene_delta.y())
                start = self._drag_start_rect
                new_x = float(start.x())
                new_y = float(start.y())
                new_w = float(start.width())
                new_h = float(start.height())
                z = self._resize_zone or ""
                if "right" in z:
                    new_w = max(self._min_width, new_w + dx)
                if "left" in z:
                    # Move X while keeping right edge stable
                    proposed_w = max(self._min_width, new_w - dx)
                    new_x = new_x + (new_w - proposed_w)
                    new_w = proposed_w
                if "bottom" in z:
                    new_h = max(self._min_height, new_h + dy)
                if "top" in z:
                    proposed_h = max(self._min_height, new_h - dy)
                    new_y = new_y + (new_h - proposed_h)
                    new_h = proposed_h

                # Apply position first (may emit position_changed)
                try:
                    self.setPos(new_x, new_y)
                except Exception:
                    pass
                # Apply size and update internals
                self.set_node_size(new_w, new_h)
                # Reuse position_changed flow to update connections and workflow state
                try:
                    self.position_changed.emit(self)
                except Exception:
                    pass
            except Exception:
                pass
            event.accept()
            return
        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):  # pragma: no cover - UI interaction
        if self._resizing_active:
            self._resizing_active = False
            self._resize_zone = None
            self._drag_start_pos = None
            self._drag_start_rect = None
            try:
                self.setCursor(Qt.ArrowCursor)
            except Exception:
                pass
            event.accept()
            return
        # Restore movable flag if we blocked it on press
        if self._move_blocked:
            try:
                self.setFlag(QGraphicsItem.ItemIsMovable, True)
            except Exception:
                pass
            self._move_blocked = False
        return super().mouseReleaseEvent(event)

    def _update_attached_connections(self) -> None:
        """Update connection paths for edges attached to this node."""
        try:
            sc = self.scene()
            if sc is None:
                return
            for it in sc.items():
                try:
                    if hasattr(it, "output_node") and hasattr(it, "input_node") and hasattr(it, "update_path"):
                        if getattr(it, "output_node", None) is self or getattr(it, "input_node", None) is self:
                            it.update_path()
                except Exception:
                    continue
        except Exception:
            pass
    
    def get_execution_state(self):
        """Get the current node execution state."""
        return self._execution_state

    def mouseDoubleClickEvent(self, event):
        """Open full settings dialog on double-click."""
        try:
            from core.settings_dialog import open_settings_dialog
        except Exception:
            open_settings_dialog = None
        if open_settings_dialog is not None:
            updated = open_settings_dialog(self)
            if updated:
                self.update()
        super().mouseDoubleClickEvent(event)

    # --- Progress & Error helpers (GUI only) ---------------------------------
    def set_progress(self, percent: int | None, message: str | None = None) -> None:  # pragma: no cover - UI hook
        """Update floating progress panel below the node and auto-hide when done.

        - percent is None: hide progress panel
        - percent < 0: show indeterminate
        - 0 <= percent <= 100: show determinate with that value
        """
        try:
            # Lazily construct floating progress panel
            if self._progress_proxy is None:
                try:
                    container = QFrame()
                    container.setObjectName("NodeProgressPanel")
                    try:
                        container.setStyleSheet(
                            """
                            QFrame#NodeProgressPanel {
                                background-color: #2b2b2b;
                                border: 1px solid #666666;
                                border-radius: 6px;
                            }
                            QProgressBar {
                                color: #e0e0e0;
                                background-color: #3a3a3a;
                                border: 1px solid #555;
                                border-radius: 4px;
                                text-align: center;
                            }
                            QProgressBar::chunk { background-color: #4CAF50; }
                            """
                        )
                    except Exception:
                        pass
                    v = QVBoxLayout(container)
                    v.setContentsMargins(8, 6, 8, 6)
                    v.setSpacing(4)
                    bar = QProgressBar()
                    bar.setTextVisible(True)
                    v.addWidget(bar)
                    self._progress_widget = container
                    self._progress_bar = bar
                    self._progress_proxy = QGraphicsProxyWidget(self)
                    self._progress_proxy.setWidget(container)
                except Exception:
                    return
            # Update bar state
            if percent is None:
                # Hide panel
                try:
                    self._progress_proxy.setVisible(False)
                except Exception:
                    pass
                # If clearing progress completely, return early
                return
            if int(percent) < 0:
                self._progress_bar.setRange(0, 0)  # indeterminate
            else:
                self._progress_bar.setRange(0, 100)
                clamped = max(0, min(100, int(percent)))
                self._progress_bar.setValue(clamped)
            # Format text with optional message
            msg = "" if message is None else str(message)
            if self._progress_bar.maximum() == 0:
                self._progress_bar.setFormat(msg if msg else "Working…")
            else:
                self._progress_bar.setFormat(("%p%" if not msg else f"%p%  —  {msg}"))
            # Ensure visible and positioned
            self._progress_proxy.setVisible(True)
            self._update_progress_geometry()
            # Auto-hide when completed (>= 100) or node not running anymore
            try:
                if self._progress_bar.maximum() == 100 and self._progress_bar.value() >= 100:
                    # Defer a tiny delay before hiding to let user notice completion
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(500, lambda: self._progress_proxy and self._progress_proxy.setVisible(False))
            except Exception:
                pass
        except Exception:
            pass

    def _build_error_widget(self, message: str) -> QWidget:
        container = QFrame()
        container.setObjectName("NodeErrorPanel")
        try:
            container.setStyleSheet(
                """
                QFrame#NodeErrorPanel {
                    background-color: #3a2020;
                    border: 1px solid #aa5555;
                    border-radius: 6px;
                }
                QLabel {
                    color: #ffd0d0;
                }
                """
            )
        except Exception:
            pass
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        lbl = QLabel(str(message))
        try:
            lbl.setWordWrap(True)
        except Exception:
            pass
        layout.addWidget(lbl)
        return container

    def _build_log_widget(self) -> QWidget:
        container = QFrame()
        container.setObjectName("NodeLogPanel")
        try:
            container.setStyleSheet(
                """
                QFrame#NodeLogPanel {
                    background-color: #222A31;
                    border: 1px solid #4A6A86;
                    border-radius: 6px;
                }
                QPlainTextEdit {
                    background-color: #1b1f23;
                    color: #d7e2eb;
                    border: none;
                }
                """
            )
        except Exception:
            pass
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        txt = QPlainTextEdit()
        try:
            txt.setReadOnly(True)
        except Exception:
            pass
        layout.addWidget(txt)
        self._log_text = txt
        return container

    def _build_pause_widget(self, message: str) -> QWidget:
        container = QFrame()
        container.setObjectName("NodePausePanel")
        try:
            container.setStyleSheet(
                """
                QFrame#NodePausePanel {
                    background-color: #3a3820; /* dark yellowish */
                    border: 1px solid #d8b400;  /* yellow border */
                    border-radius: 6px;
                }
                QLabel {
                    color: #ffe28a; /* warm yellow text */
                }
                """
            )
        except Exception:
            pass
        layout = QVBoxLayout(container)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)
        lbl = QLabel(str(message))
        try:
            lbl.setWordWrap(True)
        except Exception:
            pass
        layout.addWidget(lbl)
        return container

    def show_pause(self, message: str) -> None:  # pragma: no cover - UI hook
        """Show a pause hint panel (yellow) under the node using the same slot as error panel."""
        try:
            if self._error_proxy is None:
                self._error_widget = self._build_pause_widget(message)
                self._error_proxy = QGraphicsProxyWidget(self)
                self._error_proxy.setWidget(self._error_widget)
            else:
                try:
                    self._error_widget = self._build_pause_widget(message)
                    self._error_proxy.setWidget(self._error_widget)
                except Exception:
                    pass
            self._update_error_geometry()
            try:
                self._error_proxy.setVisible(True)
            except Exception:
                pass
        except Exception:
            pass

    def _update_error_geometry(self) -> None:
        if self._error_proxy is None:
            return
        try:
            # Match width to node and position just below node bounds
            if self._error_widget is not None:
                try:
                    self._error_widget.setFixedWidth(int(self.width))
                    self._error_widget.adjustSize()
                except Exception:
                    pass
            y_offset = float(self.height) + 6.0
            # If progress panel visible, stack error below it for spacing
            try:
                if self._progress_proxy is not None and self._progress_proxy.isVisible():
                    # Estimate height after adjustSize
                    ph = self._progress_proxy.size().height() if hasattr(self._progress_proxy, 'size') else 22
                    y_offset += float(max(18, ph + 4))
            except Exception:
                pass
            self._error_proxy.setPos(0.0, y_offset)
            # Ensure it renders above most items but below port labels
            try:
                self._error_proxy.setZValue(10)
            except Exception:
                pass
        except Exception:
            pass

    def _update_progress_geometry(self) -> None:
        if self._progress_proxy is None:
            return
        try:
            if self._progress_widget is not None:
                try:
                    self._progress_widget.setFixedWidth(int(self.width))
                    self._progress_widget.adjustSize()
                except Exception:
                    pass
            self._progress_proxy.setPos(0.0, float(self.height) + 6.0)
            try:
                self._progress_proxy.setZValue(9)
            except Exception:
                pass
        except Exception:
            pass

    def _update_log_geometry(self) -> None:
        if self._log_proxy is None:
            return
        try:
            if self._log_widget is not None:
                try:
                    self._log_widget.setFixedWidth(int(self.width))
                    self._log_widget.adjustSize()
                except Exception:
                    pass
            # Stack log panel below node; if other panels visible, stack beneath them
            y_offset = float(self.height) + 6.0
            try:
                if self._progress_proxy is not None and self._progress_proxy.isVisible():
                    ph = self._progress_proxy.size().height() if hasattr(self._progress_proxy, 'size') else 22
                    y_offset += float(max(18, ph + 4))
            except Exception:
                pass
            try:
                if self._error_proxy is not None and self._error_proxy.isVisible():
                    eh = self._error_proxy.size().height() if hasattr(self._error_proxy, 'size') else 22
                    y_offset += float(max(18, eh + 4))
            except Exception:
                pass
            self._log_proxy.setPos(0.0, y_offset)
            try:
                self._log_proxy.setZValue(8)
            except Exception:
                pass
        except Exception:
            pass

    def show_error(self, message: str) -> None:  # pragma: no cover - UI hook
        """Show an error panel under the node with the given message."""
        try:
            if self._error_proxy is None:
                self._error_widget = self._build_error_widget(message)
                self._error_proxy = QGraphicsProxyWidget(self)
                self._error_proxy.setWidget(self._error_widget)
            else:
                # Update existing widget content
                try:
                    # Rebuild to ensure style/size updates cleanly
                    self._error_widget = self._build_error_widget(message)
                    self._error_proxy.setWidget(self._error_widget)
                except Exception:
                    pass
            self._update_error_geometry()
            try:
                self._error_proxy.setVisible(True)
            except Exception:
                pass
        except Exception:
            pass

    def clear_error(self) -> None:  # pragma: no cover - UI hook
        try:
            if self._error_proxy is not None:
                self._error_proxy.setVisible(False)
        except Exception:
            pass

    # --- Floating log panel helpers (GUI only) -------------------------------
    def append_log_line(self, line: str) -> None:  # pragma: no cover - UI hook
        """Append a line to the floating log panel and ensure it is visible.

        Also hides the progress panel if both would otherwise overlap for clarity.
        """
        try:
            if self._log_proxy is None:
                try:
                    self._log_widget = self._build_log_widget()
                    self._log_proxy = QGraphicsProxyWidget(self)
                    self._log_proxy.setWidget(self._log_widget)
                except Exception:
                    return
            # Hide progress panel when log is active
            try:
                if self._progress_proxy is not None:
                    self._progress_proxy.setVisible(False)
            except Exception:
                pass
            # Append text
            try:
                if self._log_text is not None:
                    self._log_text.appendPlainText(str(line))
                    # Auto-scroll to bottom
                    try:
                        cursor = self._log_text.textCursor()
                        cursor.movePosition(cursor.End)
                        self._log_text.setTextCursor(cursor)
                    except Exception:
                        pass
            except Exception:
                pass
            # Ensure visible and positioned
            try:
                self._log_proxy.setVisible(True)
            except Exception:
                pass
            self._update_log_geometry()
        except Exception:
            pass

    def clear_log(self) -> None:  # pragma: no cover - UI hook
        try:
            if self._log_text is not None:
                self._log_text.setPlainText("")
            if self._log_proxy is not None:
                self._log_proxy.setVisible(False)
        except Exception:
            pass

    def _inline_summary(self) -> list[str]:
        """Return a list of concise property summaries to paint inside the node.
        Default is to pick a few common keys when present.
        """
        keys_priority = [
            "name",
            "receptor",
            "ligand",
            "input_file",
            "output_file",
            "deffnm",
            "method",
            "basis",
        ]
        summary = []
        for key in keys_priority:
            if key in self.properties and self.properties[key] not in (None, ""):
                value = str(self.properties[key])
                if len(value) > 28:
                    value = value[:25] + ".."
                summary.append(f"{key}: {value}")
        # Fallback if nothing
        if not summary and self.properties:
            for k, v in list(self.properties.items())[:3]:
                summary.append(f"{k}: {v}")
        return summary
    
    def _get_state_colors(self):
        """Get colors based on the current execution state using theme-aware colors."""
        # Map execution states to boolean flags for the theme-aware function
        is_validating = self._execution_state == self.STATE_VALIDATING
        is_running = self._execution_state == self.STATE_RUNNING
        is_paused = self._execution_state == self.STATE_PAUSED
        is_completed = self._execution_state == self.STATE_COMPLETED
        is_error = self._execution_state == self.STATE_ERROR

        return get_node_colors_for_state(
            is_validating=is_validating,
            is_running=is_running,
            is_paused=is_paused,
            is_completed=is_completed,
            is_error=is_error,
            is_selected=self.isSelected()
        )
    
    def _draw_running_effect(self, painter):
        """Draw a pulsing glow effect for running/validating nodes."""
        import time

        # Create pulsing effect based on time
        time_factor = time.time() * 2.5  # Balanced pulsing speed
        pulse = (1 + 0.4 * abs(time_factor % 2 - 1))  # Pulse between 0.6 and 1.4

        # Get glow color based on current state
        if self._execution_state == self.STATE_VALIDATING:
            # Balanced blue glow for validating
            glow_r, glow_g, glow_b = 80, 140, 200
        else:
            # Balanced green glow for running (without blue tints)
            glow_r, glow_g, glow_b = 60, 140, 80

        # Draw outer glow with balanced colors
        glow_rect = self.boundingRect().adjusted(-5, -5, 5, 5)  # Balanced glow area
        glow_color = QColor(glow_r, glow_g, glow_b, int(45 * pulse))  # Balanced opacity
        painter.setPen(QPen(glow_color, 2))  # Balanced pen thickness
        painter.setBrush(QBrush(QColor(glow_r, glow_g, glow_b, int(20 * pulse))))
        painter.drawRoundedRect(glow_rect, 10, 10)
    
    def execute(self, inputs=None):
        """Execute the node's operation. Override in subclasses."""
        raise NotImplementedError("Subclasses must implement execute method")
    
    def validate(self):
        """Validate the node configuration. Override in subclasses."""
        return True, "Node is valid"

    # --- Live result hook (updated by WorkflowManager on the UI node) ---
    def on_result(self, result: object) -> None:  # pragma: no cover - UI update hook
        """Called on the canvas node with the node's execution result.

        Default behavior stores the last result into properties and triggers a repaint.
        Subclasses can override to update inline widgets (e.g., tables, images).
        """
        try:
            def _sanitize(value):
                try:
                    # Drop or summarize heavy payloads to keep UI responsive
                    if isinstance(value, (bytes, bytearray)):
                        return {"__bytes__": len(value)}
                    if isinstance(value, dict):
                        out = {}
                        for k, v in value.items():
                            if isinstance(v, (bytes, bytearray)):
                                out[k] = {"__bytes__": len(v)}
                            elif isinstance(v, str) and len(v) > 10000:
                                out[k] = v[:10000] + "…"
                            elif isinstance(v, list) and len(v) > 200:
                                out[k] = v[:200] + ["…"]
                            else:
                                out[k] = v
                        return out
                    if isinstance(value, list) and len(value) > 200:
                        return value[:200] + ["…"]
                    if isinstance(value, str) and len(value) > 10000:
                        return value[:10000] + "…"
                except Exception:
                    pass
                return value

            self.properties["last_result"] = _sanitize(result)
            self.update()
        except Exception:
            pass