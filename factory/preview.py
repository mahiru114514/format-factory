import io

from PIL import Image
from PySide6.QtCore import QPoint, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QRubberBand


class ImagePreview(QGraphicsView):
    """Zoomable source preview; dragging marks a crop for single-formula OCR."""
    def __init__(self):
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(__import__('PySide6.QtGui', fromlist=['QPainter']).QPainter.RenderHint.SmoothPixmapTransform)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image = None
        self.crop_rect = None
        self.start_point = None
        self.rubber = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
        self.selection_item = None
        self.setMinimumHeight(120)

    def set_image(self, image: Image.Image):
        self.image = image.copy()
        stream = io.BytesIO()
        image.save(stream, format='PNG')
        pixmap = QPixmap.fromImage(QImage.fromData(stream.getvalue()))
        self.scene().clear()
        self.scene().addPixmap(pixmap)
        self.scene().setSceneRect(QRectF(pixmap.rect()))
        self.selection_item = None
        self.crop_rect = None
        self.fit()

    def fit(self):
        if self.image:
            self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def selected_image(self):
        if self.image is None:
            return None
        if self.crop_rect and self.crop_rect.width() >= 4 and self.crop_rect.height() >= 4:
            r = self.crop_rect
            return self.image.crop((int(r.left()), int(r.top()), int(r.right()), int(r.bottom())))
        return self.image.copy()

    def wheelEvent(self, event):
        self.scale(1.15 if event.angleDelta().y() > 0 else 1 / 1.15, 1.15 if event.angleDelta().y() > 0 else 1 / 1.15)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.image is not None:
            self.start_point = event.position().toPoint()
            self.rubber.setGeometry(QRect(self.start_point, self.start_point))
            self.rubber.show()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.start_point is not None:
            self.rubber.setGeometry(QRect(self.start_point, event.position().toPoint()).normalized())
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.start_point is not None:
            rectangle = self.mapToScene(QRect(self.start_point, event.position().toPoint()).normalized()).boundingRect().intersected(self.sceneRect())
            self.rubber.hide()
            self.start_point = None
            if self.selection_item is not None:
                self.scene().removeItem(self.selection_item)
                self.selection_item = None
            self.crop_rect = rectangle if rectangle.width() >= 4 and rectangle.height() >= 4 else None
            if self.crop_rect:
                self.selection_item = self.scene().addRect(self.crop_rect, QPen(QColor('#285df5'), 2), QColor(40, 93, 245, 24))
        else:
            super().mouseReleaseEvent(event)
