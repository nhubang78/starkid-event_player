"""EventPlayer — phần mềm phát nhạc sự kiện cho Windows."""
import json
import os
import subprocess
import sys

from PySide6.QtCore import QSettings, QStandardPaths, Qt, QTime, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout, QInputDialog,
                               QLabel, QMainWindow, QMenu, QMessageBox, QPushButton, QSlider,
                               QSpinBox, QSplitter, QStyle, QTabWidget, QToolButton, QVBoxLayout,
                               QWidget)
from PySide6.QtMultimedia import QMediaDevices

from audio import Deck, find_output_device
from pads import PadPanel
from playlist import AUDIO_FILTER, PlaylistView, fmt_ms

APP_NAME = "EventPlayer"
APP_TITLE = "EventPlayer — Phát nhạc sự kiện"

MODES = [("stop", "Dừng sau mỗi bài (chế độ sự kiện)"),
         ("continuous", "Phát liên tục"),
         ("repeat_one", "Lặp lại 1 bài"),
         ("repeat_all", "Lặp lại cả danh sách")]

DEFAULT_CFG = {
    "main_device": "", "pre_device": "", "pad_device": "",
    "fade_in_ms": 0, "fade_out_ms": 3000, "pause_fade_ms": 200,
    "warn_sec": 10, "duck_pct": 35,
}

STYLE = """
QWidget { background:#111827; color:#e5e7eb; font-size:10pt; }
QFrame#nowPlaying { background:#0b1220; border:1px solid #1f2937; border-radius:8px; }
QLabel#bigTitle { font-size:20pt; font-weight:700; color:#f9fafb; background:transparent; }
QLabel#artist { font-size:12pt; color:#9ca3af; background:transparent; }
QLabel#timeBig { font-size:30pt; font-weight:700; font-family:Consolas; background:transparent; }
QLabel#clock { font-size:16pt; font-family:Consolas; color:#93c5fd; background:transparent; }
QLabel#next { font-size:11pt; color:#facc15; background:transparent; }
QLabel#sectionTitle { font-weight:700; color:#9ca3af; letter-spacing:1px; }
QPushButton { background:#1f2937; border:1px solid #374151; border-radius:6px; padding:6px 12px; }
QPushButton:hover { background:#273449; }
QPushButton#transport { font-size:13pt; font-weight:700; min-width:96px; min-height:40px; }
QPushButton#playBtn { background:#166534; border-color:#22c55e; }
QPushButton#stopBtn { background:#7f1d1d; border-color:#ef4444; }
QPushButton#preBtn:checked { background:#1e3a8a; border-color:#60a5fa; }
QTreeWidget { background:#0f172a; alternate-background-color:#131c31; border:1px solid #1f2937; }
QTreeWidget::item { padding:3px; }
QTreeWidget::item:selected { background:#1d4ed8; color:white; }
QHeaderView::section { background:#1f2937; color:#9ca3af; border:none; padding:4px; }
QTabWidget::pane { border:1px solid #1f2937; }
QTabBar::tab { background:#1f2937; padding:6px 14px; border-top-left-radius:6px; border-top-right-radius:6px; margin-right:2px; }
QTabBar::tab:selected { background:#2563eb; color:white; }
QSlider::groove:horizontal { height:8px; background:#374151; border-radius:4px; }
QSlider::sub-page:horizontal { background:#22c55e; border-radius:4px; }
QSlider::handle:horizontal { background:#e5e7eb; width:14px; margin:-4px 0; border-radius:7px; }
QComboBox, QSpinBox { background:#1f2937; border:1px solid #374151; border-radius:4px; padding:3px 6px; }
QMenu { background:#1f2937; border:1px solid #374151; }
QMenu::item:selected { background:#2563eb; }
QStatusBar { color:#9ca3af; }
"""


class SeekSlider(QSlider):
    seekRequested = Signal(int)

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sliderReleased.connect(lambda: self.seekRequested.emit(self.value()))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            val = QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                                 int(e.position().x()), self.width())
            self.setValue(val)
            self.seekRequested.emit(val)
        super().mousePressEvent(e)


class SettingsDialog(QDialog):
    def __init__(self, parent, cfg):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt")
        self.setMinimumWidth(460)
        form = QFormLayout(self)
        names = ["(Mặc định của Windows)"] + [d.description() for d in QMediaDevices.audioOutputs()]

        def dev_combo(cur):
            c = QComboBox()
            c.addItems(names)
            c.setCurrentIndex(names.index(cur) if cur in names else 0)
            return c

        def spin(val, lo, hi, step, suffix):
            s = QSpinBox()
            s.setRange(lo, hi)
            s.setSingleStep(step)
            s.setValue(val)
            s.setSuffix(suffix)
            return s

        self.main_dev = dev_combo(cfg["main_device"])
        self.pre_dev = dev_combo(cfg["pre_device"])
        self.pad_dev = dev_combo(cfg["pad_device"])
        self.fade_in = spin(cfg["fade_in_ms"], 0, 10000, 100, " ms")
        self.fade_out = spin(cfg["fade_out_ms"], 0, 20000, 250, " ms")
        self.pause_fade = spin(cfg["pause_fade_ms"], 0, 3000, 50, " ms")
        self.warn = spin(cfg["warn_sec"], 0, 120, 1, " giây")
        self.duck = spin(cfg["duck_pct"], 0, 100, 5, " %")
        form.addRow("Loa chính (ra sân khấu):", self.main_dev)
        form.addRow("Tai nghe nghe thử:", self.pre_dev)
        form.addRow("Thiết bị phát jingle:", self.pad_dev)
        form.addRow("Fade in khi bắt đầu bài:", self.fade_in)
        form.addRow("Fade out khi bấm Dừng:", self.fade_out)
        form.addRow("Fade khi tạm dừng/tiếp tục:", self.pause_fade)
        form.addRow("Cảnh báo sắp hết bài trước:", self.warn)
        form.addRow("Mức nhạc nền khi có jingle:", self.duck)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        form.addRow(bb)

    def values(self):
        dev = lambda c: "" if c.currentIndex() == 0 else c.currentText()
        return {"main_device": dev(self.main_dev), "pre_device": dev(self.pre_dev),
                "pad_device": dev(self.pad_dev), "fade_in_ms": self.fade_in.value(),
                "fade_out_ms": self.fade_out.value(), "pause_fade_ms": self.pause_fade.value(),
                "warn_sec": self.warn.value(), "duck_pct": self.duck.value()}


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1280, 800)
        self.settings = QSettings()
        self.cfg = dict(DEFAULT_CFG)

        self.decks = [Deck(self), Deck(self)]
        self.active = 0
        self.pre = Deck(self)
        self.cur = None      # (view, track_id) bài đang / vừa phát
        self.cued = None     # (view, track_id) bài được chỉ định phát kế tiếp
        self._xfade_done = False
        self._duck_target = 1.0
        self._duck_cur = 1.0
        self._ticks = 0
        self._remain_warn = None

        for d in self.decks:
            d.ended.connect(lambda d=d: self.on_deck_ended(d))
            d.error.connect(self.on_error)
            d.stateChanged.connect(self.refresh_marks)
        self.pre.error.connect(self.on_error)

        self.build_ui()
        self.build_menu()
        self.build_shortcuts()
        self.load_settings()
        self.load_session()
        self.apply_devices()

        self.media_devices = QMediaDevices(self)
        self.media_devices.audioOutputsChanged.connect(self.apply_devices)

        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(100)
        self.ui_timer.timeout.connect(self.tick)
        self.ui_timer.start()
        self.refresh_marks()

    # ================= GIAO DIỆN =================
    def build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)

        # --- Khung đang phát ---
        np = QFrame()
        np.setObjectName("nowPlaying")
        g = QGridLayout(np)
        g.setContentsMargins(16, 12, 16, 12)
        self.lbl_title = QLabel("— Sẵn sàng —")
        self.lbl_title.setObjectName("bigTitle")
        self.lbl_artist = QLabel("")
        self.lbl_artist.setObjectName("artist")
        self.lbl_clock = QLabel("00:00:00")
        self.lbl_clock.setObjectName("clock")
        self.lbl_elapsed = QLabel("0:00")
        self.lbl_elapsed.setObjectName("timeBig")
        self.lbl_remain = QLabel("-0:00")
        self.lbl_remain.setObjectName("timeBig")
        self.lbl_remain.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek = SeekSlider()
        self.seek.setRange(0, 1)
        self.seek.seekRequested.connect(self.seek_to)
        self.lbl_next = QLabel("Tiếp theo: —")
        self.lbl_next.setObjectName("next")
        g.addWidget(self.lbl_title, 0, 0, 1, 2)
        g.addWidget(self.lbl_clock, 0, 2, Qt.AlignmentFlag.AlignRight)
        g.addWidget(self.lbl_artist, 1, 0, 1, 3)
        g.addWidget(self.lbl_elapsed, 2, 0)
        g.addWidget(self.seek, 2, 1)
        g.addWidget(self.lbl_remain, 2, 2)
        g.addWidget(self.lbl_next, 3, 0, 1, 3)
        g.setColumnStretch(1, 1)
        root.addWidget(np)

        # --- Hàng nút điều khiển ---
        tr = QHBoxLayout()

        def tbtn(text, slot, name="transport", tip=""):
            b = QPushButton(text)
            b.setObjectName(name)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            tr.addWidget(b)
            return b

        tbtn("⏮", self.prev_track, tip="Bài trước (Ctrl+←)")
        self.btn_play = tbtn("▶ PHÁT", self.play_pause, tip="Phát / Tạm dừng (Space)")
        self.btn_play.setObjectName("transport")
        self.btn_play.setProperty("class", "play")
        self.btn_play.setStyleSheet("background:#166534;border-color:#22c55e;")
        b_stop = tbtn("⏹ DỪNG", self.stop_main, tip="Dừng có fade (Esc). Bấm 2 lần = dừng ngay")
        b_stop.setStyleSheet("background:#7f1d1d;border-color:#ef4444;")
        tbtn("⏭", self.next_track, tip="Bài tiếp (Ctrl+→)")
        tr.addSpacing(16)

        col = QVBoxLayout()
        col.addWidget(QLabel("Chế độ phát"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for key, text in MODES:
            self.cmb_mode.addItem(text, key)
        self.cmb_mode.currentIndexChanged.connect(lambda _i: self.refresh_marks())
        col.addWidget(self.cmb_mode)
        tr.addLayout(col)

        col = QVBoxLayout()
        col.addWidget(QLabel("Crossfade"))
        self.spn_xfade = QSpinBox()
        self.spn_xfade.setRange(0, 20)
        self.spn_xfade.setSuffix(" giây")
        self.spn_xfade.setToolTip("Thời gian chồng/chuyển giữa 2 bài (chế độ phát liên tục)")
        col.addWidget(self.spn_xfade)
        tr.addLayout(col)

        col = QVBoxLayout()
        self.lbl_vol = QLabel("Âm lượng: 100%")
        col.addWidget(self.lbl_vol)
        self.sld_vol = QSlider(Qt.Orientation.Horizontal)
        self.sld_vol.setRange(0, 100)
        self.sld_vol.setValue(100)
        self.sld_vol.setFixedWidth(160)
        self.sld_vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sld_vol.valueChanged.connect(self.set_volume)
        col.addWidget(self.sld_vol)
        tr.addLayout(col)

        tr.addStretch()
        col = QVBoxLayout()
        self.btn_pre = QPushButton("🎧 Nghe thử")
        self.btn_pre.setObjectName("preBtn")
        self.btn_pre.setCheckable(True)
        self.btn_pre.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.btn_pre.setToolTip("Nghe thử bài đang chọn ra tai nghe (Ctrl+L)")
        self.btn_pre.clicked.connect(lambda _c: self.toggle_prelisten())
        col.addWidget(self.btn_pre)
        self.lbl_pre = QLabel("")
        self.lbl_pre.setStyleSheet("color:#60a5fa;")
        col.addWidget(self.lbl_pre)
        tr.addLayout(col)
        root.addLayout(tr)

        # --- Danh sách phát + jingle ---
        split = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        lbl = QLabel("DANH SÁCH PHÁT")
        lbl.setObjectName("sectionTitle")
        bar.addWidget(lbl)
        bar.addStretch()
        for text, slot in [("+ File", self.add_files), ("+ Thư mục", self.add_folder),
                           ("Xóa", self.remove_selected), ("Mở...", self.open_playlist),
                           ("Lưu...", self.save_playlist)]:
            b = QPushButton(text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(slot)
            bar.addWidget(b)
        lv.addLayout(bar)
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.tabBarDoubleClicked.connect(self.rename_tab)
        self.tabs.currentChanged.connect(lambda _i: self.refresh_marks())
        plus = QToolButton()
        plus.setText(" + ")
        plus.setToolTip("Tạo danh sách mới")
        plus.clicked.connect(lambda: self.new_playlist())
        self.tabs.setCornerWidget(plus, Qt.Corner.TopRightCorner)
        lv.addWidget(self.tabs, 1)
        split.addWidget(left)

        self.pads = PadPanel()
        self.pads.anyPlayingChanged.connect(self.on_pads_playing)
        split.addWidget(self.pads)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([780, 480])
        root.addWidget(split, 1)

        self.setCentralWidget(central)
        self.lbl_status = QLabel("")
        self.statusBar().addPermanentWidget(self.lbl_status)

    def build_menu(self):
        mb = self.menuBar()
        m = mb.addMenu("&Tệp")
        m.addAction("Danh sách mới", lambda: self.new_playlist(), QKeySequence("Ctrl+T"))
        m.addAction("Mở danh sách...", self.open_playlist, QKeySequence("Ctrl+O"))
        m.addAction("Lưu danh sách đang mở...", self.save_playlist, QKeySequence("Ctrl+S"))
        m.addSeparator()
        m.addAction("Thêm file nhạc...", self.add_files)
        m.addAction("Thêm thư mục nhạc...", self.add_folder)
        m.addSeparator()
        m.addAction("Thoát", self.close)
        m = mb.addMenu("&Phát")
        m.addAction("Đánh dấu tất cả là chưa phát", self.reset_played)
        m.addAction("Dừng mọi âm thanh ngay lập tức", self.panic, QKeySequence("Ctrl+Shift+Esc"))
        m = mb.addMenu("&Cài đặt")
        m.addAction("Thiết bị âm thanh && fade...", self.open_settings)
        m = mb.addMenu("Trợ &giúp")
        m.addAction("Phím tắt", self.show_help)

    def build_shortcuts(self):
        def sc(key, fn):
            s = QShortcut(QKeySequence(key), self)
            s.activated.connect(fn)

        sc(Qt.Key.Key_Space, self.play_pause)
        sc(Qt.Key.Key_Escape, self.stop_main)
        sc("Ctrl+Right", self.next_track)
        sc("Ctrl+Left", self.prev_track)
        sc("Ctrl+L", self.toggle_prelisten)
        sc("Ctrl+E", self.cue_selected)
        sc("Ctrl+Up", lambda: self.sld_vol.setValue(self.sld_vol.value() + 5))
        sc("Ctrl+Down", lambda: self.sld_vol.setValue(self.sld_vol.value() - 5))
        for i in range(12):
            sc(f"F{i + 1}", lambda i=i: self.pads.trigger(i))

    # ================= DANH SÁCH =================
    def new_playlist(self, name=None, tracks=None, select=True):
        if name is None:
            name, ok = QInputDialog.getText(self, "Danh sách mới", "Tên danh sách:",
                                            text=f"Danh sách {self.tabs.count() + 1}")
            if not ok:
                return None
            name = name.strip() or f"Danh sách {self.tabs.count() + 1}"
        view = PlaylistView()
        if tracks:
            view.from_list(tracks)
        view.itemActivated.connect(lambda item, _c, v=view: self.start_track(
            v, item.data(0, Qt.ItemDataRole.UserRole)))
        view.customContextMenuRequested.connect(lambda pos, v=view: self.track_menu(v, pos))
        view.changed.connect(self.refresh_marks)
        idx = self.tabs.addTab(view, name)
        if select:
            self.tabs.setCurrentIndex(idx)
        return view

    def current_view(self):
        w = self.tabs.currentWidget()
        return w if isinstance(w, PlaylistView) else None

    def view_valid(self, v):
        return v is not None and self.tabs.indexOf(v) != -1

    def close_tab(self, idx):
        view = self.tabs.widget(idx)
        if view.topLevelItemCount() and QMessageBox.question(
                self, "Đóng danh sách", f"Đóng danh sách “{self.tabs.tabText(idx)}”?") != QMessageBox.StandardButton.Yes:
            return
        self.tabs.removeTab(idx)
        view.deleteLater()
        if self.tabs.count() == 0:
            self.new_playlist("Danh sách 1")
        self.refresh_marks()

    def rename_tab(self, idx):
        if idx < 0:
            return
        name, ok = QInputDialog.getText(self, "Đổi tên", "Tên danh sách:", text=self.tabs.tabText(idx))
        if ok and name.strip():
            self.tabs.setTabText(idx, name.strip())

    def add_files(self):
        v = self.current_view()
        files, _ = QFileDialog.getOpenFileNames(self, "Thêm nhạc", self.settings.value("lastDir", ""), AUDIO_FILTER)
        if files and v:
            self.settings.setValue("lastDir", os.path.dirname(files[0]))
            n = v.add_paths(files)
            self.statusBar().showMessage(f"Đã thêm {n} bài", 4000)

    def add_folder(self):
        v = self.current_view()
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục nhạc", self.settings.value("lastDir", ""))
        if d and v:
            self.settings.setValue("lastDir", d)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                n = v.add_paths([d])
            finally:
                QApplication.restoreOverrideCursor()
            self.statusBar().showMessage(f"Đã thêm {n} bài", 4000)

    def remove_selected(self):
        v = self.current_view()
        if v:
            v.remove_ids(set(v.selected_ids()))

    def save_playlist(self):
        v = self.current_view()
        if not v:
            return
        name = self.tabs.tabText(self.tabs.currentIndex())
        path, flt = QFileDialog.getSaveFileName(self, "Lưu danh sách", name + ".evpl",
                                                "Danh sách EventPlayer (*.evpl);;Danh sách M3U (*.m3u8)")
        if not path:
            return
        try:
            if path.lower().endswith((".m3u", ".m3u8")):
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write("#EXTM3U\n")
                    for t in v.to_list():
                        fh.write(f"#EXTINF:{t['duration'] // 1000},{t['artist']} - {t['title']}\n{t['path']}\n")
            else:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump({"name": name, "tracks": v.to_list()}, fh, ensure_ascii=False, indent=1)
            self.statusBar().showMessage("Đã lưu " + path, 4000)
        except OSError as e:
            QMessageBox.warning(self, "Lỗi", str(e))

    def open_playlist(self):
        path, _ = QFileDialog.getOpenFileName(self, "Mở danh sách", "",
                                              "Danh sách (*.evpl *.m3u *.m3u8)")
        if not path:
            return
        name = os.path.splitext(os.path.basename(path))[0]
        if path.lower().endswith(".evpl"):
            try:
                with open(path, encoding="utf-8") as fh:
                    data = json.load(fh)
                self.new_playlist(data.get("name", name), data.get("tracks", []))
            except (OSError, ValueError) as e:
                QMessageBox.warning(self, "Lỗi", f"Không mở được danh sách:\n{e}")
        else:
            v = self.new_playlist(name)
            v.add_paths([path])

    def reset_played(self):
        for i in range(self.tabs.count()):
            for t in self.tabs.widget(i).tracks.values():
                t.played = False
        self.refresh_marks()

    def track_menu(self, view, pos):
        item = view.itemAt(pos)
        m = QMenu(self)
        if item:
            tid = item.data(0, Qt.ItemDataRole.UserRole)
            t = view.tracks[tid]
            ids = view.selected_ids() or [tid]
            m.addAction("▶  Phát ngay", lambda: self.start_track(view, tid))
            m.addAction("⏭  Đặt làm bài kế tiếp (Ctrl+E)", lambda: self.set_cue(view, tid))
            m.addAction("🎧  Nghe thử ra tai nghe", lambda: self.prelisten(view, tid))
            a = m.addAction("⏹  Dừng sau bài này")
            a.setCheckable(True)
            a.setChecked(t.stop_after)
            a.toggled.connect(lambda on: self.set_stop_after(view, ids, on))
            m.addSeparator()
            m.addAction("Đánh dấu chưa phát", lambda: self.set_played(view, ids, False))
            m.addAction("Đánh dấu đã phát", lambda: self.set_played(view, ids, True))
            m.addAction("Mở thư mục chứa file", lambda: subprocess.Popen(
                ["explorer", "/select,", os.path.normpath(t.path)]))
            m.addSeparator()
            m.addAction("Xóa khỏi danh sách (Del)", lambda: view.remove_ids(set(ids)))
        else:
            m.addAction("Thêm file nhạc...", self.add_files)
            m.addAction("Thêm thư mục nhạc...", self.add_folder)
        m.exec(view.viewport().mapToGlobal(pos))

    def set_stop_after(self, view, ids, on):
        for i in ids:
            if i in view.tracks:
                view.tracks[i].stop_after = on
        self.refresh_marks()

    def set_played(self, view, ids, on):
        for i in ids:
            if i in view.tracks:
                view.tracks[i].played = on
        self.refresh_marks()

    def set_cue(self, view, tid):
        self.cued = (view, tid)
        self.refresh_marks()

    def cue_selected(self):
        v = self.current_view()
        if v and v.selected_ids():
            self.set_cue(v, v.selected_ids()[0])

    # ================= PHÁT NHẠC =================
    @property
    def deck(self):
        return self.decks[self.active]

    def mode(self):
        return self.cmb_mode.currentData()

    def xfade_ms(self):
        return self.spn_xfade.value() * 1000

    def cur_track(self):
        if self.cur and self.view_valid(self.cur[0]):
            return self.cur[0].tracks.get(self.cur[1])
        return None

    def next_candidate(self):
        if self.cued and self.view_valid(self.cued[0]) and self.cued[1] in self.cued[0].tracks:
            return self.cued
        if self.cur and self.view_valid(self.cur[0]):
            v, tid = self.cur
            ids = v.ordered_ids()
            if tid in ids:
                i = ids.index(tid)
                if i + 1 < len(ids):
                    return v, ids[i + 1]
                if self.mode() == "repeat_all" and ids:
                    return v, ids[0]
                return None
        v = self.current_view()
        if v:
            sel = v.selected_ids()
            if sel:
                return v, sel[0]
            ids = v.ordered_ids()
            if ids:
                return v, ids[0]
        return None

    def start_track(self, view, tid, crossfade=None):
        t = view.tracks.get(tid)
        if t is None:
            return
        if t.missing:
            self.statusBar().showMessage("Không tìm thấy file: " + t.path, 6000)
            self.refresh_marks()
            return
        old = self.deck
        was_playing = old.is_playing()
        if was_playing:
            xf = self.xfade_ms() if crossfade is None else crossfade
            old.stop(xf if xf > 0 else 300)
            self.active ^= 1
        else:
            old.stop()
        new = self.deck
        new.stop()
        new.set_duck(self._duck_cur)
        new.load(t.path)
        if was_playing and crossfade:
            new.play(crossfade)
        else:
            new.play(self.cfg["fade_in_ms"])
        t.played = True
        self.cur = (view, tid)
        self.cued = None
        self._xfade_done = False
        item = view.item_of(tid)
        if item:
            view.scrollToItem(item)
        self.refresh_marks()

    def on_deck_ended(self, d):
        if d is not self.deck:
            return  # deck cũ đã crossfade xong
        t = self.cur_track()
        if self.mode() == "repeat_one" and t:
            d.player.setPosition(0)
            d.play()
            return
        nxt = self.next_candidate()
        if t is None or t.stop_after or self.mode() == "stop" or nxt is None:
            if nxt:
                it = nxt[0].item_of(nxt[1])
                if it:
                    nxt[0].scrollToItem(it)
            self.refresh_marks()
            return
        self.start_track(*nxt, crossfade=0)

    def play_pause(self):
        d = self.deck
        if d.is_playing():
            d.pause(self.cfg["pause_fade_ms"])
        elif d.is_paused():
            d.play(self.cfg["pause_fade_ms"])
        else:
            n = self.next_candidate()
            if n:
                self.start_track(*n)

    def stop_main(self):
        d = self.deck
        if d.fading_out() or not d.is_playing():
            for x in self.decks:
                x.stop()
        else:
            d.stop(self.cfg["fade_out_ms"])
            other = self.decks[self.active ^ 1]
            if other.is_playing():
                other.stop(300)

    def panic(self):
        for x in self.decks:
            x.stop()
        self.pre.stop()
        for p in self.pads.pads:
            p.deck.stop()

    def next_track(self):
        n = self.next_candidate()
        if n:
            self.start_track(*n)

    def prev_track(self):
        if not (self.cur and self.view_valid(self.cur[0])):
            return
        v, tid = self.cur
        ids = v.ordered_ids()
        if tid in ids:
            i = ids.index(tid)
            if self.deck.position() > 3000 or i == 0:
                self.start_track(v, tid)
            else:
                self.start_track(v, ids[i - 1])

    def seek_to(self, ms):
        d = self.deck
        if d.is_playing() or d.is_paused():
            d.player.setPosition(ms)
            self._xfade_done = False

    def set_volume(self, v):
        self.lbl_vol.setText(f"Âm lượng: {v}%")
        for d in self.decks:
            d.set_master(v / 100)

    def on_pads_playing(self, playing):
        duck = self.cfg["duck_pct"] / 100 if (playing and self.pads.chk_duck.isChecked()) else 1.0
        self._duck_target = duck

    # ---------- nghe thử ----------
    def prelisten(self, view, tid):
        t = view.tracks.get(tid)
        if not t or t.missing:
            return
        self.pre.load(t.path)
        self.pre.play()
        self.pre_title = t.title
        self.btn_pre.setChecked(True)

    def toggle_prelisten(self):
        if self.pre.is_playing():
            self.pre.stop()
            self.btn_pre.setChecked(False)
            return
        v = self.current_view()
        sel = v.selected_ids() if v else []
        if sel:
            self.prelisten(v, sel[0])
        else:
            self.btn_pre.setChecked(False)
            self.statusBar().showMessage("Chọn một bài trong danh sách để nghe thử", 3000)

    # ================= CẬP NHẬT HIỂN THỊ =================
    def refresh_marks(self):
        d = self.deck
        active = d.is_playing() or d.is_paused()
        nxt = self.next_candidate()
        for i in range(self.tabs.count()):
            v = self.tabs.widget(i)
            play_id = self.cur[1] if (active and self.cur and self.cur[0] is v) else None
            cued_id = self.cued[1] if (self.cued and self.cued[0] is v) else None
            next_id = nxt[1] if (nxt and nxt[0] is v) else None
            v.update_marks(play_id, d.is_paused(), cued_id, next_id)
        if nxt:
            t = nxt[0].tracks[nxt[1]]
            prefix = "Kế tiếp (đã chọn)" if self.cued else "Tiếp theo"
            self.lbl_next.setText(f"{prefix}: {t.title}" + (f" — {t.artist}" if t.artist else "")
                                  + f"   [{fmt_ms(t.duration)}]")
        else:
            self.lbl_next.setText("Tiếp theo: — (hết danh sách)")
        ct = self.cur_track()
        if active and ct:
            self.lbl_title.setText(("⏸ " if d.is_paused() else "") + ct.title)
            self.lbl_artist.setText(ct.artist)
        else:
            self.lbl_title.setText("— Sẵn sàng —")
            self.lbl_artist.setText("Nhấn Space để phát bài tiếp theo" if nxt else "")
        self.btn_play.setText("⏸ TẠM DỪNG" if d.is_playing() else "▶ PHÁT")

    def tick(self):
        self._ticks += 1
        self.lbl_clock.setText(QTime.currentTime().toString("HH:mm:ss"))
        d = self.deck
        active = d.is_playing() or d.is_paused()
        pos, dur = d.position(), d.duration()
        rem = max(0, dur - pos)
        if active:
            self.lbl_elapsed.setText(fmt_ms(pos))
            self.lbl_remain.setText("-" + fmt_ms(rem))
            if not self.seek.isSliderDown():
                self.seek.setMaximum(max(1, dur))
                self.seek.setValue(pos)
        else:
            self.lbl_elapsed.setText("0:00")
            self.lbl_remain.setText("-0:00")
            self.seek.setValue(0)

        # cảnh báo sắp hết bài (nhấp nháy đỏ)
        warn = active and dur > 0 and rem <= self.cfg["warn_sec"] * 1000
        state = ("red" if QTime.currentTime().msec() < 500 else "dim") if warn else "normal"
        if state != self._remain_warn:
            self._remain_warn = state
            color = {"red": "#ef4444", "dim": "#7f1d1d", "normal": "#f9fafb"}[state]
            self.lbl_remain.setStyleSheet(f"color:{color};")

        # crossfade tự động ở chế độ phát liên tục
        xf = self.xfade_ms()
        ct = self.cur_track()
        if (xf > 0 and d.is_playing() and not d.fading_out() and not self._xfade_done
                and self.mode() in ("continuous", "repeat_all") and dur > 0 and rem <= xf
                and ct and not ct.stop_after):
            nxt = self.next_candidate()
            if nxt:
                self._xfade_done = True
                self.start_track(*nxt, crossfade=min(xf, max(rem, 1)))

        # duck mượt khi phát jingle
        if abs(self._duck_cur - self._duck_target) > 1e-3:
            step = 0.12
            if self._duck_cur < self._duck_target:
                self._duck_cur = min(self._duck_target, self._duck_cur + step)
            else:
                self._duck_cur = max(self._duck_target, self._duck_cur - step)
            for x in self.decks:
                x.set_duck(self._duck_cur)

        # nghe thử
        if self.pre.is_playing():
            self.lbl_pre.setText(f"{getattr(self, 'pre_title', '')[:28]}  -{fmt_ms(self.pre.duration() - self.pre.position())}")
        elif self.btn_pre.isChecked() or self.lbl_pre.text():
            self.btn_pre.setChecked(False)
            self.lbl_pre.setText("")

        # thanh trạng thái
        if self._ticks % 5 == 0:
            v = self.current_view()
            if v:
                ids = v.ordered_ids()
                msg = f"{len(ids)} bài · tổng {fmt_ms(v.total_ms())}"
                if active and self.cur and self.cur[0] is v and self.cur[1] in ids:
                    after = ids[ids.index(self.cur[1]) + 1:]
                    msg += f" · còn lại đến hết danh sách {fmt_ms(rem + v.total_ms(after))}"
                self.lbl_status.setText(msg)

    def on_error(self, msg):
        self.statusBar().showMessage("Lỗi phát: " + msg, 8000)

    # ================= CÀI ĐẶT & PHIÊN =================
    def open_settings(self):
        dlg = SettingsDialog(self, self.cfg)
        if dlg.exec():
            self.cfg.update(dlg.values())
            self.apply_devices()
            self.on_pads_playing(any(p.is_playing() for p in self.pads.pads))
            self.save_settings()

    def apply_devices(self):
        main = find_output_device(self.cfg["main_device"])
        for d in self.decks:
            d.set_device(main)
        self.pre.set_device(find_output_device(self.cfg["pre_device"]))
        self.pads.set_device(find_output_device(self.cfg["pad_device"]))
        self.statusBar().showMessage(f"Loa chính: {main.description()}", 4000)

    def load_settings(self):
        try:
            self.cfg.update(json.loads(self.settings.value("config", "{}")))
        except (TypeError, ValueError):
            pass
        geo = self.settings.value("geometry")
        if geo is not None:
            self.restoreGeometry(geo)
        self.sld_vol.setValue(int(self.settings.value("volume", 100)))
        self.spn_xfade.setValue(int(self.settings.value("xfade", 0)))
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(self.settings.value("mode", "stop"))))
        self.set_volume(self.sld_vol.value())

    def save_settings(self):
        self.settings.setValue("config", json.dumps(self.cfg))
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("volume", self.sld_vol.value())
        self.settings.setValue("xfade", self.spn_xfade.value())
        self.settings.setValue("mode", self.mode())

    def session_path(self):
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "session.json")

    def load_session(self):
        data = {}
        try:
            with open(self.session_path(), encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            pass
        for pl in data.get("playlists", []):
            self.new_playlist(pl.get("name", "Danh sách"), pl.get("tracks", []), select=False)
        if self.tabs.count() == 0:
            self.new_playlist("Danh sách 1")
        self.tabs.setCurrentIndex(min(int(data.get("current", 0)), self.tabs.count() - 1))
        if "pads" in data:
            self.pads.from_dict(data["pads"])

    def save_session(self):
        data = {"playlists": [{"name": self.tabs.tabText(i), "tracks": self.tabs.widget(i).to_list()}
                              for i in range(self.tabs.count())],
                "current": self.tabs.currentIndex(),
                "pads": self.pads.to_dict()}
        try:
            with open(self.session_path(), "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
        except OSError:
            pass

    def show_help(self):
        QMessageBox.information(self, "Phím tắt", (
            "Space\tPhát / Tạm dừng (khi dừng: phát bài tiếp theo)\n"
            "Esc\tDừng có fade out (bấm 2 lần = dừng ngay)\n"
            "Enter / nháy đúp\tPhát ngay bài đang chọn\n"
            "Ctrl+→ / Ctrl+←\tBài tiếp / bài trước\n"
            "Ctrl+E\tĐặt bài đang chọn làm bài kế tiếp\n"
            "Ctrl+L\tNghe thử bài đang chọn ra tai nghe\n"
            "Ctrl+↑ / Ctrl+↓\tTăng / giảm âm lượng\n"
            "F1 … F12\tPhát / dừng jingle\n"
            "Delete\tXóa bài đang chọn khỏi danh sách\n"
            "Ctrl+Shift+Esc\tDừng mọi âm thanh ngay\n\n"
            "Kéo thả file/thư mục từ Explorer vào danh sách hoặc vào nút jingle.\n"
            "Nháy đúp vào tên tab để đổi tên danh sách."))

    def closeEvent(self, e):
        if any(d.is_playing() for d in self.decks):
            if QMessageBox.question(self, "Thoát", "Nhạc đang phát. Thoát chương trình?") != QMessageBox.StandardButton.Yes:
                e.ignore()
                return
        self.save_session()
        self.save_settings()
        e.accept()


def main():
    app = QApplication(sys.argv)
    app.setOrganizationName(APP_NAME)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
