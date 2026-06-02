"""ImageViewerNode implementation."""

from .common import *  # noqa: F401,F403

class ImageViewerNode(BaseNode):
    """Inline image viewer that displays PNG/JPEG bytes passed to input."""

    def __init__(self):
        super().__init__("image_view", "Image View")
        self.logger = get_logger(__name__)
        self.add_input_port("image", "image")
        self.add_input_port("bytes", "bytes")
        self.width = 300
        self.height = 250
        self.setMinimumSize(self.width, self.height)
        self.setMaximumSize(self.width, self.height)
        # Properties - remove lazy property as we want automatic display
        self.set_property("auto_scale", True)
        try:
            # Respect lightweight construction
            from core.nodes import BaseNode as _BaseNode
            if getattr(_BaseNode, "_lightweight_construction", False):  # type: ignore[attr-defined]
                self._label = None
            else:
                from PySide6.QtWidgets import QLabel
                from PySide6.QtCore import Qt
                from PySide6.QtWidgets import QSizePolicy
                self._label = QLabel()
                self._label.setAlignment(Qt.AlignCenter)
                try:
                    # Fill the node body completely for image display
                    self.set_content_margins(8, 40, 8, 8)
                    self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    self._label.setText("No image")
                    self._label.setStyleSheet("QLabel { background-color: rgba(40, 40, 40, 100); border: 1px solid #666; border-radius: 4px; color: #ccc; }")
                except Exception:
                    pass
                layout = self.content_layout
                if layout is not None:
                    # Only add the label - no buttons needed
                    layout.addWidget(self._label, 0, 0)
                # Re-align ports after custom width/height
                self._update_port_positions()
        except Exception:
            self._label = None

    def set_property(self, key, value):
        super().set_property(key, value)
        # Auto-render when new image/bytes arrive
        try:
            if key in ("last_input_image", "last_input_bytes"):
                # Always show image immediately when data arrives
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda d=value: self._set_image(d))
                except Exception:
                    self._set_image(value)
        except Exception:
            pass

    def _set_image(self, data: Optional[bytes]) -> None:
        """Display image data in the label with proper scaling."""
        if self._label is None or data is None or len(data) == 0:
            if self._label is not None:
                self._label.setText("No image")
            return
        
        try:
            from PySide6.QtGui import QPixmap, QImage
            from PySide6.QtCore import Qt
            
            # Try to load image with Qt first
            img = QImage.fromData(data)
            if img.isNull():
                # Fallback: decode with Pillow if Qt image plugins are unavailable
                try:
                    import io
                    from PIL import Image as _PILImage  # type: ignore
                    pil = _PILImage.open(io.BytesIO(data)).convert("RGBA")
                    w, h = pil.size
                    buf = pil.tobytes("raw", "RGBA")
                    img = QImage(buf, w, h, QImage.Format_RGBA8888).copy()
                except Exception as e:
                    self.logger.warning(f"Failed to decode image data: {e}")
                    self._label.setText("Invalid image")
                    return
            
            if img.isNull():
                self._label.setText("Invalid image")
                return
            
            # Calculate available space for image (account for margins and borders)
            available_width = max(32, self.width - 24)  # 8px margin on each side + some padding
            available_height = max(32, self.height - 56)  # 40px top margin + 8px bottom + padding
            
            # Scale image to fit available space while maintaining aspect ratio
            # Use positional args for PySide6 compatibility: scaled(w, h, mode, transform)
            scaled = img.scaled(
                available_width,
                available_height,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            
            # Set the scaled image
            self._label.setPixmap(QPixmap.fromImage(scaled))
            self._label.setText("")  # Clear "No image" text
            
            self.logger.info(f"Image displayed: {img.width()}x{img.height()} -> {scaled.width()}x{scaled.height()}")
            
        except Exception as e:
            self.logger.error(f"Error displaying image: {e}")
            self._label.setText("Error loading image")

    def execute(self, inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Process image data and return summary."""
        if not inputs:
            return {"image_size": 0}
        
        # Get image data from either port
        image_data = inputs.get("image") or inputs.get("bytes")
        size = len(image_data) if image_data else 0
        
        return {"image_size": size}

    def on_result(self, result: object) -> None:
        """Handle execution result and display image."""
        try:
            # Get image data from stored inputs
            data = self.properties.get("last_input_image")
            if data is None:
                data = self.properties.get("last_input_bytes")
            
            # Always show image automatically when data is available
            if data:
                try:
                    from PySide6.QtCore import QTimer
                    QTimer.singleShot(0, lambda d=data: self._set_image(d))
                except Exception:
                    self._set_image(data)
        except Exception:
            pass
        super().on_result(result)

    def _inline_summary(self) -> list[str]:  # type: ignore[override]
        # Hide inline summary (no label or size shown under the title)
        return []
