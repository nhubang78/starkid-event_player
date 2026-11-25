"""MC NÓI: nghe micro MC, khi có tiếng nói thì tự giảm âm lượng nhạc (ducking), ngừng nói thì nhạc lên lại.

Máy tính cần nghe được tiếng MC: micro cắm vào máy tính, hoặc ngõ ra AUX / REC của mixer cắm vào line-in.
Chỉ giảm các kênh và Playlist; tai nghe nghe thử và tone thử loa không bị giảm.
"""
import json
import math
import time

from PySide6.QtCore import QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel, QSpinBox, QVBoxLayout,
                               QWidget)

from soundcheck import MicInput, find_device
from theme import T

DEFAULTS = {"device": "", "threshold": -38, "pct": 15, "attack": 150, "hold": 700, "release": 1500}


def db_to_duck(db):
    """dB giảm -> hệ số 'duck' của Deck (Deck nhân theo thang % rồi đổi % -> biên độ với mũ 5/3)."""
    return 10 ** (db / (20 * 5 / 3))


class Ducker(QObject):
    changed = Signal()            # trạng thái / mức đổi -> cập nhật giao diện

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.cfg = dict(DEFAULTS)
        try:
            saved = json.loads(host.settings.value("duck", "{}"))
        except (TypeError, ValueError):
            saved = {}
        saved.pop("depth", None)                              # cài đặt cũ theo dB: bỏ, dùng % mặc định
        self.cfg.update(saved)
        self.mic = MicInput(self)
        self.enabled = False
        self.level_db = -120.0
        self.value = 1.0           # hệ số duck hiện tại (1 = không giảm)
        self.sfx_level = None      # hàm -> % nhạc còn lại khi hiệu ứng đang kêu (None = không giảm)
        self.by_sfx = False
        self.ducking = False
        self._last_voice = 0.0
        self._t = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(25)
        self.timer.timeout.connect(self.tick)

    def duck_level(self):
        """Hệ số âm lượng nhạc khi MC nói (theo %, cùng thang với fader: 100% = giữ nguyên)."""
        return max(0.0, min(1.0, self.cfg["pct"] / 100.0))

    def set_pct(self, v):
        self.cfg["pct"] = int(v)
        self.save()

    def save(self):
        self.host.settings.setValue("duck", json.dumps(self.cfg))

    def device(self):
        return find_device(QMediaDevices.audioInputs(), self.cfg["device"]) or QMediaDevices.defaultAudioInput()

    def set_enabled(self, on):
        if on == self.enabled:
            return True
        if on:
            dev = self.device()
            if dev.isNull() or not self.mic.start(dev):
                self.enabled = False
                self.changed.emit()
                return False
            self.enabled = True
            self._t = time.monotonic()
            self.timer.start()
        else:
            self.enabled = False
            self.mic.stop()
            self.level_db = -120.0
            self.ducking = False
            self.timer.start()          # tiếp tục chạy để nhạc lên lại từ từ rồi tự dừng
        self.changed.emit()
        return True

    def poke(self):
        """Có nguồn giảm nhạc khác (hiệu ứng) vừa bắt đầu: chạy vòng cập nhật nếu đang nghỉ."""
        self._poke_until = time.monotonic() + 1.0     # chờ trình phát kịp chuyển sang "đang phát"
        if not self.timer.isActive():
            self._t = time.monotonic()
            self.timer.start()

    def restart_mic(self):
        if self.enabled:
            self.mic.stop()
            self.mic.start(self.device())

    def tick(self):
        now = time.monotonic()
        dt = (now - self._t) * 1000
        self._t = now
        if self.enabled:
            _pk, rms = self.mic.take_level()
            db = 20 * math.log10(rms) if rms > 1e-6 else -120.0
            self.level_db = db if db > self.level_db else max(db, self.level_db - dt * 0.06)   # đồng hồ rơi mượt
            if db > self.cfg["threshold"]:
                self._last_voice = now
            voice = (now - self._last_voice) * 1000 < self.cfg["hold"]
        else:
            voice = False
        low = self.duck_level()
        target = low if voice else 1.0
        sfx = self.sfx_level() if self.sfx_level else None       # hiệu ứng đang kêu + "Hạ nhạc nền"
        self.by_sfx = sfx is not None and sfx < target
        if self.by_sfx:
            target = sfx
        span = max(1e-3, 1.0 - min(low, sfx if sfx is not None else 1.0))
        if target < self.value:
            self.value = max(target, self.value - span * dt / max(10, self.cfg["attack"]))
        elif target > self.value:
            self.value = min(target, self.value + span * dt / max(10, self.cfg["release"]))
        self.apply(self.value)
        was = self.ducking
        self.ducking = self.value < 0.999
        if not self.enabled and not self.ducking and sfx is None and now > getattr(self, "_poke_until", 0):
            self.timer.stop()
        if was != self.ducking or self.enabled:
            self.changed.emit()

    def apply(self, v):
        last = getattr(self, "_applied", 1.0)
        if v == last or (abs(v - last) < 0.002 and v != 1.0):
            return
        self._applied = v
        for s in self.host.strips:
            s.deck.set_duck(v)
        for d in self.host.playlist.decks:
            d.set_duck(v)

    def shutdown(self):
        self.timer.stop()
        self.mic.stop()
        self.apply(1.0)


class MicLevel(QWidget):
    """Thanh mức micro nhỏ có vạch ngưỡng (dùng trên thanh MC NÓI và trong hộp thoại)."""

    def __init__(self, ducker, w=64, h=8):
        super().__init__()
        self.d = ducker
        self.setFixedSize(w, h)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        lo, hi = -70.0, 0.0
        xf = lambda v: r.left() + (max(lo, min(hi, v)) - lo) / (hi - lo) * r.width()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T["meter_bg"]))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.d.enabled:
            over = self.d.level_db > self.d.cfg["threshold"]
            p.setBrush(QColor(T["warn"] if over else T["ok"]))
            p.drawRoundedRect(QRectF(r.left(), r.top(), xf(self.d.level_db) - r.left(), r.height()),
                              r.height() / 2, r.height() / 2)
        p.setBrush(QColor(T["text"]))
        x = xf(self.d.cfg["threshold"])
        p.drawRect(QRectF(x - 1, r.top() - 1, 2, r.height() + 2))


class DuckSettingsDialog(QDialog):
    def __init__(self, parent, ducker):
        super().__init__(parent)
        self.d = ducker
        self.setWindowTitle("MC nói — tự giảm nhạc")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 14)
        t = QLabel("MC nói — tự giảm nhạc")
        t.setObjectName("title")
        v.addWidget(t)
        n = QLabel("Khi tiếng micro vượt <b>ngưỡng</b>, nhạc (các kênh + Playlist) tự giảm xuống. MC ngừng nói quá "
                   "thời gian <b>giữ</b> thì nhạc lên lại từ từ. Máy tính cần nghe được micro MC: micro cắm vào máy, "
                   "hoặc ngõ AUX / REC của mixer cắm vào line-in.")
        n.setObjectName("note")
        n.setWordWrap(True)
        v.addWidget(n)
        form = QFormLayout()
        form.setVerticalSpacing(8)
        self.cmb = QComboBox()
        names = [d.description() for d in QMediaDevices.audioInputs()]
        self.cmb.addItem("(Micro mặc định của Windows)", "")
        for nm in names:
            self.cmb.addItem(nm, nm)
        self.cmb.setCurrentIndex(max(0, self.cmb.findData(ducker.cfg["device"])))
        form.addRow("Micro MC:", self.cmb)
        row = QWidget()
        from PySide6.QtWidgets import QHBoxLayout
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        self.sp_thr = self._spin(-70, -6, ducker.cfg["threshold"], " dBFS")
        h.addWidget(self.sp_thr)
        self.meter = MicLevel(ducker, 160, 12)
        h.addWidget(self.meter)
        h.addStretch()
        form.addRow("Ngưỡng nói:", row)
        self.sp_depth = self._spin(0, 95, ducker.cfg["pct"], " %", 5)
        self.sp_depth.setToolTip("Âm lượng nhạc khi MC nói, tính theo % như fader (100% = không giảm, 0% = tắt hẳn)")
        form.addRow("Nhạc giảm còn:", self.sp_depth)
        self.sp_att = self._spin(20, 2000, ducker.cfg["attack"], " ms", 10)
        form.addRow("Giảm trong:", self.sp_att)
        self.sp_hold = self._spin(0, 5000, ducker.cfg["hold"], " ms", 50)
        form.addRow("Giữ sau khi ngừng nói:", self.sp_hold)
        self.sp_rel = self._spin(100, 10000, ducker.cfg["release"], " ms", 100)
        form.addRow("Nhạc lên lại trong:", self.sp_rel)
        v.addLayout(form)
        tip = QLabel("Mẹo: bật MC NÓI rồi cho MC nói thử — chỉnh <i>Ngưỡng</i> sao cho thanh mức chuyển vàng khi nói, "
                     "xanh khi im lặng (vạch trắng là ngưỡng).")
        tip.setObjectName("note")
        tip.setWordWrap(True)
        v.addWidget(tip)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        v.addWidget(bb)
        self.sp_thr.valueChanged.connect(self._live)
        ducker.changed.connect(self.meter.update)
        self._orig = dict(ducker.cfg)

    def _spin(self, lo, hi, val, suffix, step=1):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setSingleStep(step)
        s.setValue(int(val))
        s.setSuffix(suffix)
        return s

    def _live(self, v):
        self.d.cfg["threshold"] = v       # xem trực tiếp vạch ngưỡng trên đồng hồ
        self.meter.update()

    def done(self, r):
        try:
            self.d.changed.disconnect(self.meter.update)
        except (RuntimeError, TypeError):
            pass
        if r:
            dev_changed = self.cmb.currentData() != self._orig["device"]
            self.d.cfg.update({"device": self.cmb.currentData(), "threshold": self.sp_thr.value(),
                               "pct": self.sp_depth.value(), "attack": self.sp_att.value(),
                               "hold": self.sp_hold.value(), "release": self.sp_rel.value()})
            self.d.save()
            if dev_changed:
                self.d.restart_mic()
        else:
            self.d.cfg = self._orig
        super().done(r)
