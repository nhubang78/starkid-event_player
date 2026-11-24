"""Các widget giao diện: biểu tượng, đồng hồ VU, fader, thanh tua, nút cart."""
import math

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QAbstractButton, QPushButton, QSlider, QStyle, QWidget

# ---------------------------------------------------------------- biểu tượng
_ICON_FONT = None


def icon_font_family():
    global _ICON_FONT
    if _ICON_FONT is None:
        fams = QFontDatabase.families()
        _ICON_FONT = next((f for f in ("Segoe Fluent Icons", "Segoe MDL2 Assets") if f in fams), "")
    return _ICON_FONT


def glyph_icon(code: str, color="#333333", size=64):
    """Tạo QIcon từ ký tự của font biểu tượng Windows (Segoe Fluent Icons)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    f = QFont(icon_font_family())
    f.setPixelSize(int(size * 0.78))
    p.setFont(f)
    p.setPen(QColor(color))
    p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, code)
    p.end()
    return QIcon(pm)


def shape_icon(kind: str, color="#555555", size=48):
    """Biểu tượng vẽ tay: play, stop, pause, fadein, fadeout, stopall, single."""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = QColor(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    s = size
    if kind == "play":
        p.drawPolygon(QPolygonF([QPointF(s * .22, s * .15), QPointF(s * .85, s * .5), QPointF(s * .22, s * .85)]))
    elif kind in ("prev", "next"):
        pts = [(.3, .2, .75, .5, .3, .8), (.55, .2, 1.0, .5, .55, .8)] if kind == "next" else \
              [(.7, .2, .25, .5, .7, .8), (.45, .2, .0, .5, .45, .8)]
        for a, b, c2, d, e, f in pts:
            p.drawPolygon(QPolygonF([QPointF(s * a, s * b), QPointF(s * c2, s * d), QPointF(s * e, s * f)]))
        p.drawRect(QRectF(s * (.1 if kind == "prev" else .82), s * .2, s * .08, s * .6))
    elif kind == "stop":
        p.drawRect(QRectF(s * .2, s * .2, s * .6, s * .6))
    elif kind == "pause":
        p.drawRect(QRectF(s * .2, s * .17, s * .2, s * .66))
        p.drawRect(QRectF(s * .6, s * .17, s * .2, s * .66))
    elif kind == "fadein":
        p.drawPolygon(QPolygonF([QPointF(s * .05, s * .8), QPointF(s * .95, s * .2), QPointF(s * .95, s * .8)]))
    elif kind == "fadeout":
        p.drawPolygon(QPolygonF([QPointF(s * .05, s * .2), QPointF(s * .95, s * .8), QPointF(s * .05, s * .8)]))
    elif kind == "stopall":
        p.setPen(QPen(c, s * .08))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(s * .1, s * .1, s * .8, s * .8))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawRoundedRect(QRectF(s * .34, s * .34, s * .32, s * .32), 3, 3)
    elif kind == "single":
        p.setPen(QPen(c, s * .06))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(QRectF(s * .15, s * .1, s * .7, s * .8), s * .1, s * .1)
        f = QFont("Segoe UI")
        f.setPixelSize(int(s * .5))
        f.setBold(True)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "1")
    p.end()
    return QIcon(pm)


# ---------------------------------------------------------------- thang dB
SCALE = [(0, 0.0), (-6, .1), (-12, .2), (-18, .3), (-24, .4), (-30, .5), (-40, .67), (-60, 1.0)]


def db_to_frac(db):
    """0 dB -> 0 (đỉnh), -60 dB -> 1 (đáy); nội suy theo các mốc trên thang."""
    if db >= 0:
        return 0.0
    for (d0, f0), (d1, f1) in zip(SCALE, SCALE[1:]):
        if db >= d1:
            return f0 + (f1 - f0) * (d0 - db) / (d0 - d1)
    return 1.0


def amp_to_db(a):
    return 20 * math.log10(a) if a > 1e-6 else -120.0


class VUMeter(QWidget):
    """Đồng hồ VU dọc (L/R) có thang dB bên phải và giữ đỉnh."""

    def __init__(self, parent=None, scale=True):
        super().__init__(parent)
        self.show_scale = scale
        self.level = [0.0, 0.0]   # dB-frac hiển thị
        self.peak = [-120.0, -120.0]
        self.peak_age = [0, 0]
        self.disp = [-120.0, -120.0]
        self.setMinimumWidth(32 if scale else 13)
        self.setMaximumWidth(36 if scale else 13)
        self.setMinimumHeight(80)

    def set_levels(self, amps):
        changed = False
        for i in range(2):
            db = amp_to_db(amps[i])
            new = db if db > self.disp[i] else max(db, self.disp[i] - 2.5)  # rơi ~50 dB/s
            if abs(new - self.disp[i]) > 0.05:
                changed = True
            self.disp[i] = new
            if db >= self.peak[i]:
                self.peak[i], self.peak_age[i] = db, 0
            else:
                self.peak_age[i] += 1
                if self.peak_age[i] > 30:
                    self.peak[i] = max(-120.0, self.peak[i] - 1.5)
                    changed = True
        if changed:
            self.update()

    # màu LED: (sáng, tắt)
    _ZONES = ((-6, QColor("#ef4444"), QColor("#727272")),
              (-18, QColor("#f2b81c"), QColor("#727272")),
              (-999, QColor("#2fb84a"), QColor("#727272")))
    SEG = 4   # chiều cao 1 vạch LED (px), cách nhau 1px

    def _zone(self, db):
        for lim, on, off in self._ZONES:
            if db >= lim:
                return on, off
        return self._ZONES[-1][1], self._ZONES[-1][2]

    def paintEvent(self, _e):
        p = QPainter(self)
        bar_w = 11
        top, bottom = 6, self.height() - 6
        h = bottom - top
        x0 = 1
        level = max(self.disp)
        peak = max(self.peak)
        lit_frac = db_to_frac(level) if level > -60 else 1.0
        peak_frac = db_to_frac(peak) if peak > -60 else None
        step = self.SEG + 1
        n = max(1, int(h // step))
        seg_h = h / n
        p.fillRect(QRectF(x0, top, bar_w, h), QColor("#565656"))  # khe giữa các vạch
        for i in range(n):                       # i = 0 ở đáy
            y_bot = bottom - i * seg_h
            y_top = y_bot - seg_h + 1
            mid_frac = ((y_top + y_bot) / 2 - top) / h
            db = self._frac_to_db(mid_frac)
            on, off = self._zone(db)
            lit = mid_frac >= lit_frac
            if peak_frac is not None and abs(mid_frac - peak_frac) <= (seg_h / h) / 2:
                color = QColor("#f5f5f5")         # vạch giữ đỉnh
            else:
                color = on if lit else off
            p.fillRect(QRectF(x0, y_top, bar_w, y_bot - y_top), color)
        if self.show_scale:
            f = QFont("Segoe UI")
            f.setPixelSize(9)
            p.setFont(f)
            p.setPen(QColor("#6b6b6b"))
            for db, frac in SCALE:
                y = top + frac * h
                p.drawLine(QPointF(x0 + bar_w + 1, y), QPointF(x0 + bar_w + 4, y))
                p.drawText(QRectF(x0 + bar_w + 5, y - 6, 30, 12),
                           Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, str(db))

    @staticmethod
    def _frac_to_db(frac):
        for (d0, f0), (d1, f1) in zip(SCALE, SCALE[1:]):
            if frac <= f1:
                return d0 + (d1 - d0) * (frac - f0) / (f1 - f0)
        return -60.0


class Fader(QSlider):
    """Fader dọc kiểu bàn mixer, có vạch chia hai bên."""

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Vertical, parent)
        self.setRange(0, 100)
        self.setPageStep(5)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumWidth(34)
        self.setMinimumHeight(80)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setPen(QColor("#a3a3a3"))
        h = self.height()
        cx = self.width() / 2
        handle = 14
        for i in range(0, 7):
            y = handle / 2 + (h - handle) * i / 6
            p.drawLine(QPointF(cx - 16, y), QPointF(cx - 11, y))
            p.drawLine(QPointF(cx + 11, y), QPointF(cx + 16, y))
        p.end()
        super().paintEvent(e)

    def mouseDoubleClickEvent(self, _e):
        self.setValue(80)  # nháy đúp = về mức mặc định


_KEY_VI = {"Up": "Lên", "Down": "Xuống", "Left": "Trái", "Right": "Phải", "Return": "Enter",
           "Del": "Delete", "Ins": "Insert", "PgUp": "PgUp", "PgDown": "PgDown"}


def key_label(seq: str, empty="(chưa gán)"):
    """Tên phím dễ đọc (tiếng Việt) từ chuỗi QKeySequence dạng PortableText."""
    if not seq:
        return empty
    parts = seq.split("+") if seq != "+" else ["+"]
    return "+".join(_KEY_VI.get(p, p) for p in parts if p) or seq


class KeyCaptureEdit(QPushButton):
    """Ô gán phím: bấm vào rồi bấm phím muốn gán; Backspace = bỏ gán."""
    changed = Signal(str)
    _MODS = (Qt.Key.Key_Shift, Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
             Qt.Key.Key_AltGr, Qt.Key.Key_unknown, Qt.Key.Key_Tab, Qt.Key.Key_Backtab)

    def __init__(self, seq="", parent=None):
        super().__init__(parent)
        self.setObjectName("keyEdit")
        self.setAutoDefault(False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(200)
        self.set_seq(seq)

    def set_seq(self, seq):
        self.seq = seq
        self.setText("Bấm phím..." if self.hasFocus() else key_label(seq))

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.setText("Bấm phím...")

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self.setText(key_label(self.seq))

    def keyPressEvent(self, e):
        k = e.key()
        if k in self._MODS:
            return
        mods = e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier
                                | Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.MetaModifier)
        if k == Qt.Key.Key_Backspace and not mods:
            new = ""
        else:
            from PySide6.QtCore import QKeyCombination
            from PySide6.QtGui import QKeySequence
            new = QKeySequence(QKeyCombination(mods, Qt.Key(k))).toString(
                QKeySequence.SequenceFormat.PortableText)
        e.accept()
        self.seq = new
        self.clearFocus()
        self.setText(key_label(new))
        self.changed.emit(new)

    def keyReleaseEvent(self, e):
        e.accept()


class SeekSlider(QSlider):
    seekRequested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setRange(0, 1)
        self.sliderReleased.connect(lambda: self.seekRequested.emit(self.value()))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            val = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                 int(e.position().x()), self.width())
            self.setValue(val)
            self.seekRequested.emit(val)
        super().mousePressEvent(e)


class CartButton(QAbstractButton):
    """Nút lớn của kênh: hiện số kênh + tên bài, hoặc phím tắt khi trống."""

    def __init__(self, strip, parent=None):
        super().__init__(parent)
        self.strip = strip
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumHeight(42)
        self.setMaximumHeight(50)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def sizeHint(self):
        return QSize(140, 46)

    def paintEvent(self, _e):
        s = self.strip
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QColor(s.cart_color())
        if self.isDown():
            bg = bg.darker(110)
        border = QColor("#22c55e") if s.deck.is_playing() else QColor("#cfcfcf")
        p.setPen(QPen(border, 2 if s.deck.is_playing() else 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 4, 4)
        fg = QColor("#111") if bg.lightness() > 140 else QColor("#f5f5f5")
        if s.path:
            f = QFont("Segoe UI")
            f.setPixelSize(15)
            f.setBold(True)
            p.setFont(f)
            p.setPen(fg)
            p.drawText(QRectF(r.x(), r.y() + 2, r.width(), r.height() / 2),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, str(s.number))
            f.setBold(False)
            f.setPixelSize(12)
            p.setFont(f)
            name = p.fontMetrics().elidedText(s.display_name(), Qt.TextElideMode.ElideRight, int(r.width() - 12))
            p.drawText(QRectF(r.x() + 6, r.y() + r.height() / 2, r.width() - 12, r.height() / 2 - 2),
                       Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, name)
            f.setPixelSize(10)
            p.setFont(f)
            p.setPen(QColor("#9a9a9a") if bg.lightness() > 140 else QColor("#dddddd"))
            p.drawText(QRectF(r.x() + 5, r.y() + 3, 30, 14), Qt.AlignmentFlag.AlignLeft, s.hotkey)
        else:
            f = QFont("Segoe UI")
            f.setPixelSize(17)
            p.setFont(f)
            p.setPen(QColor("#a3a3a3"))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, s.hotkey)
