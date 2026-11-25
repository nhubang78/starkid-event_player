"""Starkid Event Player — phần mềm phát nhạc sự kiện cho Windows (bảng 32 kênh + playlist)."""
import json
import os
import sys

from PySide6.QtCore import QSettings, QSize, QStandardPaths, Qt, QTime, QTimer
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea, QSizePolicy,
                               QSpinBox, QStackedWidget, QToolButton, QVBoxLayout,
                               QWidget)
from PySide6.QtMultimedia import QMediaDevices

from audio import Deck, find_output_device, percent_to_amp
from sysvolume import SystemVolume
from channel import ChannelStrip
from playlist_page import PlaylistPage
from channel_dialog import ChannelSettingsDialog
from guide import GuideDialog
from longview import LongView
from soundcheck import SoundCheckPage
from deck_editor import DeckEditor
from shortcuts import DEFAULT_KEYS, NAV_KEYS, ShortcutDialog
from shortcuts import LABELS as SHORTCUT_LABELS
from widgets import Fader, VUMeter, glyph_icon, key_label, shape_icon
import theme
from theme import T

APP_NAME = "EventPlayer"            # tên nội bộ: thư mục lưu cài đặt (giữ nguyên để không mất dữ liệu)
DISPLAY_NAME = "Starkid Event Player"
ASSET_DIR = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "assets")


def asset(name):
    return os.path.join(ASSET_DIR, name)

VERSION = "2.0"
PROJECT_EXT = ".evp"
CHANNELS = 32

DEFAULT_CFG = {
    "cart_device": "", "main_device": "", "pre_device": "",
    "cart_fade_in_ms": 2000, "cart_fade_out_ms": 3000, "single_fade_ms": 0,
    "fade_in_ms": 0, "fade_out_ms": 3000, "pause_fade_ms": 200, "warn_sec": 10,
}

def set_dark_titlebar(widget):
    """Thanh tiêu đề Windows tối/sáng theo giao diện (Windows 10 2004+ / 11)."""
    try:
        import ctypes
        val = ctypes.c_int(1 if theme.is_dark() else 0)
        hwnd = int(widget.winId())
        for attr in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(val), 4) == 0:
                break
    except Exception:
        pass


# ======================================================================
class SettingsDialog(QDialog):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.setWindowTitle("Tùy chọn")
        self.setMinimumWidth(480)
        form = QFormLayout(self)
        names = ["(Mặc định của Windows)"] + [d.description() for d in QMediaDevices.audioOutputs()]
        self.widgets = {}

        def dev(key, label):
            c = QComboBox()
            c.addItems(names)
            c.setCurrentIndex(names.index(cfg[key]) if cfg[key] in names else 0)
            self.widgets[key] = c
            form.addRow(label, c)

        def spin(key, label, hi, step, suffix):
            s = QSpinBox()
            s.setRange(0, hi)
            s.setSingleStep(step)
            s.setValue(cfg[key])
            s.setSuffix(suffix)
            self.widgets[key] = s
            form.addRow(label, s)

        dev("cart_device", "Thiết bị ra của các kênh:")
        dev("main_device", "Thiết bị ra của Playlist:")
        dev("pre_device", "Tai nghe nghe thử:")
        spin("single_fade_ms", "Phát đơn — fade kênh cũ (0 = dừng ngay):", 10000, 100, " ms")
        spin("fade_in_ms", "Playlist — fade in đầu bài:", 10000, 100, " ms")
        spin("fade_out_ms", "Playlist — fade out khi dừng:", 20000, 250, " ms")
        spin("pause_fade_ms", "Fade khi tạm dừng/tiếp tục:", 3000, 50, " ms")
        spin("warn_sec", "Cảnh báo sắp hết bài trước:", 120, 1, " giây")
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self):
        out = {}
        for k, w in self.widgets.items():
            out[k] = ("" if w.currentIndex() == 0 else w.currentText()) if isinstance(w, QComboBox) else w.value()
        return out


# ======================================================================
class LockOverlay(QWidget):
    """Lớp phủ khi khóa: chặn mọi thao tác chuột/bàn phím trên vùng kênh, playlist, GO, Master."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.hide()
        parent.installEventFilter(self)

    def eventFilter(self, obj, e):
        if obj is self.parent() and e.type() == e.Type.Resize:
            self.setGeometry(self.parent().rect())
        return False

    def showEvent(self, e):
        self.setGeometry(self.parent().rect())
        super().showEvent(e)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 14))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        text = "ĐÃ KHÓA — bấm nút Khóa cài đặt để mở"
        f = p.font()
        f.setPointSize(10)
        f.setBold(True)
        p.setFont(f)
        w = p.fontMetrics().horizontalAdvance(text) + 40
        r = QRectF((self.width() - w) / 2, self.height() - 32, w, 26)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#dc2626"))
        p.drawRoundedRect(r, 13, 13)
        p.setPen(QColor("white"))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    # chặn mọi thao tác
    def mousePressEvent(self, e): e.accept()
    def mouseReleaseEvent(self, e): e.accept()
    def mouseDoubleClickEvent(self, e): e.accept()
    def mouseMoveEvent(self, e): e.accept()
    def wheelEvent(self, e): e.accept()
    def keyPressEvent(self, e): e.accept()
    def keyReleaseEvent(self, e): e.accept()
    def contextMenuEvent(self, e): e.accept()


class PageStack(QStackedWidget):
    """Chỉ tính kích thước theo trang đang xem (QStackedWidget mặc định lấy trang lớn nhất,
    kể cả trang đang ẩn, làm cửa sổ không co lại được)."""

    def __init__(self):
        super().__init__()
        self.currentChanged.connect(lambda _i: self.updateGeometry())

    def sizeHint(self):
        w = self.currentWidget()
        return w.sizeHint() if w else super().sizeHint()

    def minimumSizeHint(self):
        w = self.currentWidget()
        return w.minimumSizeHint() if w else super().minimumSizeHint()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings()
        self.cfg = dict(DEFAULT_CFG)
        try:
            self.cfg.update(json.loads(self.settings.value("config", "{}")))
        except (TypeError, ValueError):
            pass
        self.locked = False
        self.single = False
        self.project_path = ""
        self.dirty = False
        self._loading = False
        self.go_next = 1
        self.pre = Deck(self)
        self.sysvol = SystemVolume()     # Master = âm lượng chính của sound card (Windows)
        self._sys_level = None
        self.pre_title = ""
        self.long_view = None
        self.last_started = None
        self.last_cart_page = 0
        self._shortcuts = []
        self._fixed = []
        self.keys = dict(DEFAULT_KEYS)
        try:
            self.keys.update(json.loads(self.settings.value("shortcuts", "{}")))
        except (TypeError, ValueError):
            pass

        self.build_ui()
        self.build_menu()
        self.apply_theme(self.settings.value("theme", "dark"))
        self.build_shortcuts()
        self.apply_devices()
        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self.apply_devices)

        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.load_autosave()

        self.timer = QTimer(self)
        self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.timer.start()
        self._ticks = 0

    # ================= GIAO DIỆN =================
    def build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- thanh công cụ ---
        tb = QWidget()
        tb.setObjectName("toolbar")
        # không để thanh công cụ ép cửa sổ rộng ra: update_compact() tự đổi sang chỉ-biểu-tượng khi hẹp
        tb.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        tb.setMinimumWidth(1)
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(12, 6, 12, 6)
        tl.setSpacing(2)
        self.tool_buttons = []
        self.tool_icons = []      # (nút, loại biểu tượng, mã, khóa màu) để vẽ lại khi đổi giao diện
        self.page_group = QButtonGroup(self)
        self.page_group.setExclusive(True)

        def tool(text, ic, slot=None, checkable=False, tip="", color="text_dim", name="tool"):
            b = QToolButton()
            b.setObjectName(name)
            b.setText(text)
            self.tool_icons.append((b, ic[0], ic[1], color))
            b.setIconSize(QSize(20, 20) if name == "tool" else QSize(16, 16))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if name == "tool"
                                 else Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            b.setCheckable(checkable)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(tip or text)
            if name == "tool":
                b.setMinimumWidth(64)
            if slot:
                (b.toggled if checkable else b.clicked).connect(slot)
            tl.addWidget(b)
            self.tool_buttons.append(b)
            return b

        def sep():
            line = QFrame()
            line.setObjectName("tbSep")
            line.setFixedHeight(30)
            tl.addSpacing(6)
            tl.addWidget(line)
            tl.addSpacing(6)

        self.pg_buttons = []
        for i, (text, code) in enumerate((("Audio 1-16", "\uEC4F"), ("Audio 17-32", "\uEC4F"),
                                          ("Playlist", "\uE8FD"), ("Âm thanh", "\uE9E9"))):
            b = tool(text, ("glyph", code), checkable=True, tip=f"{text} (Ctrl+{i + 1})", name="pageTab")
            self.page_group.addButton(b, i)
            self.pg_buttons.append(b)
        self.page_group.idClicked.connect(self.show_page)
        tl.addStretch(1)
        self.btn_new = tool("Dự án mới", ("glyph", "\uE8A5"), self.new_project)
        self.btn_open = tool("Mở", ("glyph", "\uE838"), self.open_project)
        tool("Lưu", ("glyph", "\uE74E"), self.save_project)
        sep()
        tool("Tùy chọn", ("glyph", "\uE713"), self.open_settings)
        tool("Phím tắt", ("glyph", "\uE765"), self.open_shortcuts)
        tool("Hướng dẫn", ("glyph", "\uE897"), self.show_guide, tip="Hướng dẫn sử dụng (F1)")
        self.btn_theme = tool("Giao diện", ("glyph", "\uE708"), self.toggle_theme,
                              tip="Đổi giao diện Tối / Sáng")
        sep()
        self.btn_single = tool("Phát đơn", ("shape", "single"), self.set_single, True,
                               "Phát đơn: khi phát một kênh, các kênh khác tự fade out")
        self.btn_single.setProperty("accent", True)
        tl.addStretch(2)
        self.btn_long = tool("Long View", ("glyph", "\uE7F4"), self.toggle_long_view, tip="Màn hình lớn")
        tool("Dừng hết", ("shape", "stopall"), self.stop_all,
             tip="Dừng tất cả (Esc). Bấm 2 lần = dừng ngay", color="danger")
        self.btn_lock = tool("Khóa cài đặt", ("glyph", "\uE785"), self.set_locked, True,
                             "Khóa: không bàn phím, không bấm chuột điều khiển được — nhạc vẫn phát.\nBấm lại nút này để mở khóa.")
        self.btn_lock.setProperty("danger", True)
        tl.addSpacing(10)
        logo = QToolButton()
        logo.setObjectName("tool")
        logo.setIcon(QIcon(asset("logo_round.png")))
        logo.setIconSize(QSize(44, 44))
        logo.setToolTip(DISPLAY_NAME)
        logo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        logo.clicked.connect(self.show_about)
        tl.addWidget(logo)
        self.logo = logo
        self._compact = None
        root.addWidget(tb)

        self.lbl_path = QLabel()
        self.lbl_path.setObjectName("pathBar")
        root.addWidget(self.lbl_path)

        # --- thân: các trang + cột phải ---
        self.body_w = QWidget()
        body = QHBoxLayout(self.body_w)
        body.setContentsMargins(10, 8, 10, 10)
        body.setSpacing(12)
        self.stack = PageStack()
        self.strips = []
        for page in range(2):
            w = QWidget()
            grid = QGridLayout(w)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(10)
            for k in range(16):
                n = page * 16 + k + 1
                s = ChannelStrip(n, "", self)
                s.started.connect(self.on_strip_started)
                s.changed.connect(self.mark_dirty)
                s.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
                s.selectRequested.connect(self.select_strip)
                s.changed.connect(lambda s=s: self.deck_editor.strip_changed(s))
                self.strips.append(s)
                grid.addWidget(s, k // 8, k % 8)
            for c in range(8):
                grid.setColumnStretch(c, 1)
            self.stack.addWidget(w)
        self.playlist = PlaylistPage(self)
        self.playlist.changed.connect(self.mark_dirty)
        self.stack.addWidget(self.playlist)
        self.soundcheck = SoundCheckPage(self)
        self.soundcheck.feedbackAlert.connect(self.on_feedback_alert)
        self.stack.addWidget(self.soundcheck)
        # khung cuộn: cửa sổ nhỏ hơn lưới kênh thì hiện thanh cuộn thay vì đòi màn hình rộng hơn
        self.body_scroll = QScrollArea()
        self.body_scroll.setObjectName("bodyScroll")
        self.body_scroll.setWidgetResizable(True)
        self.body_scroll.setFrameShape(QFrame.Shape.NoFrame)
        # bảng chỉnh bài (trên lưới kênh) + các trang
        self.deck_editor = DeckEditor(self)
        page_area = QWidget()
        pv = QVBoxLayout(page_area)
        pv.setContentsMargins(0, 0, 0, 0)
        pv.setSpacing(10)
        pv.addWidget(self.deck_editor)
        pv.addWidget(self.stack, 1)
        self.body_scroll.setWidget(page_area)
        self.body_scroll.viewport().setAutoFillBackground(False)
        body.addWidget(self.body_scroll, 1)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(6)
        right.addSpacing(22)
        self.btn_go = QPushButton("GO 1")
        self.btn_go.setObjectName("go")
        self.btn_go.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_go.setToolTip("Phát kênh kế tiếp theo thứ tự (Space). Chuột phải để chọn kênh.")
        self.btn_go.clicked.connect(self.go)
        self.btn_go.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_go.customContextMenuRequested.connect(self.go_menu)
        right.addWidget(self.btn_go)
        hint = QLabel("Space · chuột phải\nđể chọn kênh")
        hint.setObjectName("goHint")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(hint)
        right.addStretch(1)
        lbl = QLabel("MASTER")
        lbl.setObjectName("sideHead")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(lbl)
        mf = QFrame()
        mf.setObjectName("strip")
        ml = QVBoxLayout(mf)
        mh = QHBoxLayout()
        self.master = Fader()
        self.master.setToolTip("Master = âm lượng chính của sound card (giống thanh âm lượng Windows).\n"
                               "Chỉnh ở đây hoặc trên Windows đều được, hai bên tự đồng bộ.")
        self.master.valueChanged.connect(self.on_master)
        mh.addWidget(self.master, 1)
        self.master_meter = VUMeter()
        mh.addWidget(self.master_meter)
        ml.addLayout(mh, 1)
        self.lbl_master = QLabel("100%")
        self.lbl_master.setObjectName("level")
        self.lbl_master.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(self.lbl_master)
        right.addWidget(mf, 1)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(112)
        body.addWidget(rw)
        root.addWidget(self.body_w, 1)
        self.lock_overlay = LockOverlay(self.body_w)
        self.setCentralWidget(central)
        self.setMinimumSize(820, 520)

        self.lbl_clock = QLabel()
        self.lbl_clock.setObjectName("clock")
        ver = QLabel(f"v{VERSION}")
        ver.setObjectName("version")
        self.statusBar().addPermanentWidget(ver)
        self.statusBar().addPermanentWidget(self.lbl_clock)
        self.pg_buttons[0].setChecked(True)

    def build_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("Tệp")
        m.addAction("Dự án mới", self.new_project, QKeySequence("Ctrl+N"))
        m.addAction("Mở dự án...", self.open_project, QKeySequence("Ctrl+O"))
        m.addAction("Lưu", self.save_project, QKeySequence("Ctrl+S"))
        m.addAction("Lưu thành...", self.save_project_as, QKeySequence("Ctrl+Shift+S"))
        m.addSeparator()
        m.addAction("Thoát", self.close)
        m = mb.addMenu("Sửa")
        m.addAction("Đưa tất cả fader về 80%", lambda: [s.fader.setValue(80) for s in self.strips])
        m.addAction("Xóa tất cả kênh...", self.clear_all_channels)
        m.addSeparator()
        m.addAction("Playlist: đánh dấu tất cả là chưa phát", self.playlist.reset_played)
        m = mb.addMenu("Hiển thị")
        for i, t in enumerate(("Audio 1-16", "Audio 17-32", "Playlist", "Âm thanh (đo, chống hú)")):
            m.addAction(t, lambda i=i: self.show_page(i), QKeySequence(f"Ctrl+{i + 1}"))
        m.addSeparator()
        m.addAction("Long View", self.toggle_long_view)
        m.addSeparator()
        self.theme_actions = {}
        for key, label in theme.THEME_NAMES.items():
            a = m.addAction(f"Giao diện {label.lower()}", lambda k=key: self.apply_theme(k))
            a.setCheckable(True)
            self.theme_actions[key] = a
        m = mb.addMenu("Tùy chỉnh")
        m.addAction("Tùy chọn...", self.open_settings)
        m.addAction("Bảng phím tắt...", self.open_shortcuts)
        self.act_single = m.addAction("Phát đơn")
        self.act_single.setCheckable(True)
        self.act_single.toggled.connect(self.btn_single.setChecked)
        self.act_lock = m.addAction("Khóa cài đặt")
        self.act_lock.setCheckable(True)
        self.act_lock.toggled.connect(self.btn_lock.setChecked)
        m = mb.addMenu("Trợ giúp")
        m.addAction("Bảng phím tắt...", self.open_shortcuts)
        m.addAction("Hướng dẫn sử dụng", self.show_guide, QKeySequence("F1"))
        m.addSeparator()
        m.addAction(f"Giới thiệu {DISPLAY_NAME}", self.show_about)

    FIXED_KEYS = ("Ctrl+Shift+Esc", "Ctrl+Right", "Ctrl+Left", "Ctrl+E", "Ctrl+L", "F1")

    def build_shortcuts(self):
        """Phím cố định (không chỉnh trong bảng phím tắt)."""
        for key, fn in zip(self.FIXED_KEYS, (self.panic, self.playlist.next_track, self.playlist.prev_track,
                                             self.playlist.cue_selected, self.playlist.prelisten_selected,
                                             self.show_guide)):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(fn)
            self._fixed.append(s)
        self.apply_shortcuts()

    def apply_shortcuts(self):
        """Tạo lại các phím tắt chỉnh được: thao tác chung, 16 ô kênh, phím riêng từng kênh."""
        for s, _seq in self._shortcuts:
            s.setEnabled(False)
            s.setParent(None)
            s.deleteLater()
        self._shortcuts = []
        handlers = {"go": self.go_pressed, "stop_all": self.stop_all, "stop_cues": self.stop_cues,
                    "go_prev": lambda: self.go_cursor(-1), "go_next": lambda: self.go_cursor(1),
                    "long_view": self.toggle_long_view}
        for i in range(1, 17):
            handlers[f"slot{i}"] = lambda i=i: self.slot_pressed(i)
        own = {s.own_key for s in self.strips if s.own_key not in ("", "-")}
        for act, fn in handlers.items():
            seq = self.keys.get(act, "")
            if seq and seq not in own:          # phím riêng của kênh được ưu tiên
                self._add_shortcut(seq, fn)
        for s in self.strips:
            if s.own_key not in ("", "-"):
                self._add_shortcut(s.own_key, s.cart_clicked)
            slot_key = self.keys.get(f"slot{(s.number - 1) % 16 + 1}", "")
            s.hotkey = "" if s.own_key == "-" else key_label(s.own_key or slot_key, "")
            s.cart.update()
        self.update_shortcut_enabled()

    def _add_shortcut(self, seq, fn):
        sc = QShortcut(QKeySequence(seq), self)
        sc.activated.connect(fn)
        self._shortcuts.append((sc, seq))

    def update_shortcut_enabled(self):
        on_playlist = self.stack.currentIndex() >= 2     # Playlist / Âm thanh: phím mũi tên dành cho trang
        for sc, seq in self._shortcuts:
            sc.setEnabled(not self.locked and not (on_playlist and seq in NAV_KEYS))
        for sc in self._fixed:
            sc.setEnabled(not self.locked)

    def open_shortcuts(self):
        dlg = ShortcutDialog(self, self.keys,
                             {s.number: s.own_key for s in self.strips if s.own_key not in ("", "-")})
        if not dlg.exec():
            return
        self.keys = dlg.values()
        self.settings.setValue("shortcuts", json.dumps(self.keys))
        changed = False
        for s in self.strips:
            if s.own_key not in ("", "-") and dlg.channel_keys.get(s.number, s.own_key) != s.own_key:
                s.own_key = dlg.channel_keys[s.number]
                changed = True
        if changed:
            self.mark_dirty()
        self.apply_shortcuts()
        self.statusBar().showMessage("Đã lưu bảng phím tắt", 3000)

    def check_channel_key(self, strip, seq):
        """Kiểm tra / giải quyết trùng khi gán phím riêng cho kênh. Trả về False nếu hủy."""
        if seq in self.FIXED_KEYS:
            QMessageBox.warning(self, "Phím tắt", f"Phím {key_label(seq)} là phím cố định của chương trình.")
            return False
        for act, k in self.keys.items():
            if k == seq:
                if QMessageBox.question(
                        self, "Phím tắt",
                        f"Phím {key_label(seq)} đang dùng cho “{SHORTCUT_LABELS[act]}”.\n"
                        f"Chuyển phím này sang Kênh {strip.number}?") != QMessageBox.StandardButton.Yes:
                    return False
                self.keys[act] = ""
                self.settings.setValue("shortcuts", json.dumps(self.keys))
        for other in self.strips:
            if other is not strip and other.own_key == seq:
                other.own_key = ""
        return True

    # ---------- cài đặt kênh ----------
    def open_channel_settings(self, strip):
        if self.locked:
            return
        ChannelSettingsDialog(self, strip).exec()

    def add_to_playlist(self, path):
        v = self.playlist.current_view()
        if v and path:
            v.add_paths([path])
            self.statusBar().showMessage(
                f"Đã thêm vào playlist “{self.playlist.tabs.tabText(self.playlist.tabs.currentIndex())}”", 4000)

    def channel_defaults(self):
        try:
            return json.loads(self.settings.value("channel_defaults", "{}"))
        except (TypeError, ValueError):
            return {}

    def set_channel_defaults(self, d):
        self.settings.setValue("channel_defaults", json.dumps(d))

    def apply_to_all_channels(self, d):
        n = 0
        for s in self.strips:
            if s.path and not (s.deck.is_playing() or s.deck.is_paused()):
                s.mode, s.fade_in_s, s.fade_out_s = d["mode"], d["fade_in"], d["fade_out"]
                s.refresh()
                n += 1
        if n:
            self.mark_dirty()
        return n

    # ---------- xử lý phím ----------
    def cart_page(self):
        i = self.stack.currentIndex()
        return i if i < 2 else self.last_cart_page

    def slot_pressed(self, i):
        strip = self.strips[self.cart_page() * 16 + i - 1]
        if strip.own_key:          # kênh có phím riêng hoặc "không phím": bỏ qua phím ô
            return
        strip.cart_clicked()

    def go_pressed(self):
        if self.stack.currentIndex() == 2:
            self.playlist.play_pause()     # trang Playlist: phím GO = phát/tạm dừng danh sách
        else:
            self.go()

    def stop_cues(self):
        """Dừng tất cả kênh (cue); Playlist vẫn phát."""
        for s in self.strips:
            s.stop()

    def go_cursor(self, delta):
        nums = self.loaded_numbers()
        if not nums:
            return
        self.update_go()
        i = nums.index(self.go_next)
        self.go_next = nums[(i + delta) % len(nums)]
        self.update_go()

    # ================= TRANG / CHẾ ĐỘ =================
    def select_strip(self, strip):
        if not self.locked:
            self.deck_editor.set_strip(strip)

    def show_page(self, i):
        self.stack.setCurrentIndex(i)
        self.deck_editor.setVisible(i < 2)
        self.pg_buttons[i].setChecked(True)
        if i < 2:
            self.last_cart_page = i
        self.update_shortcut_enabled()
        self.statusBar().clearMessage()

    def set_single(self, on):
        self.single = on
        self.act_single.setChecked(on)
        if on and not self._loading:
            # bật Phát đơn khi đang có nhiều nguồn phát: chỉ giữ nguồn phát sau cùng
            keep = self.last_started
            if keep is self.playlist:
                self.stop_others(stop_playlist=False)
            elif keep is not None and keep.deck.is_playing():
                self.stop_others(keep=keep)
            else:
                playing = [s for s in self.strips if s.deck.is_playing()]
                self.stop_others(keep=playing[-1] if playing else None,
                                 stop_playlist=bool(playing))
        self.mark_dirty()

    def set_locked(self, on):
        """Khóa toàn bộ: không phím, không chuột điều khiển (nhạc vẫn phát). Chỉ mở bằng nút Khóa."""
        self.locked = on
        self.act_lock.setChecked(on)
        self.update_lock_icon()
        keep = set(self.pg_buttons) | {self.btn_lock, self.btn_long, self.btn_theme}
        for b in self.tool_buttons:
            if b not in keep:
                b.setEnabled(not on)
        for top in self.menuBar().actions():
            if top.menu():
                for a in top.menu().actions():
                    if a is not self.act_lock and a not in self.theme_actions.values():
                        a.setEnabled(not on)
        self.update_shortcut_enabled()
        self.lock_overlay.setVisible(on)
        if on:
            self.lock_overlay.raise_()
            self.lock_overlay.setFocus()
        for s in self.strips:
            s.refresh()
        self.statusBar().showMessage("ĐÃ KHÓA — bàn phím và chuột không điều khiển được. Bấm nút Khóa cài đặt để mở."
                                     if on else "Đã mở khóa", 0 if on else 3000)

    # ---------- giao diện Tối / Sáng ----------
    def update_lock_icon(self):
        self.btn_lock.setIcon(glyph_icon("\uE72E" if self.locked else "\uE785",
                                         "#ffffff" if self.locked else T["text_dim"]))

    def toggle_theme(self):
        self.apply_theme("light" if theme.is_dark() else "dark")

    def apply_theme(self, name):
        theme.set_theme(name)
        app = QApplication.instance()
        app.setPalette(theme.palette())
        app.setStyleSheet(theme.build_stylesheet())
        for b, kind, code, color in self.tool_icons:
            if b is self.btn_lock:
                continue
            if b is self.btn_theme:
                code = "\uE706" if theme.is_dark() else "\uE708"   # mặt trời / mặt trăng
            col = T[color]
            ic = glyph_icon(code, col) if kind == "glyph" else shape_icon(code, col)
            if b in self.pg_buttons:       # tab trang đang chọn: biểu tượng trắng trên nền xanh
                ic.addPixmap(glyph_icon(code, "#ffffff").pixmap(64, 64), QIcon.Mode.Normal, QIcon.State.On)
            b.setIcon(ic)
        self.btn_theme.setText("Sáng" if theme.is_dark() else "Tối")
        self.btn_theme.setToolTip("Chuyển sang giao diện " + ("sáng" if theme.is_dark() else "tối"))
        self.update_lock_icon()
        for k, a in self.theme_actions.items():
            a.setChecked(k == theme.current())
        for s in self.strips:
            s.retheme()
        self.playlist.retheme()
        self.soundcheck.retheme()
        self.deck_editor.retheme()
        self.master_meter.update()
        self.settings.setValue("theme", theme.current())
        set_dark_titlebar(self)

    def on_feedback_alert(self, text):
        """Báo hú cả khi đang ở trang khác: tab Âm thanh đỏ + thanh trạng thái."""
        b = self.pg_buttons[3]
        b.setProperty("alert", bool(text))
        b.style().unpolish(b)
        b.style().polish(b)
        if text:
            self.statusBar().showMessage(text + "  — xem trang Âm thanh để biết cần cắt EQ ở đâu", 4000)

    def stop_others(self, keep=None, stop_playlist=True):
        """Phát đơn: dừng mọi kênh khác (đang phát hoặc tạm dừng)."""
        fade = self.cfg["single_fade_ms"]
        for s in self.strips:
            if s is not keep and (s.deck.is_playing() or s.deck.is_paused()):
                s.stop(fade if s.deck.is_playing() else 0)
        if stop_playlist and (self.playlist.is_active() or self.playlist.deck.is_paused()):
            for d in self.playlist.decks:
                d.stop(fade if d.is_playing() else 0)

    def on_strip_started(self, strip):
        self.last_started = strip
        self.deck_editor.set_strip(strip)
        if self.single:
            self.stop_others(keep=strip)

    def on_playlist_started(self):
        self.last_started = self.playlist
        if self.single:
            self.stop_others(stop_playlist=False)

    # ---------- GO ----------
    def loaded_numbers(self):
        return [s.number for s in self.strips if s.path]

    def update_go(self):
        nums = self.loaded_numbers()
        if nums and self.go_next not in nums:
            later = [n for n in nums if n >= self.go_next]
            self.go_next = later[0] if later else nums[0]
        self.btn_go.setText(f"GO {self.go_next}" if nums else "GO")

    def go(self):
        nums = self.loaded_numbers()
        if not nums:
            return
        self.update_go()
        n = self.go_next
        self.strips[n - 1].play()
        later = [x for x in nums if x > n]
        self.go_next = later[0] if later else nums[0]
        self.update_go()

    def go_menu(self, pos):
        m = QMenu(self)
        for n in self.loaded_numbers():
            a = m.addAction(f"GO kênh {n} — {self.strips[n - 1].display_name()}")
            a.triggered.connect(lambda _c=False, n=n: (setattr(self, "go_next", n), self.update_go()))
        if m.isEmpty():
            m.addAction("(Chưa có kênh nào có nhạc)").setEnabled(False)
        m.exec(self.btn_go.mapToGlobal(pos))

    def stop_all(self):
        self.soundcheck.stop_output()
        decks = [s.deck for s in self.strips] + self.playlist.decks
        if any(d.fading_out() for d in decks):
            self.panic()
            return
        for s in self.strips:
            s.stop(500 if s.deck.is_playing() else 0)
        if self.playlist.is_active():
            self.playlist.stop_main(500)

    def panic(self):
        self.soundcheck.out.stop_now()
        for s in self.strips:
            s.stop()
        for d in self.playlist.decks:
            d.stop()
        self.pre.stop()

    # ---------- master / thiết bị ----------
    def on_master(self, v):
        """Fader Master -> âm lượng chính của sound card."""
        if self._sys_level is not None and round(self._sys_level * 100) != v:
            self.sysvol.set(v / 100)
            self._sys_level = v / 100
        self.update_master_label()

    def update_master_label(self):
        if not self.sysvol.available():
            self.lbl_master.setText("Không đọc được\nâm lượng Windows")
            return
        self.lbl_master.setText(f"{self.master.value()}%" + ("  · tắt tiếng" if self.sysvol.muted() else ""))

    def sync_master_from_system(self):
        """Đọc âm lượng Windows; nếu ai đó chỉnh trên Windows thì kéo fader Master theo."""
        lv = self.sysvol.get()
        if lv is None:
            self._sys_level = None
            self.master.setEnabled(False)
            self.update_master_label()
            return
        self.master.setEnabled(True)
        if self._sys_level is None or abs(lv - self._sys_level) > 0.004:
            self._sys_level = lv
            if not self.master.isSliderDown():
                self.master.blockSignals(True)
                self.master.setValue(round(lv * 100))
                self.master.blockSignals(False)
        self.update_master_label()

    def apply_devices(self):
        for s in self.strips:
            s.apply_device()
        self.playlist.set_device(find_output_device(self.cfg["main_device"]))
        self.pre.set_device(find_output_device(self.cfg["pre_device"]))
        # Master điều khiển sound card mà các kênh đang phát ra
        dev = find_output_device(self.cfg["cart_device"])
        dev_id = bytes(dev.id()).decode("utf-8", "ignore") if not dev.isNull() else ""
        self.sysvol.set_device(dev_id)
        self._sys_level = None
        self.sync_master_from_system()

    def prelisten_file(self, path, title):
        if self.pre.is_playing() and self.pre_title == title:
            self.pre.stop()
            return
        if not os.path.isfile(path):
            return
        self.pre.load(path)
        self.pre.play()
        self.pre_title = title
        self.statusBar().showMessage(f"🎧 Nghe thử: {title}  (chọn lại để tắt)", 5000)

    def open_settings(self):
        dlg = SettingsDialog(self, self.cfg)
        if dlg.exec():
            self.cfg.update(dlg.values())
            self.settings.setValue("config", json.dumps(self.cfg))
            self.apply_devices()

    # ---------- Long View ----------
    def toggle_long_view(self):
        if self.long_view and self.long_view.isVisible():
            self.long_view.close()
            return
        if not self.long_view:
            self.long_view = LongView(self, DISPLAY_NAME)
        self.long_view.show()
        set_dark_titlebar(self.long_view)
        self.long_view.raise_()

    # ================= VÒNG CẬP NHẬT =================
    def tick(self):
        self._ticks += 1
        if self._ticks % 4 == 0:
            self.lbl_clock.setText(QTime.currentTime().toString("HH:mm:ss"))
            self.sync_master_from_system()
        page = self.stack.currentIndex()
        # Đồng hồ Master = tổng công suất các nguồn đang phát (sau fader kênh) × âm lượng sound card
        power = [0.0, 0.0]
        for i, s in enumerate(self.strips):
            if (i // 16) == page or s.deck.is_playing() or s.deck.is_paused():
                s.tick()
                post = s.last_levels
            else:
                post = s.deck.take_levels()[1]
            power = [power[0] + post[0] ** 2, power[1] + post[1] ** 2]
        pl_pre, pl_post = self.playlist.take_levels()
        self.playlist.tick(pl_pre)
        power = [power[0] + pl_post[0] ** 2, power[1] + pl_post[1] ** 2]
        sys_amp = percent_to_amp(self._sys_level) if self._sys_level is not None else 1.0
        if self.sysvol.muted():
            sys_amp = 0.0
        self.deck_editor.tick()
        self.master_meter.set_levels([min(1.0, power[0] ** 0.5 * sys_amp), min(1.0, power[1] ** 0.5 * sys_amp)])
        if self.long_view and self.long_view.isVisible() and self._ticks % 2 == 0:
            self.long_view.refresh(self.cfg["warn_sec"] * 1000)

    # ================= DỰ ÁN =================
    def mark_dirty(self):
        if self._loading:
            return
        self.dirty = True
        self.update_title()
        self.update_go()

    def update_title(self):
        name = os.path.splitext(os.path.basename(self.project_path))[0] if self.project_path else "Chưa đặt tên"
        self.setWindowTitle(f"{DISPLAY_NAME} - {name}{' *' if self.dirty else ''}")
        self.lbl_path.setText((self.project_path or "(Dự án chưa lưu)") + (" *" if self.dirty else ""))

    def project_data(self):
        return {"app": APP_NAME, "version": 1, "channels": [s.to_dict() for s in self.strips],
                "master": self.master.value(), "single": self.single, "go_next": self.go_next,
                "playlist": self.playlist.to_dict()}

    def apply_project(self, d):
        self._loading = True
        try:
            chans = d.get("channels", [])
            for i, s in enumerate(self.strips):
                s.from_dict(chans[i] if i < len(chans) else {})
            self.btn_single.setChecked(bool(d.get("single", False)))
            self.go_next = int(d.get("go_next", 1))
            self.playlist.from_dict(d.get("playlist", {}))
        finally:
            self._loading = False
        self.update_go()
        self.apply_shortcuts()
        self.deck_editor.set_strip(self.deck_editor.strip or self.strips[0])
        self.deck_editor.load_wave()

    def confirm_discard(self):
        if not self.dirty:
            return True
        r = QMessageBox.question(self, DISPLAY_NAME, "Dự án có thay đổi chưa lưu. Lưu lại không?",
                                 QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
                                 | QMessageBox.StandardButton.Cancel)
        if r == QMessageBox.StandardButton.Save:
            return self.save_project()
        return r == QMessageBox.StandardButton.Discard

    def new_project(self):
        if self.locked or not self.confirm_discard():
            return
        self.panic()
        self.apply_project({})
        self.project_path = ""
        self.dirty = False
        self.update_title()

    def open_project(self, path=None):
        if self.locked or not self.confirm_discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, "Mở dự án", self.project_dir(),
                                                  f"Dự án Starkid Event Player (*{PROJECT_EXT})")
        if not path:
            return
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Lỗi", f"Không mở được dự án:\n{e}")
            return
        self.panic()
        self.apply_project(data)
        self.project_path = path
        self.settings.setValue("projDir", os.path.dirname(path))
        self.dirty = False
        self.update_title()

    def save_project(self):
        if not self.project_path:
            return self.save_project_as()
        try:
            with open(self.project_path, "w", encoding="utf-8") as fh:
                json.dump(self.project_data(), fh, ensure_ascii=False, indent=1)
        except OSError as e:
            QMessageBox.warning(self, "Lỗi", f"Không lưu được:\n{e}")
            return False
        self.dirty = False
        self.update_title()
        self.statusBar().showMessage("Đã lưu dự án", 3000)
        return True

    @staticmethod
    def default_project_dir():
        d = os.path.join(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation),
                         APP_NAME)
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def inside_program_dir(path):
        if not getattr(sys, "frozen", False):
            return False
        app_dir = os.path.normcase(os.path.dirname(os.path.abspath(sys.executable)))
        return os.path.normcase(os.path.abspath(path)).startswith(app_dir + os.sep)

    def project_dir(self):
        d = self.settings.value("projDir", "")
        if not d or not os.path.isdir(d) or self.inside_program_dir(os.path.join(d, "x")):
            d = self.default_project_dir()
        return d

    def save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Lưu dự án",
                                              os.path.join(self.project_dir(), "Sự kiện" + PROJECT_EXT),
                                              f"Dự án Starkid Event Player (*{PROJECT_EXT})")
        if not path:
            return False
        if self.inside_program_dir(path) and QMessageBox.warning(
                self, "Cảnh báo",
                "Bạn đang lưu dự án vào trong thư mục chương trình.\n"
                "Khi cập nhật phần mềm, thư mục này có thể bị thay thế và MẤT dự án.\n\n"
                "Vẫn lưu ở đây?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return self.save_project_as()
        self.project_path = path
        self.settings.setValue("projDir", os.path.dirname(path))
        return self.save_project()

    def clear_all_channels(self):
        if self.locked:
            return
        if QMessageBox.question(self, "Xóa tất cả", "Xóa nhạc khỏi tất cả 32 kênh?") == QMessageBox.StandardButton.Yes:
            for s in self.strips:
                s.clear()

    # ---------- tự lưu phiên ----------
    def autosave_path(self):
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "autosave.json")

    def load_autosave(self):
        try:
            with open(self.autosave_path(), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            data = {}
        self.apply_project(data.get("project", {}))
        self.project_path = data.get("project_path", "")
        self.dirty = bool(data.get("dirty", False))
        self.btn_lock.setChecked(bool(data.get("locked", False)))
        self.show_page(int(data.get("page", 0)))
        self.update_title()

    def write_autosave(self):
        data = {"project": self.project_data(), "project_path": self.project_path,
                "dirty": self.dirty, "locked": self.locked, "page": self.stack.currentIndex()}
        try:
            with open(self.autosave_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
        except OSError:
            pass

    # ================= TRỢ GIÚP =================
    def show_about(self):
        box = QMessageBox(self)
        box.setWindowTitle(f"Giới thiệu {DISPLAY_NAME}")
        box.setIconPixmap(QIcon(asset("logo_round.png")).pixmap(96, 96))
        box.setText(f"<b style='font-size:13pt'>{DISPLAY_NAME}</b><br>Phiên bản {VERSION}<br><br>"
                    "Phần mềm phát nhạc sự kiện: 32 kênh, Playlist, GO, Phát đơn, Long View.")
        box.exec()

    def show_guide(self):
        GuideDialog(self, DISPLAY_NAME, VERSION).exec()

    # ---------- co giãn theo kích thước cửa sổ ----------
    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.update_compact()

    def update_compact(self):
        """Cửa sổ hẹp: nút thanh công cụ chỉ còn biểu tượng (tên hiện khi rê chuột), ẩn logo."""
        w = self.width()
        mode = 0 if w >= 1480 else 1 if w >= 1080 else 2
        if mode == self._compact:
            return
        self._compact = mode
        for b in self.tool_buttons:
            if b.objectName() == "tool":
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon if mode == 0
                                     else Qt.ToolButtonStyle.ToolButtonIconOnly)
                b.setMinimumWidth(64 if mode == 0 else 0)
            elif b.objectName() == "pageTab":
                b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon if mode < 2
                                     else Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.logo.setVisible(mode == 0)

    def closeEvent(self, e):
        playing = any(s.deck.is_playing() for s in self.strips) or self.playlist.is_active()
        if playing and QMessageBox.question(self, "Thoát", "Nhạc đang phát. Thoát chương trình?") \
                != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        self.write_autosave()
        self.soundcheck.shutdown()
        self.settings.setValue("geometry", self.saveGeometry())
        if self.long_view:
            self.long_view.close()
        e.accept()


def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--wave-test":     # kiểm tra bộ đọc sóng trong bản exe
        import time
        from waveform import compute_wave
        t0 = time.time()
        try:
            d = compute_wave(sys.argv[2])
            msg = f"OK {d.duration / 1000:.1f}s nhạc, đọc {time.time() - t0:.2f}s" if d else "NONE"
        except Exception as e:
            msg = f"LỖI {e!r}"
        with open(sys.argv[3], "w", encoding="utf-8") as fh:
            fh.write(msg)
        return
    if len(sys.argv) >= 3 and sys.argv[1] == "--sysvol-test":   # kiểm tra đọc âm lượng Windows trong bản exe
        v = SystemVolume()
        ok = v.set_device("")
        with open(sys.argv[2], "w", encoding="utf-8") as fh:
            fh.write(f"device={ok} volume={v.get()} muted={v.muted()}")
        return
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setWindowIcon(QIcon(asset("app.ico")))
    try:   # để Windows dùng đúng icon của app trên thanh taskbar
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Starkid.EventPlayer")
    except Exception:
        pass
    app.setStyle("Fusion")
    theme.set_theme(QSettings().value("theme", "dark"))
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.build_stylesheet())
    app.setFont(QFont("Segoe UI", 9))
    w = MainWindow()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
