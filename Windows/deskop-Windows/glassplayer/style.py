"""Hoja de estilo (QSS) generada a partir del tema del usuario."""
from .settings import rgb_of


def build_qss(th):
    a, ar, t, top, bot = th["accent"], rgb_of(th["accent"]), th["text"], th["bg_top"], th["bg_bottom"]
    return f"""
QWidget {{ color: {t}; font-family: "Segoe UI", "Inter", "Ubuntu", sans-serif; font-size: 13px; }}
QMainWindow, QWidget#root {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 {top}, stop:1 {bot}); }}
QLabel {{ background: transparent; }}
QAbstractScrollArea {{ background: transparent; border: none; }}
QAbstractScrollArea > QWidget, QAbstractScrollArea > QWidget > QWidget {{ background: transparent; }}
QToolTip {{ background: #1b1b1f; color: #ffffff; border: 1px solid rgba(255,255,255,0.2); padding: 4px 8px; }}

QFrame#sidebar {{ background: rgba(0,0,0,0.30); border-right: 1px solid rgba(255,255,255,0.08); }}
QFrame#transport {{ background: rgba(0,0,0,0.38); border-top: 1px solid rgba(255,255,255,0.10); }}

QLabel[role="logo"] {{ font-size: 19px; font-weight: 700; padding: 4px 6px; }}
QLabel[role="caption"] {{ font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.55); letter-spacing: 1px; }}
QLabel[role="crumb"] {{ font-size: 11px; font-weight: 700; color: rgba(255,255,255,0.55); letter-spacing: 1px; }}
QLabel[role="title"] {{ font-size: 30px; font-weight: 800; }}
QLabel[role="muted"] {{ color: rgba(255,255,255,0.62); }}
QLabel[role="status"] {{ color: rgba(255,255,255,0.72); padding: 2px 0 6px 2px; }}
QLabel[role="now"] {{ font-weight: 700; font-size: 14px; }}

QPushButton {{ background: transparent; border: none; }}
QPushButton[kind="nav"] {{ text-align: left; padding: 9px 12px; border-radius: 9px; font-weight: 600; }}
QPushButton[kind="nav"]:hover {{ background: rgba(255,255,255,0.08); }}
QPushButton[kind="nav"]:checked {{ background: rgba({ar},0.24); color: {a}; }}
QPushButton[kind="ghost"], QPushButton[kind="primary"] {{ border-radius: 17px; padding: 8px 18px; font-weight: 600; }}
QPushButton[kind="ghost"] {{ background: rgba(0,0,0,0.28); border: 1px solid rgba(255,255,255,0.30); }}
QPushButton[kind="ghost"]:hover {{ background: rgba(0,0,0,0.42); }}
QPushButton[kind="ghost"]:checked {{ background: {a}; border-color: {a}; color: #ffffff; }}
QPushButton[kind="primary"] {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ffffff, stop:1 #d8e0e8);
                              color: #0a1018; }}
QPushButton[kind="primary"]:hover {{ background: #ffffff; }}
QPushButton[kind="icon"] {{ border-radius: 17px; min-width: 34px; max-width: 34px; min-height: 34px; max-height: 34px;
                           font-size: 16px; }}
QPushButton[kind="icon"]:hover {{ background: rgba(255,255,255,0.12); }}
QPushButton[kind="play"] {{ background: #ffffff; color: #0a1018; border-radius: 21px; min-width: 42px; max-width: 42px;
                           min-height: 42px; max-height: 42px; font-size: 17px; }}
QPushButton[kind="play"]:hover {{ background: rgba(255,255,255,0.88); }}
QPushButton[kind="heart"] {{ font-size: 17px; color: rgba(255,255,255,0.65); border-radius: 16px; min-width: 32px;
                            max-width: 32px; min-height: 32px; max-height: 32px; }}
QPushButton[kind="heart"]:hover {{ color: {a}; background: rgba(255,255,255,0.10); }}
QPushButton[kind="heart"][on="true"] {{ color: {a}; }}
QPushButton[kind="star"] {{ background: rgba(0,0,0,0.28); color: rgba(255,255,255,0.85); border-radius: 14px;
                           min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px; font-size: 15px; }}
QPushButton[kind="star"]:hover {{ background: rgba(0,0,0,0.45); }}
QPushButton[kind="star"][on="true"] {{ color: #ffd60a; }}
QPushButton[kind="swatch"] {{ border-radius: 14px; min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
                             border: 2px solid rgba(255,255,255,0.35); }}
QPushButton[kind="swatch"]:hover {{ border-color: #ffffff; }}

QFrame#row {{ border-radius: 10px; background: transparent; }}
QFrame#row:hover {{ background: rgba(255,255,255,0.08); }}
QFrame#row[playing="true"] {{ background: rgba({ar},0.22); }}
QFrame#row[playing="true"] QLabel[role="rtitle"] {{ color: {a}; }}
QLabel[role="rtitle"] {{ font-weight: 600; font-size: 14px; }}

QLineEdit {{ background: rgba(0,0,0,0.30); border: 1px solid rgba(255,255,255,0.22); border-radius: 17px;
            padding: 7px 14px; selection-background-color: {a}; }}
QLineEdit:focus {{ border-color: {a}; }}

QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.25); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {a}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: #ffffff; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.25); border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.40); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: #1c1c20; border: 1px solid rgba(255,255,255,0.14); border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 7px 22px; border-radius: 5px; color: #f2f4f7; }}
QMenu::item:selected {{ background: rgba({ar},0.35); }}
QMenu::separator {{ height: 1px; background: rgba(255,255,255,0.12); margin: 4px 8px; }}
QDialog, QMessageBox, QInputDialog {{ background: #1c1c20; }}
QDialog QPushButton, QMessageBox QPushButton, QInputDialog QPushButton {{ background: rgba(255,255,255,0.12);
    border-radius: 8px; padding: 6px 16px; min-width: 70px; }}
QDialog QPushButton:hover, QMessageBox QPushButton:hover {{ background: rgba(255,255,255,0.2); }}
"""
