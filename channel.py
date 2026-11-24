"""Một kênh phát (channel strip): fader, VU, thời gian, nút cart, điều khiển."""
import math
import os

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QColorDialog, QFileDialog, QFrame, QHBoxLayout, QInputDialog,
                               QLabel, QMenu, QPushButton, QToolButton, QVBoxLayout, QWidget)
from PySide6.QtMultimedia import QMediaDevices

from audio import Deck, find_output_device
from playlist import AUDIO_EXT, AUDIO_FILTER, read_meta
from widgets import CartButton, Fader, SeekSlider, VUMeter, glyph_icon, shape_icon

DEFAULT_FADER = 80
_icon_cache = {}


def icon(kind, color):
    key = (kind, color)
    if key not in _icon_cache:
        _icon_cache[key] = (glyph_icon("", color) if kind == "loop" else shape_icon(kind, color))
    return _icon_cache[key]


def hms(ms):
    s = max(0, int(ms) // 1000)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


class ChannelStrip(QWidget):
    started = Signal(object)    # kênh vừa bắt đầu phát (cho chế độ Phát đơn)
    changed = Signal()          # cấu hình kênh thay đổi (đánh dấu dự án chưa lưu)
    message = Signal(str)

    def __init__(self, number, hotkey, host, parent=None):
        super().__init__(parent)
        self.number, self.hotkey, self.host = number, hotkey, host
        self.deck = Deck(self, meter=True)
        self.deck.stateChanged.connect(self.refresh)
        self.deck.error.connect(lambda m: self.message.emit(f"Kênh {self.number}: {m}"))
        self.path = self.name = self.color = self.device = ""
        self.loop = False
        self.fade_in = False
        self.duration = 0
        self._last_times = None
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
        v.setContentsMargins(8, 8, 8, 6)
        v.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(2)
        left = QVBoxLayout()
        self.btn_file = QToolButton()
        self.btn_file.setIcon(glyph_icon("", "#555"))
        self.btn_file.setToolTip("Chọn file nhạc cho kênh")
        self.btn_file.setAutoRaise(True)
        self.btn_file.clicked.connect(self.choose_file)
        self.btn_more = QToolButton()
        self.btn_more.setText("•••")
        self.btn_more.setObjectName("more")
        self.btn_more.setToolTip("Tùy chọn kênh")
        self.btn_more.clicked.connect(lambda: self.show_menu(self.btn_more.mapToGlobal(self.btn_more.rect().bottomLeft())))
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
        row.setSpacing(6)
        self.btn_pause = QPushButton("‖")
        self.btn_pause.setToolTip("Tạm dừng / tiếp tục")
        self.btn_pause.clicked.connect(self.pause_toggle)
        self.btn_stop = QPushButton("Dừng")
        self.btn_stop.setToolTip("Dừng ngay")
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

        def tb(tip, slot, checkable=False):
            b = QToolButton()
            b.setAutoRaise(True)
            b.setCheckable(checkable)
            b.setToolTip(tip)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setObjectName("chIcon")
            (b.toggled if checkable else b.clicked).connect(slot)
            bot.addWidget(b)
            return b

        self.b_play = tb("Phát", lambda: self.play())
        self.b_state = tb("Tạm dừng / Dừng", self.state_clicked)
        bot.addStretch()
        self.b_loop = tb("Lặp lại liên tục", self.set_loop, True)
        bot.addStretch()
        self.b_fin = tb("Fade in khi bắt đầu phát", self.set_fade_in, True)
        bot.addStretch()
        self.b_fout = tb("Fade out rồi dừng", self.fade_out)
        v.addLayout(bot)

        self.on_fader(DEFAULT_FADER, emit=False)
        self.refresh()

    # ================= trạng thái / hiển thị =================
    def display_name(self):
        return self.name or os.path.splitext(os.path.basename(self.path))[0]

    def cart_color(self):
        if not self.path:
            return "#efefef"
        if self.deck.is_playing():
            return QColor(self.color).lighter(115).name() if self.color else "#fbd5e5"
        if self.deck.is_paused():
            return "#fde68a"
        return self.color or "#ffffff"

    def refresh(self):
        loaded = bool(self.path)
        playing, paused = self.deck.is_playing(), self.deck.is_paused()
        dim, dark, green = "#b5b5b5", "#555555", "#16a34a"
        self.b_play.setIcon(icon("play", green if playing else (dark if loaded else dim)))
        self.b_state.setIcon(icon("pause" if playing or paused else "stop",
                                  green if (playing or paused) else (dark if loaded else dim)))
        self.b_loop.setIcon(icon("loop", green if self.loop else (dark if loaded else dim)))
        self.b_fin.setIcon(icon("fadein", green if self.fade_in else (dark if loaded else dim)))
        self.b_fout.setIcon(icon("fadeout", dark if loaded else dim))
        self.b_loop.blockSignals(True)
        self.b_loop.setChecked(self.loop)
        self.b_loop.blockSignals(False)
        self.b_fin.blockSignals(True)
        self.b_fin.setChecked(self.fade_in)
        self.b_fin.blockSignals(False)
        for w in (self.btn_pause, self.btn_stop, self.seek, self.b_play, self.b_state, self.b_fout):
            w.setEnabled(loaded)
        self.btn_pause.setProperty("active", paused)
        self.btn_pause.style().unpolish(self.btn_pause)
        self.btn_pause.style().polish(self.btn_pause)
        locked = self.host.locked
        self.btn_file.setEnabled(not locked)
        for lb in (self.lbl_level, self.lbl_elapsed, self.lbl_time2):
            lb.setProperty("dim", not loaded)
            lb.style().unpolish(lb)
            lb.style().polish(lb)
        if not (playing or paused):
            self.lbl_elapsed.setText("00:00:00")
            self.lbl_time2.setText(hms(self.duration))
            self.seek.setValue(0)
            self._last_times = None
        self.cart.update()

    def tick(self):
        self.meter.set_levels(self.deck.take_levels())
        if not (self.deck.is_playing() or self.deck.is_paused()):
            return
        pos, dur = self.deck.position(), self.deck.duration() or self.duration
        times = (pos // 1000, (dur - pos) // 1000)
        if times != self._last_times:
            self._last_times = times
            self.lbl_elapsed.setText(hms(pos))
            self.lbl_time2.setText("-" + hms(max(0, dur - pos)))
        if not self.seek.isSliderDown():
            self.seek.setMaximum(max(1, dur))
            self.seek.setValue(pos)

    def on_fader(self, val, emit=True):
        self.deck.set_master(val / 100)
        db = 40 * math.log10(val / 100) if val > 0 else None
        self.lbl_level.setText(f"{val}%   " + (f"{db:+.1f} dB" if db is not None else "-∞ dB"))
        if emit:
            self.changed.emit()

    # ================= điều khiển =================
    def cart_clicked(self):
        if not self.path:
            if not self.host.locked:
                self.choose_file()
            return
        if self.deck.is_playing():
            self.stop(150)
        else:
            self.play()

    def play(self):
        if not self.path:
            return
        if self.deck.is_paused():
            self.deck.play(self.host.cfg["pause_fade_ms"])
            return
        if not os.path.isfile(self.path):
            self.message.emit(f"Kênh {self.number}: không tìm thấy file {self.path}")
            return
        self.deck.load(self.path)
        self.deck.player.setLoops(-1 if self.loop else 1)
        self.deck.play(self.host.cfg["cart_fade_in_ms"] if self.fade_in else 0)
        self.started.emit(self)

    def pause_toggle(self):
        if self.deck.is_playing():
            self.deck.pause(self.host.cfg["pause_fade_ms"])
        elif self.deck.is_paused():
            self.deck.play(self.host.cfg["pause_fade_ms"])

    def state_clicked(self):
        if self.deck.is_playing() or self.deck.is_paused():
            self.pause_toggle()

    def stop(self, fade_ms=0):
        self.deck.stop(fade_ms)

    def fade_out(self):
        if self.deck.is_playing():
            self.deck.stop(self.host.cfg["cart_fade_out_ms"])
        else:
            self.deck.stop()

    def seek_to(self, ms):
        if self.deck.is_playing() or self.deck.is_paused():
            self.deck.player.setPosition(ms)

    def set_loop(self, on):
        self.loop = on
        if self.deck.is_playing() or self.deck.is_paused():
            self.deck.player.setLoops(-1 if on else 1)
        self.refresh()
        self.changed.emit()

    def set_fade_in(self, on):
        self.fade_in = on
        self.refresh()
        self.changed.emit()

    def set_bus(self, b):
        self.deck.set_bus(b)

    def apply_device(self):
        self.deck.set_device(find_output_device(self.device or self.host.cfg["cart_device"]))

    # ================= cấu hình kênh =================
    def set_file(self, path):
        self.deck.stop()
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.duration = read_meta(path)[2]
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
        m = QMenu(self)
        locked = self.host.locked
        if self.path:
            m.addAction("🎧  Nghe thử ra tai nghe", lambda: self.host.prelisten_file(self.path, self.display_name()))
            m.addSeparator()
        for text, slot, need in (("Chọn file...", self.choose_file, False),
                                 ("Đổi tên hiển thị...", self.rename, True),
                                 ("Đổi màu nút...", self.pick_color, True),
                                 ("Bỏ màu nút", self.clear_color, True)):
            a = m.addAction(text, slot)
            a.setEnabled(not locked and (self.path != "" or not need))
        dm = m.addMenu("Thiết bị ra")
        dm.setEnabled(not locked)
        names = [""] + [d.description() for d in QMediaDevices.audioOutputs()]
        for n in names:
            a = dm.addAction(n or "(Theo cài đặt chung)")
            a.setCheckable(True)
            a.setChecked(n == self.device)
            a.triggered.connect(lambda _c=False, n=n: self.set_device(n))
        m.addSeparator()
        if self.path:
            m.addAction("Mở thư mục chứa file", lambda: os.startfile(os.path.dirname(self.path))
                        if os.path.isdir(os.path.dirname(self.path)) else None)
        a = m.addAction("Xóa kênh", self.clear)
        a.setEnabled(not locked and bool(self.path))
        m.exec(gpos)

    def set_device(self, name):
        self.device = name
        self.apply_device()
        self.changed.emit()

    def rename(self):
        name, ok = QInputDialog.getText(self, "Đổi tên", f"Tên hiển thị kênh {self.number}:", text=self.display_name())
        if ok:
            self.name = name.strip()
            self.refresh()
            self.changed.emit()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.color or "#ffffff"), self, "Màu nút")
        if c.isValid():
            self.color = c.name()
            self.refresh()
            self.changed.emit()

    def clear_color(self):
        self.color = ""
        self.refresh()
        self.changed.emit()

    def clear(self):
        self.deck.stop()
        self.path = self.name = self.color = ""
        self.loop = self.fade_in = False
        self.duration = 0
        self.fader.setValue(DEFAULT_FADER)
        self.refresh()
        self.changed.emit()

    def to_dict(self):
        return {"path": self.path, "name": self.name, "color": self.color, "loop": self.loop,
                "fade_in": self.fade_in, "volume": self.fader.value(), "device": self.device,
                "duration": self.duration}

    def from_dict(self, d):
        self.deck.stop()
        self.path = d.get("path", "")
        self.name = d.get("name", "")
        self.color = d.get("color", "")
        self.loop = bool(d.get("loop", False))
        self.fade_in = bool(d.get("fade_in", False))
        self.device = d.get("device", "")
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
