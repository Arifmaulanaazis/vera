# -*- coding: utf-8 -*-

################################################################################
## Form generated from reading UI file 'aboutUI.ui'
##
## Created by: Qt User Interface Compiler version 6.9.1
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide6.QtCore import (QCoreApplication, QDate, QDateTime, QLocale,
    QMetaObject, QObject, QPoint, QRect,
    QSize, QTime, QUrl, Qt)
from PySide6.QtGui import (QBrush, QColor, QConicalGradient, QCursor,
    QFont, QFontDatabase, QGradient, QIcon,
    QImage, QKeySequence, QLinearGradient, QPainter,
    QPalette, QPixmap, QRadialGradient, QTransform)
from PySide6.QtWidgets import (QAbstractButton, QAbstractItemView, QApplication, QCheckBox,
    QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
    QSpacerItem, QSpinBox, QTabWidget, QTextEdit,
    QVBoxLayout, QWidget, QScrollArea, QFrame)

class Ui_AboutDialog(object):
    def setupUi(self, AboutDialog):
        if not AboutDialog.objectName():
            AboutDialog.setObjectName(u"AboutDialog")
        AboutDialog.resize(700, 600)
        AboutDialog.setModal(True)
        AboutDialog.setWindowTitle("About Trion")
        
        self.verticalLayout_main = QVBoxLayout(AboutDialog)
        self.verticalLayout_main.setObjectName(u"verticalLayout_main")
        
        # Main scroll area
        self.scrollArea = QScrollArea(AboutDialog)
        self.scrollArea.setObjectName(u"scrollArea")
        self.scrollArea.setWidgetResizable(True)
        self.scrollArea.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scrollArea.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.scrollAreaWidgetContents = QWidget()
        self.scrollAreaWidgetContents.setObjectName(u"scrollAreaWidgetContents")
        self.scrollAreaWidgetContents.setGeometry(QRect(0, 0, 680, 580))
        
        self.verticalLayout_content = QVBoxLayout(self.scrollAreaWidgetContents)
        self.verticalLayout_content.setObjectName(u"verticalLayout_content")
        
        # Application Header
        self.groupBox_header = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBox_header.setObjectName(u"groupBox_header")
        self.groupBox_header.setMaximumSize(QSize(16777215, 120))
        
        self.horizontalLayout_header = QHBoxLayout(self.groupBox_header)
        self.horizontalLayout_header.setObjectName(u"horizontalLayout_header")
        
        # App Icon
        self.label_app_icon = QLabel(self.groupBox_header)
        self.label_app_icon.setObjectName(u"label_app_icon")
        self.label_app_icon.setMinimumSize(QSize(64, 64))
        self.label_app_icon.setMaximumSize(QSize(64, 64))
        self.label_app_icon.setScaledContents(True)
        
        self.horizontalLayout_header.addWidget(self.label_app_icon)
        
        # App Info
        self.verticalLayout_app_info = QVBoxLayout()
        self.verticalLayout_app_info.setObjectName(u"verticalLayout_app_info")
        
        self.label_app_name = QLabel(self.groupBox_header)
        self.label_app_name.setObjectName(u"label_app_name")
        
        self.verticalLayout_app_info.addWidget(self.label_app_name)
        
        self.label_app_version = QLabel(self.groupBox_header)
        self.label_app_version.setObjectName(u"label_app_version")
        
        self.verticalLayout_app_info.addWidget(self.label_app_version)
        
        self.label_app_description = QLabel(self.groupBox_header)
        self.label_app_description.setObjectName(u"label_app_description")
        self.label_app_description.setWordWrap(True)
        
        self.verticalLayout_app_info.addWidget(self.label_app_description)
        
        self.horizontalLayout_header.addLayout(self.verticalLayout_app_info)
        
        self.verticalLayout_content.addWidget(self.groupBox_header)
        
        # Application Details
        self.groupBox_details = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBox_details.setObjectName(u"groupBox_details")
        
        self.formLayout_details = QFormLayout(self.groupBox_details)
        self.formLayout_details.setObjectName(u"formLayout_details")
        
        # Author
        self.label_author = QLabel(self.groupBox_details)
        self.label_author.setObjectName(u"label_author")
        
        self.formLayout_details.setWidget(0, QFormLayout.ItemRole.LabelRole, self.label_author)
        
        self.label_author_value = QLabel(self.groupBox_details)
        self.label_author_value.setObjectName(u"label_author_value")
        
        self.formLayout_details.setWidget(0, QFormLayout.ItemRole.FieldRole, self.label_author_value)
        
        # Organization
        self.label_organization = QLabel(self.groupBox_details)
        self.label_organization.setObjectName(u"label_organization")
        
        self.formLayout_details.setWidget(1, QFormLayout.ItemRole.LabelRole, self.label_organization)
        
        self.label_organization_value = QLabel(self.groupBox_details)
        self.label_organization_value.setObjectName(u"label_organization_value")
        
        self.formLayout_details.setWidget(1, QFormLayout.ItemRole.FieldRole, self.label_organization_value)
        
        # Copyright
        self.label_copyright = QLabel(self.groupBox_details)
        self.label_copyright.setObjectName(u"label_copyright")
        
        self.formLayout_details.setWidget(2, QFormLayout.ItemRole.LabelRole, self.label_copyright)
        
        self.label_copyright_value = QLabel(self.groupBox_details)
        self.label_copyright_value.setObjectName(u"label_copyright_value")
        
        self.formLayout_details.setWidget(2, QFormLayout.ItemRole.FieldRole, self.label_copyright_value)
        
        # License
        self.label_license = QLabel(self.groupBox_details)
        self.label_license.setObjectName(u"label_license")
        
        self.formLayout_details.setWidget(3, QFormLayout.ItemRole.LabelRole, self.label_license)
        
        self.label_license_value = QLabel(self.groupBox_details)
        self.label_license_value.setObjectName(u"label_license_value")
        
        self.formLayout_details.setWidget(3, QFormLayout.ItemRole.FieldRole, self.label_license_value)
        
        # Website
        self.label_website = QLabel(self.groupBox_details)
        self.label_website.setObjectName(u"label_website")
        
        self.formLayout_details.setWidget(4, QFormLayout.ItemRole.LabelRole, self.label_website)
        
        self.label_website_value = QLabel(self.groupBox_details)
        self.label_website_value.setObjectName(u"label_website_value")
        self.label_website_value.setOpenExternalLinks(True)
        self.label_website_value.setTextFormat(Qt.TextFormat.RichText)
        
        self.formLayout_details.setWidget(4, QFormLayout.ItemRole.FieldRole, self.label_website_value)
        
        # Support Email
        self.label_support_email = QLabel(self.groupBox_details)
        self.label_support_email.setObjectName(u"label_support_email")
        
        self.formLayout_details.setWidget(5, QFormLayout.ItemRole.LabelRole, self.label_support_email)
        
        self.label_support_email_value = QLabel(self.groupBox_details)
        self.label_support_email_value.setObjectName(u"label_support_email_value")
        self.label_support_email_value.setOpenExternalLinks(True)
        self.label_support_email_value.setTextFormat(Qt.TextFormat.RichText)
        
        self.formLayout_details.setWidget(5, QFormLayout.ItemRole.FieldRole, self.label_support_email_value)
        
        # Repository
        self.label_repository = QLabel(self.groupBox_details)
        self.label_repository.setObjectName(u"label_repository")
        
        self.formLayout_details.setWidget(6, QFormLayout.ItemRole.LabelRole, self.label_repository)
        
        self.label_repository_value = QLabel(self.groupBox_details)
        self.label_repository_value.setObjectName(u"label_repository_value")
        self.label_repository_value.setOpenExternalLinks(True)
        self.label_repository_value.setTextFormat(Qt.TextFormat.RichText)
        
        self.formLayout_details.setWidget(6, QFormLayout.ItemRole.FieldRole, self.label_repository_value)
        
        # Issues URL
        self.label_issues_url = QLabel(self.groupBox_details)
        self.label_issues_url.setObjectName(u"label_issues_url")
        
        self.formLayout_details.setWidget(7, QFormLayout.ItemRole.LabelRole, self.label_issues_url)
        
        self.label_issues_url_value = QLabel(self.groupBox_details)
        self.label_issues_url_value.setObjectName(u"label_issues_url_value")
        self.label_issues_url_value.setOpenExternalLinks(True)
        self.label_issues_url_value.setTextFormat(Qt.TextFormat.RichText)
        
        self.formLayout_details.setWidget(7, QFormLayout.ItemRole.FieldRole, self.label_issues_url_value)
        
        self.verticalLayout_content.addWidget(self.groupBox_details)
        
        # Features Section
        self.groupBox_features = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBox_features.setObjectName(u"groupBox_features")
        
        self.verticalLayout_features = QVBoxLayout(self.groupBox_features)
        self.verticalLayout_features.setObjectName(u"verticalLayout_features")
        
        self.label_features_title = QLabel(self.groupBox_features)
        self.label_features_title.setObjectName(u"label_features_title")
        
        self.verticalLayout_features.addWidget(self.label_features_title)
        
        self.textEdit_features = QTextEdit(self.groupBox_features)
        self.textEdit_features.setObjectName(u"textEdit_features")
        self.textEdit_features.setReadOnly(True)
        self.textEdit_features.setMaximumSize(QSize(16777215, 150))
        
        self.verticalLayout_features.addWidget(self.textEdit_features)
        
        self.verticalLayout_content.addWidget(self.groupBox_features)
        
        # System Information
        self.groupBox_system_info = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBox_system_info.setObjectName(u"groupBox_system_info")
        
        self.verticalLayout_system_info = QVBoxLayout(self.groupBox_system_info)
        self.verticalLayout_system_info.setObjectName(u"verticalLayout_system_info")
        
        self.label_system_info_title = QLabel(self.groupBox_system_info)
        self.label_system_info_title.setObjectName(u"label_system_info_title")
        
        self.verticalLayout_system_info.addWidget(self.label_system_info_title)
        
        self.textEdit_system_info = QTextEdit(self.groupBox_system_info)
        self.textEdit_system_info.setObjectName(u"textEdit_system_info")
        self.textEdit_system_info.setReadOnly(True)
        self.textEdit_system_info.setMaximumSize(QSize(16777215, 120))
        
        self.verticalLayout_system_info.addWidget(self.textEdit_system_info)
        
        self.verticalLayout_content.addWidget(self.groupBox_system_info)
        
        # Library Citations
        self.groupBox_library_citations = QGroupBox(self.scrollAreaWidgetContents)
        self.groupBox_library_citations.setObjectName(u"groupBox_library_citations")
        
        self.verticalLayout_library_citations = QVBoxLayout(self.groupBox_library_citations)
        self.verticalLayout_library_citations.setObjectName(u"verticalLayout_library_citations")
        
        self.label_library_citations_title = QLabel(self.groupBox_library_citations)
        self.label_library_citations_title.setObjectName(u"label_library_citations_title")
        
        self.verticalLayout_library_citations.addWidget(self.label_library_citations_title)
        
        self.textEdit_library_citations = QTextEdit(self.groupBox_library_citations)
        self.textEdit_library_citations.setObjectName(u"textEdit_library_citations")
        self.textEdit_library_citations.setReadOnly(True)
        self.textEdit_library_citations.setMaximumSize(QSize(16777215, 300))
        
        self.verticalLayout_library_citations.addWidget(self.textEdit_library_citations)
        
        self.verticalLayout_content.addWidget(self.groupBox_library_citations)
        
        # Vertical spacer
        self.verticalSpacer = QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
        self.verticalLayout_content.addItem(self.verticalSpacer)
        
        self.scrollArea.setWidget(self.scrollAreaWidgetContents)
        self.verticalLayout_main.addWidget(self.scrollArea)
        
        # Button Layout
        self.horizontalLayout_buttons = QHBoxLayout()
        self.horizontalLayout_buttons.setObjectName(u"horizontalLayout_buttons")
        
        # Horizontal spacer
        self.horizontalSpacer = QSpacerItem(40, 20, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self.horizontalLayout_buttons.addItem(self.horizontalSpacer)
        
        # Close Button
        self.pushButton_close = QPushButton(AboutDialog)
        self.pushButton_close.setObjectName(u"pushButton_close")
        self.pushButton_close.setMinimumSize(QSize(100, 0))
        
        self.horizontalLayout_buttons.addWidget(self.pushButton_close)
        
        self.verticalLayout_main.addLayout(self.horizontalLayout_buttons)
        
        self.retranslateUi(AboutDialog)
        
        # Connect close button
        self.pushButton_close.clicked.connect(AboutDialog.accept)
        
        QMetaObject.connectSlotsByName(AboutDialog)
    
    def retranslateUi(self, AboutDialog):
        AboutDialog.setWindowTitle(QCoreApplication.translate("AboutDialog", u"About VERA", None))
        self.groupBox_header.setTitle(QCoreApplication.translate("AboutDialog", u"Application Information", None))
        self.label_app_name.setText(QCoreApplication.translate("AboutDialog", u"VERA", None))
        self.label_app_version.setText(QCoreApplication.translate("AboutDialog", u"Version 1.0.0", None))
        self.label_app_description.setText(QCoreApplication.translate("AboutDialog", u"Virtual Execution and Reaction Architecture", None))
        self.groupBox_details.setTitle(QCoreApplication.translate("AboutDialog", u"Application Details", None))
        self.label_author.setText(QCoreApplication.translate("AboutDialog", u"Author:", None))
        self.label_author_value.setText(QCoreApplication.translate("AboutDialog", u"apt. Arif Maulana Azis, S.Farm", None))
        self.label_organization.setText(QCoreApplication.translate("AboutDialog", u"Organization:", None))
        self.label_organization_value.setText(QCoreApplication.translate("AboutDialog", u"VERA", None))
        self.label_copyright.setText(QCoreApplication.translate("AboutDialog", u"Copyright:", None))
        self.label_copyright_value.setText(QCoreApplication.translate("AboutDialog", u"© 2026 VERA, All rights reserved.", None))
        self.label_license.setText(QCoreApplication.translate("AboutDialog", u"License:", None))
        self.label_license_value.setText(QCoreApplication.translate("AboutDialog", u"MIT License", None))
        self.label_website.setText(QCoreApplication.translate("AboutDialog", u"Website:", None))
        self.label_website_value.setText(QCoreApplication.translate("AboutDialog", u"<a href=\"https://vera-desktop-app.netlify.app\">https://vera-desktop-app.netlify.app</a>", None))
        self.label_support_email.setText(QCoreApplication.translate("AboutDialog", u"Support Email:", None))
        self.label_support_email_value.setText(QCoreApplication.translate("AboutDialog", u"<a href=\"mailto:titandigitalsoft@gmail.com\">titandigitalsoft@gmail.com</a>", None))
        self.label_repository.setText(QCoreApplication.translate("AboutDialog", u"Repository:", None))
        self.label_repository_value.setText(QCoreApplication.translate("AboutDialog", u"<a href=\"https://github.com/Arifmaulanaazis/Trion\">GitHub Repository</a>", None))
        self.label_issues_url.setText(QCoreApplication.translate("AboutDialog", u"Issues:", None))
        self.label_issues_url_value.setText(QCoreApplication.translate("AboutDialog", u"<a href=\"https://github.com/Arifmaulanaazis/Trion/issues\">Report Issues</a>", None))
        self.groupBox_features.setTitle(QCoreApplication.translate("AboutDialog", u"Key Features", None))
        self.label_features_title.setText(QCoreApplication.translate("AboutDialog", u"Application Features:", None))
        self.textEdit_features.setHtml(QCoreApplication.translate("AboutDialog", u"<ul><li><b>Molecular Docking:</b> Advanced molecular docking using AutoDock Vina, GPU acceleration, and comprehensive analysis tools</li><li><b>Molecular Minimization:</b> Advanced molecular minimization using RDKit and OpenBabel with conformer generation</li><li><b>Molecular Dynamics:</b> Complete GROMACS workflow from preparation to analysis with trajectory visualization</li><li><b>Chemical Visualization:</b> 2D structure drawing, 3D web viewer (NGL.js), and protein-ligand interaction visualization</li><li><b>Data Visualization:</b> Advanced plotting with histograms, scatter plots, line charts, bar charts, pie charts, and heatmaps</li><li><b>Chemical Data Collection:</b> Database access for PubChem compound search and RCSB PDB structure retrieval</li><li><b>Data Processing:</b> Advanced dataframe manipulation with filtering, sorting, merging, and column operations</li><li><b>File I/O:</b> Comprehensive support for molecular formats (SDF, MOL, MOL2, PDB, PDBQT) and data formats (CSV, Excel, JSON)</li><li><b>User Interface:</b> Intuitive drag-and-drop node-based workflow interface with real-time visualization</li><li><b>Performance:</b> GPU acceleration for computationally intensive tasks and optimized toolchains</li><li><b>Cross-platform:</b> Windows compatibility with integrated molecular modeling and analysis tools</li></ul>", None))
        self.groupBox_system_info.setTitle(QCoreApplication.translate("AboutDialog", u"System Information", None))
        self.label_system_info_title.setText(QCoreApplication.translate("AboutDialog", u"Technical Details:", None))
        self.textEdit_system_info.setHtml(QCoreApplication.translate("AboutDialog", u"<ul><li><b>Framework:</b> PySide6 (Qt6)</li><li><b>Language:</b> Python 3.13.5</li><li><b>Data Analysis:</b> NumPy, Pandas, SciPy</li><li><b>Visualization:</b> Matplotlib, Plotly</li><li><b>Machine Learning:</b> Scikit-learn</li><li><b>File Formats:</b> CSV, Excel, ARW, and more</li></ul>", None))
        self.groupBox_library_citations.setTitle(QCoreApplication.translate("AboutDialog", u"Library Citations & References", None))
        self.label_library_citations_title.setText(QCoreApplication.translate("AboutDialog", u"Third-Party Libraries Used:", None))
        self.textEdit_library_citations.setHtml(QCoreApplication.translate("AboutDialog", u"<p>Loading library information...</p>", None))
        self.pushButton_close.setText(QCoreApplication.translate("AboutDialog", u"Close", None)) 