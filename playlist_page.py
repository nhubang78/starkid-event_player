"""Trang Playlist: phát danh sách nhạc theo thứ tự, crossfade, chế độ sự kiện."""
import json
import os
import subprocess

from PySide6.QtCore import QSize, Qt, QTime, Signal
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QGridLayout,
                               QHBoxLayout, QInputDialog, QLabel, QMenu, QMessageBox, QPushButton,
                               QSlider, QSpinBox, QTabWidget, QToolButton, QVBoxLayout, QWidget)

from audio import Deck
from playlist import AUDIO_FILTER, PlaylistView, fmt_ms
from widgets import SeekSlider, VUMeter, shape_icon

MODES = [("stop", "Dừng sau mỗi bài (chế độ sự kiện)"),
         ("continuous", "Phát liên tục"),
         ("repeat_one", "Lặp lại 1 bài"),
         ("repeat_all", "Lặp lại cả danh sách")]


class PlaylistPage(QWidget):
    changed = Signal()

    def __init__(self, host, parent=None):
        super().__init__(parent)
        self.host = host
        self.decks = [Deck(self, meter=True), Deck(self, meter=True)]
        self.active = 0
        self.cur = None      # (view, track_id) bài đang / vừa phát
        self.cued = None     # (view, track_id) bài chỉ định phát kế tiếp
        self._xfade_done = False
        self._remain_warn = None
        self._ticks = 0
        for d in self.decks:
            d.ended.connect(lambda d=d: self.on_deck_ended(d))
            d.error.connect(lambda m: host.statusBar().showMessage("Lỗi phát: " + m, 8000))
            d.stateChanged.connect(self.refresh_marks)
        self.build_ui()

    # ================= GIAO DIỆN =================
    def build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        np = QFrame()
        np.setObjectName("nowPlaying")
        g = QGridLayout(np)
        g.setContentsMargins(16, 12, 16, 12)
        self.lbl_title = QLabel("— Sẵn sàng —")
        self.lbl_title.setObjectName("bigTitle")
        self.lbl_artist = QLabel("")
        self.lbl_artist.setObjectName("artist")
        self.lbl_elapsed = QLabel("0:00")
        self.lbl_elapsed.setObjectName("timeBig")
        self.lbl_remain = QLabel("-0:00")
        self.lbl_remain.setObjectName("timeBig")
        self.lbl_remain.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.seek = SeekSlider()
        self.seek.seekRequested.connect(self.seek_to)
        self.lbl_next = QLabel("Tiếp theo: —")
        self.lbl_next.setObjectName("next")
        self.meter = VUMeter(scale=False)
        self.meter.setMinimumHeight(60)
        g.addWidget(self.lbl_title, 0, 0, 1, 3)
        g.addWidget(self.lbl_artist, 1, 0, 1, 3)
        g.addWidget(self.lbl_elapsed, 2, 0)
        g.addWidget(self.seek, 2, 1)
        g.addWidget(self.lbl_remain, 2, 2)
        g.addWidget(self.lbl_next, 3, 0, 1, 3)
        g.addWidget(self.meter, 0, 3, 4, 1)
        g.setColumnStretch(1, 1)
        root.addWidget(np)

        tr = QHBoxLayout()

        def tbtn(text, slot, tip, style="", ic=None):
            b = QPushButton(text)
            b.setObjectName("transport")
            if ic:
                b.setIcon(shape_icon(*ic))
                b.setIconSize(QSize(18, 18))
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(tip)
            if style:
                b.setStyleSheet(style)
            b.clicked.connect(slot)
            tr.addWidget(b)
            return b

        tbtn("", self.prev_track, "Bài trước (Ctrl+←)", ic=("prev", "#374151"))
        self.btn_play = tbtn(" PHÁT", self.play_pause, "Phát / Tạm dừng (Space)",
                             "background:#dcfce7;border-color:#22c55e;min-width:170px;", ("play", "#15803d"))
        tbtn(" DỪNG", self.stop_main, "Dừng có fade (Esc). Bấm 2 lần = dừng ngay",
             "background:#fee2e2;border-color:#ef4444;", ("stop", "#b91c1c"))
        tbtn("", self.next_track, "Bài tiếp (Ctrl+→)", ic=("next", "#374151"))
        tr.addSpacing(16)

        col = QVBoxLayout()
        col.addWidget(QLabel("Chế độ phát"))
        self.cmb_mode = QComboBox()
        self.cmb_mode.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.cmb_mode.setMinimumWidth(250)
        for key, text in MODES:
            self.cmb_mode.addItem(text, key)
        self.cmb_mode.currentIndexChanged.connect(lambda _i: (self.refresh_marks(), self.changed.emit()))
        col.addWidget(self.cmb_mode)
        tr.addLayout(col)

        col = QVBoxLayout()
        col.addWidget(QLabel("Crossfade"))
        self.spn_xfade = QSpinBox()
        self.spn_xfade.setRange(0, 20)
        self.spn_xfade.setSuffix(" giây")
        self.spn_xfade.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.spn_xfade.valueChanged.connect(lambda _v: self.changed.emit())
        col.addWidget(self.spn_xfade)
        tr.addLayout(col)

        col = QVBoxLayout()
        self.lbl_vol = QLabel("Âm lượng: 80%")
        col.addWidget(self.lbl_vol)
        self.sld_vol = QSlider(Qt.Orientation.Horizontal)
        self.sld_vol.setRange(0, 100)
        self.sld_vol.setFixedWidth(160)
        self.sld_vol.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.sld_vol.valueChanged.connect(self.set_volume)
        self.sld_vol.setValue(80)
        col.addWidget(self.sld_vol)
        tr.addLayout(col)
        tr.addStretch()
        root.addLayout(tr)

        tr = QHBoxLayout()
        tr.addStretch()
        for text, slot in [("+ File", self.add_files), ("+ Thư mục", self.add_folder),
                           ("Xóa", self.remove_selected), ("Nhập...", self.open_playlist),
                           ("Xuất...", self.save_playlist), ("🎧 Nghe thử", self.prelisten_selected)]:
            b = QPushButton(text)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(slot)
            tr.addWidget(b)
        root.addLayout(tr)

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
        root.addWidget(self.tabs, 1)

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
        view.changed.connect(self.changed.emit)
        idx = self.tabs.addTab(view, name)
        if select:
            self.tabs.setCurrentIndex(idx)
        self.changed.emit()
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
        self.changed.emit()

    def rename_tab(self, idx):
        if idx < 0:
            return
        name, ok = QInputDialog.getText(self, "Đổi tên", "Tên danh sách:", text=self.tabs.tabText(idx))
        if ok and name.strip():
            self.tabs.setTabText(idx, name.strip())
            self.changed.emit()

    def add_files(self):
        v = self.current_view()
        s = self.host.settings
        files, _ = QFileDialog.getOpenFileNames(self, "Thêm nhạc", s.value("lastDir", ""), AUDIO_FILTER)
        if files and v:
            s.setValue("lastDir", os.path.dirname(files[0]))
            n = v.add_paths(files)
            self.host.statusBar().showMessage(f"Đã thêm {n} bài", 4000)

    def add_folder(self):
        v = self.current_view()
        s = self.host.settings
        d = QFileDialog.getExistingDirectory(self, "Chọn thư mục nhạc", s.value("lastDir", ""))
        if d and v:
            s.setValue("lastDir", d)
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try:
                n = v.add_paths([d])
            finally:
                QApplication.restoreOverrideCursor()
            self.host.statusBar().showMessage(f"Đã thêm {n} bài", 4000)

    def remove_selected(self):
        v = self.current_view()
        if v:
            v.remove_ids(set(v.selected_ids()))

    def save_playlist(self):
        v = self.current_view()
        if not v:
            return
        name = self.tabs.tabText(self.tabs.currentIndex())
        path, _ = QFileDialog.getSaveFileName(self, "Xuất danh sách", name + ".evpl",
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
            self.host.statusBar().showMessage("Đã lưu " + path, 4000)
        except OSError as e:
            QMessageBox.warning(self, "Lỗi", str(e))

    def open_playlist(self):
        path, _ = QFileDialog.getOpenFileName(self, "Nhập danh sách", "", "Danh sách (*.evpl *.m3u *.m3u8)")
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
            m.addAction("🎧  Nghe thử ra tai nghe", lambda: self.host.prelisten_file(t.path, t.title))
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
        self.changed.emit()

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

    def prelisten_selected(self):
        v = self.current_view()
        sel = v.selected_ids() if v else []
        if sel:
            t = v.tracks[sel[0]]
            self.host.prelisten_file(t.path, t.title)
        else:
            self.host.statusBar().showMessage("Chọn một bài trong danh sách để nghe thử", 3000)

    # ================= PHÁT NHẠC =================
    @property
    def deck(self):
        return self.decks[self.active]

    def mode(self):
        return self.cmb_mode.currentData()

    def xfade_ms(self):
        return self.spn_xfade.value() * 1000

    def is_active(self):
        return any(d.is_playing() for d in self.decks)

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
            self.host.statusBar().showMessage("Không tìm thấy file: " + t.path, 6000)
            self.refresh_marks()
            return
        cfg = self.host.cfg
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
        new.load(t.path)
        new.play(crossfade if (was_playing and crossfade) else cfg["fade_in_ms"])
        t.played = True
        self.cur = (view, tid)
        self.cued = None
        self._xfade_done = False
        item = view.item_of(tid)
        if item:
            view.scrollToItem(item)
        self.refresh_marks()
        self.host.on_playlist_started()

    def on_deck_ended(self, d):
        if d is not self.deck:
            return
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
        pf = self.host.cfg["pause_fade_ms"]
        if d.is_playing():
            d.pause(pf)
        elif d.is_paused():
            d.play(pf)
        else:
            n = self.next_candidate()
            if n:
                self.start_track(*n)

    def stop_main(self, fade_ms=None):
        fade_ms = self.host.cfg["fade_out_ms"] if fade_ms is None else fade_ms
        d = self.deck
        if d.fading_out() or not d.is_playing():
            for x in self.decks:
                x.stop()
        else:
            d.stop(fade_ms)
            other = self.decks[self.active ^ 1]
            if other.is_playing():
                other.stop(300)

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
        self.changed.emit()

    def set_bus(self, b):
        for d in self.decks:
            d.set_bus(b)

    def set_device(self, dev):
        for d in self.decks:
            d.set_device(dev)

    def take_levels(self):
        a, b = (d.take_levels() for d in self.decks)
        return [max(a[0], b[0]), max(a[1], b[1])]

    # ================= HIỂN THỊ =================
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
        self.btn_play.setText(" TẠM DỪNG" if d.is_playing() else " PHÁT")
        self.btn_play.setIcon(shape_icon("pause" if d.is_playing() else "play", "#15803d"))

    def now_playing(self):
        """(tên, còn lại ms, thời lượng ms) cho Long View, hoặc None."""
        d = self.deck
        ct = self.cur_track()
        if ct and (d.is_playing() or d.is_paused()):
            return ct.title, max(0, d.duration() - d.position()), d.duration()
        return None

    def tick(self, levels):
        self._ticks += 1
        self.meter.set_levels(levels)
        d = self.deck
        active = d.is_playing() or d.is_paused()
        pos, dur = d.position(), d.duration()
        rem = max(0, dur - pos)
        visible = self.isVisible()
        if visible:
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
            warn = active and dur > 0 and rem <= self.host.cfg["warn_sec"] * 1000
            state = ("red" if QTime.currentTime().msec() < 500 else "dim") if warn else "normal"
            if state != self._remain_warn:
                self._remain_warn = state
                color = {"red": "#dc2626", "dim": "#fca5a5", "normal": "#111827"}[state]
                self.lbl_remain.setStyleSheet(f"color:{color};")

        xf = self.xfade_ms()
        ct = self.cur_track()
        if (xf > 0 and d.is_playing() and not d.fading_out() and not self._xfade_done
                and self.mode() in ("continuous", "repeat_all") and dur > 0 and rem <= xf
                and ct and not ct.stop_after):
            nxt = self.next_candidate()
            if nxt:
                self._xfade_done = True
                self.start_track(*nxt, crossfade=min(xf, max(rem, 1)))

        if visible and self._ticks % 10 == 0:
            v = self.current_view()
            if v:
                ids = v.ordered_ids()
                msg = f"{len(ids)} bài · tổng {fmt_ms(v.total_ms())}"
                if active and self.cur and self.cur[0] is v and self.cur[1] in ids:
                    after = ids[ids.index(self.cur[1]) + 1:]
                    msg += f" · còn lại đến hết danh sách {fmt_ms(rem + v.total_ms(after))}"
                self.host.statusBar().showMessage(msg)

    # ================= LƯU / NẠP =================
    def to_dict(self):
        return {"playlists": [{"name": self.tabs.tabText(i), "tracks": self.tabs.widget(i).to_list()}
                              for i in range(self.tabs.count())],
                "current": self.tabs.currentIndex(), "mode": self.mode(),
                "xfade": self.spn_xfade.value(), "volume": self.sld_vol.value()}

    def from_dict(self, d):
        for x in self.decks:
            x.stop()
        self.cur = self.cued = None
        while self.tabs.count():
            w = self.tabs.widget(0)
            self.tabs.removeTab(0)
            w.deleteLater()
        for pl in d.get("playlists", []):
            self.new_playlist(pl.get("name", "Danh sách"), pl.get("tracks", []), select=False)
        if self.tabs.count() == 0:
            self.new_playlist("Danh sách 1")
        self.tabs.setCurrentIndex(min(int(d.get("current", 0)), self.tabs.count() - 1))
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(d.get("mode", "stop"))))
        self.spn_xfade.setValue(int(d.get("xfade", 0)))
        self.sld_vol.setValue(int(d.get("volume", 80)))
        self.refresh_marks()
