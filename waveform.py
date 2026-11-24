"""Dạng sóng + trình chọn đoạn phát (điểm bắt đầu / kết thúc) cho một kênh."""
import math
import re
from array import array

from PySide6.QtCore import QLineF, QObject, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtMultimedia import QAudioDecoder, QAudioFormat
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

BUCKET_MS = 5          # độ phân giải dạng sóng lưu sẵn
_CACHE = {}            # path -> WaveData


# ---------------------------------------------------------------- thời gian
def fmt_cs(ms):
    """ms -> 'HH:MM:SS.cc'"""
    ms = max(0, int(round(ms)))
    cs = (ms // 10) % 100
    s = ms // 1000
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}.{cs:02d}"


def fmt_short(ms):
    s = max(0, ms) / 1000
    return f"{int(s // 60)}:{s % 60:04.1f}"


def parse_time(text):
    """'1:02.5', '00:01:02.50', '62.5' -> ms; None nếu sai."""
    t = text.strip().replace(",", ".")
    if not t:
        return None
    if not re.fullmatch(r"[\d:.]+", t):
        return None
    try:
        parts = [float(p) for p in t.split(":")]
    except ValueError:
        return None
    if len(parts) > 3:
        return None
    sec = 0.0
    for p in parts:
        sec = sec * 60 + p
    return int(round(sec * 1000))


# ---------------------------------------------------------------- dữ liệu sóng
class WaveData:
    def __init__(self, mins, maxs, bucket_ms, duration_ms):
        self.mins, self.maxs, self.bucket_ms, self.duration = mins, maxs, bucket_ms, duration_ms


class WaveformLoader(QObject):
    done = Signal(object)        # WaveData hoặc None
    progress = Signal(int)       # ms đã đọc

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self.samples = array("h")
        self.rate = 8000
        self.dec = QAudioDecoder(self)
        fmt = QAudioFormat()
        fmt.setSampleRate(8000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        self.dec.setAudioFormat(fmt)
        self.dec.bufferReady.connect(self._on_buffer)
        self.dec.finished.connect(self._on_finished)
        self.dec.error.connect(lambda _e: self.done.emit(None))
        self._n = 0

    def start(self):
        if self.path in _CACHE:
            QTimer.singleShot(0, lambda: self.done.emit(_CACHE[self.path]))
            return
        self.dec.setSource(QUrl.fromLocalFile(self.path))
        self.dec.start()

    def stop(self):
        self.dec.stop()

    def _on_buffer(self):
        b = self.dec.read()
        f = b.format()
        data = b.constData()
        if data is None:
            return
        ch = max(1, f.channelCount())
        self.rate = f.sampleRate() or 8000
        try:
            if f.sampleFormat() == QAudioFormat.SampleFormat.Int16:
                mv = data.cast("B").cast("h")
                self.samples.frombytes((mv[::ch] if ch > 1 else mv).tobytes())
            elif f.sampleFormat() == QAudioFormat.SampleFormat.Float:
                mv = data.cast("B").cast("f")
                self.samples.extend(int(max(-1.0, min(1.0, x)) * 32767) for x in mv[::ch])
        except (TypeError, ValueError):
            return
        self._n += 1
        if self._n % 200 == 0:
            self.progress.emit(int(len(self.samples) * 1000 / self.rate))

    def _on_finished(self):
        n = len(self.samples)
        if n == 0:
            self.done.emit(None)
            return
        step = max(1, self.rate * BUCKET_MS // 1000)
        mv = memoryview(self.samples)
        mins, maxs = array("h"), array("h")
        for i in range(0, n, step):
            s = mv[i:i + step]
            mins.append(min(s))
            maxs.append(max(s))
        data = WaveData(mins, maxs, step * 1000 / self.rate, n * 1000 / self.rate)
        _CACHE[self.path] = data
        self.samples = array("h")
        self.done.emit(data)


# ---------------------------------------------------------------- khung vẽ sóng
class WaveformView(QWidget):
    markersChanged = Signal(int, int)
    viewChanged = Signal()

    RULER = 22

    def __init__(self, duration_ms, parent=None):
        super().__init__(parent)
        self.data = None
        self.duration = max(1, int(duration_ms))
        self.start_ms, self.end_ms = 0, self.duration
        self.vs, self.ve = 0, self.duration
        self.playhead = None
        self.message = "Đang đọc dạng sóng..."
        self._drag = None
        self.setMinimumHeight(230)
        self.setMouseTracking(True)

    # ----- dữ liệu / trạng thái
    def set_data(self, data):
        self.data = data
        if data:
            self.duration = max(1, int(data.duration))
            self.message = ""
        else:
            self.message = "Không đọc được dạng sóng của file này"
        self.end_ms = min(self.end_ms, self.duration)
        self.set_view(0, self.duration)

    def set_markers(self, s, e):
        self.start_ms, self.end_ms = int(s), int(e)
        self.update()

    def set_view(self, vs, ve):
        span = max(200, min(self.duration, ve - vs))
        vs = max(0, min(vs, self.duration - span))
        self.vs, self.ve = int(vs), int(vs + span)
        self.update()
        self.viewChanged.emit()

    def full_view(self):
        return self.vs <= 0 and self.ve >= self.duration

    def zoom(self, factor, center=None):
        span = self.ve - self.vs
        c = (self.vs + self.ve) / 2 if center is None else center
        new = span * factor
        rel = (c - self.vs) / span if span else .5
        self.set_view(c - new * rel, c - new * rel + new)

    # ----- toạ độ
    def x_of(self, ms):
        return (ms - self.vs) / max(1, self.ve - self.vs) * self.width()

    def ms_of(self, x):
        return self.vs + x / max(1, self.width()) * (self.ve - self.vs)

    # ----- vẽ
    def paintEvent(self, _e):
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#ffffff"))
        top = self.RULER
        wave_h = h - top - 4
        mid = top + 2 + wave_h / 2
        # thước thời gian
        span = self.ve - self.vs
        steps = [100, 200, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000, 600000]
        tick = next((s for s in steps if s / span * w >= 90), steps[-1])
        f = QFont("Segoe UI")
        f.setPixelSize(11)
        p.setFont(f)
        t = (self.vs // tick) * tick
        while t <= self.ve:
            x = self.x_of(t)
            if x >= 0:
                p.setPen(QColor("#d9d9d9"))
                p.drawLine(QPointF(x, top), QPointF(x, h))
                p.setPen(QColor("#9a9a9a"))
                p.drawLine(QPointF(x, 0), QPointF(x, top))
                lab = fmt_short(t) if tick < 1000 else f"{int(t // 60000)}:{int(t // 1000 % 60):02d}"
                p.drawText(QPointF(x + 3, 15), lab)
            t += tick
        p.setPen(QColor("#e5e5e5"))
        p.drawLine(QPointF(0, top), QPointF(w, top))
        # sóng
        d = self.data
        if d:
            lines = []
            scale = (wave_h / 2) / 32768
            n = len(d.mins)
            for x in range(w):
                t0 = self.ms_of(x)
                t1 = self.ms_of(x + 1)
                i0 = int(t0 / d.bucket_ms)
                i1 = max(i0 + 1, int(t1 / d.bucket_ms))
                if i0 >= n:
                    break
                mx = max(d.maxs[i0:i1])
                mn = min(d.mins[i0:i1])
                lines.append(QLineF(x + .5, mid - mx * scale, x + .5, mid - mn * scale + 1))
            p.setPen(QPen(QColor("#5cc78c"), 1))
            p.drawLines(lines)
        elif self.message:
            p.setPen(QColor("#888"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
        # vùng ngoài đoạn phát: làm mờ
        xs, xe = self.x_of(self.start_ms), self.x_of(self.end_ms)
        dim = QColor(236, 236, 236, 190)
        if xs > 0:
            p.fillRect(QRectF(0, top + 1, min(w, xs), h - top), dim)
        if xe < w:
            p.fillRect(QRectF(max(0, xe), top + 1, w - max(0, xe), h - top), dim)
        # mốc
        for x in (xs, xe):
            if -2 <= x <= w + 2:
                p.setPen(QPen(QColor("#2563eb"), 2))
                p.drawLine(QPointF(x, top), QPointF(x, h))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor("#2563eb"))
                p.drawPolygon(QPolygonF([QPointF(x - 6, top), QPointF(x + 6, top), QPointF(x, top + 8)]))
        if self.playhead is not None:
            x = self.x_of(self.playhead)
            p.setPen(QPen(QColor("#ef4444"), 1.5))
            p.drawLine(QPointF(x, top), QPointF(x, h))
        p.setPen(QColor("#cfcfcf"))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # ----- chuột
    def _move_marker(self, which, ms):
        ms = int(max(0, min(self.duration, ms)))
        if which == "s":
            self.start_ms = min(ms, self.end_ms - 100)
        else:
            self.end_ms = max(ms, self.start_ms + 100)
        self.update()
        self.markersChanged.emit(self.start_ms, self.end_ms)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        x = e.position().x()
        ds, de = abs(x - self.x_of(self.start_ms)), abs(x - self.x_of(self.end_ms))
        self._drag = "s" if ds <= de else "e"
        self._move_marker(self._drag, self.ms_of(x))

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if self._drag:
            self._move_marker(self._drag, self.ms_of(x))
        else:
            near = min(abs(x - self.x_of(self.start_ms)), abs(x - self.x_of(self.end_ms))) < 8
            self.setCursor(Qt.CursorShape.SizeHorCursor if near else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, _e):
        self._drag = None

    def wheelEvent(self, e):
        dy = e.angleDelta().y() or e.angleDelta().x()
        if not dy:
            return
        span = self.ve - self.vs
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier or e.angleDelta().x():
            shift = -span * 0.15 * (1 if dy > 0 else -1)
            self.set_view(self.vs + shift, self.ve + shift)
        else:
            self.zoom(0.8 if dy > 0 else 1.25, self.ms_of(e.position().x()))
        e.accept()


# ---------------------------------------------------------------- hộp thoại đoạn phát
EDITOR_STYLE = """
QDialog { background:#ececec; }
QLabel#title { font-size:12pt; font-weight:700; }
QLabel#hint, QLabel#info { color:#7a7a7a; }
QLineEdit#time { background:white; border:1px solid #cfcfcf; border-radius:5px; padding:4px 8px;
                 font-family:Consolas; font-size:11pt; min-width:150px; }
QLineEdit#time:focus { border:1px solid #2563eb; }
QPushButton { background:white; border:1px solid #cfcfcf; border-radius:5px; padding:4px 12px; min-height:22px; }
QPushButton:hover { background:#f3f4f6; }
QPushButton#save { background:#2563eb; color:white; border-color:#1d4ed8; min-width:100px; }
QSlider::groove:horizontal { height:6px; background:#d4d4d4; border-radius:3px; }
QSlider::sub-page:horizontal { background:#2563eb; border-radius:3px; }
QSlider::handle:horizontal { width:16px; height:16px; margin:-6px 0; border-radius:8px; background:#2563eb; }
QSlider#scroll::sub-page:horizontal { background:#d4d4d4; }
QSlider#scroll::handle:horizontal { background:#d4d4d4; border:1px solid #bdbdbd; width:26px; }
"""


class SegmentEditor(QDialog):
    """Chọn đoạn phát. Trả về (start_ms, end_ms) với end_ms = 0 nghĩa là tới cuối file."""

    def __init__(self, parent, name, path, duration_ms, start_ms, end_ms, pre_deck):
        super().__init__(parent)
        self.setWindowTitle(f"Đoạn phát: {name}")
        self.setStyleSheet(EDITOR_STYLE)
        self.resize(1180, 600)
        self.path, self.pre = path, pre_deck
        self.dur = max(1, int(duration_ms or 1))
        self.s = int(start_ms)
        self.e = int(end_ms) if end_ms else self.dur
        self._previewing = False

        v = QVBoxLayout(self)
        v.setContentsMargins(22, 14, 22, 14)
        v.setSpacing(8)
        t = QLabel(f"Đoạn phát: {name}")
        t.setObjectName("title")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)
        self.wave = WaveformView(self.dur)
        self.wave.set_markers(self.s, self.e)
        self.wave.markersChanged.connect(self.on_markers)
        self.wave.viewChanged.connect(self.on_view)
        v.addWidget(self.wave, 1)

        row = QHBoxLayout()
        for text, fn in (("Soi điểm đầu", lambda: self.wave.set_view(self.s - 1000, self.s + 4000)),
                         ("Soi điểm cuối", lambda: self.wave.set_view(self.e - 4000, self.e + 1000)),
                         ("+", lambda: self.wave.zoom(0.5)), ("-", lambda: self.wave.zoom(2)),
                         ("Cả bài", lambda: self.wave.set_view(0, self.dur))):
            b = QPushButton(text)
            b.setAutoDefault(False)
            b.clicked.connect(fn)
            row.addWidget(b)
        self.scroll = QSlider(Qt.Orientation.Horizontal)
        self.scroll.setObjectName("scroll")
        self.scroll.valueChanged.connect(self.on_scroll)
        row.addWidget(self.scroll, 1)
        v.addLayout(row)
        row = QHBoxLayout()
        hint = QLabel("Cuộn chuột trên sóng để phóng to, thu nhỏ. Shift + cuộn để kéo ngang. "
                      "Bấm hoặc kéo trên sóng để dời mốc gần nhất.")
        hint.setObjectName("hint")
        row.addWidget(hint, 1)
        self.lbl_view = QLabel()
        self.lbl_view.setObjectName("hint")
        row.addWidget(self.lbl_view)
        v.addLayout(row)

        g = QGridLayout()
        g.setHorizontalSpacing(10)
        self.sl_s, self.ed_s = self._point_row(g, 0, "Điểm bắt đầu", "s", (-100, -10, 10, 100, 1000))
        self.sl_e, self.ed_e = self._point_row(g, 1, "Điểm kết thúc", "e", (-1000, -100, -10, 10, 100))
        g.setColumnStretch(1, 1)
        v.addLayout(g)

        row = QHBoxLayout()
        for text, fn in (("▶  Nghe từ điểm đầu", lambda: self.preview(self.s)),
                         ("▶  Nghe 5 giây cuối", lambda: self.preview(max(self.s, self.e - 5000))),
                         ("■  Dừng", self.stop_preview), ("Đặt lại", self.reset)):
            b = QPushButton(text)
            b.setAutoDefault(False)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch()
        self.lbl_len = QLabel()
        self.lbl_len.setObjectName("info")
        row.addWidget(self.lbl_len)
        v.addLayout(row)

        row = QHBoxLayout()
        row.addStretch()
        b_back = QPushButton("Quay lại")
        b_save = QPushButton("Lưu")
        b_save.setObjectName("save")
        for b in (b_back, b_save):
            b.setAutoDefault(False)
            row.addWidget(b)
        b_back.clicked.connect(self.reject)
        b_save.clicked.connect(self.accept)
        v.addLayout(row)

        self.timer = QTimer(self)
        self.timer.setInterval(30)
        self.timer.timeout.connect(self.on_timer)
        self.sync()
        self.on_view()
        self.loader = WaveformLoader(path, self)
        self.loader.done.connect(self.on_loaded)
        self.loader.progress.connect(lambda ms: (setattr(self.wave, "message",
                                                         f"Đang đọc dạng sóng... {fmt_short(ms)}"),
                                                 self.wave.update()))
        self.loader.start()

    def _point_row(self, g, r, label, which, nudges):
        g.addWidget(QLabel(label), r, 0)
        sl = QSlider(Qt.Orientation.Horizontal)
        sl.setRange(0, self.dur)
        sl.valueChanged.connect(lambda val, w=which: self.set_point(w, val, from_slider=True))
        g.addWidget(sl, r, 1)
        ed = QLineEdit()
        ed.setObjectName("time")
        ed.editingFinished.connect(lambda w=which, ed=ed: self.on_edit(w, ed))
        g.addWidget(ed, r, 2)
        for i, d in enumerate(nudges):
            sec = d / 1000
            b = QPushButton(f"{sec:+g}")
            b.setAutoDefault(False)
            b.clicked.connect(lambda _c=False, w=which, d=d: self.set_point(w, (self.s if w == "s" else self.e) + d))
            g.addWidget(b, r, 3 + i)
        return sl, ed

    # ----- đồng bộ giá trị
    def set_point(self, which, ms, from_slider=False):
        ms = int(max(0, min(self.dur, ms)))
        if which == "s":
            self.s = min(ms, self.e - 100)
        else:
            self.e = max(ms, self.s + 100)
        self.wave.set_markers(self.s, self.e)
        self.sync(skip_slider=from_slider)

    def on_markers(self, s, e):
        self.s, self.e = s, e
        self.sync()

    def on_edit(self, which, ed):
        ms = parse_time(ed.text())
        if ms is None:
            self.sync()
            return
        self.set_point(which, ms)

    def sync(self, skip_slider=False):
        for sl, val in ((self.sl_s, self.s), (self.sl_e, self.e)):
            if not (skip_slider and sl.isSliderDown()):
                sl.blockSignals(True)
                sl.setRange(0, self.dur)
                sl.setValue(val)
                sl.blockSignals(False)
        for ed, val in ((self.ed_s, self.s), (self.ed_e, self.e)):
            if not ed.hasFocus():
                ed.setText(fmt_cs(val))
        self.lbl_len.setText(f"Độ dài đoạn phát: {fmt_short(self.e - self.s)} / cả file: {fmt_short(self.dur)}")

    def on_view(self):
        w = self.wave
        span = w.ve - w.vs
        self.scroll.blockSignals(True)
        self.scroll.setRange(0, max(0, self.dur - span))
        self.scroll.setPageStep(max(1, span))
        self.scroll.setValue(w.vs)
        self.scroll.setEnabled(not w.full_view())
        self.scroll.blockSignals(False)
        self.lbl_view.setText("Đang xem cả bài" if w.full_view() else
                              f"Đang xem {fmt_short(w.vs)} – {fmt_short(w.ve)} ({span / 1000:.1f} giây)")

    def on_scroll(self, val):
        span = self.wave.ve - self.wave.vs
        self.wave.set_view(val, val + span)

    def on_loaded(self, data):
        self.wave.set_data(data)
        if data:
            self.dur = self.wave.duration
            self.e = min(self.e, self.dur)
            self.s = min(self.s, self.e - 100)
            self.wave.set_markers(self.s, self.e)
        self.sync()
        self.on_view()

    def reset(self):
        self.s, self.e = 0, self.dur
        self.wave.set_markers(self.s, self.e)
        self.sync()

    # ----- nghe thử
    def preview(self, from_ms):
        if not self.pre:
            return
        self.pre.load(self.path)
        self.pre.play_from(int(from_ms))
        self._previewing = True
        self.timer.start()

    def stop_preview(self):
        if self.pre and self._previewing:
            self.pre.stop()
        self._previewing = False
        self.timer.stop()
        self.wave.playhead = None
        self.wave.update()

    def on_timer(self):
        pos = self.pre.position()
        self.wave.playhead = pos
        self.wave.update()
        if pos >= self.e or not (self.pre.is_playing() or self.pre._pending):
            if pos >= self.e:
                self.stop_preview()

    def done(self, r):
        self.stop_preview()
        self.loader.stop()
        super().done(r)

    def result_points(self):
        end = 0 if self.e >= self.dur - 5 else self.e
        return self.s, end
