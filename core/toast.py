"""
Toast overlay and toast message widgets for top-center in-app notifications.

Features:
- Multiple stacked toasts (top-center)
- Customizable title, message, status, duration, and closable option
- Auto-dismiss after duration; persistent if duration <= 0 and closable

Usage:
- Create a ToastOverlay(parent=canvas.viewport()) and keep it resized to the viewport
- Call show_toast(title, message, status, duration_ms, closable)
"""

from typing import Optional

from PySide6.QtCore import Qt, QTimer, QSize, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtWidgets import (
	QWidget,
	QFrame,
	QVBoxLayout,
	QHBoxLayout,
	QLabel,
	QToolButton,
	QSizePolicy,
	QGraphicsDropShadowEffect,
)


def _status_colors(status: str) -> tuple[str, str]:
	"""Return (background, border) colors for a given status name."""
	s = (status or "").strip().lower()
	if s in ("error", "danger", "failed", "fail"):
		return ("#2a1215", "#ff4d4f")
	if s in ("success", "completed", "complete", "done"):
		return ("#102a14", "#52c41a")
	if s in ("warning", "warn"):
		return ("#2b2111", "#faad14")
	if s in ("paused", "pause"):
		return ("#2a250f", "#f0c800")
	if s in ("info", "general", "running", "progress"):
		return ("#0f1f2a", "#1890ff")
	# default neutral
	return ("#1f1f1f", "#8c8c8c")


class ToastMessage(QFrame):
	"""Single toast message widget with optional close button and auto-dismiss timer."""

	def __init__(
		self,
		title: str,
		message: str = "",
		status: str = "info",
		duration_ms: int = 3000,
		closable: bool = True,
		parent: Optional[QWidget] = None,
	):
		super().__init__(parent)
		self._duration_ms = max(0, int(duration_ms))
		self._closable = bool(closable)
		self._status = str(status or "info")
		self._timer: Optional[QTimer] = None
		self._exiting: bool = False
		self._is_inserting: bool = True
		self._end_height: int = 0

		self.setObjectName("ToastMessage")
		self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
		self.setAttribute(Qt.WA_StyledBackground, True)
		self.setFrameShape(QFrame.StyledPanel)
		self.setFrameShadow(QFrame.Raised)
		# Limit max width so it doesn't span too wide
		try:
			self.setMinimumWidth(260)
			self.setMaximumWidth(520)
		except Exception:
			pass

		# Shadow
		shadow = QGraphicsDropShadowEffect(self)
		shadow.setBlurRadius(24)
		shadow.setOffset(0, 6)
		shadow.setColor(Qt.black)
		self.setGraphicsEffect(shadow)

		# Layout
		root = QHBoxLayout(self)
		root.setContentsMargins(14, 10, 14, 10)
		root.setSpacing(10)

		# Content
		content = QVBoxLayout()
		content.setContentsMargins(0, 0, 0, 0)
		content.setSpacing(2)

		self._title_lbl = QLabel(str(title or ""))
		self._title_lbl.setObjectName("ToastTitle")
		self._title_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
		content.addWidget(self._title_lbl)

		msg_text = str(message or "")
		if msg_text:
			self._msg_lbl = QLabel(msg_text)
			self._msg_lbl.setObjectName("ToastBody")
			self._msg_lbl.setWordWrap(True)
			self._msg_lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
			try:
				self._msg_lbl.setMaximumWidth(480)
			except Exception:
				pass
			content.addWidget(self._msg_lbl)
		else:
			self._msg_lbl = None  # type: ignore[assignment]

		root.addLayout(content, 1)

		# Close button
		self._close_btn = QToolButton(self)
		self._close_btn.setObjectName("ToastClose")
		self._close_btn.setText("✖")
		self._close_btn.setAutoRaise(True)
		self._close_btn.setCursor(Qt.PointingHandCursor)
		self._close_btn.setVisible(self._closable)
		self._close_btn.clicked.connect(self._on_close)
		root.addWidget(self._close_btn, 0, Qt.AlignTop)

		# Style
		bg, border = _status_colors(self._status)
		self.setStyleSheet(
			f"""
			QFrame#ToastMessage {{
				background-color: {bg};
				border: 1px solid {border};
				border-radius: 10px;
				color: #eaeaea;
			}}
			QLabel#ToastTitle {{
				font-weight: 600;
				color: #ffffff;
				background: transparent;
			}}
			QLabel#ToastBody {{
				color: #e0e0e0;
				background: transparent;
			}}
			QToolButton#ToastClose {{
				color: #cccccc;
				padding: 2px 6px;
				border: none;
				background: transparent;
			}}
			QToolButton#ToastClose:hover {{ color: #ffffff; }}
			"""
		)

		# Auto-dismiss timer logic
		# If duration <= 0 and not closable, fallback to a sane default
		if self._duration_ms <= 0 and not self._closable:
			self._duration_ms = 2500
		if self._duration_ms > 0:
			self._timer = QTimer(self)
			self._timer.setSingleShot(True)
			self._timer.timeout.connect(self._on_timeout)
			self._timer.start(self._duration_ms)

		# Slide+fade-in animation
		try:
			self.setWindowOpacity(0.0)
			self.adjustSize()
			end_h = max(1, int(self.sizeHint().height()))
			self._end_height = end_h
			self.setMaximumHeight(1)
			# Expand height
			self._in_expand = QPropertyAnimation(self, b"maximumHeight")
			self._in_expand.setDuration(190)
			self._in_expand.setStartValue(1)
			self._in_expand.setEndValue(end_h)
			self._in_expand.setEasingCurve(QEasingCurve.OutCubic)
			# Fade
			self._in_fade = QPropertyAnimation(self, b"windowOpacity")
			self._in_fade.setDuration(220)
			self._in_fade.setStartValue(0.0)
			self._in_fade.setEndValue(1.0)
			self._in_fade.setEasingCurve(QEasingCurve.OutCubic)
			# Kick off
			ov = self.parentWidget()
			def _on_insert_finished() -> None:
				self._is_inserting = False
				if hasattr(ov, "_reflow"):
					ov._reflow()  # type: ignore[arg-type]
			self._in_expand.finished.connect(_on_insert_finished)
			self._in_expand.start(QPropertyAnimation.DeleteWhenStopped)
			self._in_fade.start(QPropertyAnimation.DeleteWhenStopped)
		except Exception:
			pass

	def end_height(self) -> int:
		"""Return the target height the insert animation expands to."""
		return max(1, int(self._end_height or 0))

	def is_inserting(self) -> bool:
		"""Whether the toast is currently in its insert animation phase."""
		return bool(self._is_inserting)

	def _start_exit_animation(self) -> None:
		if self._exiting:
			return
		self._exiting = True
		try:
			# Fade out first, then shrink
			self._out_fade = QPropertyAnimation(self, b"windowOpacity")
			self._out_fade.setDuration(180)
			self._out_fade.setStartValue(max(0.0, float(self.windowOpacity())))
			self._out_fade.setEndValue(0.0)
			self._out_fade.setEasingCurve(QEasingCurve.InCubic)
			self._out_shrink = QPropertyAnimation(self, b"maximumHeight")
			self._out_shrink.setDuration(200)
			self._out_shrink.setStartValue(max(1, self.height()))
			self._out_shrink.setEndValue(0)
			self._out_shrink.setEasingCurve(QEasingCurve.InCubic)
			def _finish():
				self._detach_from_overlay()
				self.deleteLater()
			self._out_shrink.finished.connect(_finish)
			self._out_fade.start(QPropertyAnimation.DeleteWhenStopped)
			self._out_shrink.start(QPropertyAnimation.DeleteWhenStopped)
		except Exception:
			# Fallback if animation fails
			self._detach_from_overlay()
			self.deleteLater()

	def _detach_from_overlay(self) -> None:
		parent = self.parentWidget()
		if parent is None:
			return
		lay = parent.layout()
		if lay is not None:
			for i in range(lay.count()):
				item = lay.itemAt(i)
				if item and item.widget() is self:
					lay.takeAt(i)
					break
			self.setParent(None)
			try:
				# Ask overlay to reflow
				if hasattr(parent, "_reflow"):
					parent._reflow()
			except Exception:
				pass

	def _on_timeout(self) -> None:
		self._start_exit_animation()

	def _on_close(self) -> None:
		self._start_exit_animation()

	def sizeHint(self) -> QSize:  # pragma: no cover - trivial
		return QSize(400, 64)


class ToastOverlay(QWidget):
	"""Overlay container that stacks toast messages at the top-center of its parent."""

	def __init__(self, parent: Optional[QWidget] = None):
		super().__init__(parent)
		self.setObjectName("ToastOverlay")
		self.setAttribute(Qt.WA_TranslucentBackground, True)
		self.setWindowFlags(Qt.Widget | Qt.FramelessWindowHint)
		self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

		self._layout = QVBoxLayout(self)
		self._layout.setContentsMargins(0, 12, 0, 0)  # top margin
		self._layout.setSpacing(8)
		self._layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)

		# Limit concurrent toasts
		self._max_toasts = 3

		# Styling (transparent background)
		self.setStyleSheet(
			"""
			QWidget#ToastOverlay { background: transparent; }
			"""
		)

		# Start hidden until first toast
		self.hide()

	def _predict_content_height(self) -> int:
		"""Predict content height using end heights for inserting toasts to avoid relayout during insert."""
		count = self._layout.count()
		if count <= 0:
			return 0
		try:
			spacing = max(0, int(self._layout.spacing()))
		except Exception:
			spacing = 0
		total = 0
		for i in range(count):
			item = self._layout.itemAt(i)
			w = item.widget() if item is not None else None
			if w is None:
				continue
			try:
				if isinstance(w, ToastMessage) and w.is_inserting():
					h = w.end_height()
				else:
					h = max(1, int(w.height()))
			except Exception:
				h = max(1, int(getattr(w, "height", lambda: 1)()))
			total += h
		# add inter-item spacing
		total += spacing * max(0, count - 1)
		# top margin of overlay layout (12)
		return max(1, total + 12)

	def _reflow(self) -> None:
		"""Resize overlay to content height and full parent width, hide when empty."""
		parent = self.parentWidget()
		if parent is None:
			return
		count = self._layout.count()
		if count <= 0:
			self.hide()
			return
		try:
			# Ensure the layout recalculates with current children's constraints
			self._layout.activate()
		except Exception:
			pass
		# Width spans entire viewport; height enough for stacked toasts + margin
		try:
			ph = parent.height()
		except Exception:
			ph = 0
		predicted_h = 0
		try:
			predicted_h = self._predict_content_height()
		except Exception:
			predicted_h = 0
		layout_h = 0
		try:
			layout_h = max(1, int(self._layout.sizeHint().height()) + 12)
		except Exception:
			layout_h = 0
		content_h = max(predicted_h, layout_h)
		height = min(content_h, max(ph, content_h) if ph > 0 else content_h)
		self.setGeometry(0, 0, parent.width(), height)
		self.show()
		try:
			self.raise_()
			self.update()
		except Exception:
			pass

	def show_toast(
		self,
		title: str,
		message: str = "",
		status: str = "info",
		duration_ms: int = 3000,
		closable: bool = True,
	) -> ToastMessage:
		"""Create and display a toast message."""
		# Remove oldest if exceeding capacity
		while self._layout.count() >= self._max_toasts:
			item = self._layout.takeAt(0)
			w = item.widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()

		toast = ToastMessage(title=title, message=message, status=status, duration_ms=duration_ms, closable=closable, parent=self)
		self._layout.addWidget(toast)
		self._reflow()
		return toast

	def clear_all(self) -> None:
		"""Remove all active toasts."""
		while self._layout.count() > 0:
			item = self._layout.takeAt(0)
			w = item.widget()
			if w is not None:
				w.setParent(None)
				w.deleteLater()
		self._reflow()


