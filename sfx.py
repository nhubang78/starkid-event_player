"""Bảng HIỆU ỨNG: 12 ô phát nhanh (phím A S D F G H J K Z X C V) cho tiếng vỗ tay, chuông, trống dồn...

Mỗi ô: file, tên, màu, chế độ (Một lần / Bật-Tắt / Lặp), âm lượng riêng. Kéo thả file vào ô; chuột phải hoặc
bấm "…" để tùy chỉnh. "Hạ nhạc nền": khi hiệu ứng đang kêu, nhạc (kênh + Playlist) tự giảm còn X %.
Hiệu ứng phát ra thiết bị của các kênh và không bị MC NÓI làm giảm.
"""
import os

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QAbstractButton, QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QMenu, QPushButton, QSizePolicy, QSlider, QSpinBox,
                               QToolButton, QVBoxLayout)

from audio import Deck, find_output_device
from playlist import AUDIO_EXT, AUDIO_FILTER
from theme import T

SFX_KEYS = list("ASDFGHJKZXCV")
SFX_COLORS = ["#f97316", "#ef4444", "#eab308", "#22c55e", "#06b6d4", "#3b82f6",
              "#a855f7", "#ec4899", "#f97316", "#ef4444", "#eab308", "#22c55e"]
COLOR_CHOICES = [("Cam", "#f97316"), ("Đỏ", "#ef4444"), ("Vàng", "#eab308"), ("Lá", "#22c55e"),
                 ("Lục lam", "#06b6d4"), ("Lam", "#3b82f6"), ("Tím", "#a855f7"), ("Hồng", "#ec4899")]
MODES = [("once", "Một lần", "Bấm là phát từ đầu (bấm lại = phát lại từ đầu)"),
         ("toggle", "Bật / Tắt", "Bấm lần 1 phát, lần 2 dừng"),
         ("loop", "Lặp", "Phát lặp lại cho tới khi bấm lại")]
MODE_NAMES = {k: n for k, n, _t in MODES}


class SfxPad:
    def __init__(self, panel, index):
        self.panel, self.index = panel, index
        self.key = SFX_KEYS[index]
        self.path = self.name = ""
        self.color = SFX_COLORS[index]
        self.mode = "once"
        self.volume = 100
        self.deck = Deck(panel)
        self.deck.stateChanged.connect(panel.on_state)

    def playing(self):
        return self.deck.is_playing()

    def apply_volume(self):
        self.deck.set_master(self.panel.volume() / 100 * self.volume / 100)

    def trigger(self):
        if not self.path:
            return False
        if not os.path.isfile(self.path):
            self.panel.host.statusBar().showMessage(f"Hiệu ứng {self.key}: không tìm thấy file {self.path}", 5000)
            return False
        if self.mode in ("toggle", "loop") and self.playing():
            self.deck.stop(150)
            return True
        self.deck.load(self.path)
        self.deck.player.setLoops(-1 if self.mode == "loop" else 1)
        self.apply_volume()
        self.deck.play()
        return True

    def to_dict(self):
        return {"path": self.path, "name": self.name, "color": self.color, "mode": self.mode, "volume": self.volume}

    def from_dict(self, d):
        self.deck.stop()
        self.path = d.get("path", "")
        self.name = d.get("name", "")
        self.color = d.get("color", SFX_COLORS[self.index]) or SFX_COLORS[self.index]
        self.mode = d.get("mode", "once") if d.get("mode") in MODE_NAMES else "once"
        self.volume = int(d.get("volume", 100))

    def display_name(self):
        return self.name or os.path.splitext(os.path.basename(self.path))[0]


class SfxButton(QAbstractButton):
    def __init__(self, pad):
        super().__init__()
        self.pad = pad
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setMinimumSize(74, 62)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(66)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

    def sizeHint(self):
        return QSize(140, 66)

    def _dots_rect(self):
        return QRectF(self.width() - 30, 4, 26, 18)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._dots_rect().contains(e.position()):
            self.setDown(False)
            self.pad.panel.pad_menu(self.pad, self.mapToGlobal(e.position().toPoint()))
            return
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e):
        pad = self.pad
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        col = QColor(pad.color)
        playing = pad.playing()
        bg = QColor(T["surface2"])
        if playing:
            bg = QColor(col)
            bg.setAlpha(70)
        elif self.isDown():
            bg = QColor(T["pressed"])
        elif self.underMouse():
            bg = QColor(T["hover"])
        p.setPen(QPen(col if playing else QColor(T["border"]), 2 if playing else 1))
        p.setBrush(bg)
        p.drawRoundedRect(r, 9, 9)
        # viền màu phía trên
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(QRectF(r.left() + 6, r.top(), r.width() - 12, 3), 1.5, 1.5)
        # phím
        f = QFont("Segoe UI")
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        chip = QRectF(r.left() + 8, r.top() + 7, 17, 15)
        p.setPen(QPen(QColor(T["border_strong"]), 1))
        p.setBrush(QColor(T["surface"]))
        p.drawRoundedRect(chip, 3, 3)
        p.setPen(QColor(T["text"]))
        p.drawText(chip, Qt.AlignmentFlag.AlignCenter, pad.key)
        p.setPen(QColor(T["text_dim"]))
        f.setPixelSize(13)
        p.setFont(f)
        p.drawText(self._dots_rect(), Qt.AlignmentFlag.AlignCenter, "···")
        if pad.path:
            f.setPixelSize(12)
            p.setFont(f)
            p.setPen(QColor(T["text"]))
            name = p.fontMetrics().elidedText(pad.display_name(), Qt.TextElideMode.ElideRight, int(r.width() - 16))
            p.drawText(QRectF(r.left() + 8, r.top() + 24, r.width() - 16, 18),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, name)
            f.setPixelSize(8)
            p.setFont(f)
            p.setPen(QColor(T["text_dim"]))
            sub = MODE_NAMES[pad.mode].upper() + (f"  ·  {pad.volume}%" if pad.volume != 100 else "")
            p.drawText(QRectF(r.left() + 8, r.top() + 42, r.width() - 16, 12),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, sub)
            if playing:                                    # tiến trình
                dur = max(1, pad.deck.duration())
                frac = min(1.0, pad.deck.position() / dur)
                bar = QRectF(r.left() + 8, r.bottom() - 6, r.width() - 16, 3)
                c = QColor(col)
                c.setAlpha(60)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(c)
                p.drawRoundedRect(bar, 1.5, 1.5)
                p.setBrush(col)
                p.drawRoundedRect(QRectF(bar.left(), bar.top(), bar.width() * frac, bar.height()), 1.5, 1.5)
        else:
            f.setBold(False)
            f.setPixelSize(11)
            p.setFont(f)
            p.setPen(QColor(T["text_faint"]))
            p.drawText(QRectF(r.left() + 8, r.top() + 24, r.width() - 16, 34),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter | Qt.TextFlag.TextWordWrap,
                       "+  Kéo thả hiệu ứng")

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls() and not self.pad.panel.host.locked:
            e.acceptProposedAction()

    def dropEvent(self, e):
        for u in e.mimeData().urls():
            p = u.toLocalFile()
            if os.path.splitext(p)[1].lower() in AUDIO_EXT:
                self.pad.panel.set_file(self.pad, p)
                break


class SfxPanel(QFrame):
    changed = Signal()

    def __init__(self, host):
        super().__init__()
        self.host = host
        self.setObjectName("sfxPanel")
        self.pads = [SfxPad(self, i) for i in range(len(SFX_KEYS))]
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 8, 14, 10)
        root.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(10)
        t = QLabel("⚡  HIỆU ỨNG")
        t.setObjectName("sfxTitle")
        head.addWidget(t)
        self.sld = QSlider(Qt.Orientation.Horizontal)
        self.sld.setRange(0, 100)
        self.sld.setValue(100)
        self.sld.setFixedWidth(150)
        self.sld.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sld.setToolTip("Âm lượng chung của các hiệu ứng")
        self.sld.valueChanged.connect(self.on_volume)
        head.addWidget(self.sld)
        self.lbl_vol = QLabel("100%")
        self.lbl_vol.setObjectName("deZoom")
        self.lbl_vol.setFixedWidth(44)
        head.addWidget(self.lbl_vol)
        b = QPushButton("■  Dừng")
        b.setObjectName("deBtn")
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setToolTip("Dừng mọi hiệu ứng đang phát")
        b.clicked.connect(self.stop_all)
        head.addWidget(b)
        head.addSpacing(6)
        self.chk_duck = QCheckBox("Hạ nhạc nền còn")
        self.chk_duck.setChecked(True)
        self.chk_duck.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.chk_duck.setToolTip("Khi hiệu ứng đang kêu, nhạc (các kênh + Playlist) tự giảm để hiệu ứng nghe rõ")
        self.chk_duck.toggled.connect(lambda _on: self.changed.emit())
        head.addWidget(self.chk_duck)
        self.sp_duck = QSpinBox()
        self.sp_duck.setRange(0, 95)
        self.sp_duck.setSingleStep(5)
        self.sp_duck.setValue(50)
        self.sp_duck.setSuffix(" %")
        self.sp_duck.setFixedWidth(74)
        self.sp_duck.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.sp_duck.valueChanged.connect(lambda _v: self.changed.emit())
        head.addWidget(self.sp_duck)
        head.addStretch(1)
        hint = QLabel("Kéo thả file vào ô · chuột phải để tùy chỉnh")
        hint.setObjectName("deHint")
        head.addWidget(hint)
        self.btn_fold = QToolButton()
        self.btn_fold.setObjectName("deFold")
        self.btn_fold.setCheckable(True)
        self.btn_fold.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_fold.setToolTip("Thu gọn / mở bảng hiệu ứng")
        self.btn_fold.toggled.connect(self.set_folded)
        head.addWidget(self.btn_fold)
        root.addLayout(head)
        self.grid_w = QFrame()
        g = QGridLayout(self.grid_w)
        g.setContentsMargins(0, 0, 0, 0)
        g.setHorizontalSpacing(8)
        self.buttons = []
        for i, pad in enumerate(self.pads):
            btn = SfxButton(pad)
            btn.clicked.connect(lambda _c=False, i=i: self.trigger(i))
            btn.customContextMenuRequested.connect(lambda pos, b=btn: self.pad_menu(b.pad, b.mapToGlobal(pos)))
            g.addWidget(btn, 0, i)
            self.buttons.append(btn)
        root.addWidget(self.grid_w)
        self.btn_fold.setChecked(host.settings.value("sfx_folded", "false") == "true")
        self.set_folded(self.btn_fold.isChecked())
        host.ducker.sfx_level = self.duck_level
        self.apply_device()

    # ---------- điều khiển
    def volume(self):
        return self.sld.value()

    def on_volume(self, v):
        self.lbl_vol.setText(f"{v}%")
        for pad in self.pads:
            pad.apply_volume()
        self.changed.emit()

    def trigger(self, i):
        if self.host.locked:
            return
        pad = self.pads[i]
        if not pad.path:
            self.choose_file(pad)
            return
        if pad.trigger():
            self.host.ducker.poke()
        self.buttons[i].update()

    def stop_all(self):
        for pad in self.pads:
            pad.deck.stop(120 if pad.playing() else 0)

    def panic(self):
        for pad in self.pads:
            pad.deck.stop()

    def any_playing(self):
        return any(p.playing() for p in self.pads)

    def duck_level(self):
        """% nhạc còn lại khi hiệu ứng đang kêu (None = không giảm)."""
        if self.chk_duck.isChecked() and self.any_playing():
            return self.sp_duck.value() / 100
        return None

    def on_state(self):
        for b in self.buttons:
            b.update()
        if self.any_playing():
            self.host.ducker.poke()          # hiệu ứng vừa thật sự bắt đầu phát -> hạ nhạc nền

    def tick(self):
        for b in self.buttons:
            if b.pad.playing():
                b.update()

    def apply_device(self):
        dev = find_output_device(self.host.cfg.get("cart_device", ""))
        for pad in self.pads:
            pad.deck.set_device(dev)

    def set_folded(self, on):
        self.grid_w.setVisible(not on)
        self.btn_fold.setText("▸" if on else "▾")
        self.host.settings.setValue("sfx_folded", "true" if on else "false")

    # ---------- tùy chỉnh ô
    def set_file(self, pad, path):
        pad.deck.stop()
        pad.path = path
        pad.name = os.path.splitext(os.path.basename(path))[0]
        self.buttons[pad.index].update()
        self.changed.emit()

    def choose_file(self, pad):
        if self.host.locked:
            return
        path, _ = QFileDialog.getOpenFileName(self, f"Chọn hiệu ứng cho ô {pad.key}",
                                              self.host.settings.value("lastDir", ""), AUDIO_FILTER)
        if path:
            self.host.settings.setValue("lastDir", os.path.dirname(path))
            self.set_file(pad, path)

    def pad_menu(self, pad, gpos):
        if self.host.locked:
            return
        m = QMenu(self)
        loaded = bool(pad.path)
        m.addAction("Chọn file...", lambda: self.choose_file(pad))
        a = m.addAction("Đổi tên...", lambda: self.rename(pad))
        a.setEnabled(loaded)
        mc = m.addMenu("Màu")
        for name, col in COLOR_CHOICES:
            act = mc.addAction(name, lambda c=col: self._set(pad, color=c))
            act.setCheckable(True)
            act.setChecked(pad.color == col)
        mm = m.addMenu("Chế độ bấm")
        for key, name, tip in MODES:
            act = mm.addAction(name, lambda k=key: self._set(pad, mode=k))
            act.setCheckable(True)
            act.setChecked(pad.mode == key)
            act.setToolTip(tip)
        mv = m.addMenu("Âm lượng ô")
        for v in (25, 50, 75, 100):
            act = mv.addAction(f"{v}%", lambda v=v: self._set(pad, volume=v))
            act.setCheckable(True)
            act.setChecked(pad.volume == v)
        m.addSeparator()
        a = m.addAction("🎧  Nghe thử ra tai nghe", lambda: self.host.prelisten_file(pad.path, pad.display_name()))
        a.setEnabled(loaded)
        a = m.addAction("Bỏ hiệu ứng khỏi ô", lambda: self.clear(pad))
        a.setEnabled(loaded)
        m.exec(gpos)

    def _set(self, pad, **kw):
        for k, v in kw.items():
            setattr(pad, k, v)
        if "volume" in kw:
            pad.apply_volume()
        if "mode" in kw and pad.playing():
            pad.deck.player.setLoops(-1 if pad.mode == "loop" else 1)
        self.buttons[pad.index].update()
        self.changed.emit()

    def rename(self, pad):
        name, ok = QInputDialog.getText(self, "Đổi tên hiệu ứng", f"Tên ô {pad.key}:", text=pad.display_name())
        if ok:
            self._set(pad, name=name.strip())

    def clear(self, pad):
        pad.deck.stop()
        pad.path = pad.name = ""
        pad.mode, pad.volume, pad.color = "once", 100, SFX_COLORS[pad.index]
        self.buttons[pad.index].update()
        self.changed.emit()

    # ---------- lưu / nạp
    def to_dict(self):
        return {"pads": [p.to_dict() for p in self.pads], "volume": self.sld.value(),
                "duck": self.chk_duck.isChecked(), "duck_pct": self.sp_duck.value()}

    def from_dict(self, d):
        pads = d.get("pads", [])
        for i, pad in enumerate(self.pads):
            pad.from_dict(pads[i] if i < len(pads) else {})
        for w, val in ((self.sld, int(d.get("volume", 100))), (self.sp_duck, int(d.get("duck_pct", 50)))):
            w.blockSignals(True)
            w.setValue(val)
            w.blockSignals(False)
        self.lbl_vol.setText(f"{self.sld.value()}%")
        self.chk_duck.blockSignals(True)
        self.chk_duck.setChecked(bool(d.get("duck", True)))
        self.chk_duck.blockSignals(False)
        for pad in self.pads:
            pad.apply_volume()
        for b in self.buttons:
            b.update()

    def retheme(self):
        for b in self.buttons:
            b.update()
