# -*- coding: utf-8 -*-

# module import

# package import
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from models.workers import FaceAuthWorker


class FaceQRWidget(QWidget):
    def __init__(self, worker: FaceAuthWorker, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setWindowTitle("人脸认证")
        self.worker = worker
        self.setWindowFlags(
            Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        layout = QVBoxLayout()

        self.face_hint = QLabel("目标分区需要人脸认证")
        self.face_hint.setStyleSheet("color: red; font-size: 16pt;")
        self.face_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.face_qr = QLabel()
        self.face_qr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.face_hint)
        layout.addWidget(self.face_qr)
        self.setLayout(layout)

    def closeEvent(self, event):
        self.worker.stop()
        event.accept()
