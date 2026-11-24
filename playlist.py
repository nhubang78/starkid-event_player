"""Danh sách phát: kéo-thả file/thư mục, sắp xếp lại, đọc thông tin bài hát."""
import itertools
import os
from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTreeWidget, QTreeWidgetItem

AUDIO_EXT = {'.mp3', '.wav', '.flac', '.m4a', '.aac', '.ogg', '.oga', '.opus',
             '.wma', '.aif', '.aiff', '.mp2', '.ac3'}
AUDIO_FILTER = ("Âm thanh (" + " ".join("*" + e for e in sorted(AUDIO_EXT)) + ");;"
                "Danh sách M3U (*.m3u *.m3u8);;Tất cả (*.*)")

_ids = itertools.count(1)


def fmt_ms(ms: int) -> str:
    s = max(0, int(ms) // 1000)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def read_meta(path: str):
    title = os.path.splitext(os.path.basename(path))[0]
    artist, dur = "", 0
    try:
        from mutagen import File
        f = File(path, easy=True)
        if f is not None:
            if f.info is not None and getattr(f.info, "length", None):
                dur = int(f.info.length * 1000)
            tags = f.tags
            if tags is not None and hasattr(tags, "get"):
                t, a = tags.get("title"), tags.get("artist")
                if t and isinstance(t, list):
                    title = str(t[0])
                if a and isinstance(a, list):
                    artist = str(a[0])
    except Exception:
        pass
    return title, artist, dur


def read_m3u(path: str):
    base = os.path.dirname(path)
    out = []
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                p = line if os.path.isabs(line) else os.path.join(base, line)
                out.append(os.path.normpath(p))
    except OSError:
        pass
    return out


def expand_paths(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for root, dirs, files in os.walk(p):
                dirs.sort(key=str.lower)
                for f in sorted(files, key=str.lower):
                    if os.path.splitext(f)[1].lower() in AUDIO_EXT:
                        out.append(os.path.join(root, f))
        elif p.lower().endswith((".m3u", ".m3u8")):
            out.extend(read_m3u(p))
        elif os.path.splitext(p)[1].lower() in AUDIO_EXT:
            out.append(p)
    return out


@dataclass
class Track:
    path: str
    title: str
    artist: str = ""
    duration: int = 0
    stop_after: bool = False
    played: bool = False
    id: int = field(default_factory=lambda: next(_ids))

    @property
    def missing(self):
        return not os.path.isfile(self.path)

    def to_dict(self):
        return {"path": self.path, "title": self.title, "artist": self.artist,
                "duration": self.duration, "stop_after": self.stop_after}


class PlaylistView(QTreeWidget):
    changed = Signal()
    COLS = ["", "#", "Tiêu đề", "Nghệ sĩ", "Thời lượng"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracks: dict[int, Track] = {}
        self.setColumnCount(len(self.COLS))
        self.setHeaderLabels(self.COLS)
        self.setRootIsDecorated(False)
        self.setUniformRowHeights(True)
        self.setAlternatingRowColors(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        h = self.header()
        h.setStretchLastSection(False)
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.resizeSection(0, 44)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.Interactive)
        h.resizeSection(3, 180)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self._bold = QFont()
        self._bold.setBold(True)

    # ---------- thêm / xóa ----------
    def _make_item(self, t: Track):
        it = QTreeWidgetItem()
        it.setData(0, Qt.ItemDataRole.UserRole, t.id)
        it.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsDragEnabled)
        it.setText(2, t.title)
        it.setText(3, t.artist)
        it.setText(4, fmt_ms(t.duration) if t.duration else "?")
        it.setTextAlignment(4, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        it.setToolTip(2, t.path)
        return it

    def add_tracks(self, tracks, index=None):
        if index is None or index < 0:
            index = self.topLevelItemCount()
        for t in tracks:
            self.tracks[t.id] = t
            self.insertTopLevelItem(index, self._make_item(t))
            index += 1
        self.renumber()
        self.changed.emit()

    def add_paths(self, paths, index=None):
        files = expand_paths(paths)
        tracks = []
        for p in files:
            title, artist, dur = read_meta(p)
            tracks.append(Track(path=p, title=title, artist=artist, duration=dur))
        self.add_tracks(tracks, index)
        return len(tracks)

    def remove_ids(self, ids):
        for i in reversed(range(self.topLevelItemCount())):
            tid = self.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
            if tid in ids:
                self.takeTopLevelItem(i)
                self.tracks.pop(tid, None)
        self.renumber()
        self.changed.emit()

    def renumber(self):
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).setText(1, str(i + 1))

    # ---------- truy vấn ----------
    def ordered_ids(self):
        return [self.topLevelItem(i).data(0, Qt.ItemDataRole.UserRole)
                for i in range(self.topLevelItemCount())]

    def selected_ids(self):
        items = sorted(self.selectedItems(), key=self.indexOfTopLevelItem)
        return [it.data(0, Qt.ItemDataRole.UserRole) for it in items]

    def item_of(self, tid):
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            if it.data(0, Qt.ItemDataRole.UserRole) == tid:
                return it
        return None

    def total_ms(self, ids=None):
        ids = self.ordered_ids() if ids is None else ids
        return sum(self.tracks[i].duration for i in ids if i in self.tracks)

    # ---------- hiển thị trạng thái ----------
    def update_marks(self, playing_id=None, paused=False, cued_id=None, next_id=None):
        for i in range(self.topLevelItemCount()):
            it = self.topLevelItem(i)
            tid = it.data(0, Qt.ItemDataRole.UserRole)
            t = self.tracks.get(tid)
            if t is None:
                continue
            mark, color, bold = "", None, False
            if tid == playing_id:
                mark, color, bold = ("⏸" if paused else "▶"), "#4ade80", True
            elif tid == cued_id:
                mark, color = "⏭", "#facc15"
            elif tid == next_id:
                mark = "›"
            if t.missing:
                color = "#f87171"
            elif color is None and t.played:
                color = "#6b7280"
            if t.stop_after:
                mark += "⏹"
            it.setText(0, mark)
            for c in range(len(self.COLS)):
                it.setData(c, Qt.ItemDataRole.ForegroundRole, QColor(color) if color else None)
                it.setData(c, Qt.ItemDataRole.FontRole, self._bold if bold else None)

    # ---------- lưu / nạp ----------
    def to_list(self):
        return [self.tracks[i].to_dict() for i in self.ordered_ids()]

    def from_list(self, items):
        tracks = []
        for d in items:
            if not d.get("path"):
                continue
            tracks.append(Track(path=d["path"],
                                title=d.get("title") or os.path.basename(d["path"]),
                                artist=d.get("artist", ""),
                                duration=int(d.get("duration", 0)),
                                stop_after=bool(d.get("stop_after", False))))
        self.add_tracks(tracks)

    # ---------- phím & kéo thả ----------
    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Delete:
            self.remove_ids(set(self.selected_ids()))
            return
        super().keyPressEvent(e)

    def _drop_index(self, pos):
        it = self.itemAt(pos)
        if it is None:
            return self.topLevelItemCount()
        idx = self.indexOfTopLevelItem(it)
        if pos.y() > self.visualItemRect(it).center().y():
            idx += 1
        return idx

    def _external(self, e):
        return e.mimeData().hasUrls() and e.source() is not self

    def dragEnterEvent(self, e):
        if self._external(e):
            e.acceptProposedAction()
        else:
            super().dragEnterEvent(e)

    def dragMoveEvent(self, e):
        if self._external(e):
            e.acceptProposedAction()
        else:
            super().dragMoveEvent(e)

    def dropEvent(self, e):
        if self._external(e):
            paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
            self.add_paths(paths, self._drop_index(e.position().toPoint()))
            e.acceptProposedAction()
            return
        super().dropEvent(e)
        self.renumber()
        self.changed.emit()
