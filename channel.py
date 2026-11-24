"""Một kênh phát (channel strip): fader, VU, thời gian, nút cart, điều khiển."""
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QToolButton, QVBoxLayout, QWidget)

from audio import Deck, find_output_device, percent_to_db
from playlist import AUDIO_EXT, AUDIO_FILTER, read_meta
from widgets import CartButton, Fader, SeekSlider, VUMeter, glyph_icon, shape_icon

DEFAULT_FADER = 80
FADE_STEP, FADE_QUICK_MAX = 0.5, 3.0    # nút fade trên kênh: +0,5 giây mỗi lần bấm, quá 3 giây về tắt
_icon_cache = {}


def icon(kind, color):
    key = (kind, color)
    if key not in _icon_cache:
        _icon_cache[key] = (glyph_icon("", color) if kind == "loop" else shape_icon(kind, color))
    return _icon_cache[key]


def hms(ms):
    s = max(0, int(ms) // 1000)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def fmt_sec(s):
    return f"{s:g}".replace(".", ",") + " giây"


class ChannelStrip(QWidget):
    started = Signal(object)    # kênh vừa bắt đầu phát (cho chế độ Phát đơn)
    changed = Signal()          # cấu hình kênh thay đổi (đánh dấu dự án chưa lưu)
    message = Signal(str)

    def __init__(self, number, hotkey, host, parent=None):
        super().__init__(parent)
        self.number, self.hotkey, self.host = number, hotkey, host
        self.deck = Deck(self, meter=True)
        self.deck.stateChanged.connect(self.refresh)
        self.deck.ended.connect(self.on_ended)
        self.deck.error.connect(lambda m: self.message.emit(f"Kênh {self.number}: {m}"))
        self.path = self.name = self.color = self.device = ""
        self.mode = "play_stop"     # play_stop | play_pause | retrigger
        self.loop = False
        self.fade_in_s = 0.0
        self.fade_out_s = 0.0
        self.start_ms = 0           # đoạn phát: điểm bắt đầu
        self.end_ms = 0             # đoạn phát: điểm kết thúc (0 = cuối file)
        self.duration = 0
        self.own_key = ""           # "" = theo phím ô của trang, "-" = không phím, khác = phím riêng
        self._end_fading = False
        self._last_times = None
        self.last_levels = [0.0, 0.0]
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(3)
        self.lbl_head = QLabel(f"Kênh {number}")
        self.lbl_head.setObjectName("chHead")
        root.addWidget(self.lbl_head)
        frame = QFrame()
        frame.setObjectName("strip")
        root.addWidget(frame, 1)
        v = QVBoxLayout(frame)
        v.setContentsMargins(7, 7, 7, 4)
        v.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(2)
        left = QVBoxLayout()
        self.btn_file = QToolButton()
        self.btn_file.setIcon(glyph_icon("", "#555"))
        self.btn_file.setToolTip("Chọn file nhạc cho kênh")
        self.btn_file.setAutoRaise(True)
        self.btn_file.setIconSize(QSize(15, 15))
        self.btn_file.clicked.connect(self.choose_file)
        self.btn_more = QToolButton()
        self.btn_more.setText("•••")
        self.btn_more.setObjectName("more")
        self.btn_more.setToolTip("Tùy chọn kênh")
        self.btn_more.clicked.connect(
            lambda: self.show_menu(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft())))
        for b in (self.btn_file, self.btn_more):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            left.addWidget(b)
        left.addStretch()
        top.addLayout(left)
        self.fader = Fader()
        self.fader.setValue(DEFAULT_FADER)
        self.fader.valueChanged.connect(self.on_fader)
        top.addWidget(self.fader, 1)
        self.meter = VUMeter()
        top.addWidget(self.meter)
        v.addLayout(top, 1)

        self.lbl_level = QLabel()
        self.lbl_elapsed = QLabel("00:00:00")
        self.lbl_time2 = QLabel("00:00:00")
        for lb in (self.lbl_level, self.lbl_elapsed, self.lbl_time2):
            lb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v.addWidget(lb)
        self.lbl_level.setObjectName("level")
        self.lbl_elapsed.setObjectName("time")
        self.lbl_time2.setObjectName("time")

        self.cart = CartButton(self)
        self.cart.clicked.connect(self.cart_clicked)
        self.cart.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cart.customContextMenuRequested.connect(lambda pos: self.show_menu(self.cart.mapToGlobal(pos)))
        v.addSpacing(2)
        v.addWidget(self.cart)

        row = QHBoxLayout()
        row.setSpacing(5)
        self.btn_pause = QPushButton("‖")
        self.btn_pause.setToolTip("Tạm dừng / tiếp tục")
        self.btn_pause.clicked.connect(self.pause_toggle)
        self.btn_stop = QPushButton("Dừng")
        self.btn_stop.setToolTip("Dừng (có fade out nếu đã đặt)")
        self.btn_stop.clicked.connect(lambda: self.stop())
        for b in (self.btn_pause, self.btn_stop):
            b.setObjectName("chBtn")
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            row.addWidget(b)
        v.addLayout(row)

        self.seek = SeekSlider()
        self.seek.setObjectName("chSeek")
        self.seek.seekRequested.connect(self.seek_to)
        v.addWidget(self.seek)

        bot = QHBoxLayout()
        bot.setSpacing(0)

        def tb(tip, slot):
            b = QToolButton()
            b.setAutoRaise(True)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setObjectName("chIcon")
            b.setIconSize(QSize(13, 13))
            b.clicked.connect(slot)
            bot.addWidget(b)
            return b

        self.b_play = tb("Phát từ đầu đoạn", lambda: self.play(restart=True))
        self.b_state = tb("Dừng", lambda: self.stop())
        bot.addStretch()
        self.b_loop = tb("", self.toggle_loop)
        bot.addStretch()
        self.b_fin = tb("", lambda: self.bump_fade("in"))
        bot.addStretch()
        self.b_fout = tb("", lambda: self.bump_fade("out"))
        v.addLayout(bot)

        self.on_fader(DEFAULT_FADER, emit=False)
        self.refresh()

    # ================= thông tin =================
    def display_name(self):
        return self.name or os.path.splitext(os.path.basename(self.path))[0]

    def seg_end(self):
        """Điểm kết thúc thực tế (ms)."""
        dur = self.deck.duration() or self.duration
        return min(self.end_ms, dur) if self.end_ms and dur else (self.end_ms or dur)

    def seg_len(self):
        return max(0, self.seg_end() - self.start_ms)

    def remaining_ms(self):
        return max(0, self.seg_end() - self.deck.position())

    def manual_loop(self):
        return self.loop and (self.start_ms > 0 or self.end_ms > 0)

    def cart_color(self):
        if not self.path:
            return "#efefef"
        if self.deck.is_playing():
            return QColor(self.color).darker(108).name() if self.color else "#fbd5e5"
        if self.deck.is_paused():
            return "#fde68a"
        return self.color or "#ffffff"

    # ================= hiển thị =================
    def refresh(self):
        loaded = bool(self.path)
        playing, paused = self.deck.is_playing(), self.deck.is_paused()
        dim, dark, green = "#b5b5b5", "#555555", "#16a34a"
        base = dark if loaded else dim
        self.b_play.setIcon(icon("play", green if playing else base))
        self.b_state.setIcon(icon("pause" if paused else "stop", green if (playing or paused) else base))
        self.b_loop.setIcon(icon("loop", green if self.loop else base))
        self.b_fin.setIcon(icon("fadein", green if self.fade_in_s > 0 else base))
        self.b_fout.setIcon(icon("fadeout", green if self.fade_out_s > 0 else base))
        self.b_loop.setToolTip("Lặp: " + ("đang bật" if self.loop else "đang tắt") + ". Bấm để bật/tắt.")
        for b, s, what in ((self.b_fin, self.fade_in_s, "Fade in (to dần lúc phát)"),
                           (self.b_fout, self.fade_out_s, "Fade out (nhỏ dần lúc dừng)")):
            b.setToolTip(f"{what}: {'đang tắt' if s <= 0 else fmt_sec(s)}.\n"
                         f"Bấm để tăng 0,5 giây, quá 3 giây về tắt.\n"
                         f"Muốn dài hơn 3 giây vào Cài đặt kênh.")
        for w in (self.btn_pause, self.btn_stop, self.seek, self.b_play, self.b_state):
            w.setEnabled(loaded)
        self.btn_pause.setProperty("active", paused)
        self.btn_pause.style().unpolish(self.btn_pause)
        self.btn_pause.style().polish(self.btn_pause)
        for lb in (self.lbl_level, self.lbl_elapsed, self.lbl_time2):
            lb.setProperty("dim", not loaded)
            lb.style().unpolish(lb)
            lb.style().polish(lb)
        if not (playing or paused):
            self.lbl_elapsed.setText("00:00:00")
            self.lbl_time2.setText(hms(self.seg_len()))
            self.seek.setValue(self.seek.minimum())
            self._last_times = None
        self.cart.update()

    def tick(self):
        pre, self.last_levels = self.deck.take_levels()   # last_levels: sau Master
        self.meter.set_levels(pre)
        if not (self.deck.is_playing() or self.deck.is_paused()):
            return
        pos = self.deck.position()
        end = self.seg_end()
        if self.deck.is_playing() and not self.deck._pending and end:
            if self.end_ms and pos >= end - 10:            # tới điểm kết thúc tự đặt
                if self.loop:
                    self.deck.player.setPosition(self.start_ms)
                    self._end_fading = False
                else:
                    self.deck.stop()
                    return
            elif (self.fade_out_s > 0 and not self.loop and not self._end_fading
                  and not self.deck.fading_out() and end - pos <= self.fade_out_s * 1000):
                self._end_fading = True                    # nhỏ dần trước khi hết đoạn
                self.deck.fade_to(0.0, max(1, end - pos))
        times = ((pos - self.start_ms) // 1000, (end - pos) // 1000)
        if times != self._last_times:
            self._last_times = times
            self.lbl_elapsed.setText(hms(pos - self.start_ms))
            self.lbl_time2.setText("-" + hms(max(0, end - pos)))
        if not self.seek.isSliderDown():
            self.seek.setRange(self.start_ms, max(self.start_ms + 1, end))
            self.seek.setValue(pos)

    def on_fader(self, val, emit=True):
        self.deck.set_master(val / 100)
        db = percent_to_db(val / 100)
        dbt = f"{db:+.1f} dB" if db is not None else "-∞ dB"
        self.lbl_level.setText(f"<span style='font-size:9.5pt'>{val}%</span>&nbsp;&nbsp;"
                               f"<span style='font-size:8pt'>{dbt}</span>")
        self.update_out_tip()
        if emit:
            self.changed.emit()

    def update_out_tip(self):
        out = self.fader.value() * self.deck.bus
        db = percent_to_db(out / 100)
        self.lbl_level.setToolTip(f"Mức ra loa = kênh {self.fader.value()}% × Master {round(self.deck.bus * 100)}%"
                                  f" = {out:.0f}%" + (f"  ({db:+.1f} dB)" if db is not None else ""))

    # ================= điều khiển =================
    def cart_clicked(self):
        if not self.path:
            if not self.host.locked:
                self.choose_file()
            return
        playing = self.deck.is_playing()
        if self.mode == "retrigger":
            self.play(restart=True)
        elif self.mode == "play_pause":
            if playing:
                self.deck.pause(self.host.cfg["pause_fade_ms"])
            else:
                self.play()
        else:  # play_stop
            if playing and not self.deck.fading_out():
                self.stop()
            elif playing:
                self.stop_now()        # bấm lần 2 khi đang fade out = dừng ngay
            else:
                self.play()

    def play(self, restart=False):
        if not self.path:
            return
        if self.deck.is_paused() and not restart:
            self.deck.play(self.host.cfg["pause_fade_ms"])
            return
        if not os.path.isfile(self.path):
            self.message.emit(f"Kênh {self.number}: không tìm thấy file {self.path}")
            return
        self.deck.load(self.path)
        self.deck.player.setLoops(-1 if (self.loop and not self.manual_loop()) else 1)
        self._end_fading = False
        self.deck.play_from(self.start_ms, int(self.fade_in_s * 1000))
        self.started.emit(self)

    def on_ended(self):
        if self.manual_loop():                 # lặp đoạn có điểm đầu: phát lại từ điểm đầu
            self._end_fading = False
            self.deck.play_from(self.start_ms)

    def pause_toggle(self):
        if self.deck.is_playing():
            self.deck.pause(self.host.cfg["pause_fade_ms"])
        elif self.deck.is_paused():
            self.deck.play(self.host.cfg["pause_fade_ms"])

    def stop(self, fade_ms=None):
        """Dừng; mặc định dùng fade out của kênh."""
        if fade_ms is None:
            fade_ms = int(self.fade_out_s * 1000)
        self.deck.stop(fade_ms if self.deck.is_playing() else 0)

    def stop_now(self):
        self.deck.stop()

    def seek_to(self, ms):
        if self.deck.is_playing() or self.deck.is_paused():
            self.deck.player.setPosition(ms)
            self._end_fading = False
            if self.deck.gain < 1 and not self.deck.fading_out():
                self.deck.gain = 1.0
                self.deck._apply()

    def toggle_loop(self):
        self.loop = not self.loop
        if self.deck.is_playing() or self.deck.is_paused():
            self.deck.player.setLoops(-1 if (self.loop and not self.manual_loop()) else 1)
        self.refresh()
        self.changed.emit()

    def bump_fade(self, which):
        cur = self.fade_in_s if which == "in" else self.fade_out_s
        new = 0.0 if cur >= FADE_QUICK_MAX else round(cur + FADE_STEP, 1)
        if which == "in":
            self.fade_in_s = new
        else:
            self.fade_out_s = new
        self.refresh()
        self.changed.emit()
        what = "Fade in" if which == "in" else "Fade out"
        self.message.emit(f"Kênh {self.number}: {what} " + ("tắt" if new <= 0 else fmt_sec(new)))

    def set_bus(self, b):
        self.deck.set_bus(b)

    def apply_device(self):
        self.deck.set_device(find_output_device(self.device or self.host.cfg["cart_device"]))

    # ================= cấu hình kênh =================
    def set_file(self, path):
        was_empty = not self.path
        self.deck.stop()
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.duration = read_meta(path)[2]
        self.start_ms = self.end_ms = 0
        if was_empty:                          # kênh trống: áp dụng mặc định (*)
            d = self.host.channel_defaults()
            self.mode = d.get("mode", self.mode)
            self.fade_in_s = float(d.get("fade_in", self.fade_in_s))
            self.fade_out_s = float(d.get("fade_out", self.fade_out_s))
        self.refresh()
        self.changed.emit()

    def choose_file(self):
        if self.host.locked:
            return
        path, _ = QFileDialog.getOpenFileName(self, f"Chọn nhạc cho kênh {self.number}",
                                              self.host.settings.value("lastDir", ""), AUDIO_FILTER)
        if path:
            self.host.settings.setValue("lastDir", os.path.dirname(path))
            self.set_file(path)

    def show_menu(self, gpos):
        if self.host.locked:
            return
        m = QMenu(self)
        loaded = bool(self.path)
        m.addAction("Cài đặt kênh...", lambda: self.host.open_channel_settings(self))
        m.addAction("Chọn file...", self.choose_file)
        a = m.addAction("Thêm vào playlist", lambda: self.host.add_to_playlist(self.path))
        a.setEnabled(loaded)
        m.addSeparator()
        for text, fn in (("Phát từ đầu", lambda: self.play(restart=True)), ("Dừng", lambda: self.stop()),
                         ("Dừng ngay (bỏ fade)", self.stop_now)):
            a = m.addAction(text, fn)
            a.setEnabled(loaded)
        m.addSeparator()
        a = m.addAction("Bỏ file khỏi kênh", self.clear)
        a.setEnabled(loaded)
        m.exec(gpos)

    def clear(self):
        self.deck.stop()
        self.path = self.name = self.color = ""
        self.loop = False
        self.start_ms = self.end_ms = 0
        self.duration = 0
        self.refresh()
        self.changed.emit()

    def to_dict(self):
        return {"path": self.path, "name": self.name, "color": self.color, "loop": self.loop,
                "mode": self.mode, "fade_in_s": self.fade_in_s, "fade_out_s": self.fade_out_s,
                "start_ms": self.start_ms, "end_ms": self.end_ms,
                "volume": self.fader.value(), "device": self.device,
                "duration": self.duration, "key": self.own_key}

    def from_dict(self, d):
        self.deck.stop()
        self.path = d.get("path", "")
        self.name = d.get("name", "")
        self.color = d.get("color", "")
        self.loop = bool(d.get("loop", False))
        self.mode = d.get("mode", "play_stop")
        # tương thích dự án cũ: "fade_in" kiểu bật/tắt = 2 giây
        self.fade_in_s = float(d.get("fade_in_s", 2.0 if d.get("fade_in") is True else 0.0))
        self.fade_out_s = float(d.get("fade_out_s", 0.0))
        self.start_ms = int(d.get("start_ms", 0))
        self.end_ms = int(d.get("end_ms", 0))
        self.device = d.get("device", "")
        self.own_key = d.get("key", "")
        self.duration = int(d.get("duration", 0))
        if self.path and not self.duration and os.path.isfile(self.path):
            self.duration = read_meta(self.path)[2]
        self.fader.blockSignals(True)
        self.fader.setValue(int(d.get("volume", DEFAULT_FADER)))
        self.fader.blockSignals(False)
        self.on_fader(self.fader.value(), emit=False)
        self.apply_device()
        self.refresh()

    # ================= kéo thả =================
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and not self.host.locked:
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.splitext(p)[1].lower() in AUDIO_EXT:
                self.set_file(p)
                break
