"""Long View: màn hình lớn cho người điều khiển / sân khấu.

Hai khung ĐANG PHÁT và TIẾP THEO, thời gian còn lại cỡ lớn, thanh tiến trình, các nguồn đang phát
cùng lúc, lời nhắn chữ lớn và hàng nút điều khiển (Trước, GO, Sau, Dừng hết).
Luôn dùng nền tối (độc lập với giao diện Tối/Sáng của cửa sổ chính) để dễ nhìn trong hội trường.
"""
from PySide6.QtCore import QRectF, Qt, QTime
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QSizePolicy, QVBoxLayout, QWidget)

C = {"bg": "#0b0d10", "card": "#15181d", "card2": "#1b1f26", "border": "#262b33", "text": "#f3f4f6",
     "dim": "#8b93a1", "faint": "#4b525e", "green": "#22c55e", "amber": "#f59e0b", "red": "#ef4444",
     "blue": "#60a5fa"}

STYLE = f"""
QWidget#longView {{ background:{C['bg']}; }}
QLabel#lvTitle, QLabel#lvName {{ color:{C['text']}; font-weight:700; }}
QFrame#lvCard {{ background:{C['card']}; border:2px solid {C['border']}; border-radius:16px; }}
QFrame#lvCard[state="play"] {{ border-color:{C['green']}; }}
QFrame#lvCard[state="pause"] {{ border-color:{C['amber']}; }}
QFrame#lvCard[state="next"] {{ border-color:#3b3524; }}
QLabel#lvCaption {{ color:{C['dim']}; font-weight:700; letter-spacing:3px; }}
QLabel#lvBadge {{ color:{C['bg']}; background:{C['dim']}; border-radius:6px; padding:2px 10px; font-weight:700; }}
QLabel#lvBadge[state="play"] {{ background:{C['green']}; }}
QLabel#lvBadge[state="pause"] {{ background:{C['amber']}; }}
QLabel#lvBadge[state="next"] {{ background:{C['amber']}; }}
QLabel#lvBadge[state="idle"] {{ background:{C['faint']}; color:{C['text']}; }}
QLabel#lvDim {{ color:{C['dim']}; }}
QLabel[sz="oSrc"] {{ font-weight:700; }}
QLabel#lvTime {{ font-family:Consolas; font-weight:700; color:{C['green']}; }}
QLabel#lvTime[state="idle"] {{ color:{C['faint']}; }}
QLabel#lvTime[state="pause"] {{ color:{C['amber']}; }}
QLabel#lvTime[state="warn"] {{ color:{C['red']}; }}
QLabel#lvTime[state="warn2"] {{ color:#5b1b1b; }}
QLabel#lvNextTime {{ font-family:Consolas; font-weight:700; color:{C['text']}; }}
QLabel#lvClock {{ font-family:Consolas; font-weight:700; color:{C['blue']}; }}
QLabel#lvBrand {{ color:{C['dim']}; font-weight:700; letter-spacing:2px; }}
QLabel#lvMsg {{ background:{C['amber']}; color:#111; border-radius:12px; padding:10px 24px; font-weight:800; }}
QLabel#lvLock {{ background:#7f1d1d; color:#fecaca; border-radius:6px; padding:2px 10px; font-weight:700; }}
QFrame#lvOther {{ background:{C['card2']}; border-radius:10px; }}
QPushButton#lvBtn {{ background:{C['card2']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:12px;
                    font-size:14pt; font-weight:600; padding:8px 22px; min-height:56px; }}
QPushButton#lvBtn:hover {{ background:#232832; }}
QPushButton#lvBtn:pressed {{ background:#2b313c; }}
QPushButton#lvBtn:disabled {{ color:{C['faint']}; background:{C['card']}; }}
QPushButton#lvGo {{ background:{C['green']}; color:#06210f; border:none; border-radius:12px;
                   font-size:24pt; font-weight:900; min-height:56px; padding:8px 30px; }}
QPushButton#lvGo:hover {{ background:#34d06c; }}
QPushButton#lvGo:pressed {{ background:#16a34a; }}
QPushButton#lvGo:disabled {{ background:#1d3a28; color:#3f6b4f; }}
QPushButton#lvStop {{ background:#3a1414; color:#fecaca; border:1px solid {C['red']}; border-radius:12px;
                     font-size:14pt; font-weight:700; padding:8px 22px; min-height:56px; }}
QPushButton#lvStop:hover {{ background:{C['red']}; color:white; }}
QPushButton#lvStop:disabled {{ background:{C['card']}; color:{C['faint']}; border-color:{C['border']}; }}
QLineEdit#lvInput {{ background:{C['card']}; color:{C['text']}; border:1px solid {C['border']}; border-radius:12px;
                    padding:8px 16px; font-size:13pt; min-height:56px; selection-background-color:{C['amber']}; }}
QLineEdit#lvInput:focus {{ border-color:{C['amber']}; }}
"""


def big_time(ms):
    s = max(0, int(ms + 999) // 1000)         # làm tròn lên: còn 0,4 giây vẫn hiện 0:01
    h, m, s = s // 3600, s % 3600 // 60, s % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _set_state(w, state):
    if w.property("state") != state:
        w.setProperty("state", state)
        w.style().unpolish(w)
        w.style().polish(w)


# cỡ chữ (px ở cửa sổ 1280x760) theo thuộc tính "sz" của nhãn; nhân theo kích thước cửa sổ
SIZES = {"clock": 40, "brand": 13, "caption": 15, "badge": 14, "sub": 18, "titleNow": 54, "titleNext": 40,
         "timeNow": 120, "info": 18, "timeNext": 54, "pl": 17, "msg": 34, "oSrc": 15, "oName": 22, "oTime": 28}


def _sz(label, key):
    label.setProperty("sz", key)
    return label


class Progress(QWidget):
    def __init__(self):
        super().__init__()
        self.frac, self.color = 0.0, QColor(C["green"])
        self.setFixedHeight(12)

    def set(self, frac, color):
        frac = max(0.0, min(1.0, frac))
        if abs(frac - self.frac) > 0.0005 or color != self.color.name():
            self.frac, self.color = frac, QColor(color)
            self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        r = QRectF(self.rect())
        p.setBrush(QColor("#0a0c0f"))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        if self.frac > 0:
            p.setBrush(self.color)
            p.drawRoundedRect(QRectF(0, 0, max(r.height(), r.width() * self.frac), r.height()),
                              r.height() / 2, r.height() / 2)


class LongView(QWidget):
    def __init__(self, host, app_name):
        super().__init__(None, Qt.WindowType.Window)
        self.host = host
        self.setObjectName("longView")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(f"Long View — {app_name}")
        self.resize(1280, 760)
        self._blink_state = None

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 16, 24, 20)
        root.setSpacing(14)

        # ---- đầu trang: thương hiệu, trạng thái khóa, đồng hồ
        top = QHBoxLayout()
        self.brand = QLabel(app_name.upper() + "  ·  LONG VIEW")
        self.brand.setObjectName("lvBrand")
        _sz(self.brand, "brand")
        top.addWidget(self.brand)
        self.lock = QLabel("ĐÃ KHÓA")
        self.lock.setObjectName("lvLock")
        top.addWidget(self.lock)
        top.addStretch()
        self.clock = QLabel()
        self.clock.setObjectName("lvClock")
        _sz(self.clock, "clock")
        top.addWidget(self.clock)
        root.addLayout(top)

        # ---- lời nhắn
        self.msg = QLabel()
        self.msg.setObjectName("lvMsg")
        _sz(self.msg, "msg")
        self.msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg.setWordWrap(True)
        self.msg.hide()
        root.addWidget(self.msg)

        # ---- hai khung
        cards = QHBoxLayout()
        cards.setSpacing(18)
        self.now = self._card()
        self.nxt = self._card()
        cards.addWidget(self.now["frame"], 3)
        cards.addWidget(self.nxt["frame"], 2)
        root.addLayout(cards, 1)

        # khung ĐANG PHÁT: thêm thời gian, tiến trình, danh sách nguồn khác
        n = self.now
        n["caption"].setText("ĐANG PHÁT")
        times = QHBoxLayout()
        n["time"].setObjectName("lvTime")
        _sz(n["time"], "timeNow")
        _sz(n["title"], "titleNow")
        times.addWidget(n["time"])
        times.addStretch()
        n["info"] = QLabel()
        n["info"].setObjectName("lvDim")
        _sz(n["info"], "info")
        n["info"].setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom)
        times.addWidget(n["info"])
        n["lay"].addLayout(times)
        n["bar"] = Progress()
        n["lay"].addWidget(n["bar"])
        n["others_box"] = QFrame()
        n["others_box"].setObjectName("lvOther")
        n["others"] = QGridLayout(n["others_box"])
        n["others"].setContentsMargins(14, 8, 14, 8)
        n["others"].setHorizontalSpacing(16)
        n["others"].setVerticalSpacing(4)
        n["other_rows"] = []
        n["lay"].addWidget(n["others_box"])

        x = self.nxt
        x["caption"].setText("TIẾP THEO")
        x["time"].setObjectName("lvNextTime")
        _sz(x["time"], "timeNext")
        _sz(x["title"], "titleNext")
        x["lay"].addWidget(x["time"])
        x["pl"] = QLabel()
        x["pl"].setObjectName("lvDim")
        _sz(x["pl"], "pl")
        x["pl"].setWordWrap(True)
        x["lay"].addSpacing(6)
        x["lay"].addWidget(x["pl"])

        # ---- hàng điều khiển
        ctl = QHBoxLayout()
        ctl.setSpacing(12)
        self.b_prev = QPushButton("◀  Trước")
        self.b_go = QPushButton("GO")
        self.b_next = QPushButton("Sau  ▶")
        self.b_stop = QPushButton("■  Dừng hết")
        self.b_prev.setObjectName("lvBtn")
        self.b_next.setObjectName("lvBtn")
        self.b_go.setObjectName("lvGo")
        self.b_stop.setObjectName("lvStop")
        self.b_prev.setToolTip("Lùi con trỏ GO (↑)")
        self.b_next.setToolTip("Tiến con trỏ GO (↓)")
        self.b_go.setToolTip("Phát kênh kế tiếp (Space)")
        self.b_stop.setToolTip("Dừng tất cả (Esc). Bấm 2 lần = dừng ngay")
        for b in (self.b_prev, self.b_go, self.b_next, self.b_stop):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
        self.b_go.setMinimumWidth(260)
        self.b_prev.clicked.connect(lambda: self.host.go_cursor(-1))
        self.b_next.clicked.connect(lambda: self.host.go_cursor(1))
        self.b_go.clicked.connect(self.host.go)
        self.b_stop.clicked.connect(self.host.stop_all)
        ctl.addWidget(self.b_prev)
        ctl.addWidget(self.b_go, 2)
        ctl.addWidget(self.b_next)
        ctl.addWidget(self.b_stop)
        ctl.addSpacing(8)
        self.input = QLineEdit()
        self.input.setObjectName("lvInput")
        self.input.setPlaceholderText("Lời nhắn hiện to trên màn hình... (Enter để hiện)")
        self.input.returnPressed.connect(self.show_message)
        ctl.addWidget(self.input, 3)
        self.b_msg_clear = QPushButton("Xóa")
        self.b_msg_clear.setObjectName("lvBtn")
        self.b_msg_clear.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.b_msg_clear.clicked.connect(self.clear_message)
        ctl.addWidget(self.b_msg_clear)
        root.addLayout(ctl)
        self._scale()

    # ------------------------------------------------------------ dựng khung
    def _card(self):
        f = QFrame()
        f.setObjectName("lvCard")
        f.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        lay = QVBoxLayout(f)
        lay.setContentsMargins(28, 20, 28, 22)
        lay.setSpacing(8)
        head = QHBoxLayout()
        cap = QLabel()
        cap.setObjectName("lvCaption")
        _sz(cap, "caption")
        head.addWidget(cap)
        head.addStretch()
        badge = QLabel()
        badge.setObjectName("lvBadge")
        _sz(badge, "badge")
        head.addWidget(badge)
        lay.addLayout(head)
        title = QLabel()
        title.setObjectName("lvTitle")
        title.setWordWrap(True)
        title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        lay.addWidget(title, 1)
        sub = QLabel()
        sub.setObjectName("lvDim")
        _sz(sub, "sub")
        lay.addWidget(sub)
        t = QLabel()
        return {"frame": f, "lay": lay, "caption": cap, "badge": badge, "title": title, "sub": sub, "time": t}

    def _scale(self):
        k = min(max(400, self.height()) / 760, max(700, self.width()) / 1280)
        css = "".join(f"QLabel[sz=\"{key}\"] {{ font-size:{max(8, int(v * k))}px; }}\n" for key, v in SIZES.items())
        self.setStyleSheet(STYLE + css)
        self.now["bar"].setFixedHeight(max(8, int(12 * k)))

    def resizeEvent(self, e):
        self._scale()
        super().resizeEvent(e)

    # ------------------------------------------------------------ lời nhắn
    def show_message(self):
        text = self.input.text().strip()
        self.msg.setText(text)
        self.msg.setVisible(bool(text))

    def clear_message(self):
        self.input.clear()
        self.msg.clear()
        self.msg.hide()

    # ------------------------------------------------------------ phím
    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_F11:
            self.showNormal() if self.isFullScreen() else self.showFullScreen()
            return
        if k == Qt.Key.Key_F2:
            self.close()
            return
        if self.host.locked:
            return
        if k == Qt.Key.Key_Space:
            self.host.go()
        elif k == Qt.Key.Key_Escape:
            self.host.stop_all()
        elif k == Qt.Key.Key_Up:
            self.host.go_cursor(-1)
        elif k == Qt.Key.Key_Down:
            self.host.go_cursor(1)
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------ dữ liệu
    def _sources(self):
        h = self.host
        out = []
        for s in h.strips:
            if s.deck.is_playing() or s.deck.is_paused():
                out.append({"obj": s, "src": f"KÊNH {s.number}", "title": s.display_name(),
                            "rem": s.remaining_ms(), "dur": s.seg_len(),
                            "pos": s.deck.position() - s.start_ms,
                            "paused": s.deck.is_paused() or s.deck.fading_out()})
        np = h.playlist.now_playing()
        if np:
            d = h.playlist.deck
            out.append({"obj": h.playlist, "src": "PLAYLIST", "title": np[0], "rem": np[1], "dur": np[2],
                        "pos": np[2] - np[1], "paused": d.is_paused() or d.fading_out()})
        return out

    def refresh(self, warn_ms):
        h = self.host
        self.clock.setText(QTime.currentTime().toString("HH:mm:ss"))
        self.lock.setVisible(h.locked)
        for b in (self.b_prev, self.b_go, self.b_next, self.b_stop):
            b.setEnabled(not h.locked)

        # ---- ĐANG PHÁT
        src = self._sources()
        n = self.now
        main = next((x for x in src if x["obj"] is h.last_started), None) or \
            (min(src, key=lambda x: x["rem"]) if src else None)
        if main:
            state = "pause" if main["paused"] else "play"
            _set_state(n["frame"], state)
            _set_state(n["badge"], state)
            n["badge"].setText(main["src"] + ("  ·  TẠM DỪNG" if main["obj"].deck.is_paused()
                                              else "  ·  ĐANG DỪNG" if main["paused"] else ""))
            n["badge"].show()
            n["title"].setText(main["title"])
            n["sub"].setText("")
            warn = main["rem"] <= warn_ms and not main["paused"]
            blink = QTime.currentTime().msec() < 500
            _set_state(n["time"], ("warn" if blink else "warn2") if warn else state)
            n["time"].setText("-" + big_time(main["rem"]))
            n["info"].setText(f"{big_time(max(0, main['pos']))}  /  {big_time(main['dur'])}")
            col = C["red"] if warn else C["amber"] if main["paused"] else C["green"]
            n["bar"].set(main["pos"] / max(1, main["dur"]), col)
        else:
            _set_state(n["frame"], "idle")
            _set_state(n["badge"], "idle")
            n["badge"].hide()
            n["title"].setText("Chưa phát")
            n["sub"].setText("Bấm GO hoặc Space để phát kênh kế tiếp")
            _set_state(n["time"], "idle")
            n["time"].setText("--:--")
            n["info"].setText("")
            n["bar"].set(0, C["green"])
        others = [x for x in src if x is not main]
        self._fill_others(others, warn_ms)

        # ---- TIẾP THEO
        x = self.nxt
        _set_state(x["frame"], "next")
        nums = h.loaded_numbers()
        if nums:
            h.update_go()
            s = h.strips[h.go_next - 1]
            _set_state(x["badge"], "next")
            x["badge"].setText(f"GO  ·  KÊNH {s.number}")
            x["badge"].show()
            x["title"].setText(s.display_name())
            x["sub"].setText("Thời lượng")
            x["time"].setText(big_time(s.seg_len()))
            self.b_go.setText(f"GO  {s.number}")
            self.b_go.setEnabled(not h.locked)
        else:
            x["badge"].hide()
            x["title"].setText("Chưa có kênh nào có nhạc")
            x["sub"].setText("")
            x["time"].setText("")
            self.b_go.setText("GO")
            self.b_go.setEnabled(False)
        pl = h.playlist.next_candidate() if h.playlist.is_active() or h.playlist.deck.is_paused() else None
        if pl:
            t = pl[0].tracks.get(pl[1])
            x["pl"].setText(f"Playlist kế tiếp:  {t.title}  [{big_time(t.duration)}]" if t else "")
        else:
            x["pl"].setText("")

    def _fill_others(self, others, warn_ms):
        n = self.now
        rows = n["other_rows"]
        while len(rows) < len(others):
            r = len(rows)
            src, name, t = QLabel(), QLabel(), QLabel()
            src.setObjectName("lvDim")
            name.setObjectName("lvName")
            t.setObjectName("lvTime")
            _sz(src, "oSrc")
            _sz(name, "oName")
            _sz(t, "oTime")
            t.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            n["others"].addWidget(src, r, 0)
            n["others"].addWidget(name, r, 1)
            n["others"].addWidget(t, r, 2)
            n["others"].setColumnStretch(1, 1)
            rows.append((src, name, t))
        for i, (src, name, t) in enumerate(rows):
            vis = i < len(others)
            for w in (src, name, t):
                w.setVisible(vis)
            if not vis:
                continue
            o = others[i]
            src.setText(o["src"])
            name.setText(o["title"])
            t.setText("-" + big_time(o["rem"]))
            warn = o["rem"] <= warn_ms and not o["paused"]
            _set_state(t, "warn" if warn else "pause" if o["paused"] else "play")
        n["others_box"].setVisible(bool(others))
