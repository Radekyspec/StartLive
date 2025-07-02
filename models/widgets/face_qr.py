# -*- coding: utf-8 -*-

# module import

# package import
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class FaceQRWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("人脸认证")
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout()

        self.face_hint = QLabel("目标分区需要人脸认证")
        self.face_hint.setStyleSheet("color: red; font-size: 16pt;")
        self.face_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_qr = QLabel()
        self.face_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.face_hint)
        layout.addWidget(self.face_qr)
        self.setLayout(layout)
