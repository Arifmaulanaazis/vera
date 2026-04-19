"""
Workflow canvas for drag-drop functionality.
Handles the visual workflow editor with nodes and connections.
"""

from PySide6.QtWidgets import (
    QGraphicsView,
    QGraphicsScene,
    QGraphicsItem,
    QMenu,
    QMessageBox,
    QWidget
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF, QSize, QEvent, QTimer
from PySide6.QtGui import (
    QPainter,
    QPen,
    QBrush,
    QColor,
    QMouseEvent,
    QWheelEvent,
    QGuiApplication,
)

# Optional: native gesture event (trackpad pinch on some platforms)
try:  # pragma: no cover - optional on some platforms
    from PySide6.QtGui import QNativeGestureEvent
except Exception:  # pragma: no cover
    QNativeGestureEvent = None  # type: ignore

from core.nodes import BaseNode
from core.connections import NodeConnection
from core.nodes import NodePort
from core.port_types import is_compatible, compatibility_message, color_for_type, normalize_type
from core.settings_dialog import open_settings_dialog
from typing import Optional
import json
from nodes import node_factory
from core.toolbox import FloatingNodePicker
from core.toolbox import load_node_icon
from PySide6.QtGui import QIcon
from core.performance import ViewportOptimizer
from core.toast import ToastOverlay


class WorkflowCanvas(QGraphicsView):
    """Main canvas for workflow editing with drag-drop support."""
    
    # Signals
    node_selected = Signal(object)  # Emits selected node
    selection_cleared = Signal()
    workflow_changed = Signal()
    # Emitted when a node requests partial downstream re-run
    partial_rerun_requested = Signal(object)
    
    def __init__(self):
        super().__init__()
        
        # Create scene
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        
        # Setup canvas
        self._setup_canvas()
        
        # Track connections and nodes
        self.nodes = []
        self.connections = []
        self.connection_start_node = None
        self.connection_start_port = None
        self._connection_start_from_output = None
        self._dragging_connection_temp_item = None
        self._overlay_widget = None
        # Floating node picker shown after incomplete connection drag
        self._floating_picker: FloatingNodePicker | None = None
        self._port_signature_cache: dict[str, dict[str, list[tuple[str, str]]]] = {}
        # Persist origin info while picker is open
        self._pending_from_node: BaseNode | None = None
        self._pending_port_name: str | None = None
        self._pending_from_output: bool | None = None

        # Simple history for undo/redo (snapshot-based)
        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._is_restoring_snapshot: bool = False
        self._max_history: int = 50
        self._paste_offset_step: int = 20

        # Zoom state
        self._zoom_factor = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 4.0
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        # Enable pinch gesture on touch devices/trackpads
        self.setAttribute(Qt.WA_AcceptTouchEvents, True)
        self.grabGesture(Qt.PinchGesture)
        # Warm cache of node port signatures asynchronously to avoid UI stalls
        try:
            QTimer.singleShot(0, self._warm_port_signature_cache_async)
        except Exception:
            pass
            
        # Initialize viewport optimizer for performance
        self._viewport_optimizer = ViewportOptimizer(self)
        self._viewport_optimizer.start_monitoring()
        
        # No toast overlay at canvas level; handled by application-level overlay
        
    def _setup_canvas(self):
        """Setup canvas properties and behavior."""
        # Enable drag and drop
        self.setAcceptDrops(True)
        
        # Set render hints for smooth graphics
        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        try:
            self.setRenderHint(QPainter.TextAntialiasing)
        except Exception:
            pass
        # Use smart update mode for better performance
        # BoundingRectViewportUpdate updates only changed regions
        try:
            self.setViewportUpdateMode(QGraphicsView.BoundingRectViewportUpdate)
            # Enable caching for better performance
            self.setCacheMode(QGraphicsView.CacheBackground)
            # Optimize rendering
            self.setOptimizationFlag(QGraphicsView.DontAdjustForAntialiasing, True)
            self.setOptimizationFlag(QGraphicsView.DontSavePainterState, True)
        except Exception:
            pass
        
        # Set drag mode
        self.setDragMode(QGraphicsView.RubberBandDrag)
        
        # Set background
        self.setBackgroundBrush(QBrush(QColor(40, 40, 40)))
        
        # Set scene rect
        self.scene.setSceneRect(-5000, -5000, 10000, 10000)
        
        # Grid settings
        self.grid_size = 20
        self.draw_grid = True
        
        # Connect scene signals
        self.scene.selectionChanged.connect(self._on_selection_changed)

    # ---------------------------
    # Zoom helpers and handlers
    # ---------------------------
    def _apply_zoom_multiplier(self, multiplier: float) -> None:
        """Scale view by a relative multiplier with clamping.

        Keeps zoom within [_min_zoom, _max_zoom].
        """
        if multiplier == 1.0:
            return
        new_zoom = self._zoom_factor * float(multiplier)
        if new_zoom < self._min_zoom:
            multiplier = self._min_zoom / max(self._zoom_factor, 1e-9)
            new_zoom = self._min_zoom
        elif new_zoom > self._max_zoom:
            multiplier = self._max_zoom / max(self._zoom_factor, 1e-9)
            new_zoom = self._max_zoom
        self.scale(multiplier, multiplier)
        self._zoom_factor = new_zoom
        self._position_overlay()

    def zoom_in(self, step: float = 0.1) -> None:
        self._apply_zoom_multiplier(1.0 + abs(step))

    def zoom_out(self, step: float = 0.1) -> None:
        self._apply_zoom_multiplier(1.0 / (1.0 + abs(step)))

    def set_zoom(self, zoom: float) -> None:
        zoom = max(self._min_zoom, min(self._max_zoom, float(zoom)))
        multiplier = zoom / max(self._zoom_factor, 1e-9)
        self._apply_zoom_multiplier(multiplier)

    def wheelEvent(self, event: QWheelEvent):
        """Ctrl + wheel to zoom (like browsers). Otherwise, default scroll."""
        ctrl_held = bool(event.modifiers() & Qt.ControlModifier)
        if ctrl_held:
            # Use smooth exponential scaling for trackpads and wheels
            pixel_delta = event.pixelDelta()
            angle_delta = event.angleDelta()
            delta_y = 0
            if not pixel_delta.isNull():
                delta_y = pixel_delta.y()
            elif not angle_delta.isNull():
                delta_y = angle_delta.y()
            # Positive delta -> zoom in
            # Base tuned for smoothness; similar to browser zoom feel
            factor = pow(1.0015, delta_y)
            # Prevent extreme tiny multipliers around 0
            if abs(delta_y) < 1:
                factor = 1.0
            self._apply_zoom_multiplier(factor)
            event.accept()
            return
        # Default behavior when Ctrl not pressed
        super().wheelEvent(event)

    def event(self, evt):  # noqa: C901 keep simple central dispatch
        # Handle gesture events (pinch)
        if evt.type() == QEvent.Gesture:
            ge = evt  # type: ignore[assignment]
            try:
                pinch = ge.gesture(Qt.PinchGesture)
                if pinch is not None:
                    change_flags = pinch.changeFlags()
                    # 0x1 corresponds to ScaleFactorChanged in QPinchGesture::ChangeFlag
                    # We avoid importing the enum to keep compatibility across PySide6 versions
                    if int(change_flags) & 0x1:
                        scale_delta = float(pinch.scaleFactor())
                        self._apply_zoom_multiplier(scale_delta)
                    ge.accept()
                    return True
            except Exception:
                pass
        # Handle native gestures for trackpads (e.g., macOS/Windows precision touchpad)
        if QNativeGestureEvent is not None and evt.type() == QEvent.Type.NativeGesture:
            try:
                nge: QNativeGestureEvent = evt  # type: ignore[assignment]
                gtype = getattr(nge, "gestureType", None)
                # Zoom gesture provides a value typically in small increments
                if gtype is not None and int(gtype()) == int(Qt.NativeGestureType.ZoomNativeGesture):
                    value = float(nge.value())  # positive -> zoom in
                    # Convert small value into smooth multiplier
                    factor = pow(2.0, value)
                    self._apply_zoom_multiplier(factor)
                    return True
            except Exception:
                pass
        return super().event(evt)

    def attach_overlay_widget(self, widget: Optional[QWidget]):
        """Attach an overlay widget positioned bottom-center inside the viewport."""
        if widget is None:
            return
        self._overlay_widget = widget
        widget.setParent(self.viewport())
        widget.adjustSize()
        self._position_overlay()

    def show_toast(self, title: str, message: str = "", status: str = "info", duration_ms: int = 3000, closable: bool = True) -> None:
        """Forward toast request to application-level overlay via main window if possible."""
        try:
            # Traverse to the top-level window and call _show_toast
            w = self.window()
            if w is not None and hasattr(w, "_show_toast"):
                w._show_toast(title=title, message=message, status=status, duration_ms=duration_ms, closable=closable)
        except Exception:
            pass

    def _position_overlay(self):
        if not self._overlay_widget:
            return
        margin = 16
        vp_size: QSize = self.viewport().size()
        w = self._overlay_widget.width()
        h = self._overlay_widget.height()
        x = int((vp_size.width() - w) / 2)
        y = int(vp_size.height() - h - margin)
        self._overlay_widget.move(x, y)
        self._overlay_widget.raise_()
        
    def drawBackground(self, painter, rect):
        """Draw grid background."""
        super().drawBackground(painter, rect)
        
        if not self.draw_grid:
            return
            
        # Draw grid
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        
        # Vertical lines
        left = int(rect.left()) - (int(rect.left()) % self.grid_size)
        top = int(rect.top()) - (int(rect.top()) % self.grid_size)
        
        lines = []
        for x in range(left, int(rect.right()), self.grid_size):
            lines.append([x, rect.top(), x, rect.bottom()])
            
        for y in range(top, int(rect.bottom()), self.grid_size):
            lines.append([rect.left(), y, rect.right(), y])
            
        for line in lines:
            painter.drawLine(*line)

        # Keep overlay positioned when panning/zooming by updating after background draw
        self._position_overlay()
    
    def dragEnterEvent(self, event):
        """Handle drag enter event."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dragMoveEvent(self, event):
        """Handle drag move event."""
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def dropEvent(self, event):
        """Handle drop event - create new node."""
        if event.mimeData().hasText():
            node_type = event.mimeData().text()
            
            # Convert view coordinates to scene coordinates
            scene_pos = self.mapToScene(event.position().toPoint())
            
            # Create node
            self.add_node(node_type, scene_pos)
            
            event.acceptProposedAction()
        else:
            event.ignore()
    
    def add_node(self, node_type, position=None):
        """Add a new node to the canvas."""
        from nodes import node_factory
        
        # Create node
        node = node_factory.create_node(node_type)
        if not node:
            QMessageBox.warning(self, "Error", f"Unknown node type: {node_type}")
            return
        
        # Set position
        if position is None:
            position = QPointF(0, 0)
        node.setPos(position)
        
        # Add to scene
        self.scene.addItem(node)
        self.nodes.append(node)
        
        # Connect node signals
        node.connection_requested.connect(self._on_connection_requested)
        node.position_changed.connect(self._on_node_moved)
        # Re-emit partial rerun requests from nodes (e.g., Select Columns)
        try:
            node.rerun_requested.connect(self._on_node_rerun_requested)
        except Exception:
            pass
        
        # Emit workflow changed
        self.workflow_changed.emit()
        # Record history
        self._push_snapshot()
        
        return node
    
    def remove_node(self, node):
        """Remove a node from the canvas."""
        if node in self.nodes:
            # Remove connections
            connections_to_remove = []
            for conn in self.connections:
                if conn.input_node == node or conn.output_node == node:
                    connections_to_remove.append(conn)
            
            for conn in connections_to_remove:
                self.remove_connection(conn)
            
            # Remove node
            self.scene.removeItem(node)
            self.nodes.remove(node)
            
            self.workflow_changed.emit()
            self._push_snapshot()
    
    def add_connection(self, output_node, output_port, input_node, input_port):
        """Add a connection between two nodes."""
        # Check if connection already exists
        for conn in self.connections:
            if (conn.output_node == output_node and conn.output_port == output_port and
                conn.input_node == input_node and conn.input_port == input_port):
                return conn  # Connection already exists
        # Disallow multiple connections to the same single input port
        for conn in self.connections:
            if conn.input_node == input_node and conn.input_port == input_port:
                return None

        # Validate types when possible
        try:
            out_port_item = output_node.output_ports.get(output_port)
            in_port_item = input_node.input_ports.get(input_port)
            if isinstance(out_port_item, NodePort) and isinstance(in_port_item, NodePort):
                if not is_compatible(out_port_item.data_type, in_port_item.data_type):
                    return None
        except Exception:
            pass

        # Create connection
        connection = NodeConnection(output_node, output_port, input_node, input_port)
        # Default label to data type when available
        try:
            if out_port_item is not None:
                connection.set_label(getattr(out_port_item, "data_type", ""))
        except Exception:
            pass
        self.scene.addItem(connection)
        self.connections.append(connection)

        # Emit workflow changed
        self.workflow_changed.emit()
        self._push_snapshot()

        return connection
    
    def remove_connection(self, connection):
        """Remove a connection."""
        if connection in self.connections:
            self.scene.removeItem(connection)
            self.connections.remove(connection)
            self.workflow_changed.emit()
            self._push_snapshot()
    
    def clear_canvas(self):
        """Clear all nodes and connections."""
        self.scene.clear()
        self.nodes.clear()
        self.connections.clear()
        self.workflow_changed.emit()
        self._push_snapshot()
        # Toast
        try:
            self.show_toast("Canvas cleared", "All nodes and connections removed.", status="warning", duration_ms=2000, closable=False)
        except Exception:
            pass
    
    def _on_selection_changed(self):
        """Handle selection change."""
        selected_items = self.scene.selectedItems()
        
        if selected_items:
            # Find selected node
            for item in selected_items:
                if isinstance(item, BaseNode):
                    self.node_selected.emit(item)
                    return
        else:
            self.selection_cleared.emit()
    
    def _on_connection_requested(self, node, port, port_type):
        """Handle connection request from node using drag-to-connect UX."""
        # Start dragging from this port; track type to validate target later
        self.connection_start_node = node
        self.connection_start_port = port
        self._connection_start_from_output = (port in node.output_ports)
        # Create a temporary straight line path item for visual feedback
        from PySide6.QtWidgets import QGraphicsPathItem
        from PySide6.QtGui import QPainterPath
        self._dragging_connection_temp_item = QGraphicsPathItem()
        pen = QPen(QColor(160, 160, 160), 1, Qt.DashLine)
        self._dragging_connection_temp_item.setPen(pen)
        self.scene.addItem(self._dragging_connection_temp_item)
    
    def _on_node_moved(self, node):
        """Handle node position change."""
        # Update connections
        for conn in self.connections:
            if conn.input_node == node or conn.output_node == node:
                conn.update_path()
        
        self.workflow_changed.emit()
    
    def contextMenuEvent(self, event):
        """Handle right-click context menu."""
        menu = QMenu(self)
        
        # Add actions based on what's under cursor
        scene_pos = self.mapToScene(event.pos())
        item = self.scene.itemAt(scene_pos, self.transform())
        
        if isinstance(item, BaseNode):
            # Node context menu
            delete_action = menu.addAction("Delete Node")
            delete_action.triggered.connect(lambda: self.remove_node(item))
            
            menu.addSeparator()
            
            # Rename node title
            rename_action = menu.addAction("Rename Title…")
            def _rename_title():
                from PySide6.QtWidgets import QInputDialog
                text, ok = QInputDialog.getText(self, "Rename Node", "Title:", text=getattr(item, "title", ""))
                if ok:
                    try:
                        item.title = str(text)
                        item.update()
                        # Notify workflow/state systems and history
                        self.node_selected.emit(item)
                        self.workflow_changed.emit()
                        self._push_snapshot()
                    except Exception:
                        pass
            rename_action.triggered.connect(_rename_title)

            # Settings dialog
            properties_action = menu.addAction("Settings…")
            def _open_settings():
                if open_settings_dialog(item):
                    item.update()
                    try:
                        self.node_selected.emit(item)
                        self.workflow_changed.emit()
                        self._push_snapshot()
                    except Exception:
                        pass
            properties_action.triggered.connect(_open_settings)
        elif isinstance(item, NodeConnection):
            # Connection context menu
            edit_label_action = menu.addAction("Set Label…")
            remove_action = menu.addAction("Remove Connection")

            def _on_set_label():
                from PySide6.QtWidgets import QInputDialog
                text, ok = QInputDialog.getText(self, "Connection Label", "Label:", text=item.label_item.toPlainText())
                if ok:
                    item.set_label(text)
            edit_label_action.triggered.connect(_on_set_label)

            remove_action.triggered.connect(lambda: self.remove_connection(item))
            
        else:
            # Canvas context menu
            clear_action = menu.addAction("Clear Canvas")
            clear_action.triggered.connect(self.clear_canvas)
        
        menu.exec(event.globalPos())
    
    def keyPressEvent(self, event):
        """Handle key press events."""
        if event.key() == Qt.Key_Delete:
            # Delete selected items
            selected_items = self.scene.selectedItems()
            for item in selected_items:
                if isinstance(item, BaseNode):
                    self.remove_node(item)
                elif isinstance(item, NodeConnection):
                    self.remove_connection(item)
        elif (event.modifiers() & Qt.ControlModifier) and event.key() == Qt.Key_A:
            # Ctrl + A: select all nodes
            self.select_all()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ---------------------------
    # Partial re-run handling
    # ---------------------------
    def _on_node_rerun_requested(self, node):
        """Re-emit partial rerun requests to whoever manages execution (main app binds this)."""
        try:
            self.partial_rerun_requested.emit(node)
        except Exception:
            pass

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_overlay()

    def mouseMoveEvent(self, event: QMouseEvent):
        """When dragging a connection from a port, update the temp path."""
        if self._dragging_connection_temp_item and self.connection_start_node:
            from PySide6.QtGui import QPainterPath
            # Start at the start port position
            start_item = self.connection_start_node.output_ports.get(self.connection_start_port)
            if start_item is None:
                start_item = self.connection_start_node.input_ports.get(self.connection_start_port)
            if start_item is None:
                return super().mouseMoveEvent(event)
            start_pos = start_item.scenePos()
            end_pos = self.mapToScene(event.pos())
            path = QPainterPath(start_pos)
            # Simple bezier towards cursor
            dx = end_pos.x() - start_pos.x()
            control_offset = max(abs(dx) * 0.5, 50)
            from PySide6.QtCore import QRectF as _QRectF
            control1 = start_pos + _QRectF(control_offset, 0, 0, 0).topLeft()
            control2 = end_pos + _QRectF(-control_offset, 0, 0, 0).topLeft()
            path.cubicTo(control1, control2, end_pos)
            self._dragging_connection_temp_item.setPath(path)
            # Adjust color based on compatibility with hovered port
            scene_pos = self.mapToScene(event.pos())
            item = self.scene.itemAt(scene_pos, self.transform())
            pen = self._dragging_connection_temp_item.pen()
            if isinstance(item, NodePort) and isinstance(start_item, NodePort):
                # Determine target data type depending on direction
                if start_item.port_type == "output" and item.port_type == "input" and item.parentItem() != start_item.parentItem():
                    ok = is_compatible(start_item.data_type, item.data_type)
                    pen.setColor(QColor(120, 220, 120) if ok else QColor(220, 120, 120))
                elif start_item.port_type == "input" and item.port_type == "output" and item.parentItem() != start_item.parentItem():
                    ok = is_compatible(item.data_type, start_item.data_type)
                    pen.setColor(QColor(120, 220, 120) if ok else QColor(220, 120, 120))
                else:
                    base = color_for_type(getattr(start_item, "data_type", "any"))
                    pen.setColor(base)
            else:
                base = color_for_type(getattr(start_item, "data_type", "any"))
                pen.setColor(base)
            self._dragging_connection_temp_item.setPen(pen)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        """Finish a drag connection when releasing over a target port."""
        if self._dragging_connection_temp_item:
            # Remove temp item
            self.scene.removeItem(self._dragging_connection_temp_item)
            self._dragging_connection_temp_item = None

            # Detect item under cursor
            scene_pos = self.mapToScene(event.pos())
            item = self.scene.itemAt(scene_pos, self.transform())
            # Find if it's a port and create a connection if types are compatible
            if isinstance(item, NodePort):
                # If started from output, must end on input and vice versa
                start_from_output = self.connection_start_port in self.connection_start_node.output_ports
                if start_from_output and item.port_type == "input" and item.parent_node != self.connection_start_node:
                    # Validate type compatibility
                    src_port = self.connection_start_node.output_ports.get(self.connection_start_port)
                    # Disallow multiple connections to the same input port
                    for c in self.connections:
                        if c.input_node == item.parent_node and c.input_port == item.port_name:
                            from PySide6.QtWidgets import QToolTip
                            QToolTip.showText(event.globalPosition().toPoint(), f"Input port '{item.port_name}' already connected", self)
                            src_port = None  # force skip
                            break
                    if src_port is not None and is_compatible(src_port.data_type, item.data_type):
                        conn = self.add_connection(self.connection_start_node, self.connection_start_port, item.parent_node, item.port_name)
                        # Auto label connection with data type
                        if conn:
                            conn.set_label(src_port.data_type)
                    else:
                        # Show warning tooltip-like message
                        msg = compatibility_message(getattr(src_port, "data_type", "any"), getattr(item, "data_type", "any"))
                        from PySide6.QtWidgets import QToolTip
                        QToolTip.showText(event.globalPosition().toPoint(), msg, self)
                        # Offer compatible nodes via floating picker
                        try:
                            self._show_floating_node_picker(scene_pos)
                        except Exception:
                            pass
                elif (not start_from_output) and item.port_type == "output" and item.parent_node != self.connection_start_node:
                    dst_port = self.connection_start_node.input_ports.get(self.connection_start_port)
                    # Disallow multiple connections to the same input port (self side)
                    for c in self.connections:
                        if c.input_node == self.connection_start_node and c.input_port == self.connection_start_port:
                            from PySide6.QtWidgets import QToolTip
                            QToolTip.showText(event.globalPosition().toPoint(), f"Input port '{self.connection_start_port}' already connected", self)
                            dst_port = None
                            break
                    if dst_port is not None and is_compatible(item.data_type, dst_port.data_type):
                        conn = self.add_connection(item.parent_node, item.port_name, self.connection_start_node, self.connection_start_port)
                        if conn:
                            conn.set_label(item.data_type)
                    else:
                        msg = compatibility_message(getattr(item, "data_type", "any"), getattr(dst_port, "data_type", "any"))
                        from PySide6.QtWidgets import QToolTip
                        QToolTip.showText(event.globalPosition().toPoint(), msg, self)
                        try:
                            self._show_floating_node_picker(scene_pos)
                        except Exception:
                            pass
            else:
                # Not dropped on a port: show floating node picker filtered by compatibility
                try:
                    self._show_floating_node_picker(scene_pos)
                except Exception:
                    pass

            # Reset state
            self.connection_start_node = None
            self.connection_start_port = None
            self._connection_start_from_output = None
            return
        super().mouseReleaseEvent(event)

    # ---------------------------
    # Floating node picker helpers
    # ---------------------------
    def _collect_compatible_nodes(self, from_output: bool, data_type: str) -> list[tuple[str, str, QIcon]]:
        """Return list of (node_type, display_name, icon) compatible with given type.

        - If from_output is True: we need nodes having any input compatible with data_type.
        - If False: nodes with any output compatible with data_type.
        """
        out: list[tuple[str, str, QIcon]] = []
        # Strict normalization to ensure equality matching (no 'any' widening)
        dt = normalize_type(str(data_type))
        try:
            available = node_factory.get_available_nodes()  # type: ignore[attr-defined]
        except Exception:
            return out
        for node_type, cls in available.items():
            try:
                sig = self._port_signature_cache.get(node_type)
                if sig is None:
                    # Instantiate once to inspect ports. Use lightweight mode to avoid heavy UI/web views.
                    from core.nodes import BaseNode as _BaseNode
                    prev_light = getattr(_BaseNode, "_lightweight_construction", False)
                    try:
                        _BaseNode._lightweight_construction = True  # type: ignore[attr-defined]
                        inst = cls()
                    finally:
                        _BaseNode._lightweight_construction = prev_light  # type: ignore[attr-defined]
                    inputs = []
                    for name, port in (getattr(inst, "input_ports", {}) or {}).items():
                        try:
                            inputs.append((str(name), str(getattr(port, "data_type", "any"))))
                        except Exception:
                            continue
                    outputs = []
                    for name, port in (getattr(inst, "output_ports", {}) or {}).items():
                        try:
                            outputs.append((str(name), str(getattr(port, "data_type", "any"))))
                        except Exception:
                            continue
                    sig = {"inputs": inputs, "outputs": outputs, "title": getattr(inst, "title", node_type)}
                    self._port_signature_cache[node_type] = sig
                    # Proactively stop timers and delete the temporary instance to avoid UI-thread leaks
                    try:
                        timer = getattr(inst, "_animation_timer", None)
                        if timer is not None:
                            try:
                                timer.stop()
                            except Exception:
                                pass
                            try:
                                timer.deleteLater()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    try:
                        # Detach/destroy proxy widgets if they were created
                        for proxy_attr in ("_content_proxy", "_progress_proxy", "_error_proxy"):
                            proxy = getattr(inst, proxy_attr, None)
                            if proxy is not None:
                                try:
                                    # Remove any embedded widget to help GC
                                    if hasattr(proxy, "setWidget"):
                                        proxy.setWidget(None)
                                except Exception:
                                    pass
                                try:
                                    proxy.setParentItem(None)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    try:
                        inst.setParentItem(None)
                    except Exception:
                        pass
                    try:
                        inst.setParent(None)
                    except Exception:
                        pass
                    try:
                        inst.deleteLater()
                    except Exception:
                        pass
                ok = False
                if from_output:
                    for _, in_type in sig.get("inputs", []):
                        if normalize_type(in_type) == dt:
                            ok = True
                            break
                else:
                    for _, out_type in sig.get("outputs", []):
                        if normalize_type(out_type) == dt:
                            ok = True
                            break
                if not ok:
                    continue
                title = str(sig.get("title", node_type))
                icon = load_node_icon(node_type, title)
                out.append((node_type, title, icon))
            except Exception:
                continue
        # Sort by title for stable order
        try:
            out.sort(key=lambda t: t[1].lower())
        except Exception:
            pass
        return out

    def _show_floating_node_picker(self, scene_pos) -> None:
        if self.connection_start_node is None or self.connection_start_port is None:
            return
        # Determine drag direction and data type
        start_from_output = (self.connection_start_port in self.connection_start_node.output_ports)
        if start_from_output:
            src_port = self.connection_start_node.output_ports.get(self.connection_start_port)
            data_t = getattr(src_port, "data_type", "any")
        else:
            dst_port = self.connection_start_node.input_ports.get(self.connection_start_port)
            data_t = getattr(dst_port, "data_type", "any")
        # Persist for when user chooses a node
        self._pending_from_node = self.connection_start_node
        self._pending_port_name = self.connection_start_port
        self._pending_from_output = start_from_output
        items = self._collect_compatible_nodes(from_output=start_from_output, data_type=data_t)
        if not items:
            return
        # Build or reuse picker
        if self._floating_picker is None:
            self._floating_picker = FloatingNodePicker(self.viewport())
            self._floating_picker.node_chosen.connect(self._on_floating_node_chosen)
        self._floating_picker.populate(items)
        # Position near cursor
        view_pt = self.mapFromScene(scene_pos)
        x = int(view_pt.x()) + 10
        y = int(view_pt.y()) + 10
        # Clamp within viewport
        vp = self.viewport().rect()
        self._floating_picker.adjustSize()
        w = self._floating_picker.width()
        h = self._floating_picker.height()
        if x + w > vp.right() - 8:
            x = max(8, vp.right() - w - 8)
        if y + h > vp.bottom() - 8:
            y = max(8, vp.bottom() - h - 8)
        self._floating_picker.move(x, y)
        self._floating_picker.show()
        self._floating_picker.raise_()
        # Focus search for immediate typing
        try:
            self._floating_picker.search.setFocus()
            # Pre-fill with empty or keep previous
        except Exception:
            pass

    def _on_floating_node_chosen(self, node_type: str) -> None:
        if self._floating_picker is not None:
            try:
                self._floating_picker.hide()
            except Exception:
                pass
        # Create node near the last temp end position? Use mouse cursor
        try:
            cursor_pos = self.mapToScene(self.mapFromGlobal(self.cursor().pos()))
        except Exception:
            cursor_pos = None
        new_node = self.add_node(node_type, cursor_pos)
        if new_node is None:
            return
        # Connect depending on direction
        try:
            start_from_output = bool(self._pending_from_output)
        except Exception:
            start_from_output = True
        try:
            if start_from_output:
                src_port = None
                from_node = self._pending_from_node
                port_name = self._pending_port_name or ""
                if from_node is not None:
                    src_port = from_node.output_ports.get(port_name)
                # Find first compatible input on new node
                for name, port in (getattr(new_node, "input_ports", {}) or {}).items():
                    if is_compatible(getattr(src_port, "data_type", "any"), getattr(port, "data_type", "any")):
                        conn = self.add_connection(from_node, port_name, new_node, name)
                        if conn:
                            conn.set_label(getattr(src_port, "data_type", ""))
                        break
            else:
                dst_port = None
                from_node = self._pending_from_node
                port_name = self._pending_port_name or ""
                if from_node is not None:
                    dst_port = from_node.input_ports.get(port_name)
                for name, port in (getattr(new_node, "output_ports", {}) or {}).items():
                    if is_compatible(getattr(port, "data_type", "any"), getattr(dst_port, "data_type", "any")):
                        conn = self.add_connection(new_node, name, from_node, port_name)
                        if conn:
                            conn.set_label(getattr(port, "data_type", ""))
                        break
        except Exception:
            pass
        finally:
            # Clear pending state
            self._pending_from_node = None
            self._pending_port_name = None
            self._pending_from_output = None

    # ---------------------------
    # Edit actions: Undo/Redo
    # ---------------------------
    def _serialize_all(self) -> dict:
        """Serialize entire canvas to a JSON-friendly snapshot."""
        nodes_payload: list[dict] = []
        index_map: dict[object, int] = {}
        for idx, n in enumerate(self.nodes):
            try:
                pos = n.pos()
                position = {"x": float(pos.x()), "y": float(pos.y())}
            except Exception:
                position = {"x": 0.0, "y": 0.0}
            # Persist node size when available
            try:
                size = {"w": float(getattr(n, "width", 0.0)), "h": float(getattr(n, "height", 0.0))}
                if size["w"] <= 0.0 or size["h"] <= 0.0:
                    size = None
            except Exception:
                size = None
            nodes_payload.append({
                "type": getattr(n, "node_type", "unknown"),
                "title": getattr(n, "title", ""),
                "properties": dict(getattr(n, "properties", {}) or {}),
                "position": position,
                **({"size": size} if size else {}),
            })
            index_map[n] = idx

        connections_payload: list[dict] = []
        for c in self.connections:
            try:
                connections_payload.append({
                    "out_index": index_map.get(c.output_node, -1),
                    "out_port": c.output_port,
                    "in_index": index_map.get(c.input_node, -1),
                    "in_port": c.input_port,
                })
            except Exception:
                continue

        return {"format": "VERASnapshotV1", "nodes": nodes_payload, "connections": connections_payload}

    def _apply_snapshot(self, snapshot: dict) -> None:
        """Restore canvas from a snapshot created by _serialize_all."""
        if not isinstance(snapshot, dict) or snapshot.get("format") != "VERASnapshotV1":
            return
        self._is_restoring_snapshot = True
        try:
            # Clear current
            self.scene.clear()
            self.nodes.clear()
            self.connections.clear()

            # Recreate nodes
            from nodes import node_factory
            new_nodes: list[BaseNode] = []
            for nd in snapshot.get("nodes", []):
                node_type = nd.get("type", "unknown")
                node = node_factory.create_node(node_type)
                if node is None:
                    continue
                pos = nd.get("position", {"x": 0.0, "y": 0.0})
                node.setPos(QPointF(float(pos.get("x", 0.0)), float(pos.get("y", 0.0))))
                # Restore size when present
                try:
                    sz = nd.get("size")
                    if isinstance(sz, dict):
                        w = float(sz.get("w", getattr(node, "width", 200)))
                        h = float(sz.get("h", getattr(node, "height", 100)))
                        if hasattr(node, "set_node_size"):
                            node.set_node_size(w, h)
                except Exception:
                    pass
                # Restore title if present
                try:
                    if "title" in nd:
                        node.title = str(nd.get("title", node.title))
                except Exception:
                    pass
                # Restore basic properties if present
                try:
                    props = nd.get("properties", {}) or {}
                    for k, v in props.items():
                        node.set_property(k, v)
                except Exception:
                    pass
                self.scene.addItem(node)
                self.nodes.append(node)
                node.connection_requested.connect(self._on_connection_requested)
                node.position_changed.connect(self._on_node_moved)
                try:
                    node.rerun_requested.connect(self._on_node_rerun_requested)
                except Exception:
                    pass
                new_nodes.append(node)

            # Recreate connections
            for cd in snapshot.get("connections", []):
                oi = int(cd.get("out_index", -1))
                ii = int(cd.get("in_index", -1))
                out_port = cd.get("out_port")
                in_port = cd.get("in_port")
                if 0 <= oi < len(new_nodes) and 0 <= ii < len(new_nodes):
                    self.add_connection(new_nodes[oi], out_port, new_nodes[ii], in_port)

            # Signal change but avoid pushing another snapshot
            self.workflow_changed.emit()
        finally:
            self._is_restoring_snapshot = False

    def _push_snapshot(self) -> None:
        """Push current state onto the undo stack unless we're restoring."""
        if self._is_restoring_snapshot:
            return
        try:
            snap = self._serialize_all()
            self._undo_stack.append(snap)
            # Limit size
            if len(self._undo_stack) > self._max_history:
                self._undo_stack = self._undo_stack[-self._max_history:]
            # Any new edit invalidates redo history
            self._redo_stack.clear()
        except Exception:
            pass

    def undo(self) -> None:
        if len(self._undo_stack) <= 1:
            return
        current = self._undo_stack.pop()
        self._redo_stack.append(current)
        prev = self._undo_stack[-1]
        self._apply_snapshot(prev)

    def redo(self) -> None:
        if not self._redo_stack:
            return
        nxt = self._redo_stack.pop()
        self._undo_stack.append(nxt)
        self._apply_snapshot(nxt)

    # ---------------------------
    # Edit actions: Cut/Copy/Paste
    # ---------------------------
    def copy_selected(self) -> None:
        selected_nodes = [it for it in self.scene.selectedItems() if isinstance(it, BaseNode)]
        if not selected_nodes:
            return
        index_map = {n: i for i, n in enumerate(selected_nodes)}
        payload_nodes: list[dict] = []
        for n in selected_nodes:
            try:
                pos = n.pos()
                # Persist size for clipboard
                try:
                    size = {"w": float(getattr(n, "width", 0.0)), "h": float(getattr(n, "height", 0.0))}
                    if size["w"] <= 0.0 or size["h"] <= 0.0:
                        size = None
                except Exception:
                    size = None
                payload_nodes.append({
                    "type": getattr(n, "node_type", "unknown"),
                    "title": getattr(n, "title", ""),
                    "properties": dict(getattr(n, "properties", {}) or {}),
                    "position": {"x": float(pos.x()), "y": float(pos.y())},
                    **({"size": size} if size else {}),
                })
            except Exception:
                continue
        payload_conns: list[dict] = []
        for c in self.connections:
            if c.output_node in index_map and c.input_node in index_map:
                payload_conns.append({
                    "out_index": index_map[c.output_node],
                    "out_port": c.output_port,
                    "in_index": index_map[c.input_node],
                    "in_port": c.input_port,
                })
        payload = {"format": "VERAClipboardV1", "nodes": payload_nodes, "connections": payload_conns}
        try:
            QGuiApplication.clipboard().setText(json.dumps(payload))
        except Exception:
            pass
        # Toast
        try:
            self.show_toast("Copied", f"{len(selected_nodes)} node(s) copied to clipboard.", status="info", duration_ms=1800, closable=False)
        except Exception:
            pass

    def cut_selected(self) -> None:
        self.copy_selected()
        self.delete_selected()

    def delete_selected(self) -> None:
        selected_items = self.scene.selectedItems()
        # Remove connections first that involve selected nodes
        nodes_to_remove = [it for it in selected_items if isinstance(it, BaseNode)]
        conns_to_remove = [it for it in selected_items if isinstance(it, NodeConnection)]
        # Add implicit connections touching nodes
        for c in list(self.connections):
            if c.input_node in nodes_to_remove or c.output_node in nodes_to_remove:
                conns_to_remove.append(c)
        # Dedup
        conns_to_remove = list(dict.fromkeys(conns_to_remove))
        for c in conns_to_remove:
            self.remove_connection(c)
        for n in nodes_to_remove:
            self.remove_node(n)
        self._push_snapshot()
        # Toast
        try:
            if nodes_to_remove or conns_to_remove:
                self.show_toast("Deleted", f"Removed {len(nodes_to_remove)} node(s) and {len(conns_to_remove)} connection(s).", status="warning", duration_ms=1800, closable=False)
        except Exception:
            pass

    def paste_from_clipboard(self) -> None:
        try:
            text = QGuiApplication.clipboard().text()
            data = json.loads(text)
        except Exception:
            return
        if not isinstance(data, dict) or data.get("format") != "VERAClipboardV1":
            return
        # Create nodes with slight offset
        created_nodes: list[BaseNode] = []
        from nodes import node_factory
        for nd in data.get("nodes", []):
            node = node_factory.create_node(nd.get("type", "unknown"))
            if node is None:
                continue
            pos = nd.get("position", {"x": 0.0, "y": 0.0})
            x = float(pos.get("x", 0.0)) + float(self._paste_offset_step)
            y = float(pos.get("y", 0.0)) + float(self._paste_offset_step)
            node.setPos(QPointF(x, y))
            # Restore size if present
            try:
                sz = nd.get("size")
                if isinstance(sz, dict):
                    w = float(sz.get("w", getattr(node, "width", 200)))
                    h = float(sz.get("h", getattr(node, "height", 100)))
                    if hasattr(node, "set_node_size"):
                        node.set_node_size(w, h)
            except Exception:
                pass
            # Restore title when available
            try:
                if "title" in nd:
                    node.title = str(nd.get("title", node.title))
            except Exception:
                pass
            try:
                for k, v in (nd.get("properties", {}) or {}).items():
                    node.set_property(k, v)
            except Exception:
                pass
            self.scene.addItem(node)
            self.nodes.append(node)
            node.connection_requested.connect(self._on_connection_requested)
            node.position_changed.connect(self._on_node_moved)
            try:
                node.rerun_requested.connect(self._on_node_rerun_requested)
            except Exception:
                pass
            created_nodes.append(node)
        # Create connections among newly created nodes
        for cd in data.get("connections", []):
            oi = int(cd.get("out_index", -1))
            ii = int(cd.get("in_index", -1))
            if 0 <= oi < len(created_nodes) and 0 <= ii < len(created_nodes):
                self.add_connection(created_nodes[oi], cd.get("out_port"), created_nodes[ii], cd.get("in_port"))
        self.workflow_changed.emit()
        self._push_snapshot()
        # Toast
        try:
            conn_count = len([cd for cd in (data.get("connections", []) or []) if 0 <= int(cd.get("out_index", -1)) < len(created_nodes) and 0 <= int(cd.get("in_index", -1)) < len(created_nodes)])
            self.show_toast("Pasted", f"Inserted {len(created_nodes)} node(s) and {conn_count} connection(s).", status="success", duration_ms=2000, closable=False)
        except Exception:
            pass

    # ---------------------------
    # View helpers
    # ---------------------------
    def select_all(self) -> None:
        """Select all nodes on the canvas."""
        try:
            for n in self.nodes:
                n.setSelected(True)
        except Exception:
            pass

    def zoom_fit(self) -> None:
        rect = self.scene.itemsBoundingRect()
        if rect.isNull() or rect.width() == 0 or rect.height() == 0:
            rect = self.scene.sceneRect()
        margin = 40
        r = QRectF(rect)
        r.adjust(-margin, -margin, margin, margin)
        if r.width() <= 0 or r.height() <= 0:
            return
        try:
            self.fitInView(r, Qt.KeepAspectRatio)
            # Update internal zoom estimate based on transform
            try:
                self._zoom_factor = max(self._min_zoom, min(self._max_zoom, float(self.transform().m11())))
            except Exception:
                pass
            self._position_overlay()
        except Exception:
            pass
