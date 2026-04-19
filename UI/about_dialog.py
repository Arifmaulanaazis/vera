"""
About Dialog module for VERA - Virtual Execution and Reaction Architecture.

This module contains the AboutDialog class which displays application information,
features, and system details in a modal dialog.
"""

import sys
from pathlib import Path
import platform
from datetime import datetime
from PySide6.QtWidgets import QDialog, QVBoxLayout
from PySide6.QtGui import QPixmap, QIcon, QMovie
from PySide6.QtCore import Qt, QByteArray, QBuffer, QIODevice, QSize

from UI.aboutUI import Ui_AboutDialog
from core.app_control import APP_INFO

class AboutDialog(QDialog):
    """
    About dialog for displaying application information.
    
    This dialog shows comprehensive information about the VERA Application
    including version, author, features, and system information.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the About dialog.
        
        Args:
            parent: Parent widget (main window)
        """
        super().__init__(parent)
        
        # Setup UI
        self.ui = Ui_AboutDialog()
        self.ui.setupUi(self)
        
        # Set window icon
        try:
            from backend.resource_access import get_theme_icon_path
            icon_path = get_theme_icon_path("vera.ico")
            if icon_path:
                self.setWindowIcon(QIcon(icon_path))
        except ImportError:
            # Fallback to original method
            icon_path = Path(__file__).parent / "theme" / "icons" / "vera.ico"
            if icon_path.exists():
                self.setWindowIcon(QIcon(str(icon_path)))
        
        # Populate with application information
        self.populate_app_info()
        
        # Set modal behavior
        self.setModal(True)
        
        # Center the dialog on parent
        if parent:
            self.center_on_parent(parent)
    
    def populate_app_info(self):
        """
        Populate the dialog with application information from APP_INFO.
        """
        try:
            # Set animated application icon (GIF) from base64
            self._icon_gif_movie = None
            self._icon_gif_buffer = None

            try:
                from backend.resource_access import get_theme_icon_path
                icon_path = get_theme_icon_path("vera-icon.png")
                if icon_path:
                    pixmap = QPixmap(icon_path)
                    if pixmap:
                        self.ui.label_app_icon.setPixmap(pixmap)
                else:
                    # Fallback to original method
                    icon_path = Path(__file__).parent / "theme" / "icons" / "vera-icon.png"
                    if icon_path.exists():
                        pixmap = QPixmap(icon_path)
                        if pixmap:
                            self.ui.label_app_icon.setPixmap(pixmap)
            except Exception:
                pass
            
            # Update application information
            self.ui.label_app_name.setText(APP_INFO.get('full_name', 'VERA'))
            self.ui.label_app_version.setText(f"Version {APP_INFO.get('version', '1.0.0')}")
            self.ui.label_app_description.setText(APP_INFO.get('description', 'Virtual Execution and Reaction Architecture'))
            
            # Update details
            self.ui.label_author_value.setText(APP_INFO.get('author', 'apt. Arif Maulana Azis, S.Farm'))
            self.ui.label_organization_value.setText(APP_INFO.get('organization', 'VERA'))
            self.ui.label_copyright_value.setText(APP_INFO.get('copyright', f'© {datetime.now().year} VERA, All rights reserved.'))
            self.ui.label_license_value.setText(APP_INFO.get('license', 'MIT License'))
            
            # Update links
            website_url = APP_INFO.get('website', 'https://vera-desktop-app.netlify.app')
            self.ui.label_website_value.setText(f'<a href="{website_url}">{website_url}</a>')
            
            support_email = APP_INFO.get('support_email', 'titandigitalsoft@gmail.com')
            self.ui.label_support_email_value.setText(f'<a href="mailto:{support_email}">{support_email}</a>')
            
            repository_url = APP_INFO.get('repository', 'https://github.com/Arifmaulanaazis/vera')
            self.ui.label_repository_value.setText(f'<a href="{repository_url}">GitHub Repository</a>')
            
            issues_url = APP_INFO.get('issues_url', 'https://github.com/Arifmaulanaazis/vera/issues')
            self.ui.label_issues_url_value.setText(f'<a href="{issues_url}">Report Issues</a>')
            
            # Update features section
            self.populate_features()
            
            # Update system information
            self.populate_system_info()
            
            # Update library citations
            self.populate_library_citations()
            
        except Exception as e:
            # Fallback to default values if there's an error
            print(f"Error populating app info: {str(e)}")
    
    def populate_features(self):
        """
        Populate the features section with application features from APP_INFO.
        """
        try:
            features = APP_INFO.get('features', [])
            if features:
                features_html = "<ul>"
                for feature in features:
                    features_html += f"<li>{feature}</li>"
                features_html += "</ul>"
                self.ui.textEdit_features.setHtml(features_html)
            else:
                # Fallback features
                fallback_features = """
                <ul>
                    <li><b>Molecular Docking:</b> Advanced molecular docking using AutoDock Vina, GPU acceleration, and comprehensive analysis tools</li>
                    <li><b>Molecular Minimization:</b> Advanced molecular minimization using RDKit and OpenBabel with conformer generation</li>
                    <li><b>Molecular Dynamics:</b> Complete GROMACS workflow from preparation to analysis with trajectory visualization</li>
                    <li><b>Chemical Visualization:</b> 2D structure drawing, 3D web viewer (NGL.js), and protein-ligand interaction visualization</li>
                    <li><b>Data Visualization:</b> Advanced plotting with histograms, scatter plots, line charts, bar charts, pie charts, and heatmaps</li>
                    <li><b>Chemical Data Collection:</b> Database access for PubChem compound search and RCSB PDB structure retrieval</li>
                    <li><b>Data Processing:</b> Advanced dataframe manipulation with filtering, sorting, merging, and column operations</li>
                    <li><b>File I/O:</b> Comprehensive support for molecular formats (SDF, MOL, MOL2, PDB, PDBQT) and data formats (CSV, Excel, JSON)</li>
                    <li><b>User Interface:</b> Intuitive drag-and-drop node-based workflow interface with real-time visualization</li>
                    <li><b>Performance:</b> GPU acceleration for computationally intensive tasks and optimized toolchains</li>
                    <li><b>Cross-platform:</b> Windows compatibility with integrated molecular modeling and analysis tools</li>
                </ul>
                """
                self.ui.textEdit_features.setHtml(fallback_features)
                
        except Exception as e:
            print(f"Error populating features: {str(e)}")
    
    def populate_system_info(self):
        """
        Populate system information section with current system details.
        """
        try:
            system_info = []
            
            # Python version
            python_version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            system_info.append(f"<b>Python:</b> {python_version}")
            
            # Platform information
            platform_info = platform.platform()
            system_info.append(f"<b>Platform:</b> {platform_info}")
            
            # Architecture
            architecture = platform.architecture()[0]
            system_info.append(f"<b>Architecture:</b> {architecture}")
            
            # Machine
            machine = platform.machine()
            system_info.append(f"<b>Machine:</b> {machine}")
            
            # Processor
            processor = platform.processor()
            if processor:
                system_info.append(f"<b>Processor:</b> {processor}")
            
            # Qt version (if available)
            try:
                from PySide6.QtCore import QT_VERSION_STR
                system_info.append(f"<b>Qt Version:</b> {QT_VERSION_STR}")
            except ImportError:
                pass
            
            # Format as HTML list
            system_info_html = "<ul>"
            for info in system_info:
                system_info_html += f"<li>{info}</li>"
            system_info_html += "</ul>"
            
            self.ui.textEdit_system_info.setHtml(system_info_html)
            
        except Exception as e:
            # Fallback to basic information
            fallback_info = """
            <ul>
                <li><b>Python:</b> {python_version}</li>
                <li><b>Platform:</b> {platform}</li>
                <li><b>Architecture:</b> {architecture}</li>
                <li><b>Machine:</b> {machine}</li>
            </ul>
            """.format(
                python_version=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                platform=platform.platform(),
                architecture=platform.architecture()[0],
                machine=platform.machine()
            )
            self.ui.textEdit_system_info.setHtml(fallback_info)
    
    def populate_library_citations(self):
        """
        Populate library citations section with detailed library information.
        """
        try:
            libraries = APP_INFO.get('libraries', {})
            if not libraries:
                self.ui.textEdit_library_citations.setHtml("<p>No library information available.</p>")
                return
            
            citations_html = "<div style='font-size: 10pt;'>"
            
            # GUI Framework
            if 'gui_framework' in libraries:
                citations_html += "<h4>GUI Framework</h4>"
                for lib_name, lib_info in libraries['gui_framework'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)
            
            # Data Analysis
            if 'data_analysis' in libraries:
                citations_html += "<h4>Data Analysis</h4>"
                for lib_name, lib_info in libraries['data_analysis'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)

            # Cheminformatics and Bioinformatics
            if 'cheminformatics_bioinformatics' in libraries:
                citations_html += "<h4>Cheminformatics and Bioinformatics</h4>"
                for lib_name, lib_info in libraries['cheminformatics_bioinformatics'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)
            
            # Visualization
            if 'visualization' in libraries:
                citations_html += "<h4>Visualization</h4>"
                for lib_name, lib_info in libraries['visualization'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)

            # Networking
            if 'networking' in libraries:
                citations_html += "<h4>Networking</h4>"
                for lib_name, lib_info in libraries['networking'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)
            
            # Graphics Acceleration
            if 'graphics_acceleration' in libraries:
                citations_html += "<h4>Graphics Acceleration</h4>"
                for lib_name, lib_info in libraries['graphics_acceleration'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)
            
            # Utilities
            if 'utilities' in libraries:
                citations_html += "<h4>Utilities</h4>"
                for lib_name, lib_info in libraries['utilities'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)

            # Machine Learning
            if 'machine_learning' in libraries:
                citations_html += "<h4>Machine Learning</h4>"
                for lib_name, lib_info in libraries['machine_learning'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)

            # Third Party Apps
            if 'third_party_apps' in libraries:
                citations_html += "<h4>Third Party Apps</h4>"
                for lib_name, lib_info in libraries['third_party_apps'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)

            # Building and Packaging
            if 'build_packaging' in libraries:
                citations_html += "<h4>Building and Packaging</h4>"
                for lib_name, lib_info in libraries['build_packaging'].items():
                    citations_html += self._format_library_citation(lib_name, lib_info)
            
            citations_html += "</div>"
            self.ui.textEdit_library_citations.setHtml(citations_html)
            
        except Exception as e:
            self.ui.textEdit_library_citations.setHtml(f"<p>Error loading library citations: {str(e)}</p>")
    
    def _format_library_citation(self, lib_name, lib_info):
        """
        Format individual library citation with links and information.
        
        Args:
            lib_name (str): Library name
            lib_info (dict): Library information
            
        Returns:
            str: Formatted HTML citation
        """
        citation = f"<div style='margin-bottom: 10px; padding: 5px; border-left: 3px solid #007acc;'>"
        citation += f"<strong>{lib_name.title()} v{lib_info.get('version', 'Unknown')}</strong><br>"
        citation += f"<em>{lib_info.get('description', 'No description available')}</em><br>"
        
        # Add links
        links = []
        if 'website' in lib_info:
            links.append(f"<a href='{lib_info['website']}' style='color: #007acc;'>Website</a>")
        if 'pypi' in lib_info:
            links.append(f"<a href='{lib_info['pypi']}' style='color: #007acc;'>PyPI</a>")
        
        if links:
            citation += f"Links: {' | '.join(links)}<br>"
        
        citation += f"License: {lib_info.get('license', 'Unknown')}"
        citation += "</div>"
        
        return citation
    
    def center_on_parent(self, parent):
        """
        Center the dialog on its parent window.
        
        Args:
            parent: Parent widget to center on
        """
        try:
            # Get parent geometry
            parent_geometry = parent.geometry()
            parent_center = parent_geometry.center()
            
            # Get dialog geometry
            dialog_geometry = self.geometry()
            
            # Calculate new position
            new_x = parent_center.x() - dialog_geometry.width() // 2
            new_y = parent_center.y() - dialog_geometry.height() // 2
            
            # Move dialog
            self.move(new_x, new_y)
            
        except Exception as e:
            # If centering fails, just use default positioning
            print(f"Error centering dialog: {str(e)}")
    
    def show_about_dialog(self):
        """
        Show the about dialog.
        
        Returns:
            int: Dialog result (QDialog.Accepted or QDialog.Rejected)
        """
        return self.exec_() 

