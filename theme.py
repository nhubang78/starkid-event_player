"""Bảng màu và stylesheet dùng chung cho giao diện Tối / Sáng.

Mọi màu của chương trình lấy từ đây: stylesheet Qt (build_stylesheet), các widget tự vẽ
(đọc T["..."] lúc vẽ) và biểu tượng. Đổi giao diện = set_theme() rồi vẽ lại.
"""
from PySide6.QtGui import QColor, QPalette

PALETTES = {
    "dark": {
        "bg": "#111317", "toolbar": "#171a20", "surface": "#1b1f26", "surface2": "#232831",
        "hover": "#2c323d", "pressed": "#353c49", "border": "#2a2f38", "border_strong": "#3a414d",
        "text": "#e7e9ec", "text_dim": "#9aa3af", "text_faint": "#5b6370",
        "accent": "#3b82f6", "accent_hover": "#2f6fe0", "accent_soft": "#1d3456", "accent_text": "#93c5fd",
        "ok": "#22c55e", "ok_soft": "#123524", "warn": "#f59e0b", "warn_soft": "#3d2c0b",
        "danger": "#ef4444", "danger_soft": "#3e1717",
        "meter_bg": "#0c0e11", "meter_off": "#22272f", "meter_peak": "#f5f5f5",
        "groove": "#0b0d10", "tick": "#454c57",
        "handle_top": "#e8ebef", "handle_bot": "#a9b0ba", "handle_line": "#2a2f38",
        "cart_empty": "#1f232a", "cart_loaded": "#2a303b", "cart_text": "#f1f3f5",
        "go": "#facc15", "go_hover": "#fde047", "go_pressed": "#eab308", "go_text": "#17181a",
        "wave_bg": "#0f1216", "wave_grid": "#20252d", "wave_ruler": "#6b7380", "wave": "#34d399",
        "wave_dim": (15, 18, 22, 185), "list_alt": "#1e232b", "played": "#5f6773",
        "scroll": "#3a414d",
        "cart_play": "#16a34a", "cart_play_text": "#ffffff", "cart_stop": "#f59e0b", "cart_stop_text": "#1a1202",
    },
    "light": {
        "bg": "#eceef2", "toolbar": "#ffffff", "surface": "#ffffff", "surface2": "#f5f6f8",
        "hover": "#e9ecf0", "pressed": "#dde1e7", "border": "#dde1e7", "border_strong": "#c6ccd5",
        "text": "#1b1f24", "text_dim": "#5f6773", "text_faint": "#a5acb6",
        "accent": "#2563eb", "accent_hover": "#1d4ed8", "accent_soft": "#dbe7fe", "accent_text": "#1d4ed8",
        "ok": "#16a34a", "ok_soft": "#dcfce7", "warn": "#d97706", "warn_soft": "#fef3c7",
        "danger": "#dc2626", "danger_soft": "#fee2e2",
        "meter_bg": "#e3e6ea", "meter_off": "#cfd4db", "meter_peak": "#111827",
        "groove": "#c3c9d1", "tick": "#b5bcc6",
        "handle_top": "#ffffff", "handle_bot": "#d3d8df", "handle_line": "#6b7280",
        "cart_empty": "#f3f4f6", "cart_loaded": "#ffffff", "cart_text": "#111827",
        "go": "#fde047", "go_hover": "#facc15", "go_pressed": "#eab308", "go_text": "#17181a",
        "wave_bg": "#ffffff", "wave_grid": "#e5e7eb", "wave_ruler": "#8b929c", "wave": "#22a06b",
        "wave_dim": (236, 238, 242, 190), "list_alt": "#f7f8fa", "played": "#a0a7b1",
        "scroll": "#c6ccd5",
        "cart_play": "#16a34a", "cart_play_text": "#ffffff", "cart_stop": "#fbbf24", "cart_stop_text": "#1a1202",
    },
}

THEME_NAMES = {"dark": "Tối", "light": "Sáng"}

T = dict(PALETTES["dark"])
_current = "dark"

# Màu kênh: (tên, màu chấm, màu nền nút kênh lưu trong dự án — giữ nguyên để tương thích file .evp)
CHANNEL_COLORS = [("Không", "", ""), ("Vàng", "#facc15", "#fff1b8"), ("Đỏ", "#ef4444", "#fecaca"),
                  ("Tím", "#d946ef", "#f5d0fe"), ("Lục lam", "#22b8cf", "#c5f6fa"),
                  ("Lam", "#2563eb", "#c7dbff"), ("Lá", "#22c55e", "#c9f2d6")]


def current():
    return _current


def set_theme(name):
    global _current
    _current = name if name in PALETTES else "dark"
    T.clear()
    T.update(PALETTES[_current])


def is_dark():
    return _current == "dark"


def mix(a, b, t):
    """Trộn màu a với b theo tỉ lệ t (0 = a, 1 = b)."""
    a, b = QColor(a), QColor(b)
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


def channel_dot(stored):
    """Màu chấm (màu đậm) ứng với màu nền kênh đã lưu."""
    for _n, dot, bg in CHANNEL_COLORS:
        if bg and bg.lower() == (stored or "").lower():
            return dot
    return stored


def cart_bg(stored):
    """Màu nền nút kênh theo giao diện hiện tại."""
    if not stored:
        return QColor(T["cart_loaded"])
    if is_dark():
        return mix(T["surface"], channel_dot(stored), 0.42)
    return QColor(stored)


def palette():
    p = QPalette()
    c = lambda k: QColor(T[k])
    R = QPalette.ColorRole
    p.setColor(R.Window, c("bg"))
    p.setColor(R.WindowText, c("text"))
    p.setColor(R.Base, c("surface"))
    p.setColor(R.AlternateBase, c("list_alt"))
    p.setColor(R.Text, c("text"))
    p.setColor(R.Button, c("surface2"))
    p.setColor(R.ButtonText, c("text"))
    p.setColor(R.ToolTipBase, c("surface2"))
    p.setColor(R.ToolTipText, c("text"))
    p.setColor(R.PlaceholderText, c("text_faint"))
    p.setColor(R.Highlight, c("accent"))
    p.setColor(R.HighlightedText, QColor("#ffffff"))
    p.setColor(R.Link, c("accent"))
    p.setColor(R.Mid, c("border"))
    p.setColor(R.Midlight, c("hover"))
    p.setColor(R.Dark, c("border_strong"))
    for role in (R.WindowText, R.Text, R.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c("text_faint"))
    return p


def build_stylesheet():
    return _QSS.format(**{k: v for k, v in T.items() if isinstance(v, str)})


_QSS = """
QMainWindow, QDialog {{ background:{bg}; }}
QWidget {{ color:{text}; font-family:'Segoe UI'; font-size:9pt; }}
QToolTip {{ background:{surface2}; color:{text}; border:1px solid {border_strong}; padding:4px 6px; }}

/* ---------- menu ---------- */
QMenuBar {{ background:{toolbar}; border-bottom:1px solid {border}; padding:1px 4px; }}
QMenuBar::item {{ background:transparent; padding:4px 10px; border-radius:4px; }}
QMenuBar::item:selected {{ background:{hover}; }}
QMenu {{ background:{surface}; border:1px solid {border_strong}; padding:4px; }}
QMenu::item {{ padding:5px 26px 5px 22px; border-radius:4px; }}
QMenu::item:selected {{ background:{accent_soft}; color:{text}; }}
QMenu::item:disabled {{ color:{text_faint}; }}
QMenu::separator {{ height:1px; background:{border}; margin:4px 8px; }}
QMenu::indicator {{ width:12px; height:12px; left:6px; }}

/* ---------- thanh công cụ ---------- */
QWidget#toolbar {{ background:{toolbar}; border-bottom:1px solid {border}; }}
QFrame#tbSep {{ background:{border}; max-width:1px; min-width:1px; }}
QToolButton#tool {{ background:transparent; border:none; border-radius:8px; padding:4px 8px;
                   color:{text_dim}; }}
QToolButton#tool:hover {{ background:{hover}; color:{text}; }}
QToolButton#tool:pressed {{ background:{pressed}; }}
QToolButton#tool:checked {{ background:{accent_soft}; color:{accent_text}; }}
QToolButton#tool:disabled {{ color:{text_faint}; }}
QToolButton#tool[accent="true"]:checked {{ background:{accent}; color:white; }}
QToolButton#tool[danger="true"]:checked {{ background:{danger}; color:white; }}
QToolButton#pageTab {{ background:transparent; border:none; border-radius:8px; padding:6px 14px;
                      color:{text_dim}; font-size:9.5pt; font-weight:600; }}
QToolButton#pageTab:hover {{ background:{hover}; color:{text}; }}
QToolButton#pageTab:checked {{ background:{accent}; color:white; }}
QLabel#pathBar {{ background:{bg}; padding:4px 16px 0 16px; font-size:8.5pt; color:{text_faint}; }}

QScrollArea#bodyScroll {{ background:transparent; border:none; }}
QScrollArea#bodyScroll > QWidget > QWidget {{ background:transparent; }}
QAbstractScrollArea::corner {{ background:transparent; border:none; }}

/* ---------- kênh ---------- */
QLabel#chHead {{ padding-left:4px; color:{text_dim}; font-size:8.5pt; font-weight:600; }}
QLabel#chHead[playing="true"] {{ color:{ok}; }}
QFrame#strip {{ background:{surface}; border:1px solid {border}; border-radius:8px; }}
QFrame#strip[playing="true"] {{ border:1px solid {ok}; }}
QFrame#strip[paused="true"] {{ border:1px solid {warn}; }}
QFrame#strip QLabel {{ background:transparent; }}
QLabel#level {{ color:{text_dim}; font-size:8.5pt; }}
QLabel#time {{ color:{text}; font-family:Consolas; font-size:10pt; }}
QLabel#time[remain="true"] {{ color:{text_dim}; }}
QLabel#time[dim="true"], QLabel#level[dim="true"] {{ color:{text_faint}; }}
QToolButton#more {{ background:{surface2}; border:1px solid {border}; border-radius:5px; color:{text_dim};
                   font-size:6pt; min-width:22px; min-height:18px; }}
QToolButton#more:hover {{ background:{hover}; color:{text}; }}
QToolButton#fileBtn {{ background:transparent; border:none; border-radius:5px; padding:2px; }}
QToolButton#fileBtn:hover {{ background:{hover}; }}
QPushButton#chBtn {{ background:{surface2}; border:1px solid {border}; border-radius:5px; padding:1px;
                    color:{text}; font-size:8.5pt; min-height:20px; }}
QPushButton#chBtn:hover {{ background:{hover}; }}
QPushButton#chBtn:pressed {{ background:{pressed}; }}
QPushButton#chBtn:disabled {{ color:{text_faint}; background:{surface}; border-color:{border}; }}
QPushButton#chBtn[active="true"] {{ background:{warn_soft}; border-color:{warn}; color:{warn}; }}
QToolButton#chIcon {{ border:none; background:transparent; padding:1px; border-radius:4px;
                     color:{text_faint}; font-size:7.5pt; font-weight:600; }}
QToolButton#chIcon[on="true"] {{ color:{ok}; }}
QToolButton#chIcon:hover {{ background:{hover}; }}

/* ---------- fader / thanh trượt ---------- */
QSlider {{ background:transparent; }}
QSlider::groove:vertical {{ width:6px; background:{groove}; border-radius:3px; }}
QSlider::handle:vertical {{ height:16px; width:28px; margin:0 -11px; border-radius:4px;
    border:1px solid {border_strong};
    background:qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {handle_top}, stop:0.46 {handle_bot},
                               stop:0.47 {handle_line}, stop:0.53 {handle_line}, stop:0.54 {handle_top},
                               stop:1 {handle_bot}); }}
QSlider::groove:horizontal {{ height:4px; background:{groove}; border-radius:2px; }}
QSlider::sub-page:horizontal {{ background:{accent}; border-radius:2px; }}
QSlider::sub-page:horizontal:disabled {{ background:{groove}; }}
QSlider::handle:horizontal {{ width:12px; height:12px; margin:-4px 0; border-radius:6px;
                             background:{handle_top}; border:1px solid {border_strong}; }}
QSlider::handle:horizontal:disabled {{ background:{surface2}; border-color:{border}; }}
QSlider#scroll::sub-page:horizontal {{ background:{groove}; }}
QSlider#scroll::handle:horizontal {{ background:{scroll}; border:none; width:30px; border-radius:3px; }}

/* ---------- GO / Master ---------- */
QPushButton#go {{ background:{go}; color:{go_text}; border:none; border-radius:10px;
                 font-size:17pt; font-weight:800; min-height:76px; }}
QPushButton#go:hover {{ background:{go_hover}; }}
QPushButton#go:pressed {{ background:{go_pressed}; }}
QPushButton#go:disabled {{ background:{surface2}; color:{text_faint}; }}
QLabel#sideHead {{ color:{text_dim}; font-size:8.5pt; font-weight:600; }}
QLabel#goHint {{ color:{text_faint}; font-size:8pt; }}

/* ---------- playlist ---------- */
QFrame#nowPlaying {{ background:{surface}; border:1px solid {border}; border-radius:10px; }}
QFrame#nowPlaying QLabel {{ background:transparent; }}
QLabel#bigTitle {{ font-size:17pt; font-weight:700; }}
QLabel#artist {{ font-size:10pt; color:{text_dim}; }}
QLabel#timeBig {{ font-size:24pt; font-weight:700; font-family:Consolas; color:{text}; }}
QLabel#timeBig[warn="red"] {{ color:{danger}; }}
QLabel#timeBig[warn="dim"] {{ color:{danger_soft}; }}
QLabel#next {{ font-size:9.5pt; color:{warn}; }}
QLabel#fieldLabel {{ color:{text_dim}; font-size:8.5pt; }}
QPushButton#transport {{ font-size:10pt; font-weight:700; min-width:60px; min-height:34px; padding:4px 16px;
                        border-radius:8px; }}
QPushButton#transport[kind="play"] {{ background:{ok_soft}; border:1px solid {ok}; color:{ok}; min-width:170px; }}
QPushButton#transport[kind="play"]:hover {{ background:{ok}; color:white; }}
QPushButton#transport[kind="stop"] {{ background:{danger_soft}; border:1px solid {danger}; color:{danger}; }}
QPushButton#transport[kind="stop"]:hover {{ background:{danger}; color:white; }}

/* ---------- nút / ô nhập chung ---------- */
QPushButton {{ background:{surface2}; color:{text}; border:1px solid {border_strong}; border-radius:6px;
              padding:5px 12px; min-height:18px; }}
QPushButton:hover {{ background:{hover}; }}
QPushButton:pressed {{ background:{pressed}; }}
QPushButton:disabled {{ color:{text_faint}; border-color:{border}; }}
QPushButton:default {{ border-color:{accent}; }}
QPushButton#save {{ background:{accent}; color:white; border:1px solid {accent}; min-width:100px; }}
QPushButton#save:hover {{ background:{accent_hover}; }}
QPushButton#keyEdit {{ background:{surface}; border:1px solid {border_strong}; border-radius:6px; padding:4px;
                      font-family:Consolas; font-size:10pt; min-width:170px; }}
QPushButton#keyEdit:focus {{ border:1px solid {accent}; background:{accent_soft}; }}
QToolButton {{ color:{text}; }}
QToolButton#corner {{ background:{surface2}; border:1px solid {border_strong}; border-radius:6px;
                     padding:2px 8px; margin:2px; font-weight:700; }}
QToolButton#corner:hover {{ background:{hover}; }}
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {{ background:{surface}; color:{text};
    border:1px solid {border_strong}; border-radius:6px; padding:4px 8px; min-height:18px;
    selection-background-color:{accent}; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus {{ border:1px solid {accent}; }}
QLineEdit[readOnly="true"] {{ background:{surface2}; color:{text_dim}; }}
QLineEdit#time {{ font-family:Consolas; font-size:10.5pt; min-width:130px; }}
QComboBox::drop-down {{ border:none; width:22px; }}
QComboBox QAbstractItemView {{ background:{surface}; border:1px solid {border_strong};
    selection-background-color:{accent_soft}; selection-color:{text}; outline:0; }}
QCheckBox::indicator, QRadioButton::indicator {{ width:15px; height:15px; }}

/* ---------- danh sách / tab ---------- */
QTreeWidget, QTreeView, QListView {{ background:{surface}; alternate-background-color:{list_alt};
    border:1px solid {border}; border-radius:8px; outline:0; }}
QTreeWidget::item {{ padding:4px 2px; border:none; }}
QTreeWidget::item:hover {{ background:{hover}; }}
QTreeWidget::item:selected {{ background:{accent}; color:white; }}
QHeaderView {{ background:transparent; }}
QHeaderView::section {{ background:{surface2}; color:{text_dim}; border:none; border-bottom:1px solid {border};
    padding:6px 6px; font-weight:600; }}
QTabWidget::pane {{ border:none; top:-1px; }}
QTabBar::tab {{ background:transparent; color:{text_dim}; padding:6px 14px; margin-right:2px;
    border:none; border-bottom:2px solid transparent; }}
QTabBar::tab:hover {{ color:{text}; }}
QTabBar::tab:selected {{ color:{text}; border-bottom:2px solid {accent}; font-weight:600; }}

/* ---------- bảng chỉnh bài ---------- */
QFrame#deckEditor {{ background:{surface}; border:1px solid {border}; border-radius:12px; }}
QFrame#deckEditor QLabel {{ background:transparent; }}
QLabel#deTitle {{ font-size:13pt; font-weight:700; color:{text}; }}
QLabel#deSub {{ color:{text_dim}; font-size:9pt; }}
QLabel#deCap {{ color:{text_dim}; font-size:7.5pt; font-weight:700; letter-spacing:1px; }}
QLabel#deTime {{ font-family:Consolas; font-size:17pt; font-weight:700; color:{text}; }}
QLabel#deTime[kind="remain"] {{ color:{warn}; }}
QLabel#deBpm {{ font-family:Consolas; font-size:14pt; font-weight:700; color:{warn}; }}
QLabel#deZoom {{ font-family:Consolas; font-weight:700; color:{warn}; padding:0 4px; }}
QLabel#deHint {{ color:{text_faint}; font-size:8pt; }}
QToolButton#deFold {{ border:none; background:transparent; color:{text_dim}; font-size:12pt; padding:0 4px; }}
QToolButton#deFold:hover {{ color:{text}; }}
QToolButton#deLink {{ border:none; background:transparent; color:{accent_text}; text-decoration:underline; }}
QPushButton#deBtn, QPushButton#dePlay {{ padding:4px 9px; min-height:22px; border-radius:7px; }}
QPushButton#deBtn:checked {{ background:{accent}; border-color:{accent}; color:white; }}
QPushButton#dePlay[on="true"] {{ background:{warn}; border-color:{warn}; }}
QPushButton#deCue {{ padding:3px 9px; min-height:20px; border-radius:7px; background:{surface2};
    font-family:Consolas; border:1px solid {ok}; color:{text}; }}
QPushButton#deCue:hover {{ background:{ok_soft}; }}
QPushButton#deGrid {{ padding:2px 10px; min-height:16px; border-radius:6px; font-size:8.5pt; font-weight:700;
    background:{wave_bg}; color:{warn}; border:1px solid {warn}; }}
QPushButton#deGrid:checked {{ background:{warn}; color:#1a1202; }}
QWidget#beatScope {{ background:{bg}; }}
QFrame#strip[selected="true"] {{ border:2px solid {accent}; }}

/* ---------- âm thanh (đo, chống hú) ---------- */
QFrame#scCard {{ background:{surface}; border:1px solid {border}; border-radius:10px; }}
QFrame#scCard QLabel {{ background:transparent; }}
QLabel#scValue {{ font-family:Consolas; font-size:10pt; color:{text}; }}
QLabel#scStatus {{ font-size:13pt; font-weight:700; color:{text_dim}; }}
QLabel#scStatus[state="ok"] {{ color:{ok}; }}
QLabel#scStatus[state="warn"] {{ color:{warn}; }}
QLabel#scStatus[state="bad"] {{ color:{danger}; }}
QLabel#scStatus[state="idle"] {{ color:{text_faint}; }}
QLabel#scAlert {{ background:{surface2}; color:{text_dim}; border-radius:8px; padding:8px; font-weight:700; }}
QLabel#scAlert[on="true"] {{ background:{danger}; color:white; font-size:13pt; }}
QToolButton#pageTab[alert="true"] {{ background:{danger}; color:white; }}

/* ---------- hướng dẫn ---------- */
QListWidget#guideNav {{ background:{surface}; border:1px solid {border}; border-radius:10px; padding:6px;
    outline:0; font-size:10pt; }}
QListWidget#guideNav::item {{ padding:6px 10px; border-radius:6px; color:{text_dim}; }}
QListWidget#guideNav::item:hover {{ background:{hover}; color:{text}; }}
QListWidget#guideNav::item:selected {{ background:{accent}; color:white; }}
QTextBrowser#guideView {{ background:{surface}; border:1px solid {border}; border-radius:10px; }}

/* ---------- hộp thoại ---------- */
QLabel#title {{ font-size:13pt; font-weight:700; }}
QLabel#note, QLabel#desc, QLabel#hint, QLabel#info {{ color:{text_dim}; font-size:8.5pt; }}
QLabel#warnNote {{ color:{warn}; }}
QFrame#seg {{ background:{surface2}; border:1px solid {border}; border-radius:8px; }}
QFrame#seg QPushButton {{ background:transparent; border:none; border-radius:6px; padding:4px 14px; }}
QFrame#seg QPushButton:hover {{ background:{hover}; }}
QFrame#seg QPushButton:checked {{ background:{accent}; color:white; }}

/* ---------- thanh trạng thái / cuộn ---------- */
QStatusBar {{ background:{toolbar}; color:{text_dim}; border-top:1px solid {border}; }}
QStatusBar::item {{ border:none; }}
QLabel#clock {{ font-family:Consolas; font-size:10pt; color:{text}; padding-right:10px; }}
QLabel#version {{ color:{text_faint}; padding-right:12px; }}
QScrollBar:vertical {{ background:transparent; width:10px; margin:2px; }}
QScrollBar::handle:vertical {{ background:{scroll}; border-radius:3px; min-height:30px; }}
QScrollBar:horizontal {{ background:transparent; height:10px; margin:2px; }}
QScrollBar::handle:horizontal {{ background:{scroll}; border-radius:3px; min-width:30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width:0; height:0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background:transparent; }}
QMessageBox QLabel {{ color:{text}; }}
"""
