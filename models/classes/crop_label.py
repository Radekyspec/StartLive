from PySide6.QtCore import (
    Qt, QRect, QPoint, QSize, QVariantAnimation, QEasingCurve
)
from PySide6.QtGui import QPixmap, QPainter, QPen, QColor
from PySide6.QtWidgets import (
    QLabel, QRubberBand
)


class CropLabel(QLabel):
    HANDLE_SIZE = 20
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

        # ratio: None is free
        self.aspect_ratio: tuple[int, int] | None = ratio

        # animation
        self._anim: QVariantAnimation | None = None

        self.setScaledContents(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)

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
        self.update()
        super().setPixmap(pixmap)

    def get_pixmap(self) -> QPixmap | None:
        return self._orig_pixmap

    def set_aspect_ratio(self, w: int | None, h: int | None):
        """
        Sets the aspect ratio and adjusts the existing crop rectangle to the specified
        aspect ratio if applicable. If either `w` or `h` is None, the aspect ratio will
        be set to None, effectively disabling the constraint. The function recalculates
        and updates the crop rectangle based on the new aspect ratio to ensure consistency
        with the given dimensions.

        :param w: Width of the desired aspect ratio. Can be None to reset the aspect ratio.
        :param h: Height of the desired aspect ratio. Can be None to reset the aspect ratio.
        :return: None
        """
        self.aspect_ratio = None if (w is None or h is None) else (w, h)
        # fix existing rect immediately after changing a ratio
        if not self.crop_rect.isNull() and self.aspect_ratio:
            fixed = self.crop_rect.topLeft()
            new_pt = self._fix_aspect_point(fixed, self.crop_rect.bottomRight(),
                                            *self.aspect_ratio)
            rect = QRect(fixed, new_pt).normalized().intersected(
                self._disp_rect)
            self.crop_rect = rect
            self.rubber.setGeometry(rect)
            self.update()

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

        if self._orig_pixmap:
            wL, hL = self.width(), self.height()
            w0 = self._orig_pixmap.size().width() / self.devicePixelRatioF()
            h0 = self._orig_pixmap.size().height() / self.devicePixelRatioF()
            scale = min(wL / w0, hL / h0)
            new_w, new_h = int(w0 * scale), int(h0 * scale)
            x = (wL - new_w) // 2
            y = (hL - new_h) // 2
            self._disp_rect = QRect(x, y, new_w, new_h)

            scaled = self._orig_pixmap.scaled(
                int(new_w * self.devicePixelRatioF()),
                int(new_h * self.devicePixelRatioF()),
                Qt.AspectRatioMode.IgnoreAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawPixmap(x, y, scaled)

        if not self.crop_rect.isNull():
            pen = painter.pen()
            pen.setColor(Qt.GlobalColor.red)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawRect(self.crop_rect)

            painter.setBrush(Qt.GlobalColor.blue)
            self._draw_corner_l(painter)

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

    def mouseMoveEvent(self, event):
        if not self._orig_pixmap:
            return super().mouseMoveEvent(event)

        raw_pos = self._clamp(event.position().toPoint())

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
            self.update()
            return

        if self.dragging or self.resizing:
            pos = self._apply_aspect(self.origin, raw_pos)
            base_rect = QRect(self.origin, pos).normalized().intersected(
                self._disp_rect)
            rect = self._snap_and_keep_aspect(base_rect)
            self.crop_rect = rect
            self.rubber.setGeometry(rect)
            self.update()
            return

        return super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and (
                self.dragging or self.resizing or self.moving):
            self.dragging = self.resizing = self.moving = False
            self.update()
        else:
            super().mouseReleaseEvent(event)

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
        handle_len = 20
        handle_w = 8
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
                corner - QPoint(self.HANDLE_SIZE // 2, self.HANDLE_SIZE // 2),
                QSize(self.HANDLE_SIZE, self.HANDLE_SIZE)
            )
            if hit.contains(pos):
                return idx
        return None

    @staticmethod
    def _corners(rect: QRect) -> list[QPoint]:
        return [rect.topLeft(), rect.topRight(), rect.bottomRight(),
                rect.bottomLeft()]

    def _apply_aspect(self, fixed_pt: QPoint, raw_pt: QPoint) -> QPoint:
        """
        Adjusts the raw point based on a specified aspect ratio if it exists.
        If the aspect ratio is defined, the `_fix_aspect_point` method is used
        to compute an adjusted point based on the provided fixed point, raw
        point, and the aspect ratio. Otherwise, the raw point is returned as it
        is.

        :param fixed_pt: A fixed reference point for alignment.
        :param raw_pt: The actual point to be potentially adjusted.
        :return: A QPoint object representing the adjusted point if an aspect
            ratio exists, or the raw point if no adjustment is necessary.
        """
        if self.aspect_ratio:
            return self._fix_aspect_point(fixed_pt, raw_pt, *self.aspect_ratio)
        return raw_pt

    @staticmethod
    def _fix_aspect_point(fixed_pt: QPoint, raw_pt: QPoint,
                          w_ratio: int, h_ratio: int) -> QPoint:
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
        if not self._disp_rect.isNull():
            x = max(self._disp_rect.left(),
                    min(self._disp_rect.right(), pt.x()))
            y = max(self._disp_rect.top(),
                    min(self._disp_rect.bottom(), pt.y()))
        else:
            x = max(0, min(self.width(), pt.x()))
            y = max(0, min(self.height(), pt.y()))
        return QPoint(x, y)

    def _snap_and_keep_aspect(self, raw_rect: QRect) -> QRect:
        if self.aspect_ratio is None:
            return self._snap_to_edges(raw_rect)

        dr, m = self._disp_rect, self.SNAP_MARGIN
        fixed_pt = self.origin
        corners = self._corners(raw_rect)
        if self.active_handle is not None:
            moving_pt = corners[self.active_handle]
        else:
            moving_pt = raw_rect.bottomRight()

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
        return QRect(fixed_pt, new_pt).normalized()

    def _snap_to_edges(self, rect: QRect) -> QRect:
        dr, m = self._disp_rect, self.SNAP_MARGIN
        if abs(rect.left() - dr.left()) < m:
            rect.setLeft(dr.left())
        if abs(rect.right() - dr.right()) < m:
            rect.setRight(dr.right())
        if abs(rect.top() - dr.top()) < m:
            rect.setTop(dr.top())
        if abs(rect.bottom() - dr.bottom()) < m:
            rect.setBottom(dr.bottom())
        return rect

    def _largest_rect_inside(self, bounds: QRect,
                             center: QPoint | None = None) -> QRect:
        """
        Calculates the largest rectangle that can fit inside the given bounds while maintaining a specific
        aspect ratio. If no center is provided, the rectangle is centered within the bounds by default.

        :param bounds: The bounding rectangle within which the largest rectangle is to be calculated.
        :type bounds: QRect
        :param center: The optional center point around which the rectangle should be positioned.
                       If None, the rectangle will be centered within the bounds.
        :type center: QPoint | None
        :return: The largest inscribed QRect that satisfies the aspect ratio constraints.
        :rtype: QRect
        """
        if self.aspect_ratio is None:
            # free ratio
            return bounds

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
        ratio, while aligning its position based on a specified corner. If no aspect ratio is provided,
        the entire display rectangle is used.

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
        if self.aspect_ratio is None:
            return self._disp_rect

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
