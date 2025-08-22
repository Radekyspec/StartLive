from PySide6.QtCore import (
    Qt, QRect, QPoint, QSize, QVariantAnimation, QEasingCurve, QTimer
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor, QGuiApplication
from PySide6.QtWidgets import (
    QLabel, QRubberBand
)


class CropLabel(QLabel):
    HANDLE_LENGTH = 20
    HANDLE_WIDTH = 8
    SNAP_MARGIN = 10

    def __init__(self, ratio: tuple[int, int], /, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_pixmap: QPixmap | None = None
        self.setFixedSize(640, 360)

        self.rubber = QRubberBand(QRubberBand.Shape.Rectangle, self)

        # interact state
        self.origin = QPoint()
        self.crop_rect = QRect()
        self.dragging = False
        self.resizing = False
        self.moving = False
        self.active_handle: int | None = None
        self.move_offset = QPoint()

        # displaying rect (actual position of the pixmap inside the label)
        self._disp_rect = QRect()

        # ratio
        self.aspect_ratio: tuple[int, int] = ratio

        # animation
        self._anim: QVariantAnimation | None = None

        self.setScaledContents(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scaled_pixmap: QPixmap | None = None
        self._scaled_key = (0, 0, 0)  # (wL, hL, dpr*100) 用于判断缓存是否失效
        self._repaint_timer = QTimer(self)
        self._repaint_timer.setSingleShot(True)
        self._repaint_timer.setInterval(8)  # ~60 FPS 节流
        self._pending_dirty: QRect | None = None

        # 不透明绘制，减少底层重绘
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def _current_screen(self):
        # 优先用窗口句柄的屏幕；退化到主屏
        if self.windowHandle() and self.windowHandle().screen():
            return self.windowHandle().screen()
        return QGuiApplication.primaryScreen()

    def _apply_refresh_rate(self, *args, **kwargs):
        screen = self._current_screen()
        rate = screen.refreshRate() or 60.0
        # 以 1x 帧率节流，可按需改为 0.5x（*2）
        interval_ms = min(33, int(1000.0 / rate))
        self._repaint_timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._repaint_timer.setInterval(interval_ms)

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_refresh_rate()
        scr = self._current_screen()
        scr.refreshRateChanged.disconnect(self._apply_refresh_rate)
        scr.refreshRateChanged.connect(self._apply_refresh_rate)

    def enterEvent(self, e):
        # 窗口拖到另一块屏幕后刷新
        self._apply_refresh_rate()
        return super().enterEvent(e)

    def _ensure_scaled_pixmap(self):
        if not self._orig_pixmap:
            self._scaled_pixmap = None
            self._disp_rect = QRect()
            return

        wL, hL = self.width(), self.height()
        dpr = self.devicePixelRatioF()
        key = (wL, hL, int(dpr * 100))
        if self._scaled_pixmap is not None and key == self._scaled_key:
            return  # 缓存有效

        # 计算显示区域（保持原图比例铺满最短边）
        w0 = self._orig_pixmap.width() / dpr
        h0 = self._orig_pixmap.height() / dpr
        scale = min(wL / w0, hL / h0)
        new_w, new_h = int(w0 * scale), int(h0 * scale)
        x = (wL - new_w) // 2
        y = (hL - new_h) // 2
        self._disp_rect = QRect(x, y, new_w, new_h)

        # 只在这里缩放一次并缓存（高质量缩放成本转移到低频路径）
        self._scaled_pixmap = self._orig_pixmap.scaled(
            int(new_w * dpr), int(new_h * dpr),
            Qt.AspectRatioMode.IgnoreAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        self._scaled_pixmap.setDevicePixelRatio(dpr)
        self._scaled_key = key

    def setPixmap(self, pixmap: QPixmap):
        pixmap.setDevicePixelRatio(self.devicePixelRatioF())
        self._orig_pixmap = pixmap
        # reset state
        self.rubber.hide()
        self.origin = QPoint()
        self.crop_rect = QRect()
        self.dragging = self.resizing = self.moving = False
        self.active_handle = None
        self.move_offset = QPoint()
        self._disp_rect = QRect()
        self._scaled_pixmap = None
        self._scaled_key = (0, 0, 0)
        self.update()
        super().setPixmap(pixmap)

    def get_pixmap(self) -> QPixmap | None:
        return self._orig_pixmap

    def get_crop_in_pixmap(self) -> QRect:
        """
        Calculates and returns a QRect representing the crop region in the original
        pixmap's coordinate space. The calculation maps the crop rectangle from the
        display coordinate space to the original pixmap's coordinate space using
        scaling factors derived from the dimensions of the original pixmap and the
        display rectangle.

        :return: A QRect object representing the crop region in the original pixmap's
            coordinate space. If the crop rectangle is invalid or the original pixmap
            is not set, an empty QRect is returned.
        :rtype: QRect
        """
        if self.crop_rect.isNull() or not self._orig_pixmap:
            return QRect()

        w0 = self._orig_pixmap.size().width()
        h0 = self._orig_pixmap.size().height()
        wD, hD = self._disp_rect.width(), self._disp_rect.height()
        sx, sy = w0 / wD, h0 / hD
        cx = self.crop_rect.x() - self._disp_rect.x()
        cy = self.crop_rect.y() - self._disp_rect.y()
        cw, ch = self.crop_rect.width(), self.crop_rect.height()
        return QRect(round(cx * sx), round(cy * sy),
                     round(cw * sx), round(ch * sy))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), Qt.GlobalColor.black)

        self._ensure_scaled_pixmap()
        if self._scaled_pixmap:
            painter.drawPixmap(self._disp_rect.topLeft(), self._scaled_pixmap)

        if not self.crop_rect.isNull():
            pen = painter.pen()
            pen.setColor(Qt.GlobalColor.red)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self.crop_rect)

            painter.setBrush(Qt.GlobalColor.blue)
            self._draw_corner_l(painter)

    def _schedule_dirty_update(self, new_rect: QRect,
                               old_rect: QRect | None = None):
        margin = self.HANDLE_LENGTH + self.HANDLE_WIDTH
        dirty = new_rect.adjusted(-margin, -margin, margin, margin)
        if old_rect:
            dirty = dirty.united(
                old_rect.adjusted(-margin, -margin, margin, margin))

        self._pending_dirty = dirty if self._pending_dirty is None else self._pending_dirty.united(
            dirty)
        if not self._repaint_timer.isActive():
            self._repaint_timer.timeout.connect(self._flush_dirty_update)
            self._repaint_timer.start()

    def _flush_dirty_update(self):
        if self._pending_dirty is not None:
            self.update(self._pending_dirty)
        self._pending_dirty = None

    def resizeEvent(self, e):
        # 尺寸变化时仅标记缓存失效，不在此处立刻重建，延后到下一次 paint
        self._scaled_pixmap = None
        return super().resizeEvent(e)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if not self.crop_rect.isNull():
                self.crop_rect = QRect()
                self.rubber.hide()
                self.dragging = self.resizing = self.moving = False
                self.active_handle = None
                self.update()
            return

        if event.button() != Qt.MouseButton.LeftButton or not self._orig_pixmap:
            return super().mousePressEvent(event)

        pos = event.position().toPoint()

        # corner point resizing detection
        idx = self._hit_handle(pos)
        if idx is not None:
            self.resizing = True
            self.active_handle = idx
            self.origin = self._corners(self.crop_rect)[(idx + 2) % 4]
            return

        # inbox moving detection
        if self.crop_rect.contains(pos):
            self.moving = True
            self.move_offset = pos - self.crop_rect.topLeft()
            return

        # new crop detection
        self.dragging = True
        self.active_handle = None
        self.origin = self._clamp(pos)
        self.crop_rect = QRect(self.origin, QSize())
        self.rubber.setGeometry(self.crop_rect)
        self.rubber.show()

        self.update()
        self._pending_dirty = None
        self._repaint_timer.stop()
        return super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._orig_pixmap:
            return super().mouseMoveEvent(event)

        raw_pos = self._clamp(event.position().toPoint())
        old = self.crop_rect

        if self.moving:
            size = self.crop_rect.size()
            new_tl = raw_pos - self.move_offset
            max_x = self._disp_rect.right() - size.width()
            max_y = self._disp_rect.bottom() - size.height()
            x = min(max(new_tl.x(), self._disp_rect.left()), max_x)
            y = min(max(new_tl.y(), self._disp_rect.top()), max_y)
            rect = QRect(QPoint(x, y), size)
            self.crop_rect = rect
            self.rubber.setGeometry(rect)
            self._schedule_dirty_update(rect, old)
            return

        if self.dragging or self.resizing:
            base_rect = QRect(self.origin, raw_pos).normalized().intersected(
                self._disp_rect)
            rect = self._snap_and_keep_aspect(base_rect)
            self.crop_rect = rect
            self.rubber.setGeometry(rect)
            self._schedule_dirty_update(rect, old)
            return

        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.update()
        self._pending_dirty = None
        self._repaint_timer.stop()
        if event.button() == Qt.MouseButton.LeftButton and (
                self.dragging or self.resizing or self.moving):
            self.dragging = self.resizing = self.moving = False
        else:
            return super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._orig_pixmap:
            return super().mouseDoubleClickEvent(event)

        pos = event.position().toPoint()
        target_rect: QRect

        # maximize based on mouse position if no selected rect
        if self.crop_rect.isNull():
            center = self._clamp(pos)
            target_rect = self._largest_rect_inside(self._disp_rect,
                                                    center=center)
        else:
            # if double-clicked on corner points
            idx = self._hit_handle(pos)
            if idx is not None:
                # maximize based on that corner
                target_rect = self._largest_rect_with_fixed_corner(idx)
            elif self.crop_rect.contains(pos):
                # maximize based on the current rect center
                center = self.crop_rect.center()
                target_rect = self._largest_rect_inside(self._disp_rect,
                                                        center=center)
            else:
                # new maximized rect when outside current rect
                center = self._clamp(pos)
                target_rect = self._largest_rect_inside(self._disp_rect,
                                                        center=center)

        self._animate_to(target_rect)
        return

    def _animate_to(self, rect: QRect, duration: int = 150):
        rect = rect.normalized()
        if self._anim and self._anim.state() == QVariantAnimation.State.Running:
            self._anim.stop()

        start_rect = self.crop_rect if not self.crop_rect.isNull() else rect
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(start_rect)
        self._anim.setEndValue(rect)
        self._anim.setDuration(duration)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(lambda: setattr(self, "_anim", None))
        self._anim.start()

    def _on_anim_value(self, value):
        if isinstance(value, QRect):
            self.crop_rect = value
            self.rubber.setGeometry(value)
            self.update()

    def _draw_corner_l(self, painter: QPainter):
        handle_len = self.HANDLE_LENGTH
        handle_w = self.HANDLE_WIDTH
        color = QColor(255, 105, 180)

        pen = QPen(color)
        pen.setWidth(handle_w)
        pen.setCapStyle(Qt.PenCapStyle.SquareCap)
        painter.setPen(pen)

        tl = self.crop_rect.topLeft()
        tr = self.crop_rect.topRight()
        br = self.crop_rect.bottomRight()
        bl = self.crop_rect.bottomLeft()

        painter.drawLine(tl, QPoint(tl.x() + handle_len, tl.y()))
        painter.drawLine(tl, QPoint(tl.x(), tl.y() + handle_len))

        painter.drawLine(tr, QPoint(tr.x() - handle_len, tr.y()))
        painter.drawLine(tr, QPoint(tr.x(), tr.y() + handle_len))

        painter.drawLine(br, QPoint(br.x() - handle_len, br.y()))
        painter.drawLine(br, QPoint(br.x(), br.y() - handle_len))

        painter.drawLine(bl, QPoint(bl.x() + handle_len, bl.y()))
        painter.drawLine(bl, QPoint(bl.x(), bl.y() - handle_len))

    def _hit_handle(self, pos: QPoint) -> int | None:
        """
        Determine if a given position hits any of the handle corners and return the index
        of the corner if a hit occurs.

        This method checks whether a given position intersects with any of the corners of
        a defined rectangle (crop_rect). If a match is found, the index of the corner is
        returned. If no match is found, or if the rectangle is not defined, the function
        returns None.

        The function iterates through each corner of the rectangle, determines the bounds
        of the handle area by creating a smaller rectangle around the corner point, and
        checks if the given position lies within any of these handle areas.

        :param pos: Position to check against the handle corners.
            This should be a QPoint object specifying the position to test.
        :return: Index of the corner (as an integer) if the position hits the handle.
            Returns None if no hit occurs or if the crop rectangle is not defined.
        """
        if self.crop_rect.isNull():
            return None
        for idx, corner in enumerate(self._corners(self.crop_rect)):
            hit = QRect(
                corner - QPoint(self.HANDLE_LENGTH // 2, self.HANDLE_LENGTH // 2),
                QSize(self.HANDLE_LENGTH, self.HANDLE_LENGTH)
            )
            if hit.contains(pos):
                return idx
        return None

    @staticmethod
    def _corners(rect: QRect) -> list[QPoint]:
        return [rect.topLeft(), rect.topRight(), rect.bottomRight(),
                rect.bottomLeft()]

    @staticmethod
    def _fix_aspect_point(fixed_pt: QPoint, raw_pt: QPoint,
                          w_ratio: int, h_ratio: int) -> QPoint:
        """
        Adjusts a point's position relative to a fixed point while maintaining a specific
        aspect ratio defined by width and height ratios. The method computes the position
        of the second point such that the proportional relationship between width and
        height given by the ratios remains consistent.

        :param fixed_pt: The fixed reference point of type `QPoint` that determines
            the base for the aspect ratio calculation.
        :param raw_pt: The initial point of type `QPoint` whose position will be adjusted
            to ensure the aspect ratio is maintained.
        :param w_ratio: The width ratio, specified as an integer, which contributes
            to defining the aspect ratio.
        :param h_ratio: The height ratio, specified as an integer, which contributes
            to defining the aspect ratio.
        :return: A new `QPoint` object representing the adjusted point, computed
            to maintain the aspect ratio with respect to the fixed point.
        :rtype: QPoint
        """
        dx, dy = raw_pt.x() - fixed_pt.x(), raw_pt.y() - fixed_pt.y()
        frac_w, frac_h = abs(dx) / w_ratio, abs(dy) / h_ratio
        if frac_w < frac_h:
            dx_use = dx
            dy_use = (abs(dx) * h_ratio / w_ratio) * (1 if dy >= 0 else -1)
        else:
            dy_use = dy
            dx_use = (abs(dy) * w_ratio / h_ratio) * (1 if dx >= 0 else -1)
        return QPoint(int(fixed_pt.x() + dx_use), int(fixed_pt.y() + dy_use))

    def _clamp(self, pt: QPoint) -> QPoint:
        """
        Restricts the provided point to lie within the boundaries of the display rectangle
        or the widget's dimensions if the display rectangle is null. It ensures that the
        resulting point coordinates do not exceed the allowed range in either x or y
        direction.

        :param pt: The QPoint to be clamped.
        :return: A QPoint instance where its `x` and `y` coordinates have been adjusted
                 to fit within the defined boundaries.
        """
        if not self._disp_rect.isNull():
            x = max(self._disp_rect.left(),
                    min(self._disp_rect.right(), pt.x()))
            y = max(self._disp_rect.top(),
                    min(self._disp_rect.bottom(), pt.y()))
        else:
            x = max(0, min(self.width(), pt.x()))
            y = max(0, min(self.height(), pt.y()))
        return QPoint(x, y)

    def _farthest_corner(self, fixed_pt: QPoint, rect: QRect) -> QPoint:
        corners = self._corners(rect)
        return max(corners, key=lambda p: (p.x() - fixed_pt.x()) ** 2 + (
                p.y() - fixed_pt.y()) ** 2)

    def _snap_and_keep_aspect(self, raw_rect: QRect) -> QRect:
        """
        Adjusts the input rectangle's size and position to snap its moving corner
        to the closest edges of the display rectangle and ensures the aspect ratio
        is preserved. The operation limits the rectangle to stay within the
        boundaries of the display rectangle.

        :param raw_rect: The QRect instance representing the raw rectangle
            possibly moved by the user.
        :return: A normalized QRect instance that maintains the original aspect
            ratio and is constrained within the display rectangle boundaries.
        """
        dr, m = self._disp_rect, self.SNAP_MARGIN
        fixed_pt = self.origin
        corners = self._corners(raw_rect)
        if self.active_handle is not None:
            moving_pt = corners[self.active_handle]
        else:
            # moving_pt = raw_rect.bottomRight()
            moving_pt = self._farthest_corner(fixed_pt, raw_rect)

        # snap to pixmap corners
        if abs(moving_pt.x() - dr.left()) < m:
            moving_pt.setX(dr.left())
        elif abs(moving_pt.x() - dr.right()) < m:
            moving_pt.setX(dr.right())
        if abs(moving_pt.y() - dr.top()) < m:
            moving_pt.setY(dr.top())
        elif abs(moving_pt.y() - dr.bottom()) < m:
            moving_pt.setY(dr.bottom())

        new_pt = self._fix_aspect_point(fixed_pt, moving_pt, *self.aspect_ratio)
        rect = QRect(fixed_pt, new_pt).normalized().intersected(dr)
        return rect

    def _largest_rect_inside(self, bounds: QRect,
                             center: QPoint | None = None) -> QRect:
        """
        Calculates the largest rectangle that can fit inside the given bounds while maintaining
        the aspect ratio specified by the `aspect_ratio` property. Optionally positions the
        rectangle around a specified center point.

        :param bounds: The bounding `QRect` within which the rectangle must fit.
        :param center: The optional `QPoint` that specifies where the rectangle should be
            centered. If not provided, the rectangle will be centered within the bounds.
        :return: A `QRect` representing the calculated rectangle.
        """
        bw, bh = bounds.width(), bounds.height()
        wr, hr = self.aspect_ratio

        w = bw
        h = int(w * hr / wr)
        if h > bh:
            h = bh
            w = int(h * wr / hr)

        if center is None:
            x = bounds.left() + (bw - w) // 2
            y = bounds.top() + (bh - h) // 2
        else:
            x = center.x() - w // 2
            y = center.y() - h // 2
            x = max(bounds.left(), min(x, bounds.right() - w))
            y = max(bounds.top(), min(y, bounds.bottom() - h))

        return QRect(x, y, w, h)

    def _largest_rect_with_fixed_corner(self, corner_idx: int) -> QRect:
        """
        Calculate the largest rectangle that can fit within a given display rectangle with a fixed aspect
        ratio, while aligning its position based on a specified corner.

        :param corner_idx: The index of the corner where the rectangle will align. This should be one
            of the following:
            - 0: Top-left (TL)
            - 1: Top-right (TR)
            - 2: Bottom-right (BR)
            - 3: Bottom-left (BL)
        :type corner_idx: int
        :return: A QRect object representing the calculated rectangle aligned to the specified corner.
        :rtype: QRect
        """
        dr = self._disp_rect
        wr, hr = self.aspect_ratio

        # 先算满宽/满高组合
        bw, bh = dr.width(), dr.height()
        w = bw
        h = int(w * hr / wr)
        if h > bh:
            h = bh
            w = int(h * wr / hr)

        if corner_idx == 0:  # TL
            x, y = dr.left(), dr.top()
        elif corner_idx == 1:  # TR
            x, y = dr.right() - w, dr.top()
        elif corner_idx == 2:  # BR
            x, y = dr.right() - w, dr.bottom() - h
        else:  # BL
            x, y = dr.left(), dr.bottom() - h

        return QRect(x, y, w, h)
