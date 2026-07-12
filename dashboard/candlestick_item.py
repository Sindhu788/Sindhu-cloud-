import pyqtgraph as pg
from PySide6.QtGui import QPicture, QPainter, QColor
from PySide6.QtCore import QRectF, QPointF


class CandlestickItem(pg.GraphicsObject):
    """data: list of (x, open, high, low, close) with x as a plain integer
    bar index (not a timestamp) so candle spacing stays even regardless of
    gaps in the underlying time series."""

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.picture = QPicture()
        self._generate_picture()

    def _generate_picture(self):
        painter = QPainter(self.picture)
        width = 0.3
        for (x, o, h, l, c) in self.data:
            color = QColor("#2ecc71") if c >= o else QColor("#e74c3c")
            painter.setPen(pg.mkPen(color))
            painter.drawLine(QPointF(x, l), QPointF(x, h))
            painter.setBrush(pg.mkBrush(color))
            top, bottom = (c, o) if c >= o else (o, c)
            painter.drawRect(QRectF(x - width, bottom, width * 2, max(top - bottom, 1e-9)))
        painter.end()

    def paint(self, painter, *args):
        painter.drawPicture(0, 0, self.picture)

    def boundingRect(self):
        return QRectF(self.picture.boundingRect())
