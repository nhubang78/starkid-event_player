"""Starkid Event Player — phần mềm phát nhạc sự kiện cho Windows (bảng 32 kênh + playlist)."""
import json
import os
import sys

from PySide6.QtCore import QSettings, QSize, QStandardPaths, Qt, QTime, QTimer
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox,
                               QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QMainWindow, QMenu, QMessageBox, QPushButton,
                               QSizePolicy, QSpinBox, QStackedWidget, QToolButton, QVBoxLayout,
                               QWidget)
from PySide6.QtMultimedia import QMediaDevices

from audio import Deck, find_output_device, percent_to_db
from channel import ChannelStrip, hms
from playlist_page import PlaylistPage
from channel_dialog import ChannelSettingsDialog
from shortcuts import DEFAULT_KEYS, NAV_KEYS, ShortcutDialog
from shortcuts import LABELS as SHORTCUT_LABELS
from widgets import Fader, VUMeter, glyph_icon, key_label, shape_icon

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

STYLE = """
QMainWindow, QWidget { background:#ececec; color:#1f1f1f; font-family:'Segoe UI'; font-size:9pt; }
QMenuBar { background:#ffffff; }
QMenuBar::item:selected, QMenu::item:selected { background:#dbeafe; color:#111; }
QMenu { background:#ffffff; border:1px solid #cfcfcf; }
QWidget#toolbar { background:#f5f5f5; border-bottom:1px solid #dcdcdc; }
QToolButton#tool { background:transparent; border:none; border-radius:6px; padding:3px 8px;
                   font-size:9pt; color:#333; }
QToolButton#tool:hover { background:#e4e4e4; }
QToolButton#tool:checked { background:#dcdcdc; color:#1d4ed8; }
QToolButton#tool[accent="true"]:checked { background:#2563eb; color:white; }
QLabel#pathBar { background:#f5f5f5; padding:2px 12px; font-size:8.5pt; color:#333; border-bottom:1px solid #e0e0e0; }
QLabel#chHead { padding-left:10px; color:#444; font-size:9pt; }
QFrame#strip { background:#e2e2e2; border:1px solid #d2d2d2; border-radius:5px; }
QFrame#strip QLabel { background:transparent; }
QLabel#level { color:#777; font-size:8.5pt; }
QLabel#time { color:#222; font-size:9pt; }
QLabel#time[dim="true"], QLabel#level[dim="true"] { color:#a8a8a8; }
QSlider { background:transparent; }
QToolButton#more { background:#ffffff; border:1px solid #cfcfcf; border-radius:4px; font-size:6pt;
                   min-width:22px; min-height:16px; }
QPushButton#chBtn { background:#ffffff; border:1px solid #cfcfcf; border-radius:4px; padding:1px; font-size:8.5pt; min-height:18px; }
QPushButton#chBtn:hover { background:#f3f4f6; }
QPushButton#chBtn:disabled { color:#b5b5b5; background:#f2f2f2; }
QPushButton#chBtn[active="true"] { background:#fde68a; }
QToolButton#chIcon { border:none; background:transparent; padding:1px; }
QToolButton#chIcon:hover { background:#d6d6d6; border-radius:3px; }
QSlider::groove:vertical { width:6px; background:#a8a8a8; border-radius:3px; }
QSlider::handle:vertical { height:14px; width:24px; margin:0 -9px; border-radius:4px;
    border:1px solid #8a8a8a;
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #ffffff, stop:0.45 #e9e9e9,
                               stop:0.5 #7a7a7a, stop:0.55 #e9e9e9, stop:1 #d4d4d4); }
QSlider::groove:horizontal { height:4px; background:#c4c4c4; border-radius:2px; }
QSlider::sub-page:horizontal { background:#9ca3af; border-radius:2px; }
QSlider::handle:horizontal { width:11px; height:11px; margin:-5px 0; border-radius:6px;
                             background:#ffffff; border:1px solid #8a8a8a; }
QPushButton#go { background:#fff176; border:1px solid #e0cf3a; border-radius:4px; font-size:11pt;
                 font-weight:600; min-height:50px; }
QPushButton#go:hover { background:#ffee58; }
QPushButton#go:pressed { background:#fdd835; }
QFrame#nowPlaying { background:#ffffff; border:1px solid #d6d6d6; border-radius:6px; }
QFrame#nowPlaying QLabel { background:transparent; }
QLabel#bigTitle { font-size:15pt; font-weight:700; }
QLabel#artist { font-size:10pt; color:#6b7280; }
QLabel#timeBig { font-size:22pt; font-weight:700; font-family:Consolas; }
QLabel#next { font-size:9.5pt; color:#a16207; }
QPushButton { background:#ffffff; border:1px solid #cfcfcf; border-radius:5px; padding:4px 10px; }
QPushButton:hover { background:#f3f4f6; }
QPushButton#transport { font-size:10pt; font-weight:700; min-width:60px; min-height:28px; padding:4px 14px; }
QTreeWidget { background:#ffffff; alternate-background-color:#f7f7f7; border:1px solid #d6d6d6; }
QTreeWidget::item { padding:2px; }
QTreeWidget::item:selected { background:#2563eb; color:white; }
QHeaderView::section { background:#f1f1f1; border:none; border-bottom:1px solid #ddd; padding:4px; }
QTabWidget::pane { border:1px solid #d6d6d6; }
QTabBar::tab { background:#e2e2e2; padding:4px 12px; border-top-left-radius:5px;
               border-top-right-radius:5px; margin-right:2px; }
QTabBar::tab:selected { background:#ffffff; color:#1d4ed8; }
QComboBox, QSpinBox { background:#ffffff; border:1px solid #cfcfcf; border-radius:4px; padding:3px 6px; }
QStatusBar { background:#f5f5f5; color:#555; }
"""


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
class LongView(QWidget):
    """Màn hình lớn cho người điều khiển: tên bài + thời gian còn lại cỡ lớn."""

    def __init__(self, host):
        super().__init__(None, Qt.WindowType.Window)
        self.host = host
        self.setWindowTitle(f"Long View — {DISPLAY_NAME}")
        self.resize(1000, 600)
        self.setStyleSheet("QWidget{background:#0b0b0b;color:#f5f5f5;font-family:'Segoe UI';}")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(30, 20, 30, 20)
        self.clock = QLabel()
        self.clock.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.clock.setStyleSheet("font-size:28pt;color:#93c5fd;font-family:Consolas;")
        self.lay.addWidget(self.clock)
        self.rows = []
        self.empty = QLabel("Không có kênh nào đang phát")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty.setStyleSheet("font-size:28pt;color:#555;")
        self.lay.addWidget(self.empty, 1)
        self.body = QVBoxLayout()
        self.lay.addLayout(self.body, 1)

    def update_view(self, items, warn_ms):
        self.clock.setText(QTime.currentTime().toString("HH:mm:ss"))
        while len(self.rows) < len(items):
            w = QWidget()
            h = QHBoxLayout(w)
            name, t = QLabel(), QLabel()
            name.setStyleSheet("font-size:30pt;font-weight:600;")
            t.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            h.addWidget(name, 1)
            h.addWidget(t)
            self.body.addWidget(w)
            self.rows.append((w, name, t))
        blink = QTime.currentTime().msec() < 500
        for i, (w, name, t) in enumerate(self.rows):
            if i < len(items):
                label, rem, _dur = items[i]
                w.show()
                name.setText(label)
                t.setText("-" + hms(rem))
                col = ("#ef4444" if blink else "#7f1d1d") if rem <= warn_ms else "#4ade80"
                t.setStyleSheet(f"font-size:64pt;font-weight:700;font-family:Consolas;color:{col};")
            else:
                w.hide()
        self.empty.setVisible(not items)


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
        tl = QHBoxLayout(tb)
        tl.setContentsMargins(10, 2, 10, 2)
        tl.setSpacing(2)
        self.tool_buttons = []
        self.page_group = QButtonGroup(self)
        self.page_group.setExclusive(True)

        def tool(text, ic, slot=None, checkable=False, tip=""):
            b = QToolButton()
            b.setObjectName("tool")
            b.setText(text)
            b.setIcon(ic)
            b.setIconSize(QSize(22, 22))
            b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            b.setCheckable(checkable)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(tip or text)
            b.setMinimumWidth(62)
            if slot:
                (b.toggled if checkable else b.clicked).connect(slot)
            tl.addWidget(b)
            self.tool_buttons.append(b)
            return b

        def sep():
            line = QFrame()
            line.setFrameShape(QFrame.Shape.VLine)
            line.setStyleSheet("color:#d4d4d4;")
            line.setFixedHeight(34)
            tl.addSpacing(6)
            tl.addWidget(line)
            tl.addSpacing(6)

        g = "#3a3a3a"
        self.pg_buttons = []
        for i, (text, code) in enumerate((("Audio 1-16", "\uEC4F"), ("Audio 17-32", "\uEC4F"),
                                          ("Playlist", "\uE8FD"))):
            b = tool(text, glyph_icon(code, g), checkable=True, tip=f"{text} (Ctrl+{i + 1})")
            self.page_group.addButton(b, i)
            self.pg_buttons.append(b)
        self.page_group.idClicked.connect(self.show_page)
        tl.addStretch(1)
        self.btn_new = tool("Dự án mới", glyph_icon("\uE8A5", g), self.new_project)
        self.btn_open = tool("Mở", glyph_icon("\uE838", g), self.open_project)
        tool("Lưu", glyph_icon("\uE74E", g), self.save_project)
        sep()
        tool("Tùy chọn", glyph_icon("\uE713", g), self.open_settings)
        tool("Phím tắt", glyph_icon("\uE765", g), self.open_shortcuts)
        tool("Hướng dẫn", glyph_icon("\uE897", g), self.show_guide)
        sep()
        self.btn_single = tool("Phát đơn", shape_icon("single", g), self.set_single, True,
                               "Phát đơn: khi phát một kênh, các kênh khác tự fade out")
        self.btn_single.setProperty("accent", True)
        tl.addStretch(2)
        self.btn_long = tool("Long View", glyph_icon("\uE7F4", g), self.toggle_long_view, tip="Màn hình lớn")
        tool("Dừng hết", shape_icon("stopall", "#dc2626"), self.stop_all,
             tip="Dừng tất cả (Esc). Bấm 2 lần = dừng ngay")
        self.btn_lock = tool("Khóa cài đặt", glyph_icon("\uE785", g), self.set_locked, True,
                             "Khóa: không bàn phím, không bấm chuột điều khiển được — nhạc vẫn phát.\nBấm lại nút này để mở khóa.")
        tl.addSpacing(10)
        logo = QToolButton()
        logo.setObjectName("tool")
        logo.setIcon(QIcon(asset("logo_round.png")))
        logo.setIconSize(QSize(50, 50))
        logo.setToolTip(DISPLAY_NAME)
        logo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        logo.clicked.connect(self.show_about)
        tl.addWidget(logo)
        root.addWidget(tb)

        self.lbl_path = QLabel()
        self.lbl_path.setObjectName("pathBar")
        root.addWidget(self.lbl_path)

        # --- thân: các trang + cột phải ---
        self.body_w = QWidget()
        body = QHBoxLayout(self.body_w)
        body.setContentsMargins(14, 10, 14, 6)
        body.setSpacing(16)
        self.stack = QStackedWidget()
        self.strips = []
        for page in range(2):
            w = QWidget()
            grid = QGridLayout(w)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(14)
            grid.setVerticalSpacing(10)
            for k in range(16):
                n = page * 16 + k + 1
                s = ChannelStrip(n, "", self)
                s.started.connect(self.on_strip_started)
                s.changed.connect(self.mark_dirty)
                s.message.connect(lambda m: self.statusBar().showMessage(m, 6000))
                self.strips.append(s)
                grid.addWidget(s, k // 8, k % 8)
            for c in range(8):
                grid.setColumnStretch(c, 1)
            self.stack.addWidget(w)
        self.playlist = PlaylistPage(self)
        self.playlist.changed.connect(self.mark_dirty)
        self.stack.addWidget(self.playlist)
        body.addWidget(self.stack, 1)

        right = QVBoxLayout()
        right.setSpacing(3)
        right.addSpacing(20)
        self.btn_go = QPushButton("GO 1")
        self.btn_go.setObjectName("go")
        self.btn_go.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_go.setToolTip("Phát kênh kế tiếp theo thứ tự (Space). Chuột phải để chọn kênh.")
        self.btn_go.clicked.connect(self.go)
        self.btn_go.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.btn_go.customContextMenuRequested.connect(self.go_menu)
        right.addWidget(self.btn_go)
        right.addStretch(1)
        lbl = QLabel("Master")
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(lbl)
        mf = QFrame()
        mf.setObjectName("strip")
        ml = QVBoxLayout(mf)
        mh = QHBoxLayout()
        self.master = Fader()
        self.master.valueChanged.connect(self.on_master)
        mh.addWidget(self.master, 1)
        self.master_meter = VUMeter()
        mh.addWidget(self.master_meter)
        ml.addLayout(mh, 1)
        self.lbl_master = QLabel("100%")
        self.lbl_master.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ml.addWidget(self.lbl_master)
        right.addWidget(mf, 1)
        rw = QWidget()
        rw.setLayout(right)
        rw.setFixedWidth(116)
        body.addWidget(rw)
        root.addWidget(self.body_w, 1)
        self.lock_overlay = LockOverlay(self.body_w)
        self.setCentralWidget(central)

        self.lbl_clock = QLabel()
        self.lbl_clock.setStyleSheet("font-family:Consolas;font-size:9.5pt;padding-right:8px;")
        ver = QLabel(f"v{VERSION}")
        ver.setStyleSheet("color:#888;padding-right:12px;")
        self.statusBar().addPermanentWidget(ver)
        self.statusBar().addPermanentWidget(self.lbl_clock)
        self.master.setValue(97)
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
        for i, t in enumerate(("Audio 1-16", "Audio 17-32", "Playlist")):
            m.addAction(t, lambda i=i: self.show_page(i), QKeySequence(f"Ctrl+{i + 1}"))
        m.addSeparator()
        m.addAction("Long View", self.toggle_long_view)
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
        m.addAction("Hướng dẫn", self.show_guide)
        m.addSeparator()
        m.addAction(f"Giới thiệu {DISPLAY_NAME}", self.show_about)

    FIXED_KEYS = ("Ctrl+Shift+Esc", "Ctrl+Right", "Ctrl+Left", "Ctrl+E", "Ctrl+L")

    def build_shortcuts(self):
        """Phím cố định (không chỉnh trong bảng phím tắt)."""
        for key, fn in zip(self.FIXED_KEYS, (self.panic, self.playlist.next_track, self.playlist.prev_track,
                                             self.playlist.cue_selected, self.playlist.prelisten_selected)):
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
        on_playlist = self.stack.currentIndex() == 2
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
    def show_page(self, i):
        self.stack.setCurrentIndex(i)
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
        self.btn_lock.setIcon(glyph_icon("\uE72E" if on else "\uE785", "#dc2626" if on else "#3a3a3a"))
        keep = set(self.pg_buttons) | {self.btn_lock, self.btn_long}
        for b in self.tool_buttons:
            if b not in keep:
                b.setEnabled(not on)
        for top in self.menuBar().actions():
            if top.menu():
                for a in top.menu().actions():
                    if a is not self.act_lock:
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
        decks = [s.deck for s in self.strips] + self.playlist.decks
        if any(d.fading_out() for d in decks):
            self.panic()
            return
        for s in self.strips:
            s.stop(500 if s.deck.is_playing() else 0)
        if self.playlist.is_active():
            self.playlist.stop_main(500)

    def panic(self):
        for s in self.strips:
            s.stop()
        for d in self.playlist.decks:
            d.stop()
        self.pre.stop()

    # ---------- master / thiết bị ----------
    def on_master(self, v):
        db = percent_to_db(v / 100)
        self.lbl_master.setText(f"{v}%  " + (f"{db:+.1f} dB" if db is not None else "-∞ dB"))
        for s in self.strips:
            s.set_bus(v / 100)
            s.update_out_tip()
        self.playlist.set_bus(v / 100)
        self.mark_dirty()

    def apply_devices(self):
        for s in self.strips:
            s.apply_device()
        self.playlist.set_device(find_output_device(self.cfg["main_device"]))
        self.pre.set_device(find_output_device(self.cfg["pre_device"]))

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
            self.long_view = LongView(self)
        self.long_view.show()
        self.long_view.raise_()

    # ================= VÒNG CẬP NHẬT =================
    def tick(self):
        self._ticks += 1
        if self._ticks % 4 == 0:
            self.lbl_clock.setText(QTime.currentTime().toString("HH:mm:ss"))
        page = self.stack.currentIndex()
        # Master = tổng công suất các nguồn đang phát (sau fader kênh và fader Master)
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
        self.master_meter.set_levels([min(1.0, power[0] ** 0.5), min(1.0, power[1] ** 0.5)])
        if self.long_view and self.long_view.isVisible() and self._ticks % 2 == 0:
            items = [(f"{s.number}. {s.display_name()}", s.remaining_ms(), s.seg_len()) for s in self.strips if s.deck.is_playing() or s.deck.is_paused()]
            np = self.playlist.now_playing()
            if np:
                items.insert(0, ("▶ " + np[0], np[1], np[2]))
            self.long_view.update_view(items, self.cfg["warn_sec"] * 1000)

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
            self.master.setValue(int(d.get("master", 97)))
            self.btn_single.setChecked(bool(d.get("single", False)))
            self.go_next = int(d.get("go_next", 1))
            self.playlist.from_dict(d.get("playlist", {}))
        finally:
            self._loading = False
        self.update_go()
        self.apply_shortcuts()

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
        QMessageBox.information(self, "Hướng dẫn", (
            "• Kéo thả file nhạc từ Explorer vào một kênh, hoặc bấm biểu tượng nốt nhạc / nút lớn của kênh trống.\n"
            "• Bấm nút lớn (hoặc phím tắt in trên nút) để phát; bấm lại để dừng. Đổi phím ở nút Phím tắt.\n"
            "• ‖ tạm dừng / tiếp tục · Dừng: dừng (có fade out nếu đặt) · 🔁 lặp · ◢ fade in, ◣ fade out: mỗi lần bấm +0,5 giây, quá 3 giây về tắt.\n"
            "• Nút ••• (hoặc chuột phải nút lớn) → Cài đặt kênh: tên, màu, ngõ ra, chế độ bấm, fade, đoạn phát (cắt đầu/cuối bằng dạng sóng), phím phát.\n"
            "• Nháy đúp vào fader để về 80%.\n"
            "• GO phát lần lượt các kênh có nhạc theo thứ tự; chuột phải GO để chọn kênh tiếp theo.\n"
            "• Phát đơn: phát kênh mới thì các kênh khác tự fade out.\n"
            "• Khóa cài đặt: khóa toàn bộ bàn phím và chuột (nhạc vẫn phát) — chỉ mở bằng cách bấm lại nút Khóa.\n"
            "• Trang Playlist: phát danh sách dài theo thứ tự, crossfade, dừng sau mỗi bài.\n"
            "• Dự án (.evp) lưu toàn bộ kênh + playlist. Chương trình tự nhớ trạng thái khi tắt."))

    def closeEvent(self, e):
        playing = any(s.deck.is_playing() for s in self.strips) or self.playlist.is_active()
        if playing and QMessageBox.question(self, "Thoát", "Nhạc đang phát. Thoát chương trình?") \
                != QMessageBox.StandardButton.Yes:
            e.ignore()
            return
        self.write_autosave()
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
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(DISPLAY_NAME)
    app.setWindowIcon(QIcon(asset("app.ico")))
    try:   # để Windows dùng đúng icon của app trên thanh taskbar
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Starkid.EventPlayer")
    except Exception:
        pass
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 9))
    w = MainWindow()
    w.showMaximized()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
