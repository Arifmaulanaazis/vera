"""
Recent Projects Dialog for VERA
A startup dialog similar to Orange Data Mining for managing projects
"""

import os
import json
import webbrowser
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem,
    QWidget, QFrame, QScrollArea, QMessageBox,
    QFileDialog, QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, Signal, QSize, QSettings, QTimer, QPropertyAnimation, QEasingCurve, QRect, QVariantAnimation
from PySide6.QtGui import QIcon, QPixmap, QPainter, QBrush, QColor, QPen, QFont, QFontMetrics

from core.app_control import APP_INFO
from backend.resource_access import get_theme_icon_path


class CircularButton(QWidget):
    """Custom circular button with icon and label for Orange-like appearance"""
    
    clicked = Signal()  # Custom signal for click events
    
    def __init__(self, icon_path: str, label: str, parent=None):
        super().__init__(parent)
        self.label_text = label
        self.icon_path = icon_path
        self._hover = False
        self._pressed = False
        
        # Set widget size
        self.setFixedSize(100, 120)
        self.setCursor(Qt.PointingHandCursor)
        
        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(8)
        layout.setAlignment(Qt.AlignCenter)
        
        # Create icon label
        self.icon_label = QLabel()
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setFixedSize(70, 70)
        self._setup_icon()
        layout.addWidget(self.icon_label)
        
        # Create text label
        self.text_label = QLabel(label)
        self.text_label.setAlignment(Qt.AlignCenter)
        self.text_label.setWordWrap(True)
        self.text_label.setStyleSheet("""
            QLabel {
                color: #333;
                font-size: 11px;
                font-weight: 500;
                font-family: 'Segoe UI', Arial, sans-serif;
                background: transparent;
            }
        """)
        layout.addWidget(self.text_label)
        
        # Setup modern hover shadow effect
        self.shadow = QGraphicsDropShadowEffect(self)
        self.shadow.setBlurRadius(0)
        self.shadow.setOffset(0, 0)
        self.shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(self.shadow)
        
        # Smooth shadow animation for hover
        self.shadow_anim = QVariantAnimation(self)
        self.shadow_anim.setDuration(250)
        self.shadow_anim.setEasingCurve(QEasingCurve.OutQuad)
        self.shadow_anim.valueChanged.connect(self._update_shadow)
        
        # Setup widget styling
        self._update_style()
    
    def _update_shadow(self, value):
        """Update shadow blur and offset based on float value 0.0 - 1.0"""
        self.shadow.setBlurRadius(value * 20)
        self.shadow.setOffset(0, value * 6)
    
    def _setup_icon(self):
        """Setup the circular icon with proper styling"""
        size = 60
        pix = QPixmap(size, size)
        pix.fill(Qt.transparent)
        
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get color based on button type
        color = self._get_button_color()
        
        # Draw circular background
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(2, 2, size - 4, size - 4)
        
        # Try to load icon from resources
        if self.icon_path:
            icon_pix = QPixmap(self.icon_path)
            if not icon_pix.isNull():
                # Scale icon to fit
                scaled = icon_pix.scaled(36, 36, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = (size - scaled.width()) // 2
                y = (size - scaled.height()) // 2
                painter.drawPixmap(x, y, scaled)
        else:
            # Draw text if no icon
            painter.setPen(QPen(Qt.white))
            font = QFont()
            font.setPointSize(18)
            font.setBold(True)
            painter.setFont(font)
            letter = self.label_text[0].upper() if self.label_text else "?"
            painter.drawText(pix.rect(), Qt.AlignCenter, letter)
        
        painter.end()
        self.icon_label.setPixmap(pix)
    
    def _get_button_color(self) -> QColor:
        """Get button color based on label"""
        colors = {
            "New Project": QColor(52, 152, 219),      # Blue
            "Open Recent": QColor(46, 204, 113),      # Green
            "Examples": QColor(155, 89, 182),         # Purple
            "Help": QColor(241, 196, 15),             # Yellow
            "Website": QColor(231, 76, 60),           # Red
        }
        return colors.get(self.label_text, QColor(149, 165, 166))
    
    def _update_style(self):
        """Update widget styling based on state"""
        if self._pressed:
            bg_color = "rgba(0, 0, 0, 0.1)"
        elif self._hover:
            bg_color = "rgba(0, 0, 0, 0.05)"
        else:
            bg_color = "transparent"
        
        self.setStyleSheet(f"""
            CircularButton {{
                background-color: {bg_color};
                border-radius: 6px;
            }}
        """)
    
    def enterEvent(self, event):
        """Handle mouse enter"""
        self._hover = True
        self._update_style()
        self.shadow_anim.stop()
        self.shadow_anim.setStartValue(self.shadow.blurRadius() / 20.0 if self.shadow.blurRadius() else 0.0) # approx current progress
        self.shadow_anim.setEndValue(1.0)
        self.shadow_anim.start()
        super().enterEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leave"""
        self._hover = False
        self._pressed = False
        self._update_style()
        self.shadow_anim.stop()
        self.shadow_anim.setStartValue(self.shadow.blurRadius() / 20.0 if self.shadow.blurRadius() else 0.0)
        self.shadow_anim.setEndValue(0.0)
        self.shadow_anim.start()
        super().leaveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse press"""
        if event.button() == Qt.LeftButton:
            self._pressed = True
            self._update_style()
            # Compress shadow on press
            self.shadow.setBlurRadius(5)
            self.shadow.setOffset(0, 2)
        super().mousePressEvent(event)
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release"""
        if event.button() == Qt.LeftButton and self._pressed:
            self._pressed = False
            self._update_style()
            # Restore hover shadow immediately on release
            self.shadow.setBlurRadius(20)
            self.shadow.setOffset(0, 6)
            if self.rect().contains(event.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)


class ExampleSelectionDialog(QDialog):
    """Custom styled dialog for selecting example workflows"""
    
    def __init__(self, example_files, parent=None):
        super().__init__(parent)
        self.example_files = example_files
        self.selected_file = None
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the dialog UI with consistent styling"""
        self.setWindowTitle("Select Example Workflow")
        self.setFixedSize(400, 300)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Title label
        title_label = QLabel("Choose an example workflow:")
        title_label.setStyleSheet("""
            QLabel {
                color: #2c3e50;
                font-size: 16px;
                font-weight: bold;
                font-family: 'Segoe UI', Arial, sans-serif;
                margin-bottom: 10px;
                background: transparent;
            }
        """)
        main_layout.addWidget(title_label)
        
        # Example list
        self.example_list = QListWidget()
        self.example_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: #333;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #f0f0f0;
            }
            QListWidget::item:hover {
                background-color: #e3f2fd;
            }
            QListWidget::item:selected {
                background-color: #2196f3;
                color: white;
            }
        """)
        
        # Populate the list
        for file_path in self.example_files:
            item = QListWidgetItem(file_path.stem)
            item.setData(Qt.UserRole, file_path)
            self.example_list.addItem(item)
        
        # Select first item by default
        if self.example_list.count() > 0:
            self.example_list.setCurrentRow(0)
        
        # Handle double-click
        self.example_list.itemDoubleClicked.connect(self._on_item_double_clicked)
        
        main_layout.addWidget(self.example_list)
        
        # Buttons
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
                font-family: 'Segoe UI', Arial, sans-serif;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #7f8c8d;
            }
            QPushButton:pressed {
                background-color: #6c7b7d;
            }
        """)
        cancel_btn.clicked.connect(self.reject)
        
        # OK button
        ok_btn = QPushButton("Open")
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
                font-family: 'Segoe UI', Arial, sans-serif;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        ok_btn.clicked.connect(self._on_ok_clicked)
        ok_btn.setDefault(True)
        
        button_layout.addStretch()
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        
        main_layout.addLayout(button_layout)
        
        # Set dialog styling
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
        """)
    
    def _on_item_double_clicked(self, item):
        """Handle double-click on item"""
        self.selected_file = item.data(Qt.UserRole)
        self.accept()
    
    def _on_ok_clicked(self):
        """Handle OK button click"""
        current_item = self.example_list.currentItem()
        if current_item:
            self.selected_file = current_item.data(Qt.UserRole)
            self.accept()
    
    def get_selected_file(self):
        """Get the selected file path"""
        return self.selected_file


class RecentProjectsDialog(QDialog):
    """Recent projects dialog similar to Orange Data Mining"""
    
    project_selected = Signal(str)  # Emits the selected project path
    new_project_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings()
        self.recent_projects = []
        
        self._setup_ui()
        self._load_recent_projects()
        self._populate_recent_list()
        
        # Add fade-in animation
        self._setup_animation()
    
    def _setup_ui(self):
        """Setup the dialog UI"""
        self.setWindowTitle("Welcome to VERA - Virtual Execution and Reaction Architecture")
        self.setFixedSize(900, 600)
        self.setWindowFlags(Qt.Dialog | Qt.WindowCloseButtonHint)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header section with gradient
        header = QFrame()
        header.setFixedHeight(180)
        header.setStyleSheet("""
            QFrame {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #1A2980,
                    stop: 1 #26D0CE
                );
            }
        """)
        
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(40, 30, 40, 30)
        
        # Left side - text content
        left_header = QWidget()
        left_header.setStyleSheet("QWidget { background: transparent; }")
        left_header_layout = QVBoxLayout(left_header)
        left_header_layout.setContentsMargins(0, 0, 0, 0)
        
        # App title
        title = QLabel("VERA")
        title.setStyleSheet("""
            QLabel {
                color: white;
                font-size: 42px;
                font-weight: bold;
                font-family: 'Segoe UI', Arial, sans-serif;
                background: transparent;
            }
        """)
        left_header_layout.addWidget(title)
        
        # App subtitle
        subtitle = QLabel("Virtual Execution and Reaction Architecture")
        subtitle.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.9);
                font-size: 14px;
                font-style: italic;
                font-family: 'Segoe UI', Arial, sans-serif;
                background: transparent;
            }
        """)
        left_header_layout.addWidget(subtitle)
        
        # Version
        version = QLabel(f"Version {APP_INFO.get('version', '1.0.0')}")
        version.setStyleSheet("""
            QLabel {
                color: rgba(255, 255, 255, 0.7);
                font-size: 12px;
                font-family: 'Segoe UI', Arial, sans-serif;
                background: transparent;
            }
        """)
        left_header_layout.addWidget(version)
        left_header_layout.addStretch()
        
        # Right side - vera icon
        right_header = QWidget()
        right_header.setStyleSheet("QWidget { background: transparent; }")
        right_header_layout = QVBoxLayout(right_header)
        right_header_layout.setContentsMargins(0, 0, 0, 0)
        
        # VERA icon
        vera_icon = QLabel()
        vera_icon.setStyleSheet("""
            QLabel {
                background: transparent;
            }
        """)
        vera_icon_path = get_theme_icon_path("vera.png")
        if vera_icon_path:
            pixmap = QPixmap(vera_icon_path)
            if not pixmap.isNull():
                # Scale icon to fit header height while maintaining aspect ratio
                scaled_pixmap = pixmap.scaled(160, 160, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                vera_icon.setPixmap(scaled_pixmap)
                vera_icon.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                
                # Add shadow to make icon pop out perfectly from the gradient
                self.icon_shadow = QGraphicsDropShadowEffect()
                self.icon_shadow.setBlurRadius(20)
                self.icon_shadow.setOffset(0, 5)
                self.icon_shadow.setColor(QColor(0, 0, 0, 120))
                vera_icon.setGraphicsEffect(self.icon_shadow)
                
                # Setup floating animation for inner window icon
                self.float_anim = QVariantAnimation(self)
                self.float_anim.setDuration(2500)
                self.float_anim.setStartValue(5.0)  # Min offset
                self.float_anim.setEndValue(12.0)   # Max offset to simulate float
                
                def update_float(val):
                    self.icon_shadow.setOffset(0, val)
                    self.icon_shadow.setBlurRadius(15 + val * 1.5)
                    
                self.float_anim.valueChanged.connect(update_float)
                self.float_anim.setLoopCount(-1)
                self.float_anim.setDirection(QVariantAnimation.Backward)
                # Starts after fade-in
                QTimer.singleShot(500, self.float_anim.start)
        right_header_layout.addStretch()
        right_header_layout.addWidget(vera_icon)
        right_header_layout.addStretch()
        
        header_layout.addWidget(left_header, 3)
        header_layout.addWidget(right_header, 1)
        
        header_layout.addStretch()
        main_layout.addWidget(header)
        
        # Content area
        content = QWidget()
        content.setStyleSheet("""
            QWidget {
                background-color: #f5f5f5;
            }
        """)
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(40, 40, 40, 40)  # Increased margins for better centering
        content_layout.setSpacing(40)  # Increased spacing
        
        # Left side - Action buttons
        left_panel = QWidget()
        left_panel.setStyleSheet("QWidget { background: transparent; }")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(20)
        
        actions_label = QLabel("Get Started")
        actions_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #2c3e50;
                font-family: 'Segoe UI', Arial, sans-serif;
                margin-bottom: 10px;
                background: transparent;
            }
        """)
        left_layout.addWidget(actions_label)
        
        # Action buttons grid
        buttons_widget = QWidget()
        buttons_widget.setStyleSheet("QWidget { background: transparent; }")
        buttons_layout = QGridLayout(buttons_widget)
        buttons_layout.setSpacing(15)  # Reduced spacing for smaller buttons
        buttons_layout.setAlignment(Qt.AlignCenter)  # Center the grid
        
        # Create action buttons using resource system
        new_btn = CircularButton(
            get_theme_icon_path("file_input.png"),  
            "New Project"
        )
        new_btn.clicked.connect(self._on_new_project)
        
        recent_btn = CircularButton(
            get_theme_icon_path("folder_input.png"),  
            "Open Recent"
        )
        recent_btn.clicked.connect(self._on_open_recent_clicked)
        
        examples_btn = CircularButton(
            get_theme_icon_path("example.png"),  
            "Examples"
        )
        examples_btn.clicked.connect(self._on_examples)
        
        help_btn = CircularButton(
            get_theme_icon_path("help.png"),  
            "Help"
        )
        help_btn.clicked.connect(self._on_help)
        
        website_btn = CircularButton(
            get_theme_icon_path("website.png"),  
            "Website"
        )
        website_btn.clicked.connect(self._on_website)
        
        # Add buttons to grid
        buttons_layout.addWidget(new_btn, 0, 0)
        buttons_layout.addWidget(recent_btn, 0, 1)
        buttons_layout.addWidget(examples_btn, 0, 2)
        buttons_layout.addWidget(help_btn, 1, 0)
        buttons_layout.addWidget(website_btn, 1, 1)
        
        self.action_buttons = [new_btn, recent_btn, examples_btn, help_btn, website_btn]
        
        left_layout.addWidget(buttons_widget)
        left_layout.addStretch()
        
        # Right side - Recent projects list
        self.right_panel = QWidget()
        self.right_panel.setStyleSheet("""
            QWidget {
                background-color: white;
                border-radius: 8px;
            }
        """)
        
        # Add shadow effect
        self.right_panel_shadow = QGraphicsDropShadowEffect()
        self.right_panel_shadow.setBlurRadius(15)
        self.right_panel_shadow.setOffset(0, 4)
        self.right_panel_shadow.setColor(QColor(0, 0, 0, 20))
        self.right_panel.setGraphicsEffect(self.right_panel_shadow)
        
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(20, 20, 20, 20)
        right_layout.setSpacing(10)
        
        recent_label = QLabel("Recent Projects")
        recent_label.setStyleSheet("""
            QLabel {
                font-size: 16px;
                font-weight: bold;
                color: #2c3e50;
                font-family: 'Segoe UI', Arial, sans-serif;
                background: transparent;
            }
        """)
        right_layout.addWidget(recent_label)
        
        # Recent projects list
        self.recent_list = QListWidget()
        self.recent_list.setStyleSheet("""
            QListWidget {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: white;
                font-family: 'Segoe UI', Arial, sans-serif;
                font-size: 14px;
                color: #333; /* ensure visible text on light background */
            }
            QListWidget::item {
                padding: 8px;
                border-bottom: 1px solid #f0f0f0;
                color: #333;
            }
            QListWidget::item:hover {
                background-color: #e3f2fd;
                color: #333;
            }
            QListWidget::item:selected {
                background-color: #2196f3;
                color: white;
            }
        """)
        self.recent_list.itemDoubleClicked.connect(self._on_recent_item_double_clicked)
        right_layout.addWidget(self.recent_list)
        
        # Open selected button
        open_btn = QPushButton("Open Selected")
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 10px 20px;
                font-size: 14px;
                font-weight: 500;
                font-family: 'Segoe UI', Arial, sans-serif;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)
        open_btn.clicked.connect(self._on_open_selected)
        right_layout.addWidget(open_btn)
        
        # Add panels to content
        content_layout.addWidget(left_panel, 2)
        content_layout.addWidget(self.right_panel, 3)
        
        main_layout.addWidget(content)
        
        # Set window styling
        self.setStyleSheet("""
            QDialog {
                background-color: #f5f5f5;
            }
        """)
    
    def _setup_animation(self):
        """Setup fade-in and staggered entrance animations"""
        self.setWindowOpacity(0)
        
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(400)
        self.fade_anim.setStartValue(0.0)
        self.fade_anim.setEndValue(1.0)
        self.fade_anim.setEasingCurve(QEasingCurve.OutQuad)
        
        QTimer.singleShot(50, self.fade_anim.start)
    
    def _load_recent_projects(self):
        """Load recent projects from AppData"""
        try:
            # Get AppData path
            appdata_path = Path(os.getenv('APPDATA')) / 'VERA'
            appdata_path.mkdir(parents=True, exist_ok=True)
            
            recent_file = appdata_path / 'recent_projects.json'
            
            if recent_file.exists():
                with open(recent_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.recent_projects = data.get('projects', [])
                    # Keep only existing files
                    self.recent_projects = [p for p in self.recent_projects if Path(p['path']).exists()]
                    # Limit to 10 most recent
                    self.recent_projects = self.recent_projects[:10]
        except Exception as e:
            print(f"Error loading recent projects: {e}")
            self.recent_projects = []
    
    def _save_recent_projects(self):
        """Save recent projects to AppData"""
        try:
            appdata_path = Path(os.getenv('APPDATA')) / 'VERA'
            appdata_path.mkdir(parents=True, exist_ok=True)
            
            recent_file = appdata_path / 'recent_projects.json'
            
            with open(recent_file, 'w', encoding='utf-8') as f:
                json.dump({'projects': self.recent_projects}, f, indent=2)
        except Exception as e:
            print(f"Error saving recent projects: {e}")
    
    def add_recent_project(self, path: str):
        """Add a project to recent projects list"""
        try:
            # Remove if already exists
            self.recent_projects = [p for p in self.recent_projects if p['path'] != path]
            
            # Add to beginning
            project_data = {
                'path': path,
                'name': Path(path).stem,
                'last_opened': datetime.now().isoformat()
            }
            self.recent_projects.insert(0, project_data)
            
            # Limit to 10
            self.recent_projects = self.recent_projects[:10]
            
            # Save
            self._save_recent_projects()
        except Exception as e:
            print(f"Error adding recent project: {e}")
    
    def _populate_recent_list(self):
        """Populate the recent projects list widget"""
        self.recent_list.clear()
        
        for project in self.recent_projects:
            try:
                path = Path(project['path'])
                item = QListWidgetItem()
                
                # Format display text
                name = path.stem
                folder = path.parent.name
                
                item.setText(f"{name}\n{path}")
                item.setData(Qt.UserRole, project['path'])
                
                # Set tooltip
                last_opened = project.get('last_opened', '')
                if last_opened:
                    try:
                        dt = datetime.fromisoformat(last_opened)
                        last_opened = dt.strftime("%Y-%m-%d %H:%M")
                        item.setToolTip(f"Path: {path}\nLast opened: {last_opened}")
                    except:
                        item.setToolTip(f"Path: {path}")
                
                self.recent_list.addItem(item)
            except Exception as e:
                print(f"Error adding recent item: {e}")
    
    def _on_new_project(self):
        """Handle new project button click"""
        self.new_project_requested.emit()
        self.accept()
    
    def _on_open_recent_clicked(self):
        """Handle open recent button click - open file dialog"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Workflow",
            "",
            "VERA Workflow Files (*.vsw);;All Files (*.*)"
        )
        
        if file_path:
            self.add_recent_project(file_path)
            self.project_selected.emit(file_path)
            self.accept()
    
    def _on_examples(self):
        """Handle examples button click"""
        try:
            # Get example files
            example_dir = Path(__file__).parent.parent / "example"
            if example_dir.exists():
                example_files = list(example_dir.glob("*.vsw"))
                
                if example_files:
                    # Show custom styled selection dialog
                    dialog = ExampleSelectionDialog(example_files, self)
                    if dialog.exec_() == QDialog.Accepted:
                        selected_file = dialog.get_selected_file()
                        if selected_file:
                            self.project_selected.emit(str(selected_file))
                            self.accept()
                else:
                    QMessageBox.information(self, "No Examples", "No example workflows found.")
            else:
                QMessageBox.warning(self, "Examples Not Found", "Example directory not found.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading examples: {e}")
    
    def _on_help(self):
        """Handle help button click"""
        try:
            doc_url = APP_INFO.get("documentation_url", "")
            if doc_url:
                webbrowser.open(doc_url)
            else:
                QMessageBox.information(self, "Help", "Documentation URL not configured.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error opening documentation: {e}")
    
    def _on_website(self):
        """Handle website button click"""
        try:
            website_url = APP_INFO.get("website", "")
            if website_url:
                webbrowser.open(website_url)
            else:
                QMessageBox.information(self, "Website", "Website URL not configured.")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error opening website: {e}")
    
    def _on_recent_item_double_clicked(self, item):
        """Handle double click on recent item"""
        path = item.data(Qt.UserRole)
        if path and Path(path).exists():
            self.project_selected.emit(path)
            self.accept()
    
    def _on_open_selected(self):
        """Handle open selected button click"""
        current_item = self.recent_list.currentItem()
        if current_item:
            path = current_item.data(Qt.UserRole)
            if path and Path(path).exists():
                self.project_selected.emit(path)
                self.accept()
            else:
                QMessageBox.warning(self, "File Not Found", f"The selected file no longer exists:\n{path}")
