"""Live OBS thumbnail with a fixed-size, movable RTC crop aperture."""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from startlive.core.pk.states.video_crop import VideoCrop


class CropThumbnail(QWidget):
    cropChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(360, 210)
        self.setMouseTracking(True)
        self._image = None
        self.crop = VideoCrop()
        self._drag = None
        self._source_size = None

    def set_image(self, image):
        size = (int(image.text("source_width") or image.width()),
                int(image.text(
                    "source_height") or image.height())) if image is not None else None
        if size != self._source_size:
            self._drag = None
            self._source_size = size
            self.unsetCursor()
        self._image = image
        self.update()

    def set_crop(self, crop):
        self.crop = crop
        self.update()

    def _rectangles(self):
        if self._image is None:
            return None
        width, height = self._source_size
        scale = min(self.width() / width, self.height() / height)
        image = QRectF((self.width() - width * scale) / 2,
                       (self.height() - height * scale) / 2,
                       width * scale, height * scale)
        x, y, w, h = self.crop.rectangle(width, height)
        crop = QRectF(image.x() + x * scale, image.y() + y * scale, w * scale,
                      h * scale)
        return image, crop

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#151719"))
        geometry = self._rectangles()
        if geometry is None:
            painter.setPen(QColor("#a2a7ae"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                             "等待 OBS 采集画面")
            return
        image, crop = geometry
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(image, self._image)
        mask = QPainterPath()
        mask.addRect(image)
        mask.addRect(crop)
        painter.fillPath(mask, QColor(0, 0, 0, 135))
        painter.setPen(QPen(QColor("#00aeec"), 2))
        painter.drawRect(crop.adjusted(1, 1, -1, -1))
        # Native BestAreaView uses 5:8 inside the 5:4 crop, centered by default.
        best = QRectF(crop.x() + crop.width() / 4, crop.y(), crop.width() / 2,
                      crop.height())
        painter.setPen(
            QPen(QColor(255, 255, 255, 170), 1, Qt.PenStyle.DashLine))
        painter.drawLine(best.topLeft(), best.bottomLeft())
        painter.drawLine(best.topRight(), best.bottomRight())
        label = QRectF(best.x(), best.bottom() - 43, best.width(), 42)
        painter.fillRect(label, QColor(0, 0, 0, 120))
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(label, Qt.AlignmentFlag.AlignCenter, "最佳\n显示区域")

    def mousePressEvent(self, event):
        geometry = self._rectangles()
        if event.button() == Qt.MouseButton.LeftButton and geometry is not None:
            _, crop = geometry
            if crop.contains(event.position()):
                self._drag = event.position() - crop.topLeft()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        geometry = self._rectangles()
        if geometry is None:
            return
        image, crop = geometry
        if self._drag is not None:
            if not event.buttons() & Qt.MouseButton.LeftButton:
                self._drag = None
                self.unsetCursor()
                return
            position = event.position() - self._drag - image.topLeft()
            travel = QPointF(image.width() - crop.width(),
                             image.height() - crop.height())
            x = min(1.0, max(0.0,
                             position.x() / travel.x())) if travel.x() > 0 else 0.5
            y = min(1.0, max(0.0,
                             position.y() / travel.y())) if travel.y() > 0 else 0.5
            self.crop = VideoCrop(x, y)
            self.cropChanged.emit(self.crop)
            self.update()
        else:
            self.setCursor(
                Qt.CursorShape.OpenHandCursor if crop.contains(event.position())
                else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, event):
        self._drag = None
        self.unsetCursor()
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        self._drag = None
        self.unsetCursor()
        super().hideEvent(event)


class PkCropSelector(QWidget):
    cropChanged = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Popup)
        self.setWindowTitle("画面截取")
        self.setStyleSheet("""
            PkCropSelector { background: #242628; color: #e8eaed; }
            QPushButton { background: #303438; color: #e8eaed; border: 1px solid #484c50;
                          border-radius: 8px; padding: 8px 20px; }
            QPushButton:hover { background: #3b4146; }
        """)
        layout = QVBoxLayout(self)
        title = QLabel(
            '拖动调整<span style="color:#00aeec">画面截取位置</span>')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #a2a7ae; padding: 8px")
        layout.addWidget(title)
        self.thumbnail = CropThumbnail(self)
        self.thumbnail.cropChanged.connect(self.cropChanged)
        layout.addWidget(self.thumbnail)
        hint = QLabel("蓝框内画面用于本地预览和发送给对方，尺寸固定")
        hint.setStyleSheet("color: #a2a7ae")
        layout.addWidget(hint)
        reset = QPushButton("恢复居中")
        reset.clicked.connect(self._reset)
        layout.addWidget(reset)

    def _reset(self):
        crop = VideoCrop()
        self.thumbnail.set_crop(crop)
        self.cropChanged.emit(crop)

    def show_above(self, button):
        if self.isVisible():
            self.hide()
            return
        self.adjustSize()
        point = button.mapToGlobal(button.rect().topLeft())
        available = button.screen().availableGeometry()
        x = max(available.left(),
                min(point.x(), available.right() - self.width() + 1))
        y = max(available.top(), point.y() - self.height() - 8)
        self.move(x, y)
        self.show()
