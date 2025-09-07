from functools import partial

from PIL.ImageQt import toqpixmap
from PySide6.QtCore import (
    Qt, QBuffer, QByteArray, QIODevice,
)
from PySide6.QtWidgets import (
    QWidget, QPushButton, QFileDialog,
    QGridLayout, QLabel,
)

from models.widgets import CropLabel
from models.workers import CoverUploadWorker


class CoverCropWidget(QWidget):
    def __init__(self, parent_window: "StreamConfigPanel", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parent_window = parent_window
        self.setWindowTitle("直播封面选框")
        self.setFixedSize(660, 560)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.label = CropLabel((16, 9), self)

        btn_load = QPushButton("更换封面")
        btn_load.clicked.connect(self.load_image)

        text_hint = QLabel("封面选区操作：\n"
                           "拖拽鼠标：新建选区\n"
                           "拖动选区：调整位置\n"
                           "双击选区：最大化并应用当前区域\n"
                           "双击角点：放大并与图片角对齐\n"
                           "右键：取消当前选区")
        text_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text_hint.setStyleSheet("font-size: 12pt")

        self.btn_upload = QPushButton("保存封面")
        self.btn_upload.clicked.connect(self.save_crop)

        layout = QGridLayout(self)
        layout.addWidget(self.label, 0, 0, 1, 2)
        layout.addWidget(text_hint, 1, 0, 1, 2)
        layout.addWidget(btn_load, 2, 0, 1, 1)
        layout.addWidget(self.btn_upload, 2, 1, 1, 1)

    def load_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图片", "",
            "Images (*.jfif;*.pjpeg;*.jpeg;*.pjp;*.jpg;*.png)"
        )
        if not path:
            return
        self.label.setPixmap(toqpixmap(path))

    def closeEvent(self, event):
        self.label.close()
        event.accept()

    def save_crop(self):
        rect = self.label.get_crop_in_pixmap()
        pixmap = self.label.get_pixmap()
        if pixmap is None or rect.isNull():
            return
        self.btn_upload.setText("封面上传中...")
        self.btn_upload.setEnabled(False)
        pixmap = pixmap.copy(rect)
        if pixmap.size().width() > 704 or pixmap.size().height() > 396:
            pixmap = pixmap.scaled(
                704, 396, Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        pixmap.save(buf, "PNG")
        buf.close()
        cover_uploader = CoverUploadWorker(ba.data())
        self.parent_window.parent_window.add_thread(
            cover_uploader,
            on_finished=partial(cover_uploader.on_finished,
                                self.parent_window),
            on_exception=partial(cover_uploader.on_exception, self)
        )
