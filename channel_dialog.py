"""Hộp thoại Cài đặt kênh âm thanh."""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtMultimedia import QMediaDevices
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDoubleSpinBox, QFileDialog, QFrame,
                               QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

from playlist import AUDIO_FILTER, read_meta
from waveform import SegmentEditor, fmt_cs, parse_time
from widgets import KeyCaptureEdit, key_label

from theme import CHANNEL_COLORS as COLORS   # (tên, màu chấm, màu nền nút kênh)
MODES = [("play_stop", "Play / Stop"), ("play_pause", "Play / Pause"), ("retrigger", "Retrigger")]

STYLE = ""   # màu lấy từ stylesheet chung (theme.py)


def dot_icon(color):
    pm = QPixmap(14, 14)
    pm.fill(Qt.GlobalColor.transparent)
    if color:
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(QColor(color))
        p.setPen(QColor(color).darker(130))
        p.drawEllipse(1, 1, 12, 12)
        p.end()
    return QIcon(pm)


class Segmented(QFrame):
    """Nhóm nút chọn 1 (kiểu segmented control)."""

    def __init__(self, items, current, icons=None):
        super().__init__()
        self.setObjectName("seg")
        h = QHBoxLayout(self)
        h.setContentsMargins(3, 3, 3, 3)
        h.setSpacing(2)
        self.group = QButtonGroup(self)
        self.keys = []
        for i, (key, text) in enumerate(items):
            b = QPushButton(text)
            b.setCheckable(True)
            b.setAutoDefault(False)
            if icons:
                b.setIcon(icons[i])
            self.group.addButton(b, i)
            self.keys.append(key)
            h.addWidget(b)
        self.set(current)

    def set(self, key):
        i = self.keys.index(key) if key in self.keys else 0
        self.group.button(i).setChecked(True)

    def value(self):
        return self.keys[max(0, self.group.checkedId())]


class ChannelKeyEdit(KeyCaptureEdit):
    """Phím phát: '' = theo phím ô của trang, '-' = không phím, còn lại = phím riêng."""
    CLEARED = "-"

    def __init__(self, seq, slot_key):
        self.slot_key = slot_key
        super().__init__(seq)

    def display(self, seq):
        if seq == "":
            return f"Theo trang ({key_label(self.slot_key, 'chưa gán')})"
        if seq == "-":
            return "(không phím)"
        return key_label(seq)


class ChannelSettingsDialog(QDialog):
    def __init__(self, host, strip):
        super().__init__(host)
        self.host, self.strip = host, strip
        self.path = strip.path
        self.duration = strip.duration
        self.setWindowTitle(f"Cài đặt Kênh âm thanh {strip.number}")
        self.setStyleSheet(STYLE)
        self.setMinimumWidth(820)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 14, 24, 14)
        t = QLabel(f"Cài đặt Kênh âm thanh {strip.number}")
        t.setObjectName("title")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(t)

        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(9)
        r = 0

        def row(label, widget, stretch=True):
            nonlocal r
            lb = QLabel(label)
            lb.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            g.addWidget(lb, r, 0)
            if isinstance(widget, QWidget):
                if stretch:
                    g.addWidget(widget, r, 1)
                else:
                    h = QHBoxLayout()
                    h.addWidget(widget)
                    h.addStretch()
                    g.addLayout(h, r, 1)
            else:
                g.addLayout(widget, r, 1)
            r += 1

        self.ed_name = QLineEdit(strip.display_name() if strip.path else strip.name)
        row("Tên:", self.ed_name)
        cur_color = next((c[0] for c in COLORS if c[2] and c[2] == strip.color), "Không")
        self.seg_color = Segmented([(c[0], c[0]) for c in COLORS], cur_color, [dot_icon(c[1]) for c in COLORS])
        row("Màu:", self.seg_color, False)

        h = QHBoxLayout()
        self.ed_file = QLineEdit(strip.path)
        self.ed_file.setReadOnly(True)
        b = QPushButton("Chọn...")
        b.setAutoDefault(False)
        b.clicked.connect(self.choose_file)
        h.addWidget(self.ed_file, 1)
        h.addWidget(b)
        row("Tên file:", h)

        self.cmb_dev = QComboBox()
        names = [""] + [d.description() for d in QMediaDevices.audioOutputs()]
        for n in names:
            self.cmb_dev.addItem(n or "Theo cài đặt chung (Tùy chọn)", n)
        self.cmb_dev.setCurrentIndex(max(0, self.cmb_dev.findData(strip.device)))
        row("Ngõ ra âm thanh:", self.cmb_dev)

        self.seg_mode = Segmented(MODES, strip.mode)
        row("*Chế độ bấm:", self.seg_mode, False)
        self.seg_loop = Segmented([(False, "Tắt"), (True, "Bật")], strip.loop)
        row("Lặp:", self.seg_loop, False)

        def fade_spin(val):
            s = QDoubleSpinBox()
            s.setRange(0, 60)
            s.setDecimals(1)
            s.setSingleStep(0.5)
            s.setValue(val)
            s.setFixedWidth(130)
            h = QHBoxLayout()
            h.addWidget(s)
            h.addWidget(QLabel("giây (0 - tắt, 60 - tối đa)"))
            h.addStretch()
            return s, h

        self.sp_in, h = fade_spin(strip.fade_in_s)
        row("*Fade-In:", h)
        self.sp_out, h = fade_spin(strip.fade_out_s)
        row("*Fade-Out:", h)

        h = QHBoxLayout()
        self.ed_start = QLineEdit(fmt_cs(strip.start_ms))
        self.ed_start.setObjectName("time")
        self.ed_end = QLineEdit(fmt_cs(strip.end_ms) if strip.end_ms else "")
        self.ed_end.setObjectName("time")
        self.ed_end.setPlaceholderText("cuối file")
        b_edit = QPushButton("Sửa...")
        b_reset = QPushButton("Đặt lại")
        for b in (b_edit, b_reset):
            b.setAutoDefault(False)
        b_edit.clicked.connect(self.edit_segment)
        b_reset.clicked.connect(lambda: (self.ed_start.setText(fmt_cs(0)), self.ed_end.setText("")))
        for w in (self.ed_start, self.ed_end, b_edit, b_reset):
            h.addWidget(w)
        h.addStretch()
        row("Đoạn phát:", h)

        h = QHBoxLayout()
        slot_key = host.keys.get(f"slot{(strip.number - 1) % 16 + 1}", "")
        self.key = ChannelKeyEdit(strip.own_key, slot_key)
        b_slot = QPushButton("Dùng phím ô")
        b_slot.setAutoDefault(False)
        b_slot.clicked.connect(lambda: self.key.set_seq(""))
        h.addWidget(self.key)
        h.addWidget(b_slot)
        h.addWidget(QLabel("Xóa lùi = không phím"))
        h.addStretch()
        row("Phím phát:", h)
        g.setColumnStretch(1, 1)
        v.addLayout(g)

        for text in ("*Đặt làm mặc định: các mục có dấu * sẽ được áp dụng mỗi khi nạp file nhạc vào kênh trống.",
                     "*Áp dụng cho tất cả: các mục có dấu * sẽ được áp dụng cho mọi kênh đã nạp nhạc và đang dừng."):
            n = QLabel(text)
            n.setObjectName("note")
            v.addWidget(n)

        h = QHBoxLayout()
        b_del = QPushButton("Xóa")
        b_def = QPushButton("*Đặt làm mặc định")
        b_all = QPushButton("*Áp dụng cho tất cả")
        b_cancel = QPushButton("Hủy")
        b_save = QPushButton("Lưu")
        b_save.setObjectName("save")
        for b in (b_del, b_def, b_all, b_cancel, b_save):
            b.setAutoDefault(False)
        h.addWidget(b_del)
        h.addStretch()
        for b in (b_def, b_all, b_cancel, b_save):
            h.addWidget(b)
        b_del.clicked.connect(self.clear_channel)
        b_def.clicked.connect(self.set_defaults)
        b_all.clicked.connect(self.apply_all)
        b_cancel.clicked.connect(self.reject)
        b_save.clicked.connect(self.save)
        v.addLayout(h)
        self.ed_name.setFocus()

    # ----- các mục *
    def starred(self):
        return {"mode": self.seg_mode.value(), "fade_in": self.sp_in.value(), "fade_out": self.sp_out.value()}

    def set_defaults(self):
        self.host.set_channel_defaults(self.starred())
        QMessageBox.information(self, "Đặt làm mặc định",
                                "Đã lưu chế độ bấm, fade-in, fade-out làm mặc định cho kênh mới nạp nhạc.")

    def apply_all(self):
        n = self.host.apply_to_all_channels(self.starred())
        QMessageBox.information(self, "Áp dụng cho tất cả",
                                f"Đã áp dụng chế độ bấm, fade-in, fade-out cho {n} kênh đang dừng.")

    # ----- file / đoạn phát
    def choose_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Chọn nhạc", os.path.dirname(self.path) or
                                              self.host.settings.value("lastDir", ""), AUDIO_FILTER)
        if not path:
            return
        old_name = os.path.splitext(os.path.basename(self.path))[0] if self.path else ""
        self.path = path
        self.duration = read_meta(path)[2]
        self.ed_file.setText(path)
        if not self.ed_name.text().strip() or self.ed_name.text() == old_name:
            self.ed_name.setText(os.path.splitext(os.path.basename(path))[0])
        self.ed_start.setText(fmt_cs(0))
        self.ed_end.setText("")

    def segment_values(self):
        s = parse_time(self.ed_start.text()) or 0
        e = parse_time(self.ed_end.text()) if self.ed_end.text().strip() else 0
        if e is None:
            e = 0
        if self.duration and e >= self.duration - 5:
            e = 0
        if e and s >= e - 100:
            s = max(0, e - 100)
        return s, e

    def edit_segment(self):
        if not self.path or not os.path.isfile(self.path):
            QMessageBox.warning(self, "Đoạn phát", "Kênh chưa có file nhạc.")
            return
        s, e = self.segment_values()
        dlg = SegmentEditor(self, self.ed_name.text() or os.path.basename(self.path), self.path,
                            self.duration, s, e, self.host.pre)
        if dlg.exec():
            s, e = dlg.result_points()
            self.duration = dlg.dur
            self.ed_start.setText(fmt_cs(s))
            self.ed_end.setText(fmt_cs(e) if e else "")

    def clear_channel(self):
        if QMessageBox.question(self, "Xóa", f"Bỏ file và đặt lại Kênh {self.strip.number}?") \
                == QMessageBox.StandardButton.Yes:
            self.strip.clear()
            self.reject()

    def save(self):
        seq = self.key.seq
        if seq not in ("", "-") and seq != self.strip.own_key and not self.host.check_channel_key(self.strip, seq):
            return
        st = self.strip
        if self.path != st.path:
            st.set_file(self.path)
        st.name = self.ed_name.text().strip()
        st.color = next(c[2] for c in COLORS if c[0] == self.seg_color.value())
        st.device = self.cmb_dev.currentData()
        st.mode = self.seg_mode.value()
        st.loop = self.seg_loop.value()
        st.fade_in_s = self.sp_in.value()
        st.fade_out_s = self.sp_out.value()
        st.start_ms, st.end_ms = self.segment_values()
        st.duration = self.duration or st.duration
        st.own_key = seq
        st.apply_device()
        st.refresh()
        st.changed.emit()
        self.host.apply_shortcuts()
        self.accept()
