"""Bộ phát âm thanh (Deck) có hỗ trợ fade in/out, ducking và chọn thiết bị ra."""
import math

from PySide6.QtCore import QObject, QTimer, QUrl, Signal, QElapsedTimer
from PySide6.QtMultimedia import (QAudioBufferOutput, QAudioFormat, QAudioOutput, QMediaDevices,
                                  QMediaPlayer)


# Đường cong âm lượng giống thanh âm lượng Windows: 100% = 0 dB, 80% ≈ -3.2 dB, 50% ≈ -10 dB,
# 20% ≈ -23 dB. Biên độ = p^TAPER  (dB = 20·TAPER·log10 p).
TAPER = 5 / 3


def percent_to_amp(p: float) -> float:
    return max(0.0, min(1.0, p)) ** TAPER


def percent_to_db(p: float):
    import math
    return 20 * TAPER * math.log10(p) if p > 0 else None


def find_output_device(description: str):
    """Tìm thiết bị âm thanh theo tên; trả về thiết bị mặc định nếu không thấy."""
    if description:
        for dev in QMediaDevices.audioOutputs():
            if dev.description() == description:
                return dev
    return QMediaDevices.defaultAudioOutput()


class Deck(QObject):
    ended = Signal()
    error = Signal(str)
    stateChanged = Signal()

    def __init__(self, parent=None, meter=False):
        super().__init__(parent)
        self.player = QMediaPlayer(self)
        self.out = QAudioOutput(self)
        self.player.setAudioOutput(self.out)
        self.levels = [0.0, 0.0]  # đỉnh tín hiệu L/R (0..1) kể từ lần đọc trước
        if meter:
            self._buf = QAudioBufferOutput(self)
            self.player.setAudioBufferOutput(self._buf)
            self._buf.audioBufferReceived.connect(self._on_buffer)
        self.bus = 1.0      # âm lượng Master
        self.master = 1.0   # âm lượng kênh (0..1, thang cảm nhận)
        self.duck = 1.0     # hệ số giảm khi phát jingle
        self.gain = 1.0     # hệ số fade
        self._fade = None   # (gain đầu, gain đích, thời gian ms, hàm gọi khi xong)
        self._pending = None  # (vị trí bắt đầu, fade in) chờ file nạp xong
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(20)
        self._timer.timeout.connect(self._tick)
        self.player.mediaStatusChanged.connect(self._on_status)
        self.player.errorOccurred.connect(lambda _e, msg: self.error.emit(msg))
        self.player.playbackStateChanged.connect(lambda _s: self.stateChanged.emit())
        self._apply()

    # ---------- âm lượng ----------
    def _apply(self):
        # Mức ra loa (%) = % kênh × % Master (× fade × duck) — rồi quy đổi % → biên độ
        v = max(0.0, min(1.0, self.bus * self.master * self.gain * self.duck))
        self.out.setVolume(percent_to_amp(v))

    def set_bus(self, b: float):
        self.bus = b
        self._apply()

    # ---------- đo mức (VU) ----------
    _FMT = {QAudioFormat.SampleFormat.Int16: ("h", 32768.0),
            QAudioFormat.SampleFormat.Int32: ("i", 2147483648.0),
            QAudioFormat.SampleFormat.Float: ("f", 1.0)}

    def _on_buffer(self, buf):
        f = buf.format()
        spec = self._FMT.get(f.sampleFormat())
        data = buf.constData()
        if spec is None or data is None:
            return
        code, scale = spec
        ch = max(1, f.channelCount())
        try:
            m = data.cast("B").cast(code)
        except (TypeError, ValueError):
            return
        if len(m) < ch:
            return
        peaks = []
        for c in range(min(ch, 2)):
            s = m[c::ch * 2]  # lấy mẫu thưa cho nhẹ CPU
            peaks.append(max(max(s), -min(s)) / scale)
        if len(peaks) == 1:
            peaks.append(peaks[0])
        self.levels = [max(self.levels[0], peaks[0]), max(self.levels[1], peaks[1])]

    def take_levels(self):
        """Trả về (mức sau fader kênh, mức sau Master) — mỗi cái là [L, R] 0..1 —
        rồi xóa bộ giữ đỉnh."""
        lv, self.levels = self.levels, [0.0, 0.0]
        if not self.is_playing():
            return [0.0, 0.0], [0.0, 0.0]
        ch = percent_to_amp(max(0.0, min(1.0, self.master * self.gain * self.duck)))
        post = self.out.volume()
        return [min(1.0, x * ch) for x in lv], [min(1.0, x * post) for x in lv]

    def set_master(self, m: float):
        self.master = m
        self._apply()

    def set_duck(self, d: float):
        self.duck = d
        self._apply()

    def set_device(self, dev):
        self.out.setDevice(dev)

    # ---------- điều khiển ----------
    def load(self, path: str):
        self._pending = None
        self.cancel_fade()
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(path))

    def play(self, fade_ms: int = 0):
        self.cancel_fade()
        if fade_ms > 0:
            self.gain = 0.0
            self._apply()
            self.player.play()
            self.fade_to(1.0, fade_ms)
        else:
            self.gain = 1.0
            self._apply()
            self.player.play()

    _READY = (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia,
              QMediaPlayer.MediaStatus.BufferingMedia, QMediaPlayer.MediaStatus.EndOfMedia)

    def play_from(self, start_ms: int = 0, fade_ms: int = 0):
        """Phát từ vị trí start_ms. Nếu file chưa nạp xong thì tắt tiếng chờ nạp rồi mới tua,
        tránh nghe lọt đoạn đầu bài."""
        if start_ms <= 0:
            self._pending = None
            self.play(fade_ms)
            return
        if self.player.mediaStatus() in self._READY:
            self._pending = None
            self.player.setPosition(start_ms)
            self.play(fade_ms)
            return
        self.cancel_fade()
        self._pending = (start_ms, fade_ms)
        self.gain = 0.0
        self._apply()
        self.player.play()

    def _apply_pending(self):
        if self._pending is None:
            return
        start_ms, fade_ms = self._pending
        self._pending = None
        curve, self._pending_curve = getattr(self, "_pending_curve", "lin"), "lin"
        self.player.setPosition(start_ms)
        if fade_ms > 0:
            self.fade_to(1.0, fade_ms, curve=curve)
        else:
            self.gain = 1.0
            self._apply()

    def pause(self, fade_ms: int = 0):
        if fade_ms > 0 and self.is_playing():
            self.fade_to(0.0, fade_ms, self.player.pause)
        else:
            self.cancel_fade()
            self.player.pause()

    def stop(self, fade_ms: int = 0, curve: str = "lin"):
        if fade_ms > 0 and self.is_playing():
            self.fade_to(0.0, fade_ms, self._hard_stop, curve)
        else:
            self._hard_stop()

    def _hard_stop(self):
        self._pending = None
        self.cancel_fade()
        self.player.stop()
        self.gain = 1.0
        self._apply()

    # ---------- fade ----------
    def fade_to(self, target: float, ms: int, then=None, curve: str = "lin"):
        """curve: "lin" = đều; "in" / "out" = đường cong công suất đều (crossfade kiểu bàn DJ:
        bài vào lên nhanh lúc đầu, bài ra giữ lâu rồi mới xuống -> tổng âm lượng không hụt ở giữa)."""
        self._fade = (self.gain, target, max(1, ms), then, curve)
        self._clock.start()
        self._timer.start()

    def cancel_fade(self):
        self._fade = None
        self._timer.stop()

    def fading_out(self) -> bool:
        return self._fade is not None and self._fade[1] < self._fade[0]

    def _tick(self):
        if not self._fade:
            self._timer.stop()
            return
        g0, g1, ms, then, curve = self._fade
        t = min(1.0, self._clock.elapsed() / ms)
        # công suất đều theo BIÊN ĐỘ thật: biên độ = gain^TAPER nên gain = (sin|cos)^(1/TAPER)
        if curve == "in":
            k = math.sin(t * math.pi / 2) ** (1 / TAPER)
        elif curve == "out":
            k = 1 - math.cos(t * math.pi / 2) ** (1 / TAPER)
        else:
            k = t
        self.gain = g0 + (g1 - g0) * k
        self._apply()
        if t >= 1.0:
            self._fade = None
            self._timer.stop()
            if then:
                then()

    # ---------- trạng thái ----------
    def _on_status(self, st):
        if st in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self._apply_pending()
        if st == QMediaPlayer.MediaStatus.EndOfMedia:
            self.ended.emit()
        elif st == QMediaPlayer.MediaStatus.InvalidMedia:
            self.error.emit("Không đọc được file: " + self.player.source().toLocalFile())

    def is_playing(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState

    def is_paused(self) -> bool:
        return self.player.playbackState() == QMediaPlayer.PlaybackState.PausedState

    def position(self) -> int:
        return self.player.position()

    def duration(self) -> int:
        return self.player.duration()
