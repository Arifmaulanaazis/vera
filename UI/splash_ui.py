# -*- coding: utf-8 -*-

"""
Form converted from UI file 'splash.ui'

Created by: hand conversion compatible with PySide6

WARNING! Changes in UI XML won't reflect here automatically.
Regenerate if you update 'splash.ui'.
"""

from PySide6.QtCore import (QCoreApplication, QMetaObject, QObject, QRect, QSize, Qt)
from PySide6.QtGui import (QIcon, QPixmap)
from PySide6.QtWidgets import (QApplication, QDialog, QLabel, QProgressBar, QSpacerItem, QVBoxLayout, QSizePolicy, QFrame, QHBoxLayout)


class Ui_SplashDialog(object):
    def setupUi(self, SplashRoot):
        if not SplashRoot.objectName():
            SplashRoot.setObjectName(u"SplashRoot")
        SplashRoot.resize(700, 400)
        
        # Main layout - no margins for full coverage
        self.mainLayout = QVBoxLayout(SplashRoot)
        self.mainLayout.setObjectName(u"mainLayout")
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.mainLayout.setSpacing(0)
        
        # Top frame for image
        self.imageFrame = QFrame(SplashRoot)
        self.imageFrame.setObjectName(u"imageFrame")
        self.imageFrame.setFixedHeight(300)  # 300px for image
        
        # Image frame layout
        self.imageLayout = QVBoxLayout(self.imageFrame)
        self.imageLayout.setObjectName(u"imageLayout")
        self.imageLayout.setContentsMargins(40, 30, 40, 20)
        self.imageLayout.setSpacing(5)
        
        # Logo image label
        self.labelLogo = QLabel(self.imageFrame)
        self.labelLogo.setObjectName(u"labelLogo")
        self.labelLogo.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.labelLogo.setScaledContents(False)
        self.labelLogo.setMinimumHeight(200)  # Reserve more space for larger logo
        self.labelLogo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.imageLayout.addWidget(self.labelLogo)
        
        # App name and subtitle in image frame
        self.labelAppName = QLabel(self.imageFrame)
        self.labelAppName.setObjectName(u"labelAppName")
        self.labelAppName.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.labelAppName.setWordWrap(False)
        self.imageLayout.addWidget(self.labelAppName)

        self.labelStatus = QLabel(self.imageFrame)
        self.labelStatus.setObjectName(u"labelStatus")
        self.labelStatus.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.imageLayout.addWidget(self.labelStatus)
        
        self.mainLayout.addWidget(self.imageFrame)
        
        # Bottom frame for progress (white background)
        self.progressFrame = QFrame(SplashRoot)
        self.progressFrame.setObjectName(u"progressFrame")
        self.progressFrame.setFixedHeight(100)  # 100px for progress area
        
        # Progress frame layout
        self.progressLayout = QVBoxLayout(self.progressFrame)
        self.progressLayout.setObjectName(u"progressLayout")
        self.progressLayout.setContentsMargins(40, 20, 40, 20)
        self.progressLayout.setSpacing(10)
        
        # Progress bar
        self.progressBar = QProgressBar(self.progressFrame)
        self.progressBar.setObjectName(u"progressBar")
        self.progressBar.setMinimum(0)
        self.progressBar.setMaximum(100)
        self.progressBar.setValue(0)
        self.progressBar.setTextVisible(True)
        self.progressBar.setFormat("")
        self.progressLayout.addWidget(self.progressBar)

        # Version label in progress frame
        self.labelVersion = QLabel(self.progressFrame)
        self.labelVersion.setObjectName(u"labelVersion")
        self.labelVersion.setAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
        self.progressLayout.addWidget(self.labelVersion)
        
        self.mainLayout.addWidget(self.progressFrame)

        self.retranslateUi(SplashRoot)
        QMetaObject.connectSlotsByName(SplashRoot)

    def retranslateUi(self, SplashRoot):
        SplashRoot.setWindowTitle(QCoreApplication.translate("SplashDialog", u"VERA Loading", None))
        self.labelAppName.setText(QCoreApplication.translate("SplashDialog", u"VERA", None))
        self.labelStatus.setText(QCoreApplication.translate("SplashDialog", u"Loading…", None))
        self.labelVersion.setText(QCoreApplication.translate("SplashDialog", u"Version", None))


