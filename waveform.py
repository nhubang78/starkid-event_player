"""Dạng sóng + trình chọn đoạn phát (điểm bắt đầu / kết thúc) cho một kênh."""
import hashlib
import os
import queue
import re
import struct
import threading
from array import array

from PySide6.QtCore import QLineF, QObject, QPointF, QRectF, QStandardPaths, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSlider, QVBoxLayout, QWidget)

from theme import T

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


RATE = 8000          # giải mã xuống 8 kHz mono — đủ để vẽ sóng, rất nhanh
_MAGIC = b"EPW1"


def _cache_file(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = hashlib.sha1(f"{os.path.abspath(path)}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8")).hexdigest()
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    d = os.path.join(base, "waves")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, key + ".wav.peaks")


def load_cached(path):
    """Lấy dạng sóng đã lưu (bộ nhớ hoặc ổ đĩa); None nếu chưa có."""
    if path in _CACHE:
        return _CACHE[path]
    f = _cache_file(path)
    if not f or not os.path.isfile(f):
        return None
    try:
        with open(f, "rb") as fh:
            magic, n, bucket_ms, dur = struct.unpack("<4sIdd", fh.read(24))
            if magic != _MAGIC:
                return None
            mins, maxs = array("h"), array("h")
            mins.frombytes(fh.read(n * 2))
            maxs.frombytes(fh.read(n * 2))
        if len(mins) != n or len(maxs) != n:
            return None
        data = WaveData(mins, maxs, bucket_ms, dur)
        _CACHE[path] = data
        return data
    except (OSError, struct.error):
        return None


def _save_cached(path, data):
    _CACHE[path] = data
    f = _cache_file(path)
    if not f:
        return
    try:
        with open(f + ".tmp", "wb") as fh:
            fh.write(struct.pack("<4sIdd", _MAGIC, len(data.mins), data.bucket_ms, data.duration))
            fh.write(data.mins.tobytes())
            fh.write(data.maxs.tobytes())
        os.replace(f + ".tmp", f)
    except OSError:
        pass


def compute_wave(path, progress=None, cancel=None):
    """Giải mã file bằng PyAV (FFmpeg) và tính đỉnh sóng. Trả về WaveData hoặc None."""
    import av
    samples = array("h")
    with av.open(path) as c:
        st = next((x for x in c.streams if x.type == "audio"), None)
        if st is None:
            return None
        st.thread_type = "AUTO"
        total = (float(st.duration * st.time_base) if st.duration else (c.duration or 0) / 1e6) * RATE
        rs = av.AudioResampler(format="s16", layout="mono", rate=RATE)
        k = 0
        for fr in c.decode(st):
            for r in rs.resample(fr):
                samples.frombytes(bytes(r.planes[0])[: r.samples * 2])
            k += 1
            if k % 200 == 0:
                if cancel is not None and cancel.is_set():
                    return None
                if progress and total:
                    progress(min(99, int(len(samples) * 100 / total)))
        for r in rs.resample(None):
            samples.frombytes(bytes(r.planes[0])[: r.samples * 2])
    n = len(samples)
    if n == 0:
        return None
    step = RATE * BUCKET_MS // 1000
    mv = memoryview(samples)
    mins, maxs = array("h"), array("h")
    for i in range(0, n, step):
        seg = mv[i:i + step]
        mins.append(min(seg))
        maxs.append(max(seg))
    data = WaveData(mins, maxs, step * 1000 / RATE, n * 1000 / RATE)
    _save_cached(path, data)
    return data


class WaveformLoader(QObject):
    """Đọc dạng sóng trong luồng nền; báo % tiến độ và kết quả."""
    done = Signal(object)        # WaveData hoặc None
    progress = Signal(int)       # %

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = path
        self._cancel = threading.Event()

    def start(self):
        data = load_cached(self.path)
        if data is not None:
            QTimer.singleShot(0, lambda: self.done.emit(data))
            return
        threading.Thread(target=self._run, daemon=True).start()

    def stop(self):
        self._cancel.set()

    def _run(self):
        try:
            data = compute_wave(self.path, lambda pc: self._emit(self.progress, pc), self._cancel)
        except Exception:
            data = None
        self._emit(self.done, data)

    def _emit(self, sig, value):
        if self._cancel.is_set():
            return
        try:
            sig.emit(value)
        except RuntimeError:      # hộp thoại đã đóng
            pass


# ----- đọc trước dạng sóng khi nạp nhạc vào kênh (1 luồng nền, lần lượt)
_prefetch_q = queue.Queue()
_prefetch_started = False


def prefetch(path):
    global _prefetch_started
    if not path or path in _CACHE:
        return
    _prefetch_q.put(path)
    if not _prefetch_started:
        _prefetch_started = True
        threading.Thread(target=_prefetch_worker, daemon=True).start()


def _prefetch_worker():
    while True:
        path = _prefetch_q.get()
        try:
            if os.path.isfile(path) and load_cached(path) is None:
                compute_wave(path)
        except Exception:
            pass


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
        p.fillRect(self.rect(), QColor(T["wave_bg"]))
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
                p.setPen(QColor(T["wave_grid"]))
                p.drawLine(QPointF(x, top), QPointF(x, h))
                p.setPen(QColor(T["wave_ruler"]))
                p.drawLine(QPointF(x, 0), QPointF(x, top))
                lab = fmt_short(t) if tick < 1000 else f"{int(t // 60000)}:{int(t // 1000 % 60):02d}"
                p.drawText(QPointF(x + 3, 15), lab)
            t += tick
        p.setPen(QColor(T["wave_grid"]))
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
            p.setPen(QPen(QColor(T["wave"]), 1))
            p.drawLines(lines)
        elif self.message:
            p.setPen(QColor(T["text_dim"]))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
        # vùng ngoài đoạn phát: làm mờ
        xs, xe = self.x_of(self.start_ms), self.x_of(self.end_ms)
        dim = QColor(*T["wave_dim"])
        if xs > 0:
            p.fillRect(QRectF(0, top + 1, min(w, xs), h - top), dim)
        if xe < w:
            p.fillRect(QRectF(max(0, xe), top + 1, w - max(0, xe), h - top), dim)
        # mốc
        for x in (xs, xe):
            if -2 <= x <= w + 2:
                p.setPen(QPen(QColor(T["accent"]), 2))
                p.drawLine(QPointF(x, top), QPointF(x, h))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(T["accent"]))
                p.drawPolygon(QPolygonF([QPointF(x - 6, top), QPointF(x + 6, top), QPointF(x, top + 8)]))
        if self.playhead is not None:
            x = self.x_of(self.playhead)
            p.setPen(QPen(QColor(T["danger"]), 1.5))
            p.drawLine(QPointF(x, top), QPointF(x, h))
        p.setPen(QColor(T["border_strong"]))
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
EDITOR_STYLE = ""   # màu lấy từ stylesheet chung (theme.py)


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
        self.loader.progress.connect(lambda pc: (setattr(self.wave, "message", f"Đang đọc dạng sóng... {pc}%"),
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
