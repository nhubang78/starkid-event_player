"""Bảng chỉnh bài: dạng sóng của kênh đang chọn (zoom, tua, chọn đoạn), BPM + lưới nhịp,
điểm CUE, cắt IN / OUT (= đoạn phát của kênh), LOOP A-B / 1-2-4-8 giây / vùng chọn, nghe trước."""
import math

import numpy as np
from PySide6.QtCore import QLineF, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen, QPolygonF
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy, QSlider,
                               QToolButton, QVBoxLayout, QWidget)

from theme import T, channel_dot
from waveform import WaveformLoader
from widgets import shape_icon

PLAYED_DEFAULT = "#f59e0b"
MAX_CUES = 9


def tfmt(ms, tenths=True):
    """ms -> 'MM:SS.d' (hoặc H:MM:SS.d khi dài hơn 1 giờ)."""
    ms = max(0, int(ms))
    s = ms // 1000
    d = (ms % 1000) // 100
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    base = f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
    return f"{base}.{d}" if tenths else base


# ------------------------------------------------------------------ dò BPM
def detect_bpm(data):
    """Ước lượng nhịp (BPM) và vị trí phách đầu (ms) từ dữ liệu sóng (đỉnh 5 ms)."""
    try:
        mn = np.frombuffer(data.mins, dtype=np.int16).astype(np.float32)
        mx = np.frombuffer(data.maxs, dtype=np.int16).astype(np.float32)
    except (TypeError, ValueError):
        return 0.0, 0
    fs = 1000.0 / data.bucket_ms
    n = min(mn.size, int(fs * 240))                    # tối đa 4 phút đầu là đủ
    if n < fs * 8:
        return 0.0, 0
    env = np.log1p(60 * (mx[:n] - mn[:n]) / 65536.0)
    onset = np.maximum(0.0, np.diff(env))
    k = int(fs * 0.5)
    onset = np.maximum(0.0, onset - np.convolve(onset, np.ones(k) / k, mode="same"))
    m = onset.size
    spec = np.fft.rfft(onset, 2 * m)
    ac = np.fft.irfft(spec * np.conj(spec))[:m]
    lmin, lmax = int(60 * fs / 200), int(60 * fs / 60) + 1
    if lmax + 2 >= m:
        return 0.0, 0
    lags = np.arange(lmin, lmax)
    bpms = 60 * fs / lags
    score = ac[lmin:lmax] * np.exp(-0.5 * (np.log2(bpms / 120.0) / 0.9) ** 2)   # ưu tiên quanh 120 BPM
    i = int(np.argmax(score))
    lag = float(lags[i])
    if 0 < i < score.size - 1:
        a, b, c = score[i - 1], score[i], score[i + 1]
        den = a - 2 * b + c
        if den != 0:
            lag += 0.5 * (a - c) / den
    # tránh nhầm nửa nhịp: nhịp gấp đôi vẫn tương quan mạnh -> chọn nhịp gấp đôi
    if 60 * fs / lag < 100:
        h = lag / 2
        hi = int(round(h))
        if hi - 1 >= lmin and float(ac[hi - 1:hi + 2].max()) >= 0.6 * float(ac[int(round(lag))]):
            lag = h

    # dò tinh: thử các bước nhịp sát nhau + mọi pha, chọn lưới khớp onset nhất
    best, best_lag, off = -1.0, lag, 0
    for L in np.linspace(lag * 0.99, lag * 1.01, 41):
        nb = int((m - 1) // L)
        if nb < 4:
            continue
        phases = np.arange(int(np.ceil(L)))[:, None]
        idx = (phases + np.arange(nb)[None, :] * L).astype(int)
        idx = np.minimum(idx, m - 1)
        sums = onset[idx].sum(axis=1)
        p = int(np.argmax(sums))
        if sums[p] > best:
            best, best_lag, off = float(sums[p]), float(L), p
    bpm = 60 * fs / best_lag
    return round(bpm, 1), int((off + 1) * data.bucket_ms)       # +1: onset là hiệu giữa 2 mẫu


# ------------------------------------------------------------------ khung sóng
class DeckWave(QWidget):
    seekRequested = Signal(int)
    inOutChanged = Signal(int, int)       # start_ms, end_ms (0 = cuối file)
    viewChanged = Signal()
    menuRequested = Signal(int, object)   # ms, vị trí toàn cục
    centerRequested = Signal(int)         # (khung tổng quan) dời khung xem tới ms

    RULER = 18

    def __init__(self, overview=False):
        super().__init__()
        self.overview = overview
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(40 if overview else 124)
        self.mins = self.maxs = None
        self.bucket = 5.0
        self.duration = 1
        self.vs, self.ve = 0, 1
        self.pos = 0
        self.playing = False
        self.start_ms, self.end_ms = 0, 0
        self.cues = []
        self.loop = (0, 0, False)
        self.sel = None
        self.bpm, self.beat_off, self.grid = 0.0, 0, False
        self.played_color = QColor(PLAYED_DEFAULT)
        self.title = ""
        self.message = "Chọn một kênh có nhạc để chỉnh"
        self.view_win = None              # (vs, ve) của khung chính — chỉ dùng ở khung tổng quan
        self._cols = None
        self._cols_key = None
        self._drag = None
        self._press = None
        self.hover_ms = None

    # ---------- dữ liệu
    def set_data(self, data, duration):
        if data is not None:
            self.mins = np.frombuffer(data.mins, dtype=np.int16).astype(np.float32) / 32768.0
            self.maxs = np.frombuffer(data.maxs, dtype=np.int16).astype(np.float32) / 32768.0
            self.bucket = float(data.bucket_ms)
            self.duration = max(1, int(duration or data.duration))
            self.message = ""
        else:
            self.mins = self.maxs = None
            self.duration = max(1, int(duration or 1))
        self._cols_key = None
        self.update()

    def set_view(self, vs, ve):
        span = max(300, min(self.duration, int(ve - vs)))
        vs = max(0, min(int(vs), self.duration - span))
        if (vs, vs + span) != (self.vs, self.ve):
            self.vs, self.ve = vs, vs + span
            self.update()
            self.viewChanged.emit()

    def zoom(self, factor, center=None):
        span = self.ve - self.vs
        c = (self.vs + self.ve) / 2 if center is None else center
        rel = (c - self.vs) / span if span else 0.5
        new = span * factor
        self.set_view(c - new * rel, c - new * rel + new)

    def x_of(self, ms):
        return (ms - self.vs) / max(1, self.ve - self.vs) * self.width()

    def ms_of(self, x):
        return int(self.vs + x / max(1, self.width()) * (self.ve - self.vs))

    def _end(self):
        return self.end_ms if self.end_ms else self.duration

    # ---------- vẽ
    def _columns(self, w):
        key = (self.vs, self.ve, w, id(self.mins))
        if key == self._cols_key:
            return self._cols
        n = self.mins.size
        i0 = self.vs / self.bucket
        i1 = self.ve / self.bucket
        per = (i1 - i0) / max(1, w)
        if per >= 1:
            edges = np.clip(np.linspace(i0, i1, w + 1).astype(int), 0, n)
            starts = np.minimum(edges[:-1], n - 1)
            lo = np.minimum.reduceat(self.mins, starts)
            hi = np.maximum.reduceat(self.maxs, starts)
            empty = edges[:-1] >= n
            lo[empty] = hi[empty] = 0
        else:
            idx = np.clip((i0 + (np.arange(w) + 0.5) * per).astype(int), 0, n - 1)
            lo, hi = self.mins[idx], self.maxs[idx]
            lo = np.where(np.arange(w) * per + i0 >= n, 0, lo)
            hi = np.where(np.arange(w) * per + i0 >= n, 0, hi)
        self._cols, self._cols_key = (lo, hi), key
        return self._cols

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        full = QRectF(0.5, 0.5, w - 1, h - 1)
        p.setPen(QPen(self.played_color if self.playing else QColor(T["border_strong"]), 1.5 if self.playing else 1))
        p.setBrush(QColor(T["wave_bg"]))
        p.drawRoundedRect(full, 8, 8)
        ruler = 0 if self.overview else self.RULER
        top, bot = 4, h - ruler - 4
        mid, half = (top + bot) / 2, (bot - top) / 2
        p.setClipRect(QRectF(1, 1, w - 2, h - 2))
        f = QFont("Consolas")
        f.setPixelSize(10)
        p.setFont(f)
        # lưới thời gian
        if not self.overview:
            span = self.ve - self.vs
            steps = [100, 250, 500, 1000, 2000, 5000, 10000, 15000, 30000, 60000, 120000, 300000]
            tick = next((s for s in steps if s / span * w >= 80), steps[-1])
            t = (self.vs // tick) * tick
            while t <= self.ve:
                x = self.x_of(t)
                if x >= 0:
                    p.setPen(QPen(QColor(T["wave_grid"]), 1))
                    p.drawLine(QPointF(x, top), QPointF(x, bot))
                    p.setPen(QColor(T["wave_ruler"]))
                    p.drawLine(QPointF(x, h - ruler), QPointF(x, h - ruler + 4))
                    lab = tfmt(t, tick < 1000)
                    p.drawText(QPointF(x + 3, h - 5), lab)
                t += tick
        # lưới nhịp
        if self.grid and self.bpm > 0 and not self.overview:
            beat = 60000.0 / self.bpm
            if beat / max(1, self.ve - self.vs) * w >= 5:
                k0 = math.floor((self.vs - self.beat_off) / beat)
                k = k0
                while True:
                    t = self.beat_off + k * beat
                    if t > self.ve:
                        break
                    x = self.x_of(t)
                    bar = k % 4 == 0
                    c = QColor(T["accent"])
                    c.setAlpha(150 if bar else 60)
                    p.setPen(QPen(c, 1.6 if bar else 1))
                    p.drawLine(QPointF(x, top), QPointF(x, bot))
                    k += 1
        # sóng
        if self.mins is not None:
            lo, hi = self._columns(w)
            xp = self.x_of(self.pos)
            played, rest = [], []
            for x in range(w):
                y1, y2 = mid - hi[x] * half, mid - lo[x] * half + 1
                (played if x < xp else rest).append(QLineF(x + .5, y1, x + .5, y2))
            p.setPen(QPen(self.played_color, 1))
            p.drawLines(played)
            p.setPen(QPen(QColor(T["text_faint"]), 1))
            p.drawLines(rest)
        elif self.message:
            p.setPen(QColor(T["text_faint"]))
            f2 = QFont("Segoe UI")
            f2.setPixelSize(13)
            p.setFont(f2)
            p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, self.message)
            p.setFont(f)
        # ngoài vùng IN / OUT: làm mờ
        dim = QColor(T["wave_bg"])
        dim.setAlpha(170)
        xs, xe = self.x_of(self.start_ms), self.x_of(self._end())
        if xs > 0:
            p.fillRect(QRectF(0, 0, xs, h - ruler), dim)
        if xe < w:
            p.fillRect(QRectF(xe, 0, w - xe, h - ruler), dim)
        # vùng loop A-B
        a, b, on = self.loop
        if b > a:
            c = QColor("#a855f7")
            c.setAlpha(70 if on else 30)
            xa, xb = self.x_of(a), self.x_of(b)
            p.fillRect(QRectF(xa, top, xb - xa, bot - top), c)
            c.setAlpha(230 if on else 120)
            p.setPen(QPen(c, 1.5))
            for x, lab in ((xa, "A"), (xb, "B")):
                p.drawLine(QPointF(x, top), QPointF(x, bot))
                if not self.overview:
                    p.fillRect(QRectF(x - 6 if lab == "B" else x, top, 12, 13), c)
                    p.setPen(QColor("white"))
                    p.drawText(QRectF(x - 6 if lab == "B" else x, top, 12, 13), Qt.AlignmentFlag.AlignCenter, lab)
                    p.setPen(QPen(c, 1.5))
        # vùng đang chọn
        if self.sel and not self.overview:
            c = QColor(T["accent"])
            c.setAlpha(55)
            xa, xb = self.x_of(min(self.sel)), self.x_of(max(self.sel))
            p.fillRect(QRectF(xa, top, xb - xa, bot - top), c)
        # IN / OUT
        for x, col, lab in ((xs, T["ok"], "IN"), (xe, T["danger"], "OUT")):
            if -2 <= x <= w + 2:
                c = QColor(col)
                p.setPen(QPen(c, 2))
                p.drawLine(QPointF(x, 0), QPointF(x, h - ruler))
                if not self.overview:
                    tw = 26 if lab == "OUT" else 18
                    r = QRectF(x if lab == "IN" else x - tw, bot - 14, tw, 14)
                    p.fillRect(r, c)
                    p.setPen(QColor("white"))
                    p.drawText(r, Qt.AlignmentFlag.AlignCenter, lab)
        # CUE
        for i, cm in enumerate(self.cues):
            x = self.x_of(cm)
            if -10 <= x <= w + 10:
                c = QColor(T["ok"])
                p.setPen(QPen(c, 1, Qt.PenStyle.DashLine))
                p.drawLine(QPointF(x, top), QPointF(x, bot))
                if not self.overview:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(c)
                    p.drawEllipse(QPointF(x, top + 8), 7, 7)
                    p.setPen(QColor("white"))
                    p.drawText(QRectF(x - 7, top + 1, 14, 14), Qt.AlignmentFlag.AlignCenter, str(i + 1))
        # khung xem (ở dải tổng quan)
        if self.overview and self.view_win:
            vx0, vx1 = self.x_of(self.view_win[0]), self.x_of(self.view_win[1])
            c = QColor(T["accent"])
            c.setAlpha(40)
            p.setBrush(c)
            c.setAlpha(220)
            p.setPen(QPen(c, 1.5))
            p.drawRoundedRect(QRectF(vx0, 1.5, max(3.0, vx1 - vx0), h - 3), 3, 3)
        # đầu phát
        xp = self.x_of(self.pos)
        if -2 <= xp <= w + 2:
            p.setPen(QPen(QColor(T["text"]), 1.6))
            p.drawLine(QPointF(xp, 0), QPointF(xp, h - ruler))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T["text"]))
            p.drawPolygon(QPolygonF([QPointF(xp - 5, 0), QPointF(xp + 5, 0), QPointF(xp, 7)]))
        # tiêu đề góc trên trái
        if self.title and not self.overview:
            tw = p.fontMetrics().horizontalAdvance(self.title) + 14
            r = QRectF(6, 5, tw, 16)
            bg = QColor(T["wave_bg"])
            bg.setAlpha(200)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, 4, 4)
            p.setPen(self.played_color)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.title)
        # vị trí chuột
        if self.hover_ms is not None and not self.overview and self.mins is not None:
            x = self.x_of(self.hover_ms)
            c = QColor(T["text_dim"])
            c.setAlpha(120)
            p.setPen(QPen(c, 1, Qt.PenStyle.DotLine))
            p.drawLine(QPointF(x, top), QPointF(x, bot))

    # ---------- chuột / phím
    def _near_handle(self, x):
        if self.overview:
            return None
        for name, ms in (("in", self.start_ms), ("out", self._end())):
            if abs(x - self.x_of(ms)) <= 6:
                return name
        return None

    def mousePressEvent(self, e):
        if self.mins is None:
            return
        x = e.position().x()
        if e.button() == Qt.MouseButton.RightButton:
            self.menuRequested.emit(self.ms_of(x), e.globalPosition().toPoint())
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.overview:
            self.centerRequested.emit(self.ms_of(x))
            self._drag = "view"
            return
        self._drag = self._near_handle(x)
        self._press = x

    def mouseMoveEvent(self, e):
        x = e.position().x()
        ms = max(0, min(self.duration, self.ms_of(x)))
        if not self.overview:
            self.hover_ms = ms
        if self._drag == "view":
            self.centerRequested.emit(ms)
        elif self._drag == "in":
            self.start_ms = min(ms, self._end() - 100)
            self.inOutChanged.emit(self.start_ms, self.end_ms)
        elif self._drag == "out":
            end = max(ms, self.start_ms + 100)
            self.end_ms = 0 if end >= self.duration - 5 else end
            self.inOutChanged.emit(self.start_ms, self.end_ms)
        elif self._press is not None and abs(x - self._press) > 4:
            self.sel = (self.ms_of(self._press), ms)
        else:
            self.setCursor(Qt.CursorShape.SizeHorCursor if self._near_handle(x) else Qt.CursorShape.IBeamCursor
                           if not self.overview else Qt.CursorShape.PointingHandCursor)
        self.update()

    def leaveEvent(self, e):
        self.hover_ms = None
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._drag is None and self._press is not None and not self.overview:
            if abs(e.position().x() - self._press) <= 4:
                self.sel = None
                self.seekRequested.emit(self.ms_of(e.position().x()))
        self._drag = self._press = None
        self.update()

    def wheelEvent(self, e):
        if self.overview or self.mins is None:
            return
        dy = e.angleDelta().y() or e.angleDelta().x()
        if not dy:
            return
        span = self.ve - self.vs
        if e.modifiers() & Qt.KeyboardModifier.ShiftModifier or e.angleDelta().x():
            shift = -span * 0.15 * (1 if dy > 0 else -1)
            self.set_view(self.vs + shift, self.ve + shift)
            self.viewChanged.emit()
        else:
            self.zoom(0.8 if dy > 0 else 1.25, self.ms_of(e.position().x()))
        e.accept()

    def keyPressEvent(self, e):
        if self.hover_ms is not None and e.key() in (Qt.Key.Key_I, Qt.Key.Key_O):
            if e.key() == Qt.Key.Key_I:
                self.start_ms = min(self.hover_ms, self._end() - 100)
            else:
                self.end_ms = max(self.hover_ms, self.start_ms + 100)
                if self.end_ms >= self.duration - 5:
                    self.end_ms = 0
            self.inOutChanged.emit(self.start_ms, self.end_ms)
            self.update()
            return
        super().keyPressEvent(e)


# ------------------------------------------------------------------ bảng chỉnh bài
class DeckEditor(QFrame):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.strip = None
        self.cursor_ms = 0
        self.follow = True
        self.loader = None
        self._wave_path = None
        self._busy = False
        self.setObjectName("deckEditor")
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(8)

        # ---- đầu bảng
        head = QHBoxLayout()
        head.setSpacing(10)
        self.btn_fold = QToolButton()
        self.btn_fold.setObjectName("deFold")
        self.btn_fold.setCheckable(True)
        self.btn_fold.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_fold.setToolTip("Thu gọn / mở bảng chỉnh bài")
        self.btn_fold.toggled.connect(self.set_folded)
        head.addWidget(self.btn_fold)
        self.lbl_title = QLabel("Bảng chỉnh bài")
        self.lbl_title.setObjectName("deTitle")
        self.lbl_title.setMaximumWidth(560)
        head.addWidget(self.lbl_title)
        self.lbl_ch = QLabel("")
        self.lbl_ch.setObjectName("deSub")
        head.addWidget(self.lbl_ch)
        head.addStretch(1)
        bpm_box = QVBoxLayout()
        bpm_box.setSpacing(0)
        row = QHBoxLayout()
        row.setSpacing(6)
        cap = QLabel("BPM")
        cap.setObjectName("deCap")
        row.addWidget(cap)
        self.lbl_bpm = QLabel("–")
        self.lbl_bpm.setObjectName("deBpm")
        row.addWidget(self.lbl_bpm)
        self.btn_auto = QToolButton()
        self.btn_auto.setObjectName("deLink")
        self.btn_auto.setText("Dùng tự động")
        self.btn_auto.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_auto.setToolTip("Bỏ BPM chỉnh tay, dùng BPM tự dò từ bài")
        self.btn_auto.clicked.connect(self.bpm_auto)
        row.addWidget(self.btn_auto)
        bpm_box.addLayout(row)
        self.sld_bpm = QSlider(Qt.Orientation.Horizontal)
        self.sld_bpm.setRange(60, 200)
        self.sld_bpm.setFixedWidth(170)
        self.sld_bpm.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sld_bpm.setToolTip("Chỉnh BPM bằng tay (dùng cho lưới nhịp)")
        self.sld_bpm.valueChanged.connect(self.bpm_manual)
        bpm_box.addWidget(self.sld_bpm)
        head.addLayout(bpm_box)
        head.addSpacing(14)
        self.t_el, self.t_rem, self.t_tot = self._time(head, "ĐÃ CHẠY"), self._time(head, "CÒN LẠI", "remain"), \
            self._time(head, "TỔNG")
        root.addLayout(head)

        # ---- thân (thu gọn được)
        self.body = QWidget()
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(0, 0, 0, 0)
        bl.setSpacing(6)
        self.overview = DeckWave(overview=True)
        self.overview.centerRequested.connect(self.center_view)
        self.overview.menuRequested.connect(self.wave_menu)
        self.overview.hide()
        bl.addWidget(self.overview)
        self.wave = DeckWave()
        self.wave.seekRequested.connect(self.seek)
        self.wave.inOutChanged.connect(self.set_in_out)
        self.wave.menuRequested.connect(self.wave_menu)
        self.wave.viewChanged.connect(self.view_changed)
        bl.addWidget(self.wave)
        self.btn_grid = QPushButton("Soi nhịp", self.wave)
        self.btn_grid.setObjectName("deGrid")
        self.btn_grid.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_grid.setToolTip("Mở cửa sổ Soi nhịp: nhạc cụ (Kick, Snare, Clap, Hi-hat, Bass, Giọng hát), "
                                 "phách, ô nhịp, đoạn, điểm Drop, Hot Cue")
        self.btn_grid.clicked.connect(self.open_scope)
        self.scope = None
        self.wave.installEventFilter(self)

        ctl = QHBoxLayout()
        ctl.setSpacing(5)
        self.b_home = self._btn(ctl, "", self.go_home, "Về điểm IN", icon="prev")
        self.b_play = self._btn(ctl, "", self.play_pause, "Phát / tạm dừng", icon="play", name="dePlay")
        self.b_stop = self._btn(ctl, "", self.stop, "Dừng", icon="stop")
        self._group(ctl, "CUE")
        self._btn(ctl, "+ Cue", self.add_cue, "Thêm điểm CUE tại vị trí hiện tại (bấm điểm để nhảy tới, chuột phải để xóa)")
        self.cue_row = QHBoxLayout()
        self.cue_row.setSpacing(4)
        ctl.addLayout(self.cue_row)
        ctl.addStretch(1)
        self._group(ctl, "ZOOM")
        self._btn(ctl, "−", lambda: self.wave.zoom(2.0), "Thu nhỏ")
        self.lbl_zoom = QLabel("1.0x")
        self.lbl_zoom.setObjectName("deZoom")
        ctl.addWidget(self.lbl_zoom)
        self._btn(ctl, "+", lambda: self.wave.zoom(0.5, self.cur()), "Phóng to quanh vị trí hiện tại")
        self._btn(ctl, "Toàn bài", self.full_view, "Xem cả bài")
        ctl.addSpacing(8)
        self.b_waves = self._btn(ctl, "☰  1 sóng", self.toggle_overview, "1 sóng / 2 sóng (thêm dải tổng quan cả bài)")
        self.b_waves.setCheckable(True)
        self.b_pre = self._btn(ctl, "🎧  Nghe trước", self.prelisten, "Nghe trước ra tai nghe từ vị trí hiện tại "
                               "(thiết bị tai nghe chọn trong Tùy chọn)")
        self.b_pre.setCheckable(True)
        bl.addLayout(ctl)

        ctl2 = QHBoxLayout()           # hàng 2: cắt + lặp
        ctl2.setSpacing(5)
        lb = QLabel("CẮT")
        lb.setObjectName("deCap")
        ctl2.addWidget(lb)
        self._btn(ctl2, "IN", self.set_in, "Đặt điểm bắt đầu phát tại vị trí hiện tại")
        self._btn(ctl2, "OUT", self.set_out, "Đặt điểm kết thúc phát tại vị trí hiện tại")
        self._btn(ctl2, "✕", self.clear_in_out, "Bỏ cắt (phát cả bài)")
        self._group(ctl2, "LOOP")
        self._btn(ctl2, "A", self.set_a, "Đặt điểm đầu vùng lặp")
        self._btn(ctl2, "B", self.set_b, "Đặt điểm cuối vùng lặp và bật lặp")
        self.b_loop = self._btn(ctl2, "⟳", self.toggle_ab, "Bật / tắt lặp vùng A-B")
        self.b_loop.setCheckable(True)
        for sec in (1, 2, 4, 8):
            self._btn(ctl2, f"{sec}s", lambda _c=False, s=sec: self.loop_len(s), f"Lặp {sec} giây từ vị trí hiện tại")
        self._btn(ctl2, "Loop vùng chọn", self.loop_selection, "Lặp đúng đoạn vừa kéo chọn trên sóng")
        self._btn(ctl2, "✕", self.clear_loop, "Bỏ vùng lặp")
        ctl2.addStretch(1)
        bl.addLayout(ctl2)
        hint = QLabel("Lăn chuột trên sóng: zoom · Shift + lăn: kéo ngang · Bấm: tua · Kéo: chọn đoạn · "
                      "Rê chuột rồi bấm  I / O : đặt IN / OUT · Kéo tay cầm IN / OUT để tinh chỉnh · Chuột phải: menu nhanh")
        hint.setObjectName("deHint")
        hint.setWordWrap(True)
        bl.addWidget(hint)
        root.addWidget(self.body)
        self.btn_fold.setChecked(self.host.settings.value("deck_folded", "false") == "true")
        self.set_folded(self.btn_fold.isChecked())
        self.retheme()
        self.set_strip(None)

    # ---------- dựng giao diện
    def _time(self, lay, cap, kind=""):
        box = QVBoxLayout()
        box.setSpacing(0)
        c = QLabel(cap)
        c.setObjectName("deCap")
        c.setAlignment(Qt.AlignmentFlag.AlignRight)
        box.addWidget(c)
        v = QLabel("--:--.-")
        v.setObjectName("deTime")
        if kind:
            v.setProperty("kind", kind)
        v.setAlignment(Qt.AlignmentFlag.AlignRight)
        box.addWidget(v)
        lay.addLayout(box)
        lay.addSpacing(10)
        return v

    def _btn(self, lay, text, fn, tip, icon=None, name="deBtn"):
        b = QPushButton(text)
        b.setObjectName(name)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setToolTip(tip)
        if icon:
            b.setProperty("icon_kind", icon)
            b.setFixedWidth(44)
        b.clicked.connect(fn)
        lay.addWidget(b)
        return b

    def _group(self, lay, text):
        lay.addSpacing(8)
        lb = QLabel(text)
        lb.setObjectName("deCap")
        lay.addWidget(lb)

    def eventFilter(self, obj, e):
        if obj is self.wave and e.type() == e.Type.Resize:
            self.btn_grid.adjustSize()
            self.btn_grid.move(self.wave.width() - self.btn_grid.width() - 8, 6)
        return False

    def retheme(self):
        for b in (self.b_home, self.b_play, self.b_stop):
            kind = b.property("icon_kind")
            if b is self.b_play:
                kind = "pause" if self.strip and self.strip.deck.is_playing() else "play"
                col = "#1a1202" if b.property("on") else T["text"]
            else:
                col = T["text"]
            b.setIcon(shape_icon(kind, col))
        self.btn_fold.setText("▸" if self.btn_fold.isChecked() else "▾")
        self.wave.update()
        self.overview.update()

    def set_folded(self, on):
        self.body.setVisible(not on)
        self.btn_fold.setText("▸" if on else "▾")
        self.host.settings.setValue("deck_folded", "true" if on else "false")

    # ---------- kênh đang chỉnh
    def set_strip(self, strip):
        old = self.strip
        self.strip = strip
        if old is not None and old is not strip:
            old.set_selected(False)
        if strip is not None:
            strip.set_selected(True)
        if old is not strip:
            self.cursor_ms = strip.start_ms if strip else 0
            self.wave.sel = None
            self.follow = True
            if self.b_pre.isChecked():
                self.b_pre.setChecked(False)
                self.host.pre.stop()
        self.load_wave()
        self.refresh()
        if self.scope is not None and self.scope.isVisible() and old is not strip:
            self.scope.set_strip(strip)

    def strip_changed(self, strip):
        """Kênh đang chỉnh vừa đổi cấu hình ở chỗ khác (cài đặt kênh, nạp file...)."""
        if strip is self.strip and not self._busy:
            self._busy = True
            try:
                self.load_wave()
                self.refresh()
            finally:
                self._busy = False

    def load_wave(self):
        s = self.strip
        path = s.path if s else ""
        if path == self._wave_path:
            return
        self._wave_path = path
        if self.loader:
            self.loader.stop()
            self.loader = None
        self.wave.set_data(None, s.duration if s else 1)
        self.overview.set_data(None, s.duration if s else 1)
        if not path:
            self.wave.message = "Kênh trống — kéo thả file nhạc vào kênh" if s else "Chọn một kênh có nhạc để chỉnh"
            self.wave.update()
            return
        self.wave.message = "Đang đọc dạng sóng..."
        self.loader = WaveformLoader(path, self)
        self.loader.progress.connect(lambda pc: (setattr(self.wave, "message", f"Đang đọc dạng sóng... {pc}%"),
                                                 self.wave.update()))
        self.loader.done.connect(lambda data, p=path: self.on_wave(p, data))
        self.loader.start()

    def on_wave(self, path, data):
        s = self.strip
        if s is None or s.path != path:
            return
        if data is None:
            self.wave.message = "Không đọc được dạng sóng của file này"
            self.wave.update()
            return
        dur = s.deck.duration() or s.duration or int(data.duration)
        if not s.duration:
            s.duration = dur
        self.wave.set_data(data, dur)
        self.overview.set_data(data, dur)
        self.overview.set_view(0, dur)
        self.wave.set_view(0, dur)
        if not s.bpm_auto:
            s.bpm_auto, s.bpm_off = detect_bpm(data)
        self.refresh()

    # ---------- vị trí hiện tại
    def active(self):
        s = self.strip
        return s is not None and (s.deck.is_playing() or s.deck.is_paused())

    def cur(self):
        return self.strip.deck.position() if self.active() else self.cursor_ms

    def bpm(self):
        s = self.strip
        return (s.bpm or s.bpm_auto) if s else 0.0

    # ---------- cập nhật hiển thị
    def refresh(self):
        s = self.strip
        loaded = bool(s and s.path)
        self.setEnabled(True)
        if s is None:
            self.lbl_title.setText("Bảng chỉnh bài")
            self.lbl_ch.setText("— bấm vào một kênh để chỉnh")
        else:
            self.lbl_title.setText(s.display_name() if loaded else f"Kênh {s.number} (trống)")
            self.lbl_ch.setText(f"Kênh {s.number}")
        for w in (self.wave, self.overview):
            w.played_color = QColor(channel_dot(s.color) if (s and s.color) else PLAYED_DEFAULT)
            if s:
                w.start_ms, w.end_ms = s.start_ms, s.end_ms
                w.cues = list(s.cues)
                w.loop = (s.loop_a, s.loop_b, s.ab_on)
            else:
                w.cues, w.loop = [], (0, 0, False)
        bpm = self.bpm()
        self.lbl_bpm.setText(f"{bpm:.0f}" if bpm else "–")
        self.sld_bpm.blockSignals(True)
        self.sld_bpm.setValue(int(round(bpm)) if bpm else 120)
        self.sld_bpm.blockSignals(False)
        self.btn_auto.setVisible(bool(s and s.bpm))
        self.wave.bpm = bpm
        self.wave.beat_off = getattr(s, "bpm_off", 0) if s else 0
        self.b_loop.blockSignals(True)
        self.b_loop.setChecked(bool(s and s.ab_on))
        self.b_loop.blockSignals(False)
        self.rebuild_cues()
        if self.scope is not None and self.scope.isVisible() and self.scope.strip is s:
            self.scope.sync_light()
        for b in self.findChildren(QPushButton):
            if b not in (self.b_waves, self.btn_grid):
                b.setEnabled(loaded)
        self.tick(force=True)

    def rebuild_cues(self):
        while self.cue_row.count():
            it = self.cue_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not self.strip:
            return
        for i, ms in enumerate(self.strip.cues):
            b = QPushButton(f"{i + 1}  {tfmt(ms)}")
            b.setObjectName("deCue")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip("Bấm: nhảy tới điểm CUE · Chuột phải: xóa")
            b.clicked.connect(lambda _c=False, ms=ms: self.jump(ms))
            b.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            b.customContextMenuRequested.connect(lambda _p, i=i: self.remove_cue(i))
            self.cue_row.addWidget(b)

    def tick(self, force=False):
        s = self.strip
        if s is None or (not force and not self.isVisible()):
            return
        dur = self.wave.duration if self.wave.mins is not None else (s.deck.duration() or s.duration or 0)
        pos = self.cur()
        playing = s.deck.is_playing()
        self.t_el.setText(tfmt(pos) if s.path else "--:--.-")
        self.t_rem.setText(tfmt(max(0, dur - pos)) if s.path else "--:--.-")
        self.t_tot.setText(tfmt(dur) if s.path else "--:--.-")
        for w in (self.wave, self.overview):
            w.pos, w.playing = pos, playing
            w.title = (f"Kênh {s.number} · {s.display_name()} · {tfmt(pos, False)} / {tfmt(dur, False)} · "
                       f"zoom {self.zoom_factor():.1f}x") if s.path else ""
        self.overview.view_win = (self.wave.vs, self.wave.ve)
        # theo đầu phát khi đang phát
        if playing and self.follow and self.wave.mins is not None:
            vs, ve = self.wave.vs, self.wave.ve
            if pos > ve - (ve - vs) * 0.1 or pos < vs:
                span = ve - vs
                self.wave.set_view(pos - span * 0.1, pos + span * 0.9)
        on = playing
        if self.b_play.property("on") != on:
            self.b_play.setProperty("on", on)
            self.b_play.style().unpolish(self.b_play)
            self.b_play.style().polish(self.b_play)
            self.retheme()
        pre = self.host.pre
        if self.b_pre.isChecked() and not pre.is_playing():
            self.b_pre.setChecked(False)
        self.wave.update()
        self.overview.update()

    def zoom_factor(self):
        return self.wave.duration / max(1, self.wave.ve - self.wave.vs)

    def view_changed(self):
        self.lbl_zoom.setText(f"{self.zoom_factor():.1f}x")
        pos = self.cur()
        if not (self.wave.vs <= pos <= self.wave.ve):
            self.follow = False            # người dùng kéo khung xem đi chỗ khác
        self.overview.view_win = (self.wave.vs, self.wave.ve)
        self.overview.update()

    def center_view(self, ms):
        span = self.wave.ve - self.wave.vs
        self.wave.set_view(ms - span / 2, ms + span / 2)

    def full_view(self):
        self.follow = True
        self.wave.set_view(0, self.wave.duration)

    def toggle_overview(self):
        on = self.b_waves.isChecked()
        self.overview.setVisible(on)
        self.b_waves.setText("☰  2 sóng" if on else "☰  1 sóng")

    def open_scope(self):
        """Mở cửa sổ Soi nhịp cho kênh đang chọn (và bật lưới nhịp trên sóng)."""
        from beatscope import BeatScope, dark_titlebar
        if self.scope is None:
            self.scope = BeatScope(self.host, self)
        self.scope.set_strip(self.strip)
        self.scope.show()
        dark_titlebar(self.scope)
        self.scope.raise_()
        self.scope.activateWindow()
        self.toggle_grid(True)

    def toggle_grid(self, on):
        self.wave.grid = on
        self.wave.update()
        if on and not self.bpm():
            self.host.statusBar().showMessage("Chưa dò được BPM của bài này — chỉnh BPM bằng thanh trượt", 4000)

    # ---------- điều khiển phát
    def changed(self):
        s = self.strip
        self._busy = True
        try:
            if s:
                s.refresh()
                s.changed.emit()
        finally:
            self._busy = False
        self.refresh()

    def seek(self, ms):
        s = self.strip
        if not s or not s.path:
            return
        ms = max(0, min(self.wave.duration, ms))
        if self.active():
            s.seek_to(ms)
        self.cursor_ms = ms
        self.follow = True
        self.tick(force=True)

    def jump(self, ms):
        self.seek(ms)

    def go_home(self):
        if self.strip:
            self.seek(self.strip.start_ms)

    def play_pause(self):
        s = self.strip
        if not s or not s.path:
            return
        pf = self.host.cfg["pause_fade_ms"]
        if s.deck.is_playing():
            s.deck.pause(pf)
        elif s.deck.is_paused():
            s.deck.play(pf)
        elif self.cursor_ms <= s.start_ms + 5:
            s.play(restart=True)
        else:
            s.play_from(self.cursor_ms)
        self.follow = True

    def stop(self):
        if self.strip:
            self.strip.stop()

    # ---------- CUE
    def add_cue(self):
        s = self.strip
        if not s or not s.path:
            return
        ms = int(self.cur())
        if any(abs(ms - c) < 100 for c in s.cues):
            return
        if len(s.cues) >= MAX_CUES:
            self.host.statusBar().showMessage(f"Tối đa {MAX_CUES} điểm CUE mỗi kênh", 3000)
            return
        s.cues = sorted(s.cues + [ms])
        self.changed()

    def remove_cue(self, i):
        s = self.strip
        if s and 0 <= i < len(s.cues):
            del s.cues[i]
            self.changed()

    # ---------- IN / OUT
    def set_in_out(self, start, end):
        s = self.strip
        if not s:
            return
        s.start_ms, s.end_ms = int(start), int(end)
        self.changed()

    def set_in(self):
        s = self.strip
        if s:
            end = s.end_ms or self.wave.duration
            self.set_in_out(min(int(self.cur()), end - 100), s.end_ms)

    def set_out(self):
        s = self.strip
        if s:
            end = max(int(self.cur()), s.start_ms + 100)
            self.set_in_out(s.start_ms, 0 if end >= self.wave.duration - 5 else end)

    def clear_in_out(self):
        self.set_in_out(0, 0)

    # ---------- LOOP
    def set_a(self):
        s = self.strip
        if s:
            s.loop_a = int(self.cur())
            if s.loop_b and s.loop_b <= s.loop_a + 20:
                s.loop_b, s.ab_on = 0, False
            self.changed()

    def set_b(self):
        s = self.strip
        if s:
            b = int(self.cur())
            if b <= s.loop_a + 20:
                self.host.statusBar().showMessage("Điểm B phải sau điểm A", 3000)
                return
            s.loop_b, s.ab_on = b, True
            self.changed()

    def toggle_ab(self):
        s = self.strip
        if s:
            if not s.ab_valid():
                self.b_loop.setChecked(False)
                self.host.statusBar().showMessage("Chưa có vùng lặp — đặt A và B, hoặc bấm 1s / 2s / 4s / 8s", 3000)
                return
            s.ab_on = self.b_loop.isChecked()
            self.changed()

    def loop_len(self, sec):
        s = self.strip
        if s:
            a = int(self.cur())
            s.loop_a, s.loop_b, s.ab_on = a, min(self.wave.duration, a + sec * 1000), True
            self.changed()

    def loop_selection(self):
        s = self.strip
        sel = self.wave.sel
        if not s:
            return
        if not sel or abs(sel[1] - sel[0]) < 50:
            self.host.statusBar().showMessage("Kéo chuột trên sóng để chọn một đoạn trước", 3000)
            return
        s.loop_a, s.loop_b, s.ab_on = int(min(sel)), int(max(sel)), True
        self.wave.sel = None
        self.changed()

    def clear_loop(self):
        s = self.strip
        if s:
            s.loop_a = s.loop_b = 0
            s.ab_on = False
            self.changed()

    # ---------- BPM
    def bpm_manual(self, v):
        s = self.strip
        if s:
            s.bpm = float(v)
            self.lbl_bpm.setText(str(v))
            self.btn_auto.setVisible(True)
            self.wave.bpm = float(v)
            self.wave.update()
            s.changed.emit()

    def bpm_auto(self):
        s = self.strip
        if s:
            s.bpm = 0.0
            self.changed()

    # ---------- nghe trước
    def prelisten(self):
        s = self.strip
        pre = self.host.pre
        if not self.b_pre.isChecked():
            pre.stop()
            return
        if not s or not s.path:
            self.b_pre.setChecked(False)
            return
        pre.load(s.path)
        pre.play_from(int(self.cur()))
        self.host.pre_title = f"deck:{s.number}"
        self.host.statusBar().showMessage(f"🎧 Nghe trước kênh {s.number} ra tai nghe (bấm lại để tắt)", 4000)

    # ---------- menu chuột phải
    def wave_menu(self, ms, gpos):
        s = self.strip
        if not s or not s.path or self.host.locked:
            return
        m = QMenu(self)
        m.addAction(f"Phát từ {tfmt(ms)}", lambda: (self.seek(ms), self.play_pause() if not self.active() else None))
        m.addAction("Nghe trước từ đây (tai nghe)", lambda: (setattr(self, "cursor_ms", ms), self.b_pre.setChecked(True),
                                                             self.prelisten()))
        m.addSeparator()
        m.addAction("Đặt IN tại đây", lambda: self.set_in_out(min(ms, (s.end_ms or self.wave.duration) - 100), s.end_ms))
        m.addAction("Đặt OUT tại đây", lambda: self.set_in_out(
            s.start_ms, 0 if ms >= self.wave.duration - 5 else max(ms, s.start_ms + 100)))
        m.addAction("Thêm CUE tại đây", lambda: (setattr(self, "cursor_ms", ms), self.add_cue()) if not self.active()
                    else self._cue_at(ms))
        m.addSeparator()
        m.addAction("Đặt A tại đây", lambda: self._ab_at(ms, None))
        m.addAction("Đặt B tại đây", lambda: self._ab_at(None, ms))
        a = m.addAction("Lặp vùng đang chọn", self.loop_selection)
        a.setEnabled(bool(self.wave.sel))
        m.addSeparator()
        m.addAction("Xem cả bài", self.full_view)
        m.exec(gpos)

    def _cue_at(self, ms):
        s = self.strip
        if s and not any(abs(ms - c) < 100 for c in s.cues) and len(s.cues) < MAX_CUES:
            s.cues = sorted(s.cues + [int(ms)])
            self.changed()

    def _ab_at(self, a, b):
        s = self.strip
        if not s:
            return
        if a is not None:
            s.loop_a = int(a)
            if s.loop_b <= s.loop_a + 20:
                s.loop_b, s.ab_on = 0, False
        if b is not None:
            if b <= s.loop_a + 20:
                self.host.statusBar().showMessage("Điểm B phải sau điểm A", 3000)
                return
            s.loop_b, s.ab_on = int(b), True
        self.changed()
