"""Trang Âm thanh: đo tần số (RTA), đo mức micro, phát hiện hú (chống hú), ring-out,
đo phòng bằng pink noise và phát tone thử loa.

Máy tính nghe qua một micro đo / cổng line-in (tín hiệu từ mixer) để phân tích; phần mềm không xử lý
tiếng micro sân khấu mà chỉ báo cho người điều khiển biết cần chỉnh gì trên mixer.
"""
import math
import time

import numpy as np
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPolygonF
from PySide6.QtMultimedia import QAudioFormat, QAudioSink, QAudioSource, QMediaDevices
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFrame, QGridLayout, QHBoxLayout, QHeaderView,
                               QLabel, QMessageBox, QPushButton, QSizePolicy, QSpinBox, QTabWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from theme import T

FFT_N = 8192
ISO_BANDS = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250,
             1600, 2000, 2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000]
F_MIN, F_MAX = 20.0, 20000.0
DB_MIN, DB_MAX = -90.0, 0.0
SENS = {"low": ("Thấp", 22.0, 14, -45.0), "mid": ("Vừa", 16.0, 10, -55.0), "high": ("Cao", 12.0, 6, -62.0)}


# ------------------------------------------------------------------ tiện ích
def fmt_hz(f):
    if f >= 1000:
        s = f"{f / 1000:.2f}".rstrip("0").rstrip(".")
        return s.replace(".", ",") + " kHz"
    return (f"{f:.0f}" if f >= 100 else f"{f:.1f}".replace(".", ",")) + " Hz"


def band_label(fc):
    if fc >= 1000:
        s = f"{fc / 1000:g}".replace(".", ",")
        return s + "k"
    return f"{fc:g}".replace(".", ",")


def nearest_band(f):
    return min(ISO_BANDS, key=lambda b: abs(math.log2(f / b)))


def db(x, floor=-140.0):
    return np.maximum(floor, 10 * np.log10(np.maximum(x, 1e-30)))


def find_device(devices, name):
    for d in devices:
        if d.description() == name:
            return d
    return None


# ------------------------------------------------------------------ nguồn vào (micro đo)
class MicInput:
    """Đọc âm thanh từ thiết bị vào, giữ bộ đệm vòng FFT_N mẫu (mono float)."""

    def __init__(self, parent):
        self.parent = parent
        self.src = None
        self.io = None
        self.fs = 48000
        self.buf = np.zeros(FFT_N, dtype=np.float32)
        self.new = 0                 # số mẫu mới kể từ lần lấy mức
        self.peak = 0.0
        self.sumsq = 0.0
        self.count = 0
        self.error = ""

    def start(self, device):
        self.stop()
        fmt = QAudioFormat()
        fmt.setSampleRate(48000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
        if not device.isFormatSupported(fmt):
            fmt = device.preferredFormat()
        self.fmt = fmt
        self.fs = fmt.sampleRate()
        self.ch = max(1, fmt.channelCount())
        self.src = QAudioSource(device, fmt, self.parent)
        self.src.setBufferSize(int(self.fs * self.ch * fmt.bytesPerSample() * 0.05))
        self.io = self.src.start()
        if self.io is None:
            self.error = "Không mở được thiết bị vào"
            return False
        self.io.readyRead.connect(self._read)
        self.buf[:] = 0
        self.error = ""
        return True

    def stop(self):
        if self.src is not None:
            self.src.stop()
            self.src.deleteLater()
        self.src = self.io = None

    def running(self):
        return self.src is not None

    _DT = {QAudioFormat.SampleFormat.Float: (np.float32, 1.0), QAudioFormat.SampleFormat.Int16: (np.int16, 32768.0),
           QAudioFormat.SampleFormat.Int32: (np.int32, 2147483648.0), QAudioFormat.SampleFormat.UInt8: (np.uint8, 128.0)}

    def _read(self):
        if self.io is None:
            return
        raw = bytes(self.io.readAll())
        dt, scale = self._DT.get(self.fmt.sampleFormat(), (np.float32, 1.0))
        x = np.frombuffer(raw, dtype=dt)
        if x.size < self.ch:
            return
        x = x[: x.size - x.size % self.ch].astype(np.float32)
        if dt is np.uint8:
            x -= 128.0
        x /= scale
        if self.ch > 1:
            x = x.reshape(-1, self.ch).mean(axis=1)
        n = x.size
        if n >= FFT_N:
            self.buf[:] = x[-FFT_N:]
        else:
            self.buf[:-n] = self.buf[n:]
            self.buf[-n:] = x
        self.new += n
        self.peak = max(self.peak, float(np.max(np.abs(x))))
        self.sumsq += float(np.dot(x, x))
        self.count += n

    def take_level(self):
        """(đỉnh, RMS) kể từ lần gọi trước."""
        p = self.peak
        r = math.sqrt(self.sumsq / self.count) if self.count else 0.0
        self.peak = self.sumsq = 0.0
        self.count = 0
        return p, r


# ------------------------------------------------------------------ máy phát (tone / noise)
class ToneOut:
    """Phát sóng sin, quét tần số, pink / white noise ra một thiết bị (chế độ push, an toàn trên luồng chính)."""

    def __init__(self, parent):
        self.parent = parent
        self.sink = None
        self.io = None
        self.kind = "sine"
        self.freq = 1000.0
        self.level_db = -20.0
        self.sweep = (20.0, 20000.0, 10.0)
        self.phase = 0.0
        self.t = 0.0
        self.gain = 0.0
        self.target = 0.0
        self.pos = 0
        self._pink = None
        self._dev_name = ""
        self.timer = QTimer(parent)
        self.timer.setInterval(15)
        self.timer.timeout.connect(self._pump)
        self.cur_freq = 0.0

    def playing(self):
        return self.sink is not None and self.target > 0

    def start(self, device, kind, freq=1000.0, level_db=-20.0, sweep=None):
        self.kind, self.freq, self.level_db = kind, float(freq), float(level_db)
        if sweep:
            self.sweep = sweep
        if self.sink is None or self._dev_name != device.description():
            self._close()
            fmt = QAudioFormat()
            fmt.setSampleRate(48000)
            fmt.setChannelCount(2)
            fmt.setSampleFormat(QAudioFormat.SampleFormat.Float)
            if not device.isFormatSupported(fmt):
                fmt = device.preferredFormat()
            self.fmt = fmt
            self.fs = fmt.sampleRate()
            self.ch = max(1, fmt.channelCount())
            self.sink = QAudioSink(device, fmt, self.parent)
            self.sink.setBufferSize(int(self.fs * self.ch * fmt.bytesPerSample() * 0.12))
            self.io = self.sink.start()
            self._dev_name = device.description()
            if self.io is None:
                self._close()
                return False
        self.phase = 0.0
        self.t = 0.0
        self.target = 1.0
        self.timer.start()
        return True

    def set_level(self, level_db):
        self.level_db = float(level_db)

    def stop(self):
        self.target = 0.0          # nhỏ dần rồi tự đóng ở _pump

    def stop_now(self):
        self._close()

    def _close(self):
        self.timer.stop()
        if self.sink is not None:
            self.sink.stop()
            self.sink.deleteLater()
        self.sink = self.io = None
        self.gain = self.target = 0.0
        self._dev_name = ""

    def _pink_buf(self):
        if self._pink is None:
            n = 1 << 18
            rng = np.random.default_rng(7)
            spec = (rng.standard_normal(n // 2 + 1) + 1j * rng.standard_normal(n // 2 + 1))
            f = np.fft.rfftfreq(n, 1 / self.fs)
            mag = np.zeros_like(f)
            ok = (f >= 18) & (f <= 22000)
            mag[ok] = 1 / np.sqrt(f[ok])
            x = np.fft.irfft(spec * mag, n).astype(np.float32)   # tuần hoàn -> lặp không bị nối
            self._pink = x / np.sqrt(np.mean(x ** 2))
        return self._pink

    def _gen(self, n):
        amp = 10 ** (self.level_db / 20)
        if self.kind == "sine":
            w = 2 * math.pi * self.freq / self.fs
            ph = self.phase + w * np.arange(1, n + 1)
            x = np.sin(ph) * amp
            self.phase = float(ph[-1] % (2 * math.pi))
            self.cur_freq = self.freq
        elif self.kind == "sweep":
            f1, f2, dur = self.sweep
            k = math.log(f2 / f1)
            t = self.t + np.arange(1, n + 1) / self.fs
            t = np.mod(t, dur)
            ph = 2 * math.pi * f1 * dur / k * (np.exp(t / dur * k) - 1)
            x = np.sin(ph) * amp
            self.t = float(t[-1])
            self.cur_freq = f1 * math.exp(self.t / dur * k)
        elif self.kind == "pink":
            buf = self._pink_buf()
            idx = (self.pos + np.arange(n)) % buf.size
            self.pos = int((self.pos + n) % buf.size)
            x = buf[idx] * amp / math.sqrt(2)
            self.cur_freq = 0.0
        else:
            x = np.random.default_rng().standard_normal(n) * amp / math.sqrt(2)
            self.cur_freq = 0.0
        # đổi mức mượt (tránh tiếng "bụp")
        g = self.gain + (self.target - self.gain) * np.linspace(0, 1, n, endpoint=True)
        self.gain = float(g[-1]) if abs(self.target - g[-1]) > 1e-3 else self.target
        return np.clip(x * g, -1.0, 1.0).astype(np.float32)

    def _pump(self):
        if self.sink is None or self.io is None:
            return
        bpf = self.ch * self.fmt.bytesPerSample()
        frames = self.sink.bytesFree() // bpf
        if frames <= 0:
            return
        frames = min(frames, int(self.fs * 0.06))
        x = self._gen(frames)
        if self.ch > 1:
            x = np.repeat(x[:, None], self.ch, axis=1).ravel()
        sf = self.fmt.sampleFormat()
        if sf == QAudioFormat.SampleFormat.Int16:
            data = (x * 32767).astype(np.int16).tobytes()
        elif sf == QAudioFormat.SampleFormat.Int32:
            data = (x * 2147483647).astype(np.int32).tobytes()
        else:
            data = x.tobytes()
        self.io.write(data)
        if self.target == 0 and self.gain == 0:
            QTimer.singleShot(150, lambda: self._close() if self.target == 0 else None)
            self.timer.stop()


# ------------------------------------------------------------------ phân tích
class Analyzer:
    def __init__(self):
        self.win = np.hanning(FFT_N).astype(np.float32)
        self.wsum = float(self.win.sum())
        self.fs = 48000
        self._edges(48000)

    def _edges(self, fs):
        self.fs = fs
        self.freqs = np.fft.rfftfreq(FFT_N, 1 / fs)
        self.band_idx = []
        for fc in ISO_BANDS:
            lo, hi = fc * 2 ** (-1 / 6), fc * 2 ** (1 / 6)
            i0 = int(np.searchsorted(self.freqs, lo))
            i1 = max(i0 + 1, int(np.searchsorted(self.freqs, hi)))
            self.band_idx.append((i0, i1))

    def run(self, x, fs):
        if fs != self.fs:
            self._edges(fs)
        spec = np.fft.rfft(x * self.win)
        mag = np.abs(spec) * 2 / self.wsum           # sóng sin biên độ 1 -> 1 (0 dBFS)
        pw = mag ** 2
        # cộng công suất các bin trong dải, chia băng thông nhiễu tương đương của cửa sổ Hann (1,5 bin)
        bands = np.array([pw[a:b].sum() for a, b in self.band_idx]) / 1.5
        return pw, bands


class FeedbackDetector:
    """Tìm đỉnh tần số hẹp, nổi hẳn so với xung quanh và kéo dài -> nghi hú."""

    def __init__(self):
        self.tracks = []
        self.frame = 0
        self.sens = "mid"

    def reset(self):
        self.tracks = []

    def update(self, pw, freqs):
        _name, prom_thr, persist, floor = SENS[self.sens]
        self.frame += 1
        d = db(pw)
        lo = int(np.searchsorted(freqs, 60))
        hi = int(np.searchsorted(freqs, 16000))
        seg = d[lo:hi]
        if seg.size < 5:
            return []
        is_max = (seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:]) & (seg[1:-1] > floor)
        cand = np.nonzero(is_max)[0] + 1 + lo
        if cand.size > 60:
            cand = cand[np.argsort(d[cand])[-60:]]
        found = []
        for i in cand:
            f = freqs[i]
            w = max(4, int(i * (2 ** (1 / 6) - 1)))      # ±1/6 octave
            a, b = max(lo, i - w), min(hi, i + w + 1)
            neigh = np.concatenate((d[a:max(a, i - 3)], d[min(b, i + 4):b]))
            if neigh.size < 4:
                continue
            prom = d[i] - float(np.median(neigh))
            if prom < prom_thr:
                continue
            al, bl, cl = d[i - 1], d[i], d[i + 1]
            den = al - 2 * bl + cl
            p = 0.5 * (al - cl) / den if den != 0 else 0.0
            f = (i + max(-0.5, min(0.5, p))) * (freqs[1] - freqs[0])
            found.append((f, float(bl), prom))
        # ghép với các vết đang theo dõi
        # ghép với các vết đang theo dõi: tiếng hú đứng yên một tần số (lệch < 1/48 octave),
        # mỗi vết chỉ nhận đỉnh to nhất gần nó trong khung này
        found.sort(key=lambda x: -x[1])
        used = set()
        for f, lv, prom in found:
            tr = next((t for t in self.tracks if id(t) not in used
                       and abs(math.log2(f / t["hz"])) < 1 / 48), None)
            if tr is None:
                tr = {"hz": f, "hz0": f, "level": lv, "first": lv, "max": lv, "frames": 1, "start": self.frame,
                      "seen": self.frame, "prom": prom, "t0": time.time()}
                self.tracks.append(tr)
            else:
                tr["hz"] = tr["hz"] * 0.8 + f * 0.2
                tr["level"], tr["prom"] = lv, prom
                tr["max"] = max(tr["max"], lv)
                tr["frames"] += 1
                tr["seen"] = self.frame
            used.add(id(tr))
        self.tracks = [t for t in self.tracks if self.frame - t["seen"] <= 2]

        def is_howl(t):
            span = self.frame - t["start"] + 1
            return (t["frames"] >= persist and t["frames"] >= 0.8 * span          # xuất hiện liên tục
                    and t["level"] >= t["first"] - 3                              # không nhỏ dần
                    and abs(math.log2(t["hz"] / t["hz0"])) < 1 / 96)              # tần số đứng yên
        return [t for t in self.tracks if is_howl(t)]


def eq_advice(level):
    cut = 9 if level > -20 else 6 if level > -40 else 4
    return cut


# ------------------------------------------------------------------ widget: biểu đồ tần số
class SpectrumView(QWidget):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(420, 180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.bands = None
        self.peaks = None
        self.line = None
        self.freqs = None
        self.mode = "both"
        self.feedback = []
        self.ringout = []

    def _x(self, f, r):
        return r.left() + (math.log10(f) - math.log10(F_MIN)) / (math.log10(F_MAX) - math.log10(F_MIN)) * r.width()

    def _y(self, v, r):
        v = max(DB_MIN, min(DB_MAX, v))
        return r.top() + (DB_MAX - v) / (DB_MAX - DB_MIN) * r.height()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["wave_bg"]))
        p.drawRoundedRect(full.adjusted(.5, .5, -.5, -.5), 10, 10)
        r = full.adjusted(44, 14, -14, -26)
        f = QFont("Segoe UI")
        f.setPixelSize(10)
        p.setFont(f)
        # lưới
        for v in range(int(DB_MIN), int(DB_MAX) + 1, 10):
            y = self._y(v, r)
            p.setPen(QPen(QColor(T["wave_grid"]), 1))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
            p.setPen(QColor(T["wave_ruler"]))
            p.drawText(QRectF(0, y - 7, 38, 14), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{v}")
        for fq, lab in ((31.5, "31"), (63, "63"), (125, "125"), (250, "250"), (500, "500"), (1000, "1k"),
                        (2000, "2k"), (4000, "4k"), (8000, "8k"), (16000, "16k")):
            x = self._x(fq, r)
            p.setPen(QPen(QColor(T["wave_grid"]), 1))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.setPen(QColor(T["wave_ruler"]))
            p.drawText(QRectF(x - 20, r.bottom() + 4, 40, 14), Qt.AlignmentFlag.AlignCenter, lab)
        p.drawText(QRectF(0, r.bottom() + 4, 40, 14), Qt.AlignmentFlag.AlignRight, "dBFS")
        # dải 1/3 octave
        if self.bands is not None and self.mode in ("both", "bands"):
            bd = db(self.bands)
            acc, warn, dang = QColor(T["accent"]), QColor(T["warn"]), QColor(T["danger"])
            for k, fc in enumerate(ISO_BANDS):
                x0 = self._x(fc * 2 ** (-1 / 6), r) + 1.5
                x1 = self._x(min(F_MAX, fc * 2 ** (1 / 6)), r) - 1.5
                v = bd[k]
                if v <= DB_MIN:
                    continue
                y = self._y(v, r)
                c = QColor(dang if v > -6 else warn if v > -18 else acc)
                c.setAlpha(170 if self.mode == "both" else 230)
                p.setBrush(c)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(QRectF(x0, y, max(1.0, x1 - x0), r.bottom() - y), 2, 2)
                if self.peaks is not None:
                    py = self._y(float(db(self.peaks[k])), r)
                    p.setBrush(QColor(T["text"]))
                    p.drawRect(QRectF(x0, py - 1, max(1.0, x1 - x0), 2))
        # đường FFT chi tiết
        if self.line is not None and self.mode in ("both", "fft"):
            fr = self.freqs
            ok = (fr >= F_MIN) & (fr <= F_MAX)
            fx = fr[ok]
            dv = db(self.line[ok])
            xs = ((np.log10(fx) - math.log10(F_MIN)) / (math.log10(F_MAX) - math.log10(F_MIN)) * r.width()).astype(int)
            _u, idx = np.unique(xs, return_index=True)
            mx = np.maximum.reduceat(dv, idx)
            path = QPainterPath()
            for j, (xi, v) in enumerate(zip(xs[idx], mx)):
                pt = QPointF(r.left() + xi, self._y(float(v), r))
                path.moveTo(pt) if j == 0 else path.lineTo(pt)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(T["wave"]), 1.4))
            p.drawPath(path)
        # tần số ring-out đã lưu
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["warn"]))
        for hz in self.ringout:
            x = self._x(hz, r)
            p.drawPolygon(QPolygonF([QPointF(x - 5, r.top()), QPointF(x + 5, r.top()), QPointF(x, r.top() + 8)]))
        # đang hú
        f.setBold(True)
        f.setPixelSize(12)
        p.setFont(f)
        for t in self.feedback:
            x = self._x(t["hz"], r)
            p.setPen(QPen(QColor(T["danger"]), 2))
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            lab = fmt_hz(t["hz"])
            w = p.fontMetrics().horizontalAdvance(lab) + 12
            box = QRectF(min(r.right() - w, x + 4), r.top() + 10, w, 20)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T["danger"]))
            p.drawRoundedRect(box, 5, 5)
            p.setPen(QColor("white"))
            p.drawText(box, Qt.AlignmentFlag.AlignCenter, lab)
        if self.bands is None:
            p.setPen(QColor(T["text_faint"]))
            f.setPixelSize(15)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Chọn nguồn vào rồi bấm  ▶ Bắt đầu đo")


class LevelBar(QWidget):
    """Đồng hồ mức micro nằm ngang: RMS (đặc) + đỉnh (vạch) + giữ đỉnh."""

    def __init__(self):
        super().__init__()
        self.setFixedHeight(34)
        self.rms = self.peak = self.hold = -120.0

    def set(self, peak_db, rms_db, hold_db):
        self.peak, self.rms, self.hold = peak_db, rms_db, hold_db
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0, 0, 0, -14)
        lo, hi = -60.0, 0.0
        xf = lambda v: r.left() + (max(lo, min(hi, v)) - lo) / (hi - lo) * r.width()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["meter_bg"]))
        p.drawRoundedRect(r, 4, 4)
        for a, b, c in ((-60, -18, T["ok"]), (-18, -6, T["warn"]), (-6, 0, T["danger"])):
            col = QColor(c)
            col.setAlpha(45)
            p.setBrush(col)
            p.drawRect(QRectF(xf(a), r.top(), xf(b) - xf(a), r.height()))
        x = xf(self.rms)
        for a, b, c in ((-60, -18, T["ok"]), (-18, -6, T["warn"]), (-6, 0, T["danger"])):
            if x > xf(a):
                p.setBrush(QColor(c))
                p.drawRect(QRectF(xf(a), r.top() + 3, min(x, xf(b)) - xf(a), r.height() - 6))
        p.setBrush(QColor(T["text"]))
        p.drawRect(QRectF(xf(self.peak) - 1, r.top(), 2, r.height()))
        p.setBrush(QColor(T["danger"] if self.hold > -1 else T["text_dim"]))
        p.drawRect(QRectF(xf(self.hold) - 1.5, r.top(), 3, r.height()))
        f = QFont("Segoe UI")
        f.setPixelSize(9)
        p.setFont(f)
        p.setPen(QColor(T["text_faint"]))
        for v in (-60, -48, -36, -24, -18, -12, -6, 0):
            p.drawText(QRectF(xf(v) - 15, r.bottom() + 2, 30, 12), Qt.AlignmentFlag.AlignCenter, str(v))


class RoomChart(QWidget):
    """Kết quả đo phòng: lệch (dB) của mỗi dải 1/3 octave so với trung bình."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(120)
        self.dev = None
        self.valid = None

    def set(self, dev, valid):
        self.dev, self.valid = dev, valid
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["wave_bg"]))
        p.drawRoundedRect(full.adjusted(.5, .5, -.5, -.5), 8, 8)
        r = full.adjusted(34, 10, -8, -20)
        rng = 12.0
        yf = lambda v: r.center().y() - max(-rng, min(rng, v)) / rng * (r.height() / 2)
        f = QFont("Segoe UI")
        f.setPixelSize(9)
        p.setFont(f)
        for v in (-12, -6, 0, 6, 12):
            p.setPen(QPen(QColor(T["border_strong"] if v == 0 else T["wave_grid"]), 1))
            p.drawLine(QPointF(r.left(), yf(v)), QPointF(r.right(), yf(v)))
            p.setPen(QColor(T["wave_ruler"]))
            p.drawText(QRectF(0, yf(v) - 6, 30, 12), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       f"{v:+d}" if v else "0")
        n = len(ISO_BANDS)
        bw = r.width() / n
        for k, fc in enumerate(ISO_BANDS):
            x = r.left() + k * bw
            if k % 3 == 2 or fc in (1000,):
                p.setPen(QColor(T["wave_ruler"]))
                p.drawText(QRectF(x - 8, r.bottom() + 4, bw + 16, 12), Qt.AlignmentFlag.AlignCenter, band_label(fc))
            if self.dev is None:
                continue
            v = float(self.dev[k])
            ok = bool(self.valid[k])
            c = QColor(T["danger"] if v > 3 else T["accent"] if v < -3 else T["ok"])
            if not ok:
                c = QColor(T["text_faint"])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            y0, y1 = yf(0), yf(v)
            p.drawRoundedRect(QRectF(x + 2, min(y0, y1), bw - 4, max(1.5, abs(y1 - y0))), 2, 2)
        if self.dev is None:
            p.setPen(QColor(T["text_faint"]))
            f.setPixelSize(12)
            p.setFont(f)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "Chưa có kết quả đo phòng")


# ------------------------------------------------------------------ trang Âm thanh
def card(title):
    fr = QFrame()
    fr.setObjectName("scCard")
    v = QVBoxLayout(fr)
    v.setContentsMargins(12, 8, 12, 10)
    v.setSpacing(5)
    if title:
        t = QLabel(title)
        t.setObjectName("sideHead")
        v.addWidget(t)
    return fr, v


class SoundCheckPage(QWidget):
    feedbackAlert = Signal(str)       # "" = hết hú; khác = mô tả tần số đang hú

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.mic = MicInput(self)
        self.out = ToneOut(self)
        self.an = Analyzer()
        self.det = FeedbackDetector()
        self.det.sens = host.settings.value("sc_sens", "mid")
        self.avg = None
        self.peaks = None
        self.hold_db, self.hold_t = -120.0, 0.0
        self.clips = 0
        self.ringing = False
        self.ringout = self._load_ringout()
        self.room = None               # trạng thái đo phòng
        self._alert = ""
        self._advice_t = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.build_ui()
        self.fill_devices()

    # ============ giao diện
    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # --- thanh điều khiển
        bar, bl = card("")
        h = QHBoxLayout()
        h.setSpacing(10)
        bl.addLayout(h)
        h.addWidget(self._lab("Nguồn vào (micro đo / line-in):"))
        self.cmb_in = QComboBox()
        self.cmb_in.setMinimumWidth(240)
        self.cmb_in.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        h.addWidget(self.cmb_in, 1)
        self.btn_run = QPushButton("▶  Bắt đầu đo")
        self.btn_run.setObjectName("save")
        self.btn_run.setCheckable(True)
        self.btn_run.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_run.toggled.connect(self.set_running)
        h.addWidget(self.btn_run)
        h.addSpacing(10)
        h.addWidget(self._lab("Hiển thị:"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for k, t in (("both", "1/3 octave + FFT"), ("bands", "Dải 1/3 octave"), ("fft", "FFT chi tiết")):
            self.cmb_mode.addItem(t, k)
        self.cmb_mode.currentIndexChanged.connect(lambda _i: setattr(self.spec, "mode", self.cmb_mode.currentData()))
        h.addWidget(self.cmb_mode)
        h.addWidget(self._lab("Tốc độ:"))
        self.cmb_speed = QComboBox()
        self.cmb_speed.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cmb_speed.addItem("Nhanh", 0.45)
        self.cmb_speed.addItem("Vừa", 0.2)
        self.cmb_speed.addItem("Chậm", 0.06)
        self.cmb_speed.setCurrentIndex(1)
        h.addWidget(self.cmb_speed)
        b = QPushButton("Xóa đỉnh")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(self.reset_peaks)
        h.addWidget(b)
        root.addWidget(bar)

        # --- thân: biểu đồ + cột phải
        mid = QHBoxLayout()
        mid.setSpacing(10)
        self.spec = SpectrumView()
        self.spec.ringout = [x["hz"] for x in self.ringout]
        mid.addWidget(self.spec, 1)
        right = QVBoxLayout()
        right.setSpacing(10)
        c, v = card("MỨC MICRO")
        self.level = LevelBar()
        v.addWidget(self.level)
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(2)
        self.lbl_peak, self.lbl_rms, self.lbl_hold, self.lbl_clip = QLabel("–"), QLabel("–"), QLabel("–"), QLabel("0")
        g.setColumnStretch(3, 0)
        for i, (t, w) in enumerate((("Đỉnh", self.lbl_peak), ("RMS", self.lbl_rms),
                                    ("Đỉnh 3 giây", self.lbl_hold), ("Vỡ", self.lbl_clip))):
            g.addWidget(self._lab(t), 0, i)
            w.setObjectName("scValue")
            g.addWidget(w, 1, i)
        v.addLayout(g)
        self.lbl_status = QLabel("Chưa đo")
        self.lbl_status.setObjectName("scStatus")
        self.lbl_status.setWordWrap(True)
        v.addWidget(self.lbl_status)
        self.lbl_advice = QLabel("")
        self.lbl_advice.setObjectName("note")
        self.lbl_advice.setWordWrap(True)
        v.addWidget(self.lbl_advice)
        right.addWidget(c)

        c, v = card("")
        hh = QHBoxLayout()
        head = QLabel("CHỐNG HÚ")
        head.setObjectName("sideHead")
        hh.addWidget(head)
        hh.addStretch()
        hh.addWidget(self._lab("Độ nhạy:"))
        self.cmb_sens = QComboBox()
        self.cmb_sens.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for k, (name, *_r) in SENS.items():
            self.cmb_sens.addItem(name, k)
        self.cmb_sens.setCurrentIndex(max(0, self.cmb_sens.findData(self.det.sens)))
        self.cmb_sens.currentIndexChanged.connect(self.set_sens)
        hh.addWidget(self.cmb_sens)
        v.addLayout(hh)
        self.lbl_alert = QLabel("Không phát hiện hú")
        self.lbl_alert.setObjectName("scAlert")
        self.lbl_alert.setProperty("on", False)
        self.lbl_alert.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_alert.setWordWrap(True)
        v.addWidget(self.lbl_alert)
        self.fb_list = QTreeWidget()
        self.fb_list.setHeaderLabels(["Tần số", "Mức", "Gợi ý trên mixer"])
        self.fb_list.setRootIsDecorated(False)
        self.fb_list.setMinimumHeight(56)
        self.fb_list.header().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        v.addWidget(self.fb_list, 1)
        right.addWidget(c, 1)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(360)
        mid.addWidget(rw)
        root.addLayout(mid, 1)

        # --- công cụ
        self.tools = QTabWidget()
        self.tools.setMinimumHeight(200)
        self.tools.setMaximumHeight(270)
        self.cmb_out = QComboBox()
        self.cmb_out.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cmb_out.setMinimumWidth(260)
        corner = QWidget()
        ch = QHBoxLayout(corner)
        ch.setContentsMargins(0, 0, 0, 4)
        ch.addWidget(self._lab("Loa phát thử / đo:"))
        ch.addWidget(self.cmb_out)
        self.tools.setCornerWidget(corner, Qt.Corner.TopRightCorner)
        self.tools.addTab(self._ring_tab(), "Ring-out (tìm tần số dễ hú)")
        self.tools.addTab(self._room_tab(), "Đo phòng (pink noise)")
        self.tools.addTab(self._tone_tab(), "Phát tone thử loa")
        root.addWidget(self.tools)

    def _lab(self, t):
        lb = QLabel(t)
        lb.setObjectName("fieldLabel")
        return lb

    def _ring_tab(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(14)
        left = QVBoxLayout()
        t = QLabel("<b>Cách làm trước giờ diễn</b> (phòng yên lặng, không phát nhạc):<br>"
                   "1. Đặt micro sân khấu đúng chỗ MC / ca sĩ sẽ đứng, bật micro đo của máy tính.<br>"
                   "2. Bấm <b>Bắt đầu ring-out</b>, rồi tăng từ từ fader micro trên mixer.<br>"
                   "3. Khi bắt đầu nghe hú, phần mềm ghi lại tần số &rarr; cắt tần số đó trên EQ của mixer.<br>"
                   "4. Lặp lại tới khi đạt mức to mong muốn, sau đó hạ fader 3–6 dB để có khoảng an toàn.")
        t.setWordWrap(True)
        t.setObjectName("note")
        left.addWidget(t)
        hb = QHBoxLayout()
        self.btn_ring = QPushButton("●  Bắt đầu ring-out")
        self.btn_ring.setCheckable(True)
        self.btn_ring.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_ring.toggled.connect(self.set_ringout)
        hb.addWidget(self.btn_ring)
        for text, fn in (("Xóa dòng chọn", self.ring_remove), ("Xóa hết", self.ring_clear),
                         ("Sao chép danh sách", self.ring_copy)):
            b = QPushButton(text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(fn)
            hb.addWidget(b)
        hb.addStretch()
        left.addLayout(hb)
        left.addStretch()
        h.addLayout(left, 2)
        self.ring_list = QTreeWidget()
        self.ring_list.setHeaderLabels(["#", "Tần số", "EQ 31 băng", "Gợi ý cắt", "Lúc"])
        self.ring_list.setRootIsDecorated(False)
        self.ring_list.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h.addWidget(self.ring_list, 3)
        self.refresh_ring_list()
        return w

    def _room_tab(self):
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(12, 10, 12, 10)
        h.setSpacing(14)
        left = QVBoxLayout()
        t = QLabel("Phát pink noise ra loa, micro đo đặt ở vị trí khán giả. Phần mềm đo tiếng ồn nền 2 giây, "
                   "rồi đo tiếng loa và vẽ độ lệch từng dải tần (cột đỏ = dư, nên cắt; cột xanh dương = thiếu).")
        t.setWordWrap(True)
        t.setObjectName("note")
        left.addWidget(t)
        g = QHBoxLayout()
        g.addWidget(self._lab("Mức pink noise:"))
        self.sp_room_lv = QSpinBox()
        self.sp_room_lv.setRange(-50, -6)
        self.sp_room_lv.setValue(-24)
        self.sp_room_lv.setSuffix(" dBFS")
        g.addWidget(self.sp_room_lv)
        g.addSpacing(8)
        g.addWidget(self._lab("Đo trong:"))
        self.sp_room_t = QSpinBox()
        self.sp_room_t.setRange(4, 60)
        self.sp_room_t.setValue(10)
        self.sp_room_t.setSuffix(" giây")
        g.addWidget(self.sp_room_t)
        g.addStretch()
        left.addLayout(g)
        self.btn_room = QPushButton("▶  Bắt đầu đo phòng")
        self.btn_room.setObjectName("save")
        self.btn_room.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_room.clicked.connect(self.room_toggle)
        hb = QHBoxLayout()
        hb.addWidget(self.btn_room)
        hb.addStretch()
        left.addLayout(hb)
        self.lbl_room = QLabel("")
        self.lbl_room.setObjectName("note")
        self.lbl_room.setWordWrap(True)
        left.addWidget(self.lbl_room)
        left.addStretch()
        h.addLayout(left, 2)
        right = QVBoxLayout()
        self.room_chart = RoomChart()
        right.addWidget(self.room_chart, 1)
        self.lbl_room_adv = QLabel("")
        self.lbl_room_adv.setWordWrap(True)
        self.lbl_room_adv.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.lbl_room_adv)
        h.addLayout(right, 4)
        return w

    def _tone_tab(self):
        w = QWidget()
        g = QGridLayout(w)
        g.setContentsMargins(12, 10, 12, 10)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(6)
        g.addWidget(self._lab("Loại tín hiệu:"), 0, 0)
        self.cmb_kind = QComboBox()
        for k, t in (("sine", "Sóng sin (1 tần số)"), ("sweep", "Quét tần số (sweep)"),
                     ("pink", "Pink noise"), ("white", "White noise")):
            self.cmb_kind.addItem(t, k)
        self.cmb_kind.currentIndexChanged.connect(self.tone_params)
        g.addWidget(self.cmb_kind, 0, 1)
        g.addWidget(self._lab("Tần số:"), 1, 0)
        self.sp_freq = QDoubleSpinBox()
        self.sp_freq.setRange(20, 20000)
        self.sp_freq.setDecimals(0)
        self.sp_freq.setValue(1000)
        self.sp_freq.setSuffix(" Hz")
        self.sp_freq.valueChanged.connect(self.tone_params)
        g.addWidget(self.sp_freq, 1, 1)
        pr = QHBoxLayout()
        pr.setSpacing(4)
        for f in (63, 125, 250, 500, 1000, 2000, 4000, 8000, 16000):
            b = QPushButton(band_label(f))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setFixedWidth(46)
            b.clicked.connect(lambda _c=False, f=f: self.sp_freq.setValue(f))
            pr.addWidget(b)
        pr.addStretch()
        g.addLayout(pr, 1, 2)
        g.addWidget(self._lab("Quét từ / đến / thời gian:"), 2, 0)
        sw = QHBoxLayout()
        self.sp_sw1 = QSpinBox()
        self.sp_sw1.setRange(20, 20000)
        self.sp_sw1.setValue(20)
        self.sp_sw1.setSuffix(" Hz")
        self.sp_sw2 = QSpinBox()
        self.sp_sw2.setRange(20, 20000)
        self.sp_sw2.setValue(20000)
        self.sp_sw2.setSuffix(" Hz")
        self.sp_swt = QSpinBox()
        self.sp_swt.setRange(2, 120)
        self.sp_swt.setValue(15)
        self.sp_swt.setSuffix(" giây")
        for s in (self.sp_sw1, self.sp_sw2, self.sp_swt):
            s.valueChanged.connect(self.tone_params)
            sw.addWidget(s)
        g.addLayout(sw, 2, 1)
        g.addWidget(self._lab("Mức phát:"), 3, 0)
        self.sp_lv = QSpinBox()
        self.sp_lv.setRange(-60, -3)
        self.sp_lv.setValue(-24)
        self.sp_lv.setSuffix(" dBFS")
        self.sp_lv.valueChanged.connect(lambda v: self.out.set_level(v))
        g.addWidget(self.sp_lv, 3, 1)
        warn = QLabel("Bắt đầu ở mức nhỏ rồi tăng dần bằng fader / Master. Tone và tần số cao có thể làm hỏng loa tweeter.")
        warn.setObjectName("warnNote")
        warn.setWordWrap(True)
        g.addWidget(warn, 3, 2)
        hb = QHBoxLayout()
        hb.setContentsMargins(0, 0, 0, 0)
        self.btn_tone = QPushButton("▶  Phát")
        self.btn_tone.setObjectName("save")
        self.btn_tone.setCheckable(True)
        self.btn_tone.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_tone.toggled.connect(self.tone_toggle)
        hb.addWidget(self.btn_tone)
        self.lbl_tone = QLabel("")
        self.lbl_tone.setObjectName("scValue")
        hb.addWidget(self.lbl_tone)
        hb.addStretch()
        g.addLayout(hb, 0, 2)
        g.setColumnStretch(2, 1)
        g.setRowStretch(4, 1)
        return w

    # ============ thiết bị
    def fill_devices(self):
        s = self.host.settings
        ins = QMediaDevices.audioInputs()
        outs = QMediaDevices.audioOutputs()
        cur_in = self.cmb_in.currentText() or s.value("sc_in", "")
        cur_out = self.cmb_out.currentText() or s.value("sc_out", "") or self.host.cfg.get("cart_device", "")
        for cmb, devs, cur in ((self.cmb_in, ins, cur_in), (self.cmb_out, outs, cur_out)):
            cmb.blockSignals(True)
            cmb.clear()
            for d in devs:
                cmb.addItem(d.description())
            i = cmb.findText(cur)
            if i < 0:
                i = next((k for k, d in enumerate(devs) if d.isDefault()), 0)
            cmb.setCurrentIndex(i)
            cmb.blockSignals(False)
        self.cmb_in.currentIndexChanged.connect(self.input_changed)

    def input_dev(self):
        return find_device(QMediaDevices.audioInputs(), self.cmb_in.currentText()) or QMediaDevices.defaultAudioInput()

    def output_dev(self):
        return find_device(QMediaDevices.audioOutputs(), self.cmb_out.currentText()) or QMediaDevices.defaultAudioOutput()

    def input_changed(self, _i):
        self.host.settings.setValue("sc_in", self.cmb_in.currentText())
        if self.mic.running():
            self.set_running(True)

    # ============ đo
    def set_running(self, on):
        if self.btn_run.isChecked() != on:
            self.btn_run.setChecked(on)
            return
        if on:
            dev = self.input_dev()
            if dev.isNull() or not self.mic.start(dev):
                self.btn_run.setChecked(False)
                QMessageBox.warning(self, "Đo âm thanh",
                                    "Không mở được nguồn vào.\nKiểm tra micro đã cắm, và Windows cho phép ứng dụng "
                                    "dùng micro (Cài đặt → Quyền riêng tư → Micro).")
                return
            self.host.settings.setValue("sc_in", self.cmb_in.currentText())
            self.avg = None
            self.timer.start()
            self.btn_run.setText("■  Dừng đo")
        else:
            self.mic.stop()
            self.timer.stop()
            self.btn_run.setText("▶  Bắt đầu đo")
            self.lbl_status.setText("Chưa đo")
            self._set_status_state("")
            self.lbl_advice.setText("")
            self.det.reset()
            self.show_feedback([])
            if self.room:
                self.room_stop("Đã dừng vì tắt đo.")

    def set_sens(self, _i):
        self.det.sens = self.cmb_sens.currentData()
        self.host.settings.setValue("sc_sens", self.det.sens)
        self.det.reset()

    def reset_peaks(self):
        self.peaks = None
        self.clips = 0
        self.hold_db = -120.0

    def tick(self):
        if not self.mic.running():
            return
        pw, bands = self.an.run(self.mic.buf, self.mic.fs)
        a = self.cmb_speed.currentData()
        self.avg = bands if self.avg is None else self.avg * (1 - a) + bands * a
        self.line = pw if getattr(self, "line", None) is None or self.line.shape != pw.shape else \
            self.line * (1 - a) + pw * a
        self.peaks = self.avg.copy() if self.peaks is None else np.maximum(self.peaks * 0.995, self.avg)
        if self.isVisible():
            self.spec.bands, self.spec.peaks = self.avg, self.peaks
            self.spec.line, self.spec.freqs = self.line, self.an.freqs
            self.spec.update()
        self.level_tick()
        fb = self.det.update(pw, self.an.freqs)
        self.show_feedback(fb)
        if self.ringing:
            for t in fb:
                self.ring_add(t)
        if self.room:
            self.room_tick(bands)

    def level_tick(self):
        pk, rms = self.mic.take_level()
        pk_db = 20 * math.log10(pk) if pk > 1e-6 else -120.0
        rms_db = 20 * math.log10(rms) if rms > 1e-6 else -120.0
        now = time.time()
        if pk_db >= self.hold_db or now - self.hold_t > 3:
            self.hold_db, self.hold_t = pk_db, now
        if pk >= 0.989:
            self.clips += 1
        if not self.isVisible():
            return
        self.level.set(pk_db, rms_db, self.hold_db)
        self.lbl_peak.setText(f"{pk_db:.1f} dBFS" if pk_db > -120 else "–")
        self.lbl_rms.setText(f"{rms_db:.1f} dBFS" if rms_db > -120 else "–")
        self.lbl_hold.setText(f"{self.hold_db:.1f} dBFS" if self.hold_db > -120 else "–")
        self.lbl_clip.setText(str(self.clips))
        if now - self._advice_t < 0.4:
            return
        self._advice_t = now
        h = self.hold_db
        if h >= -1:
            st, msg, adv = "bad", "VỠ TIẾNG — quá tải", f"Giảm gain khoảng {max(6, round(h + 12))} dB."
        elif h >= -6:
            st, msg, adv = "warn", "Hơi to", f"Nên giảm gain khoảng {round(h + 12)} dB để chừa khoảng an toàn."
        elif h >= -24:
            st, msg, adv = "ok", "Tốt", "Mức vào hợp lý (đỉnh −24 … −6 dBFS)."
        elif h >= -45:
            st, msg, adv = "warn", "Nhỏ", f"Thử tăng gain khoảng {round(-12 - h)} dB (nói / hát ở mức thật khi chỉnh)."
        else:
            st, msg, adv = "idle", "Gần như không có tín hiệu", "Kiểm tra micro, dây và nguồn vào đã chọn."
        self.lbl_status.setText(msg)
        self.lbl_advice.setText(adv)
        self._set_status_state(st)

    def _set_status_state(self, st):
        w = self.lbl_status
        if w.property("state") != st:
            w.setProperty("state", st)
            w.style().unpolish(w)
            w.style().polish(w)

    # ============ hú
    def show_feedback(self, fb):
        self.spec.feedback = fb
        if fb:
            top = max(fb, key=lambda t: t["level"])
            text = "⚠ HÚ  " + "  ·  ".join(fmt_hz(t["hz"]) for t in sorted(fb, key=lambda t: -t["level"])[:3])
        else:
            top, text = None, ""
        on = bool(fb)
        if self.lbl_alert.property("on") != on:
            self.lbl_alert.setProperty("on", on)
            self.lbl_alert.style().unpolish(self.lbl_alert)
            self.lbl_alert.style().polish(self.lbl_alert)
        self.lbl_alert.setText(text if on else ("Đang theo dõi — không phát hiện hú" if self.mic.running()
                                                else "Không phát hiện hú"))
        if self.isVisible() or not on:
            self.fb_list.clear()
            for t in sorted(fb, key=lambda t: -t["level"]):
                cut = eq_advice(t["level"])
                it = QTreeWidgetItem([fmt_hz(t["hz"]), f"{t['level']:.0f} dB",
                                      f"Cắt −{cut} dB, Q hẹp (8–10) · EQ 31 băng: {band_label(nearest_band(t['hz']))}"])
                it.setForeground(0, QColor(T["danger"]))
                self.fb_list.addTopLevelItem(it)
        if text != self._alert:
            self._alert = text
            self.feedbackAlert.emit(text if top else "")

    # ============ ring-out
    def _load_ringout(self):
        import json
        try:
            return json.loads(self.host.settings.value("sc_ringout", "[]"))
        except (TypeError, ValueError):
            return []

    def _save_ringout(self):
        import json
        self.host.settings.setValue("sc_ringout", json.dumps(self.ringout))
        self.spec.ringout = [x["hz"] for x in self.ringout]
        self.spec.update()

    def set_ringout(self, on):
        if on and not self.mic.running():
            self.set_running(True)
            if not self.mic.running():
                self.btn_ring.setChecked(False)
                return
        self.ringing = on
        self.btn_ring.setText("■  Dừng ring-out" if on else "●  Bắt đầu ring-out")
        if on:
            self.det.reset()

    def ring_add(self, t):
        hz = float(t["hz"])
        for x in self.ringout:
            if abs(math.log2(hz / x["hz"])) < 1 / 12:
                x["level"] = max(x["level"], t["level"])
                return
        self.ringout.append({"hz": round(hz, 1), "level": round(t["level"], 1), "time": time.strftime("%H:%M:%S")})
        self.ringout.sort(key=lambda x: x["hz"])
        self._save_ringout()
        self.refresh_ring_list()
        QGuiApplication.beep()

    def refresh_ring_list(self):
        self.ring_list.clear()
        for i, x in enumerate(self.ringout):
            self.ring_list.addTopLevelItem(QTreeWidgetItem(
                [str(i + 1), fmt_hz(x["hz"]), band_label(nearest_band(x["hz"])),
                 f"Cắt −{eq_advice(x['level'])} dB, Q hẹp", x.get("time", "")]))

    def ring_remove(self):
        rows = sorted({self.ring_list.indexOfTopLevelItem(it) for it in self.ring_list.selectedItems()}, reverse=True)
        for r in rows:
            del self.ringout[r]
        self._save_ringout()
        self.refresh_ring_list()

    def ring_clear(self):
        if self.ringout and QMessageBox.question(self, "Ring-out", "Xóa toàn bộ danh sách tần số dễ hú?") \
                == QMessageBox.StandardButton.Yes:
            self.ringout = []
            self._save_ringout()
            self.refresh_ring_list()

    def ring_copy(self):
        lines = ["Tần số dễ hú (ring-out):"] + [
            f"{i + 1}. {fmt_hz(x['hz'])}  (EQ 31 băng: {band_label(nearest_band(x['hz']))})  "
            f"cắt −{eq_advice(x['level'])} dB" for i, x in enumerate(self.ringout)]
        QGuiApplication.clipboard().setText("\n".join(lines))
        self.host.statusBar().showMessage("Đã sao chép danh sách ring-out", 3000)

    # ============ đo phòng
    def room_toggle(self):
        if self.room:
            self.room_stop("Đã hủy đo phòng.")
            return
        if not self.mic.running():
            self.set_running(True)
            if not self.mic.running():
                return
        if self.btn_tone.isChecked():
            self.btn_tone.setChecked(False)
        self.room = {"phase": "noise", "t0": time.time(), "noise": np.zeros(len(ISO_BANDS)), "nn": 0,
                     "sig": np.zeros(len(ISO_BANDS)), "ns": 0}
        self.btn_room.setText("■  Hủy đo phòng")
        self.lbl_room.setText("Đang đo tiếng ồn nền (2 giây) — giữ yên lặng...")

    def room_tick(self, bands):
        r = self.room
        el = time.time() - r["t0"]
        if r["phase"] == "noise":
            r["noise"] += bands
            r["nn"] += 1
            if el >= 2:
                if not self.out.start(self.output_dev(), "pink", level_db=self.sp_room_lv.value()):
                    self.room_stop("Không mở được loa phát.")
                    return
                r["phase"], r["t0"] = "settle", time.time()
                self.lbl_room.setText("Đang phát pink noise...")
        elif r["phase"] == "settle":
            if el >= 1:
                r["phase"], r["t0"] = "measure", time.time()
        elif r["phase"] == "measure":
            r["sig"] += bands
            r["ns"] += 1
            dur = self.sp_room_t.value()
            self.lbl_room.setText(f"Đang đo... {min(dur, el):.0f} / {dur} giây")
            if el >= dur:
                self.out.stop()
                self.room_result()

    def room_result(self):
        r = self.room
        noise = r["noise"] / max(1, r["nn"])
        sig = r["sig"] / max(1, r["ns"])
        sig_db, noise_db = db(sig), db(noise)
        snr = sig_db - noise_db
        idx = [k for k, f in enumerate(ISO_BANDS) if 63 <= f <= 12500]
        valid = snr > 10
        ref_k = [k for k in idx if valid[k]]
        if len(ref_k) < 6:
            self.room_stop("Tín hiệu đo quá nhỏ so với tiếng ồn nền (cần lớn hơn 10 dB). "
                           "Tăng mức pink noise hoặc âm lượng loa rồi đo lại.")
            return
        ref = float(np.mean(sig_db[ref_k]))
        dev = sig_db - ref
        self.room_chart.set(dev, valid)
        cuts = sorted([k for k in ref_k if dev[k] > 3], key=lambda k: -dev[k])[:6]
        dips = sorted([k for k in ref_k if dev[k] < -6], key=lambda k: dev[k])[:3]
        lines = []
        if cuts:
            lines.append("<b>Nên cắt:</b> " + ", ".join(
                f"{band_label(ISO_BANDS[k])} <b>−{min(12, round(dev[k]))} dB</b>" for k in cuts))
        if dips:
            lines.append("<b>Bị thiếu:</b> " + ", ".join(f"{band_label(ISO_BANDS[k])} ({dev[k]:.0f} dB)" for k in dips)
                         + " — chỉ nên tăng tối đa +3 dB; thiếu nhiều thường do vị trí loa / phản xạ phòng.")
        if not lines:
            lines.append("<b>Đáp tuyến khá phẳng</b> (lệch dưới ±3 dB) — không cần chỉnh EQ nhiều.")
        lines.append(f"<span style='color:{T['text_dim']}'>Tín hiệu trên ồn nền: trung bình {np.mean(snr[ref_k]):.0f} dB. "
                     "Cột xám = dải quá gần tiếng ồn, bỏ qua.</span>")
        self.lbl_room_adv.setText("<br>".join(lines))
        self.room_stop("Đo xong lúc " + time.strftime("%H:%M:%S") + ".")

    def room_stop(self, msg):
        if self.room and self.room["phase"] != "noise":
            self.out.stop()
        self.room = None
        self.btn_room.setText("▶  Bắt đầu đo phòng")
        self.lbl_room.setText(msg)

    # ============ tone
    def tone_params(self, *_a):
        kind = self.cmb_kind.currentData()
        self.sp_freq.setEnabled(kind == "sine")
        for s in (self.sp_sw1, self.sp_sw2, self.sp_swt):
            s.setEnabled(kind == "sweep")
        if self.out.playing():
            self.out.kind = kind
            self.out.freq = self.sp_freq.value()
            self.out.sweep = (float(min(self.sp_sw1.value(), self.sp_sw2.value() - 1)),
                              float(self.sp_sw2.value()), float(self.sp_swt.value()))

    def tone_toggle(self, on):
        if on:
            if self.room:
                self.room_stop("Đã hủy đo phòng để phát tone.")
            kind = self.cmb_kind.currentData()
            sweep = (float(min(self.sp_sw1.value(), self.sp_sw2.value() - 1)), float(self.sp_sw2.value()),
                     float(self.sp_swt.value()))
            if not self.out.start(self.output_dev(), kind, self.sp_freq.value(), self.sp_lv.value(), sweep):
                self.btn_tone.setChecked(False)
                QMessageBox.warning(self, "Phát tone", "Không mở được loa phát.")
                return
            self.host.settings.setValue("sc_out", self.cmb_out.currentText())
            self.btn_tone.setText("■  Dừng")
            self._tone_timer = QTimer(self)
            self._tone_timer.setInterval(100)
            self._tone_timer.timeout.connect(self._tone_label)
            self._tone_timer.start()
        else:
            self.out.stop()
            self.btn_tone.setText("▶  Phát")
            if getattr(self, "_tone_timer", None):
                self._tone_timer.stop()
            self.lbl_tone.setText("")
        self.tone_params()

    def _tone_label(self):
        k = self.cmb_kind.currentData()
        if k in ("sine", "sweep") and self.out.cur_freq:
            self.lbl_tone.setText("Đang phát: " + fmt_hz(self.out.cur_freq))
        else:
            self.lbl_tone.setText("Đang phát: " + self.cmb_kind.currentText())

    # ============ dừng / tắt
    def stop_output(self):
        """Dừng mọi tín hiệu phát thử (gọi khi bấm Dừng hết / Esc)."""
        if self.room:
            self.room_stop("Đã dừng.")
        if self.btn_tone.isChecked():
            self.btn_tone.setChecked(False)
        self.out.stop()

    def shutdown(self):
        self.out.stop_now()
        self.mic.stop()
        self.timer.stop()

    def retheme(self):
        for w in (self.spec, self.level, self.room_chart):
            w.update()

    def sizeHint(self):
        return QSize(1100, 700)
