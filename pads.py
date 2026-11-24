"""Bảng nút Jingle / hiệu ứng âm thanh (F1–F12)."""
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QFileDialog, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QMenu, QPushButton, QSizePolicy, QSlider,
                               QVBoxLayout, QWidget)

from audio import Deck
from playlist import AUDIO_EXT, AUDIO_FILTER, fmt_ms

PAD_COUNT = 12
DEFAULT_COLOR = "#374151"


class Pad(QPushButton):
    def __init__(self, index: int, parent=None):
        super().__init__(parent)
        self.index = index
        self.deck = Deck(self)
        self.path = ""
        self.name = ""
        self.color = DEFAULT_COLOR
        self.loop = False
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumHeight(62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.show_menu)
        self.clicked.connect(self.trigger)
        self.deck.stateChanged.connect(self.refresh)
        self.refresh()

    def trigger(self):
        if not self.path:
            self.choose_file()
            return
        if self.deck.is_playing():
            self.deck.stop(400)
        else:
            self.deck.load(self.path)
            self.deck.player.setLoops(-1 if self.loop else 1)
            self.deck.play()

    def is_playing(self):
        return self.deck.is_playing()

    def refresh(self):
        label = self.name or ("(trống — bấm để chọn)" if not self.path else os.path.basename(self.path))
        line2 = ""
        if self.deck.is_playing():
            rem = self.deck.duration() - self.deck.position()
            line2 = ("🔁 " if self.loop else "▶ ") + ("-" + fmt_ms(rem) if not self.loop else fmt_ms(self.deck.position()))
        elif self.loop:
            line2 = "🔁"
        self.setText(f"F{self.index + 1}   {label}" + (f"\n{line2}" if line2 else ""))
        base = QColor(self.color)
        bg = base.lighter(160).name() if self.deck.is_playing() else base.name()
        border = "#4ade80" if self.deck.is_playing() else base.darker(140).name()
        fg = "#111" if QColor(bg).lightness() > 150 else "#f3f4f6"
        self.setStyleSheet(f"QPushButton{{background:{bg};color:{fg};border:2px solid {border};"
                           f"border-radius:6px;font-weight:600;text-align:left;padding:6px;}}")

    # ---------- cấu hình ----------
    def set_file(self, path: str):
        self.deck.stop()
        self.path = path
        self.name = os.path.splitext(os.path.basename(path))[0]
        self.refresh()

    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, f"Chọn âm thanh cho F{self.index + 1}", "", AUDIO_FILTER)
        if path:
            self.set_file(path)

    def show_menu(self, pos):
        m = QMenu(self)
        m.addAction("Chọn file...", self.choose_file)
        m.addAction("Đổi tên...", self.rename)
        m.addAction("Đổi màu...", self.pick_color)
        a = m.addAction("Lặp lại liên tục")
        a.setCheckable(True)
        a.setChecked(self.loop)
        a.toggled.connect(self.set_loop)
        m.addSeparator()
        m.addAction("Xóa nút này", self.clear)
        m.exec(self.mapToGlobal(pos))

    def rename(self):
        name, ok = QInputDialog.getText(self, "Đổi tên", "Tên hiển thị:", text=self.name)
        if ok:
            self.name = name.strip()
            self.refresh()

    def pick_color(self):
        c = QColorDialog.getColor(QColor(self.color), self, "Chọn màu")
        if c.isValid():
            self.color = c.name()
            self.refresh()

    def set_loop(self, on):
        self.loop = on
        self.refresh()

    def clear(self):
        self.deck.stop()
        self.path, self.name, self.color, self.loop = "", "", DEFAULT_COLOR, False
        self.refresh()

    def to_dict(self):
        return {"path": self.path, "name": self.name, "color": self.color, "loop": self.loop}

    def from_dict(self, d):
        self.path = d.get("path", "")
        self.name = d.get("name", "")
        self.color = d.get("color", DEFAULT_COLOR)
        self.loop = bool(d.get("loop", False))
        self.refresh()

    # ---------- kéo thả file vào nút ----------
    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.splitext(p)[1].lower() in AUDIO_EXT:
                self.set_file(p)
                break


class PadPanel(QWidget):
    anyPlayingChanged = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        head = QHBoxLayout()
        title = QLabel("JINGLE / HIỆU ỨNG")
        title.setObjectName("sectionTitle")
        head.addWidget(title)
        head.addStretch()
        btn_stop = QPushButton("⏹ Dừng tất cả")
        btn_stop.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn_stop.clicked.connect(self.stop_all)
        head.addWidget(btn_stop)
        v.addLayout(head)

        grid = QGridLayout()
        grid.setSpacing(6)
        self.pads = [Pad(i, self) for i in range(PAD_COUNT)]
        for i, p in enumerate(self.pads):
            grid.addWidget(p, i // 3, i % 3)
        v.addLayout(grid, 1)

        foot = QHBoxLayout()
        self.chk_duck = QCheckBox("Giảm nhạc nền khi phát jingle")
        self.chk_duck.setChecked(True)
        self.chk_duck.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        foot.addWidget(self.chk_duck)
        foot.addStretch()
        foot.addWidget(QLabel("Âm lượng"))
        self.vol = QSlider(Qt.Orientation.Horizontal)
        self.vol.setRange(0, 100)
        self.vol.setValue(100)
        self.vol.setFixedWidth(120)
        self.vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.vol.valueChanged.connect(self.set_volume)
        foot.addWidget(self.vol)
        v.addLayout(foot)

        self._any = False
        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        any_playing = False
        for p in self.pads:
            if p.is_playing():
                any_playing = True
                p.refresh()
        if any_playing != self._any:
            self._any = any_playing
            self.anyPlayingChanged.emit(any_playing)

    def trigger(self, i):
        if 0 <= i < len(self.pads):
            self.pads[i].trigger()

    def stop_all(self):
        for p in self.pads:
            p.deck.stop(300)

    def set_volume(self, v):
        for p in self.pads:
            p.deck.set_master(v / 100)

    def set_device(self, dev):
        for p in self.pads:
            p.deck.set_device(dev)

    def to_dict(self):
        return {"pads": [p.to_dict() for p in self.pads], "volume": self.vol.value(),
                "duck": self.chk_duck.isChecked()}

    def from_dict(self, d):
        for p, pd in zip(self.pads, d.get("pads", [])):
            p.from_dict(pd)
        self.vol.setValue(int(d.get("volume", 100)))
        self.chk_duck.setChecked(bool(d.get("duck", True)))
