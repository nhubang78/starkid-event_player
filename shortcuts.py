"""Bảng phím tắt: định nghĩa thao tác, phím mặc định và hộp thoại chỉnh phím."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton,
                               QVBoxLayout)

from widgets import KeyCaptureEdit, key_label

SLOT_DEFAULTS = list("12345678") + ["9", "0", "Q", "W", "E", "R", "T", "Y"]

ACTIONS = [("go", "GO (chạy cue kế)", "Space"),
           ("stop_all", "Dừng tất cả", "Esc"),
           ("stop_cues", "Dừng các cue", ""),
           ("go_prev", "Lùi con trỏ GO", "Up"),
           ("go_next", "Tiến con trỏ GO", "Down"),
           ("long_view", "Bật/tắt Long View", "F2")] + \
          [(f"slot{i}", f"Kênh thứ {i} của trang đang xem", SLOT_DEFAULTS[i - 1]) for i in range(1, 17)]

DEFAULT_KEYS = {a: k for a, _l, k in ACTIONS}
LABELS = {a: l for a, l, _k in ACTIONS}

# Phím điều hướng: tạm tắt khi đang ở trang Playlist để danh sách vẫn dùng được mũi tên
NAV_KEYS = {"Up", "Down", "Left", "Right", "Home", "End", "PgUp", "PgDown", "Return", "Enter", "Del"}

DIALOG_STYLE = ""   # màu lấy từ stylesheet chung (theme.py)


class ShortcutDialog(QDialog):
    def __init__(self, parent, keys: dict, channel_keys: dict):
        super().__init__(parent)
        self.setWindowTitle("Bảng phím tắt")
        self.setStyleSheet(DIALOG_STYLE)
        self.channel_keys = dict(channel_keys)   # số kênh -> phím riêng
        self.edits = {}
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 16, 24, 16)
        v.setSpacing(10)
        title = QLabel("Bảng phím tắt")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(title)
        desc = QLabel("Bấm vào ô rồi bấm phím muốn gán. Phím Xóa lùi (Backspace) để bỏ gán. Phím ô kênh tác "
                      "động lên trang kênh đang mở. Muốn kênh nào có phím riêng (bấm ở trang nào cũng phát) "
                      "thì vào menu ••• của kênh, mục Phím phát riêng.")
        desc.setObjectName("desc")
        desc.setWordWrap(True)
        v.addWidget(desc)

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(6)
        for i, (act, label, _d) in enumerate(ACTIONS):
            r, c = divmod(i, 2)
            grid.addWidget(QLabel(label), r, c * 2)
            ed = KeyCaptureEdit(keys.get(act, ""))
            ed.changed.connect(lambda seq, act=act: self.on_changed(act, seq))
            grid.addWidget(ed, r, c * 2 + 1)
            self.edits[act] = ed
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(2, 1)
        v.addLayout(grid)

        self.note = QLabel("")
        self.note.setObjectName("warnNote")
        self.note.setWordWrap(True)
        v.addWidget(self.note)

        bb = QHBoxLayout()
        bb.addStretch()
        b_def = QPushButton("Về mặc định")
        b_cancel = QPushButton("Hủy")
        b_save = QPushButton("Lưu")
        b_def.setObjectName("dlgBtn")
        b_cancel.setObjectName("dlgBtn")
        b_save.setObjectName("save")
        for b in (b_def, b_cancel, b_save):
            b.setAutoDefault(False)
            bb.addWidget(b)
        b_def.clicked.connect(self.reset_defaults)
        b_cancel.clicked.connect(self.reject)
        b_save.clicked.connect(self.accept)
        v.addLayout(bb)
        self.resize(980, self.sizeHint().height())
        b_cancel.setFocus()   # mở ra chưa chọn ô nào, tránh gán nhầm

    def on_changed(self, act, seq):
        if not seq:
            self.note.setText("")
            return
        msgs = []
        for other, ed in self.edits.items():
            if other != act and ed.seq == seq:
                ed.set_seq("")
                msgs.append(f"Phím {key_label(seq)} đã bỏ khỏi “{LABELS[other]}”.")
        for num, k in list(self.channel_keys.items()):
            if k == seq:
                self.channel_keys[num] = ""
                msgs.append(f"Phím {key_label(seq)} đã bỏ khỏi phím phát riêng của Kênh {num}.")
        self.note.setText(" ".join(msgs))

    def reset_defaults(self):
        for act, ed in self.edits.items():
            ed.set_seq(DEFAULT_KEYS[act])
        used = set(DEFAULT_KEYS.values())
        cleared = [n for n, k in self.channel_keys.items() if k and k in used]
        for n in cleared:
            self.channel_keys[n] = ""
        self.note.setText("Đã đưa về phím mặc định." +
                          (f" Bỏ phím riêng trùng của kênh {', '.join(map(str, cleared))}." if cleared else ""))

    def values(self):
        return {act: ed.seq for act, ed in self.edits.items()}


class ChannelKeyDialog(QDialog):
    """Gán phím phát riêng cho một kênh."""

    def __init__(self, parent, number, seq):
        super().__init__(parent)
        self.setWindowTitle(f"Phím phát riêng — Kênh {number}")
        self.setStyleSheet(DIALOG_STYLE)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 14, 20, 14)
        d = QLabel(f"Bấm vào ô rồi bấm phím để phát Kênh {number} ở bất kỳ trang nào.\n"
                   "Backspace để bỏ gán.")
        d.setObjectName("desc")
        v.addWidget(d)
        self.edit = KeyCaptureEdit(seq)
        v.addWidget(self.edit)
        bb = QHBoxLayout()
        bb.addStretch()
        b_cancel = QPushButton("Hủy")
        b_cancel.setObjectName("dlgBtn")
        b_save = QPushButton("Lưu")
        b_save.setObjectName("save")
        for b in (b_cancel, b_save):
            b.setAutoDefault(False)
            bb.addWidget(b)
        b_cancel.clicked.connect(self.reject)
        b_save.clicked.connect(self.accept)
        v.addLayout(bb)

    def value(self):
        return self.edit.seq
