"""
Node connection classes for the workflow system.
Handles connections between nodes and data flow.
"""

from PySide6.QtWidgets import QGraphicsItem, QGraphicsPathItem, QGraphicsTextItem
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QPen, QColor, QPainterPath

from .port_types import color_for_type


class NodeConnection(QGraphicsPathItem):
    """Represents a connection between two nodes."""
    
    def __init__(self, output_node, output_port, input_node, input_port):
        super().__init__()
        
        self.output_node = output_node
        self.output_port = output_port
        self.input_node = input_node
        self.input_port = input_port
        
        # Connection properties
        self.line_width = 2
        self.line_color = QColor(200, 200, 200)
        self.selected_color = QColor(255, 255, 100)
        
        # Label text item (centered on path)
        self.label_item = QGraphicsTextItem("")
        self.label_item.setDefaultTextColor(QColor(220, 220, 220))
        self.label_item.setZValue(1)
        self.label_item.setParentItem(self)

        # Setup connection
        self._setup_connection()
        self.update_path()
        
    def _setup_connection(self):
        """Setup connection properties."""
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setZValue(-1)  # Draw behind nodes
        
    def update_path(self):
        """Update the connection path based on node positions."""
        # Get port positions
        output_port_item = self.output_node.output_ports.get(self.output_port)
        input_port_item = self.input_node.input_ports.get(self.input_port)
        
        if not output_port_item or not input_port_item:
            return
        
        # Get global positions
        start_pos = output_port_item.scenePos()
        end_pos = input_port_item.scenePos()
        
        # Create path
        path = QPainterPath()
        path.moveTo(start_pos)
        
        # Calculate control points for smooth curve
        dx = end_pos.x() - start_pos.x()
        control_offset = max(abs(dx) * 0.5, 50)
        
        control1 = start_pos + QRectF(control_offset, 0, 0, 0).topLeft()
        control2 = end_pos + QRectF(-control_offset, 0, 0, 0).topLeft()
        
        path.cubicTo(control1, control2, end_pos)
        
        # Set path
        self.setPath(path)

        # Update label position to be at the middle of the path
        mid_point = path.pointAtPercent(0.5)
        brect = self.label_item.boundingRect()
        self.label_item.setPos(mid_point.x() - brect.width() / 2, mid_point.y() - brect.height() / 2)
        # Update color to reflect output port data type when available
        try:
            out_port_item = self.output_node.output_ports.get(self.output_port)
            if out_port_item is not None and hasattr(out_port_item, "data_type"):
                self.line_color = color_for_type(out_port_item.data_type)
        except Exception:
            pass
    
    def paint(self, painter, option, widget):
        """Paint the connection."""
        # Set pen based on selection state
        if self.isSelected():
            pen = QPen(self.selected_color, self.line_width + 1)
        else:
            pen = QPen(self.line_color, self.line_width)
        
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawPath(self.path())
        
        # Draw arrow at the end
        self._draw_arrow(painter, pen)

    def set_label(self, text: str):
        """Set the center label text for this connection."""
        self.label_item.setPlainText(text or "")
        # Recenter on next update_path or do a quick reposition now
        path = self.path()
        if not path.isEmpty():
            mid = path.pointAtPercent(0.5)
            brect = self.label_item.boundingRect()
            self.label_item.setPos(mid.x() - brect.width() / 2, mid.y() - brect.height() / 2)
    
    def _draw_arrow(self, painter, pen):
        """Draw an arrow at the end of the connection."""
        # Get the end point and direction
        path = self.path()
        if path.elementCount() < 2:
            return
        
        # Get last segment direction
        last_point = path.pointAtPercent(1.0)
        prev_point = path.pointAtPercent(0.95)
        
        dx = last_point.x() - prev_point.x()
        dy = last_point.y() - prev_point.y()
        
        # Normalize
        length = (dx * dx + dy * dy) ** 0.5
        if length == 0:
            return
        
        dx /= length
        dy /= length
        
        # Arrow size
        arrow_size = 10
        
        # Calculate arrow points
        arrow_p1 = last_point + QRectF(
            -arrow_size * dx + arrow_size * dy * 0.5,
            -arrow_size * dy - arrow_size * dx * 0.5,
            0, 0
        ).topLeft()
        
        arrow_p2 = last_point + QRectF(
            -arrow_size * dx - arrow_size * dy * 0.5,
            -arrow_size * dy + arrow_size * dx * 0.5,
            0, 0
        ).topLeft()
        
        # Draw arrow
        painter.setPen(pen)
        painter.drawLine(last_point, arrow_p1)
        painter.drawLine(last_point, arrow_p2)
    
    def boundingRect(self):
        """Return the bounding rectangle."""
        return self.path().boundingRect().adjusted(-10, -10, 10, 10)
