"""
Performance optimization utilities for the workflow canvas.
Handles viewport-based virtualization, lazy loading, and LOD rendering.
"""

from PySide6.QtCore import QRectF, QPointF, QTimer, QObject, Signal
from PySide6.QtWidgets import QGraphicsItem, QGraphicsWidget
from typing import Optional, Callable, Dict, Any, Set
import weakref
try:  # Optional: helps detect deleted Qt objects safely
    import shiboken6  # type: ignore
except Exception:  # pragma: no cover - environment may not expose shiboken6 explicitly
    shiboken6 = None  # type: ignore


class ViewportOptimizer(QObject):
    """Manages viewport-based optimization for canvas nodes."""
    
    # Signals
    node_visibility_changed = Signal(object, bool)  # node, is_visible
    
    def __init__(self, canvas):
        # Parent to canvas so we're destroyed with it; prevents timers firing on dead widgets
        super().__init__(canvas)
        self.canvas = canvas
        self._visible_nodes: Set[weakref.ref] = set()
        self._update_timer = QTimer(self)
        self._update_timer.timeout.connect(self._update_visible_nodes)
        self._update_timer.setInterval(100)  # Update every 100ms
        self._viewport_margin = 200  # Extra margin around viewport
        self._lod_thresholds = {
            'full': 1.0,      # Zoom >= 100%
            'medium': 0.5,    # Zoom >= 50%
            'low': 0.25,      # Zoom >= 25%
            'minimal': 0.0    # Any zoom level
        }
        # Track lifecycle so we can stop cleanly if canvas is deleted
        self._is_active = True
        try:
            self.canvas.destroyed.connect(self._on_canvas_destroyed)
        except Exception:
            pass
        
    def start_monitoring(self):
        """Start monitoring viewport changes."""
        if not self._is_canvas_valid():
            return
        self._update_timer.start()
        # Connect to canvas events
        try:
            self.canvas.scene.sceneRectChanged.connect(self._schedule_update)
        except Exception:
            pass
        
    def stop_monitoring(self):
        """Stop monitoring viewport changes."""
        self._is_active = False
        try:
            self._update_timer.stop()
        except Exception:
            pass
        try:
            self.canvas.scene.sceneRectChanged.disconnect(self._schedule_update)
        except Exception:
            pass

    def _on_canvas_destroyed(self, *args, **kwargs):
        """Handle canvas deletion to avoid calling into dead C++ objects."""
        self.stop_monitoring()
        try:
            self.canvas = None  # type: ignore[assignment]
        except Exception:
            pass

    def _is_canvas_valid(self) -> bool:
        """Return True if the canvas (and its C++ object) is still alive."""
        if not self._is_active:
            return False
        c = getattr(self, 'canvas', None)
        if c is None:
            return False
        # If shiboken6 is available, use it to check the underlying C++ object
        try:
            if shiboken6 is not None and not shiboken6.isValid(c):  # type: ignore[attr-defined]
                return False
        except Exception:
            # Fall back to best effort when validation isn't available
            pass
        return True
        
    def _schedule_update(self):
        """Schedule an update for the next timer tick."""
        # Debounce rapid updates
        if not self._update_timer.isActive():
            self._update_timer.start()
            
    def _update_visible_nodes(self):
        """Update which nodes are visible in the viewport."""
        if not self._is_canvas_valid():
            # Stop further updates if canvas is gone
            self.stop_monitoring()
            return
        viewport_rect = self._get_expanded_viewport_rect()
        new_visible = set()
        
        try:
            nodes_iterable = list(getattr(self.canvas, 'nodes', []) or [])
        except Exception:
            nodes_iterable = []
        for node in nodes_iterable:
            try:
                node_ref = weakref.ref(node)
                node_rect = node.sceneBoundingRect()
            except Exception:
                continue
            
            if viewport_rect.intersects(node_rect):
                # Node is visible
                new_visible.add(node_ref)
                if node_ref not in self._visible_nodes:
                    # Node became visible
                    self._on_node_became_visible(node)
            else:
                # Node is not visible
                if node_ref in self._visible_nodes:
                    # Node became hidden
                    self._on_node_became_hidden(node)
                    
        self._visible_nodes = new_visible
        
    def _get_expanded_viewport_rect(self) -> QRectF:
        """Get the viewport rect with extra margin."""
        if not self._is_canvas_valid():
            return QRectF()
        try:
            viewport_rect = self.canvas.mapToScene(
                self.canvas.viewport().rect()
            ).boundingRect()
        except RuntimeError:
            # Underlying C++ object likely deleted; stop updates gracefully
            self.stop_monitoring()
            return QRectF()
        except Exception:
            return QRectF()
        
        # Expand by margin
        return viewport_rect.adjusted(
            -self._viewport_margin,
            -self._viewport_margin,
            self._viewport_margin,
            self._viewport_margin
        )
        
    def _on_node_became_visible(self, node):
        """Handle node becoming visible."""
        self.node_visibility_changed.emit(node, True)
        if hasattr(node, 'on_became_visible'):
            node.on_became_visible()
            
    def _on_node_became_hidden(self, node):
        """Handle node becoming hidden."""
        self.node_visibility_changed.emit(node, False)
        if hasattr(node, 'on_became_hidden'):
            node.on_became_hidden()
            
    def get_lod_level(self, node) -> str:
        """Get the appropriate LOD level for a node based on zoom."""
        zoom = getattr(self.canvas, '_zoom_factor', 1.0)
        
        for level, threshold in self._lod_thresholds.items():
            if zoom >= threshold:
                return level
        return 'minimal'
        
    def is_node_in_viewport(self, node) -> bool:
        """Check if a node is currently in the viewport."""
        viewport_rect = self._get_expanded_viewport_rect()
        return viewport_rect.intersects(node.sceneBoundingRect())


class LazyWidget:
    """Wrapper for lazy-loaded widgets in nodes."""
    
    def __init__(self, widget_factory: Callable[[], QGraphicsWidget],
                 placeholder_factory: Optional[Callable[[], QGraphicsWidget]] = None):
        self._widget_factory = widget_factory
        self._placeholder_factory = placeholder_factory
        self._widget: Optional[QGraphicsWidget] = None
        self._placeholder: Optional[QGraphicsWidget] = None
        self._is_loaded = False
        self._load_timer: Optional[QTimer] = None
        
    def get_widget(self, immediate: bool = False) -> QGraphicsWidget:
        """Get the widget, loading it if necessary."""
        if self._is_loaded and self._widget:
            return self._widget
            
        if immediate:
            self._load_widget()
            return self._widget
        else:
            # Return placeholder and schedule loading
            if not self._placeholder and self._placeholder_factory:
                self._placeholder = self._placeholder_factory()
            self._schedule_load()
            return self._placeholder or self._create_default_placeholder()
            
    def _schedule_load(self):
        """Schedule widget loading after a delay."""
        if self._load_timer is None:
            self._load_timer = QTimer()
            self._load_timer.setSingleShot(True)
            self._load_timer.timeout.connect(self._load_widget)
        self._load_timer.start(500)  # 500ms delay
        
    def _load_widget(self):
        """Actually load the widget."""
        if not self._is_loaded:
            self._widget = self._widget_factory()
            self._is_loaded = True
            # Replace placeholder if it exists
            if self._placeholder and self._placeholder.parentItem():
                parent = self._placeholder.parentItem()
                layout = getattr(parent, 'content_layout', None)
                if layout:
                    # Remove placeholder and add real widget
                    layout.removeItem(self._placeholder)
                    self._placeholder.setParent(None)
                    layout.addWidget(self._widget, 0, 0)
                    
    def _create_default_placeholder(self) -> QGraphicsWidget:
        """Create a default placeholder widget."""
        from PySide6.QtWidgets import QLabel, QGraphicsProxyWidget
        label = QLabel("Loading...")
        label.setStyleSheet("color: #888; padding: 10px;")
        proxy = QGraphicsProxyWidget()
        proxy.setWidget(label)
        return proxy
        
    def unload(self):
        """Unload the widget to free memory."""
        if self._widget:
            if self._widget.parentItem():
                parent = self._widget.parentItem()
                layout = getattr(parent, 'content_layout', None)
                if layout:
                    layout.removeItem(self._widget)
            self._widget.setParent(None)
            self._widget = None
            self._is_loaded = False
            
            
class NodeContentCache:
    """Caches rendered content for nodes to avoid re-rendering."""
    
    def __init__(self, max_cache_size: int = 50):
        self._cache: Dict[str, Any] = {}
        self._access_order: list = []
        self._max_cache_size = max_cache_size
        
    def get(self, key: str) -> Optional[Any]:
        """Get cached content."""
        if key in self._cache:
            # Update access order
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None
        
    def set(self, key: str, value: Any):
        """Cache content."""
        if key in self._cache:
            self._access_order.remove(key)
        elif len(self._cache) >= self._max_cache_size:
            # Evict least recently used
            lru_key = self._access_order.pop(0)
            del self._cache[lru_key]
            
        self._cache[key] = value
        self._access_order.append(key)
        
    def clear(self):
        """Clear all cached content."""
        self._cache.clear()
        self._access_order.clear()


class ProgressiveRenderer:
    """Handles progressive rendering of large data sets."""
    
    def __init__(self, render_func: Callable[[int, int], None],
                 total_items: int,
                 chunk_size: int = 100):
        self._render_func = render_func
        self._total_items = total_items
        self._chunk_size = chunk_size
        self._current_index = 0
        self._timer = QTimer()
        self._timer.timeout.connect(self._render_next_chunk)
        self._timer.setInterval(16)  # ~60 FPS
        
    def start(self):
        """Start progressive rendering."""
        self._current_index = 0
        self._timer.start()
        
    def stop(self):
        """Stop progressive rendering."""
        self._timer.stop()
        
    def _render_next_chunk(self):
        """Render the next chunk of items."""
        if self._current_index >= self._total_items:
            self._timer.stop()
            return
            
        end_index = min(self._current_index + self._chunk_size,
                       self._total_items)
        self._render_func(self._current_index, end_index)
        self._current_index = end_index
        
    def is_complete(self) -> bool:
        """Check if rendering is complete."""
        return self._current_index >= self._total_items
