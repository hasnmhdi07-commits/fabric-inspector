"""Fabric Inspector - floating bubble app (Windows, PyQt6), v2 "fern" design.

 - A round pick-glass bubble floats on top of all windows. Drag it anywhere; it snaps to the nearest
   screen edge. Click = open/close the panel. Right-click = quick menu. The dot on its rim shows the
   last verdict.
 - Panel: [Select screen area] or [Upload photo] -> verdict first, then the annotated image and one card
   per finding; click a card to see likely causes, remedy and prevention (rule-based knowledge base).
Run:  venv\\Scripts\\pythonw.exe -m src.app.main     (from C:\\thesis)  or double-click run_app.bat
"""
import sys, time, html
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QPoint, QPointF, QRect, QRectF, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPalette,
                         QPen, QPixmap, QRadialGradient)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QFrame,
                             QGroupBox, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QSlider,
                             QToolButton, QVBoxLayout, QWidget, QScrollArea, QSizePolicy)

from src.app.engine import Analyzer, Settings, Report, DEFAULT_MODEL, ROOT, report_to_text
from src.app.report_html import report_html, SEV_COLOR
from src.app.verdict import SEV_LABEL

APP, ORG = "Inspector", "ThesisFabric"

# ---------------------------------------------------------------- fern theme (spec v2, section 6)
PAPER, SURFACE, INK, INK2, LINE = "#ffffff", "#f6f9f5", "#15211a", "#4d5c52", "#dde6da"
FERN, SWATCH, SOFT, CHALK, CRIT = "#2f7d3b", "#63b96c", "#e5f3e6", "#e7b53a", "#c23a3a"
F_BODY, F_MONO = "Segoe UI", "Consolas"

QSS = f"""
QWidget {{ color: {INK}; font-family: '{F_BODY}'; font-size: 9.5pt; }}
#panel, #scrollBody {{ background: {SURFACE}; }}
QScrollArea {{ border: none; background: {SURFACE}; }}
#title {{ font-size: 11pt; font-weight: 700; }}
#model, #sub, #pts {{ font-family: '{F_MONO}'; font-size: 8pt; color: {INK2}; }}
#pts {{ font-weight: 700; color: {INK}; }}
#muted {{ color: {INK2}; font-size: 8.5pt; }}
#h4 {{ color: {INK2}; font-size: 7.5pt; font-weight: 700; letter-spacing: 1px; }}
QPushButton {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 8px; padding: 8px 10px; font-weight: 600; }}
QPushButton:hover {{ border-color: {SWATCH}; }}
QPushButton:disabled {{ color: #9aa59d; }}
QPushButton#primary {{ background: {FERN}; color: #ffffff; border-color: {FERN}; }}
QPushButton#primary:hover {{ background: #276b32; }}
QPushButton#primary:disabled {{ background: #9dc3a3; border-color: #9dc3a3; color: #ffffff; }}
QPushButton#tab {{ border-radius: 12px; padding: 3px 10px; font-weight: 500; font-size: 8.5pt; color: {INK2}; }}
QPushButton#tab:checked {{ background: {FERN}; border-color: {FERN}; color: #ffffff; }}
QToolButton {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 8px; padding: 4px 8px; }}
QToolButton:checked {{ background: {SOFT}; border-color: {SWATCH}; }}
QFrame#card, QFrame#verdict, QFrame#tile {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 8px; }}
QFrame#finding {{ background: {SURFACE}; border: 1px solid {LINE}; border-radius: 8px; }}
QFrame#finding[open="true"] {{ background: {PAPER}; }}
QFrame#verdict[state="none"] {{ border: 1px dashed #b9c7b6; }}
QFrame#verdict[state="cannot"] {{ border: 1px dashed {CRIT}; }}
#vtitle {{ font-size: 11.5pt; font-weight: 700; }}
#tileval {{ font-family: '{F_MONO}'; font-size: 10.5pt; font-weight: 700; }}
#shot {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 8px; color: {INK2}; }}
QGroupBox {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 8px; margin-top: 8px; padding: 10px 8px 6px 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {INK2}; font-size: 8pt; font-weight: 700; }}
QDoubleSpinBox, QComboBox {{ background: {PAPER}; border: 1px solid {LINE}; border-radius: 6px; padding: 3px 6px; }}
QComboBox QAbstractItemView {{ background: {PAPER}; selection-background-color: {SOFT}; selection-color: {INK}; }}
QSlider::groove:horizontal {{ height: 4px; background: {LINE}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {SWATCH}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; margin: -6px 0; border-radius: 7px; background: {FERN}; }}
QCheckBox::indicator {{ width: 15px; height: 15px; border: 1px solid #b9c7b6; border-radius: 4px; background: {PAPER}; }}
QCheckBox::indicator:checked {{ background: {FERN}; border-color: {FERN}; image: none; }}
QMenu {{ background: {PAPER}; border: 1px solid {LINE}; padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 4px; }}
QMenu::item:selected {{ background: {SOFT}; color: {INK}; }}
QToolTip {{ background: {INK}; color: #ffffff; border: none; padding: 4px 6px; }}
"""


def draw_pick_glass(p: QPainter, rect: QRectF, big=True):
    """The bubble icon: a pick glass (thread-counting lens) with a 5 mm reticle scale and a chalk-yellow handle."""
    s = rect.width() / 54.0
    X, Y = (lambda v: rect.left() + v * s), (lambda v: rect.top() + v * s)
    p.setPen(QPen(QColor("#ffffff"), (2.2 if big else 3.0) * s)); p.setBrush(QColor(255, 255, 255, 26))
    p.drawEllipse(QPointF(X(27), Y(27)), 17 * s, 17 * s)
    p.setPen(QPen(QColor(255, 255, 255, 140), 1.0 * s))
    p.drawLine(QPointF(X(14), Y(27)), QPointF(X(40), Y(27))); p.drawLine(QPointF(X(27), Y(14)), QPointF(X(27), Y(40)))
    p.setPen(QPen(QColor("#ffffff"), 1.1 * s))
    for i in range(6):
        p.drawLine(QPointF(X(17 + i * 4), Y(27)), QPointF(X(17 + i * 4), Y(27 - (5 if i % 5 == 0 else 3))))
    pen = QPen(QColor("#f0bf45"), (4 if big else 5) * s); pen.setCapStyle(Qt.PenCapStyle.RoundCap); p.setPen(pen)
    p.drawLine(QPointF(X(39.5), Y(39.5)), QPointF(X(45.5), Y(45.5)))


def fern_disc(p: QPainter, rect: QRectF):
    g = QRadialGradient(rect.left() + rect.width() * .35, rect.top() + rect.height() * .30, rect.width() * .75)
    g.setColorAt(0, QColor("#86cf8d")); g.setColorAt(.45, QColor(SWATCH)); g.setColorAt(1, QColor("#3f8f48"))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(g); p.drawEllipse(rect)


class PickGlassIcon(QWidget):
    def __init__(self, size=22):
        super().__init__(); self.setFixedSize(size, size)

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()); fern_disc(p, r); draw_pick_glass(p, r, big=False)


# ---------------------------------------------------------------- image helpers
def bgr_to_pixmap(img: np.ndarray) -> QPixmap:
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    return QPixmap.fromImage(QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy())


def pixmap_to_bgr(pix: QPixmap) -> np.ndarray:
    img = pix.toImage().convertToFormat(QImage.Format.Format_RGB888)
    w, h, bpl = img.width(), img.height(), img.bytesPerLine()
    ptr = img.constBits(); ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(h, bpl)[:, :w * 3].reshape(h, w, 3)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR).copy()


# ---------------------------------------------------------------- background work
class Worker(QThread):
    """Runs model loading / analysis off the GUI thread so the window never freezes."""
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, *args):
        super().__init__()
        self.fn, self.args = fn, args

    def run(self):
        try:
            self.done.emit(self.fn(*self.args))
        except Exception as e:  # report any error to the user instead of crashing
            self.failed.emit(f"{type(e).__name__}: {e}")


# ---------------------------------------------------------------- floating bubble
class Bubble(QWidget):
    clicked = pyqtSignal()
    SIZE = 60

    def __init__(self, menu_factory):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip("Fabric Inspector\nclick: open panel · drag: move · right-click: menu")
        self.menu_factory = menu_factory
        self._press, self._start, self._dragged = None, None, False
        self.badge = None                     # colour of the last verdict (None = nothing found / no check yet)
        self.setWindowOpacity(0.9)
        s = QSettings(ORG, APP)
        pos = s.value("bubble_pos")
        if isinstance(pos, QPoint) and QGuiApplication.screenAt(pos + QPoint(10, 10)):
            self.move(pos)
        else:
            g = QGuiApplication.primaryScreen().availableGeometry()
            self.move(g.right() - self.SIZE - 6, g.center().y())

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(30, 80, 40, 50)); p.drawEllipse(r.translated(0, 2))   # soft shadow
        fern_disc(p, r)
        p.setPen(QPen(QColor(255, 255, 255, 180), 2)); p.setBrush(Qt.BrushStyle.NoBrush); p.drawEllipse(r.adjusted(1, 1, -1, -1))
        draw_pick_glass(p, r)
        if self.badge:
            p.setPen(QPen(QColor("#ffffff"), 2)); p.setBrush(QColor(self.badge))
            p.drawEllipse(QPointF(r.right() - 7, r.top() + 7), 7, 7)

    def enterEvent(self, _): self.setWindowOpacity(1.0)
    def leaveEvent(self, _): self.setWindowOpacity(0.9)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._press, self._start, self._dragged = e.globalPosition().toPoint(), self.pos(), False

    def mouseMoveEvent(self, e):
        if self._press is None:
            return
        delta = e.globalPosition().toPoint() - self._press
        if delta.manhattanLength() > 5:
            self._dragged = True
        if self._dragged:
            self.move(self._start + delta)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton or self._press is None:
            return
        if self._dragged:
            self.snap_to_edge()
        else:
            self.clicked.emit()
        self._press = None

    def contextMenuEvent(self, e):
        self.menu_factory().exec(e.globalPos())

    def snap_to_edge(self):
        scr = QGuiApplication.screenAt(self.geometry().center()) or QGuiApplication.primaryScreen()
        g = scr.availableGeometry()
        x = g.left() + 6 if self.geometry().center().x() < g.center().x() else g.right() - self.SIZE - 6
        y = min(max(self.y(), g.top() + 6), g.bottom() - self.SIZE - 6)
        self.move(x, y)
        QSettings(ORG, APP).setValue("bubble_pos", self.pos())


# ---------------------------------------------------------------- screen area selector
class AreaSelector(QWidget):
    """Full-screen dim overlay: drag a rectangle to capture that part of the screen. Esc cancels."""
    selected = pyqtSignal(QRect)       # global (logical) coordinates
    cancelled = pyqtSignal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QGuiApplication.primaryScreen().virtualGeometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.origin, self.sel = None, QRect()

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QPainterPath(); full.addRect(self.rect().toRectF())
        hole = QPainterPath(); hole.addRect(self.sel.toRectF())
        p.fillPath(full.subtracted(hole), QColor(10, 12, 30, 140))
        p.fillRect(self.sel, QColor(255, 255, 255, 1))    # alpha 1: still receives mouse events
        if not self.sel.isNull():
            p.setPen(QPen(QColor("#ffffff"), 2)); p.drawRect(self.sel)
            p.setFont(QFont(F_MONO, 9)); p.setPen(QColor("#ffffff"))
            p.drawText(self.sel.bottomLeft() + QPoint(2, 18), f"{self.sel.width()} × {self.sel.height()} px")
        else:
            text = "Drag over the fabric  ·  Esc to cancel"
            p.setFont(QFont(F_BODY, 12, QFont.Weight.DemiBold))
            tw = p.fontMetrics().horizontalAdvance(text)
            scr = QGuiApplication.primaryScreen().geometry().translated(-self.geometry().topLeft())
            box = QRectF(scr.center().x() - tw / 2 - 16, scr.top() + scr.height() * .08, tw + 32, 38)
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor(0, 0, 0, 130)); p.drawRoundedRect(box, 8, 8)
            p.setPen(QColor("#ffffff")); p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def mousePressEvent(self, e):
        self.origin = e.position().toPoint(); self.sel = QRect(self.origin, self.origin); self.update()

    def mouseMoveEvent(self, e):
        if self.origin is not None:
            self.sel = QRect(self.origin, e.position().toPoint()).normalized(); self.update()

    def mouseReleaseEvent(self, e):
        r = self.sel.translated(self.geometry().topLeft())
        self.close()
        if r.width() > 15 and r.height() > 15:
            self.selected.emit(r)
        else:
            self.cancelled.emit()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Escape:
            self.close(); self.cancelled.emit()


def grab_screen_rect(r: QRect) -> np.ndarray:
    scr = QGuiApplication.screenAt(r.center()) or QGuiApplication.primaryScreen()
    g = scr.geometry()
    pix = scr.grabWindow(0, r.x() - g.x(), r.y() - g.y(), r.width(), r.height())
    return pixmap_to_bgr(pix)


# ---------------------------------------------------------------- result widgets
def chip(text, color) -> QLabel:
    lb = QLabel(text.upper())
    lb.setStyleSheet(f"background:{color};color:#ffffff;border-radius:9px;padding:2px 8px;font-size:7.5pt;"
                     f"font-weight:700;letter-spacing:1px;")
    lb.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return lb


def wrap_label(text="", name=None, rich=False) -> QLabel:
    lb = QLabel(text); lb.setWordWrap(True)
    lb.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    lb.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    if name: lb.setObjectName(name)
    return lb


class VerdictCard(QFrame):
    """Verdict first: severity chip + 'N defects · P points', or 'No defects detected', or why it cannot analyse."""
    def __init__(self, v: dict, footnote=""):
        super().__init__(); self.setObjectName("verdict"); self.setProperty("state", v["state"])
        h = QHBoxLayout(self); h.setContentsMargins(12, 10, 12, 10); h.setSpacing(10)
        if v["severity"]:
            h.addWidget(chip(SEV_LABEL[v["severity"]], SEV_COLOR[v["severity"]]), 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout(); col.setSpacing(1)
        t = wrap_label(v["title"], "vtitle")
        if v["state"] == "cannot": t.setStyleSheet(f"color:{CRIT};")
        col.addWidget(t)
        col.addWidget(wrap_label(v["detail"] + (f"  {footnote}" if footnote else ""), "muted"))
        h.addLayout(col, 1)


class FindingCard(QFrame):
    """One finding: coloured stripe, name, size/confidence, severity chip and points. Click to open the
    likely causes, remedy and prevention from the knowledge base."""
    def __init__(self, r: dict, sub: str, max_items=3, opened=False):
        super().__init__(); self.setObjectName("finding")
        col = SEV_COLOR[r["severity"]]
        outer = QHBoxLayout(self); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        stripe = QFrame(); stripe.setFixedWidth(5)
        stripe.setStyleSheet(f"background:{col};border:none;border-top-left-radius:7px;border-bottom-left-radius:7px;")
        outer.addWidget(stripe)
        v = QVBoxLayout(); v.setContentsMargins(10, 8, 10, 8); v.setSpacing(6); outer.addLayout(v, 1)

        head = QHBoxLayout(); head.setSpacing(8)
        tcol = QVBoxLayout(); tcol.setSpacing(0)
        name = QLabel(f"#{r['index']} {r['name']}"); name.setStyleSheet("font-weight:600;"); name.setWordWrap(True)
        tcol.addWidget(name); s = QLabel(sub); s.setObjectName("sub"); s.setWordWrap(True); tcol.addWidget(s)
        head.addLayout(tcol, 1)
        rcol = QVBoxLayout(); rcol.setSpacing(2)
        rcol.addWidget(chip(SEV_LABEL[r["severity"]], col), 0, Qt.AlignmentFlag.AlignRight)
        if r.get("points") is not None:
            pt = QLabel(f"{r['points']} pt"); pt.setObjectName("pts"); rcol.addWidget(pt, 0, Qt.AlignmentFlag.AlignRight)
        head.addLayout(rcol)
        self.arrow = QLabel("▸"); self.arrow.setObjectName("muted"); head.addWidget(self.arrow)
        v.addLayout(head)

        e = html.escape
        parts = [f"<span style='color:{INK2}'>{e(r['severity_basis'])}</span>"]
        if r.get("measure"):
            parts.append(f"<br><span style='color:{INK2}'>{e(r['measure'])}</span>")
        if r["severity"] != "acceptable":
            def block(title, rows):
                return (f"<p style='margin:8px 0 2px 0;color:{INK2};font-size:7.5pt;font-weight:700'>{title}</p>"
                        "<ul style='margin:0 0 0 -22px'>" + "".join(f"<li>{x}</li>" for x in rows) + "</ul>")
            parts.append(block("LIKELY CAUSES", [f"<i>{e(c['stage'])}</i>: {e(c['cause'])}" for c in r["causes"][:max_items]]))
            parts.append(block("REMEDY", [e(x) for x in r["remedy"][:max_items]]))
            parts.append(block("PREVENTION", [e(x) for x in r["prevention"][:max_items]]))
        self.body = wrap_label("".join(parts), rich=True)
        v.addWidget(self.body)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.set_open(opened)

    def set_open(self, on: bool):
        self.body.setVisible(on); self.arrow.setText("▾" if on else "▸")
        self.setProperty("open", "true" if on else "false"); self.style().unpolish(self); self.style().polish(self)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.body.hasSelectedText():
            self.set_open(not self.body.isVisible())


class Tile(QFrame):
    def __init__(self, label, value, color=INK):
        super().__init__(); self.setObjectName("tile")
        v = QVBoxLayout(self); v.setContentsMargins(8, 6, 8, 6); v.setSpacing(0)
        a = QLabel(label); a.setObjectName("muted"); a.setStyleSheet("font-size:7.5pt;"); v.addWidget(a)
        b = QLabel(value); b.setObjectName("tileval"); b.setStyleSheet(f"color:{color};"); v.addWidget(b)


# ---------------------------------------------------------------- main panel
class Panel(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("panel"); self.setWindowTitle("Fabric Inspector"); self.setStyleSheet(QSS)
        self.resize(460, 780)
        self.qs = QSettings(ORG, APP)
        if self.qs.value("ui_version") != "2":            # v2 uses the ONNX model: forget the old .pt choice once
            self.qs.remove("model_path"); self.qs.setValue("ui_version", "2")
        self.analyzer, self.image, self.report, self.worker = None, None, None, None
        self.bubble, self.source, self.current_view, self.run_settings = None, "", "", Settings()
        self._build()
        self._load_settings()
        self.load_model(self.qs.value("model_path", str(DEFAULT_MODEL)))

    # ---------- UI
    def _build(self):
        v = QVBoxLayout(self); v.setSpacing(8); v.setContentsMargins(12, 10, 12, 10)

        head = QHBoxLayout(); head.setSpacing(8)
        head.addWidget(PickGlassIcon(22))
        t = QLabel("Fabric Inspector"); t.setObjectName("title"); head.addWidget(t)
        head.addStretch()
        self.lb_model = QLabel(""); self.lb_model.setObjectName("model"); head.addWidget(self.lb_model)
        v.addLayout(head)

        row = QHBoxLayout(); row.setSpacing(8)
        self.btn_area = QPushButton("Select screen area"); self.btn_area.setObjectName("primary")
        self.btn_area.clicked.connect(self.select_area)
        self.btn_upload = QPushButton("Upload photo"); self.btn_upload.clicked.connect(self.upload)
        row.addWidget(self.btn_area, 1); row.addWidget(self.btn_upload, 1)
        v.addLayout(row)

        row = QHBoxLayout(); row.setSpacing(10)
        self.cb_def = QCheckBox("Defects (AI)"); self.cb_shade = QCheckBox("Shade ΔE"); self.cb_skew = QCheckBox("Bow / skew")
        self.cb_shade.setToolTip("Only for flat fabric, photographed straight from above in even light")
        self.cb_skew.setToolTip("Only for flat fabric, photographed straight from above in even light")
        for cb in (self.cb_def, self.cb_shade, self.cb_skew):
            row.addWidget(cb); cb.toggled.connect(self._save_settings)
        row.addStretch()
        self.btn_again = QToolButton(); self.btn_again.setText("↻"); self.btn_again.setToolTip("Analyse again with the current settings")
        self.btn_again.clicked.connect(self.run_analysis); row.addWidget(self.btn_again)
        self.btn_cfg = QToolButton(); self.btn_cfg.setText("⚙"); self.btn_cfg.setCheckable(True)
        self.btn_cfg.setToolTip("Settings"); row.addWidget(self.btn_cfg)
        v.addLayout(row)

        self.cfg = QGroupBox("SETTINGS"); f = QFormLayout(self.cfg); f.setVerticalSpacing(6)
        self.sl_conf = QSlider(Qt.Orientation.Horizontal); self.sl_conf.setRange(5, 90)
        self.lb_conf = QLabel(); self.lb_conf.setObjectName("model")
        self.sl_conf.valueChanged.connect(lambda x: self.lb_conf.setText(f"{x / 100:.2f}"))
        h = QHBoxLayout(); h.addWidget(self.sl_conf); h.addWidget(self.lb_conf)
        f.addRow("Detection confidence", h)
        self.sp_scale = QDoubleSpinBox(); self.sp_scale.setRange(0, 100); self.sp_scale.setDecimals(2)
        self.sp_scale.setSpecialValueText("unknown"); self.sp_scale.setSuffix(" px/mm")
        self.sp_scale.setToolTip("Image scale for the 4-point system. Put a ruler in the photo:\n"
                                 "pixels between two cm marks / 10 = px per mm. 0 = unknown.")
        f.addRow("Image scale", self.sp_scale)
        self.sp_tol = QDoubleSpinBox(); self.sp_tol.setRange(0.2, 5); self.sp_tol.setSingleStep(0.1)
        f.addRow("Shade tolerance ΔE CMC", self.sp_tol)
        self.sp_skew = QDoubleSpinBox(); self.sp_skew.setRange(0.5, 10); self.sp_skew.setSuffix(" %")
        self.sp_bow = QDoubleSpinBox(); self.sp_bow.setRange(0.5, 10); self.sp_bow.setSuffix(" %")
        f.addRow("Skew limit", self.sp_skew); f.addRow("Bow limit", self.sp_bow)
        self.cmb_weft = QComboBox(); self.cmb_weft.addItems(["horizontal", "vertical"])
        f.addRow("Weft direction in photo", self.cmb_weft)
        mrow = QHBoxLayout(); self.lb_model_file = QLabel(); self.lb_model_file.setObjectName("model")
        b = QPushButton("Change…"); b.setStyleSheet("padding:4px 8px;"); b.clicked.connect(self.choose_model)
        mrow.addWidget(self.lb_model_file, 1); mrow.addWidget(b)
        f.addRow("AI model", mrow)
        for wdg in (self.sl_conf, self.sp_scale, self.sp_tol, self.sp_skew, self.sp_bow):
            wdg.valueChanged.connect(self._save_settings)
        self.cmb_weft.currentIndexChanged.connect(self._save_settings)
        self.cfg.setVisible(False); self.btn_cfg.toggled.connect(self.cfg.setVisible)
        v.addWidget(self.cfg)

        # scrolling result area: verdict, picture, findings
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(); body.setObjectName("scrollBody")
        self.res = QVBoxLayout(body); self.res.setContentsMargins(0, 0, 4, 0); self.res.setSpacing(8)
        self.verdict_slot = QVBoxLayout(); self.res.addLayout(self.verdict_slot)
        self.tabs = QHBoxLayout(); self.tabs.setSpacing(6); self.res.addLayout(self.tabs)
        self.lb_img = QLabel("Click “Select screen area” and drag over any fabric on the screen,\nor upload a photo.")
        self.lb_img.setObjectName("shot"); self.lb_img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lb_img.setMinimumHeight(200); self.lb_img.setWordWrap(True)
        self.lb_img.setToolTip("Double-click to open full size")
        self.lb_img.mouseDoubleClickEvent = lambda e: self.open_full()
        self.res.addWidget(self.lb_img)
        self.tiles = QHBoxLayout(); self.tiles.setSpacing(6); self.res.addLayout(self.tiles)
        self.findings = QVBoxLayout(); self.findings.setSpacing(6); self.res.addLayout(self.findings)
        self.res.addStretch(1)
        self.scroll.setWidget(body)
        v.addWidget(self.scroll, 1)

        row = QHBoxLayout()
        self.lb_status = QLabel(""); self.lb_status.setObjectName("muted"); self.lb_status.setWordWrap(True)
        self.btn_save = QPushButton("Save report"); self.btn_save.clicked.connect(self.save_report)
        self.btn_save.setEnabled(False)
        row.addWidget(self.lb_status, 1); row.addWidget(self.btn_save)
        v.addLayout(row)

    def _load_settings(self):
        self._loading = True          # don't save while widgets are being filled one by one
        try:
            self._load_settings_inner()
        finally:
            self._loading = False

    def _load_settings_inner(self):
        d = Settings()
        g = lambda k, default, t: t(self.qs.value(k, default))
        self.cb_def.setChecked(g("do_defects", True, lambda x: str(x).lower() == "true"))
        self.cb_shade.setChecked(g("do_shade", False, lambda x: str(x).lower() == "true"))
        self.cb_skew.setChecked(g("do_skew", False, lambda x: str(x).lower() == "true"))
        self.sl_conf.setValue(round(g("conf", d.conf, float) * 100)); self.lb_conf.setText(f"{self.sl_conf.value() / 100:.2f}")
        self.sp_scale.setValue(g("px_per_mm", d.px_per_mm, float))
        self.sp_tol.setValue(g("shade_tol", d.shade_tol, float))
        self.sp_skew.setValue(g("skew_limit", d.skew_limit, float))
        self.sp_bow.setValue(g("bow_limit", d.bow_limit, float))
        self.cmb_weft.setCurrentText(g("weft", d.weft, str))

    def _save_settings(self, *_):
        if getattr(self, "_loading", False):
            return
        for k, v in asdict(self.settings()).items():
            self.qs.setValue(k, v)

    def settings(self) -> Settings:
        return Settings(conf=self.sl_conf.value() / 100, px_per_mm=self.sp_scale.value(),
                        shade_tol=self.sp_tol.value(), skew_limit=self.sp_skew.value(),
                        bow_limit=self.sp_bow.value(), weft=self.cmb_weft.currentText(),
                        do_defects=self.cb_def.isChecked(), do_shade=self.cb_shade.isChecked(),
                        do_skew=self.cb_skew.isChecked())

    # ---------- model
    def load_model(self, path):
        path = Path(path)
        if not path.exists():
            self.lb_model_file.setText(f"not found: {path.name}"); self.lb_model.setText("no model")
            self.status("AI model file not found. Open ⚙ Settings and choose the model file.")
            return
        self.lb_model_file.setText(path.name)
        self.status("Loading the AI model…")
        self._busy(True)
        self.worker = Worker(Analyzer, path)
        self.worker.done.connect(self._model_loaded)
        self.worker.failed.connect(lambda m: (self._busy(False), self.status(
            "The AI model could not be loaded. Open ⚙ Settings and choose another model file."), print(m, file=sys.stderr)))
        self.worker.start()

    def _model_loaded(self, analyzer):
        self.analyzer = analyzer
        self.qs.setValue("model_path", str(analyzer.model_path))
        self._busy(False)
        self.lb_model.setText(f"{analyzer.model_path.name} · on this PC")
        self.status("Ready.")
        if self.image is not None:
            self.run_analysis()

    def choose_model(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose the AI model file", str(ROOT / "models"),
                                           "YOLO model (*.onnx *.pt)")
        if p:
            self.load_model(p)

    # ---------- input
    def upload(self):
        start = self.qs.value("last_dir", str(Path.home() / "Pictures"))
        p, _ = QFileDialog.getOpenFileName(self, "Choose a fabric photo", start,
                                           "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)")
        if not p:
            return
        self.qs.setValue("last_dir", str(Path(p).parent))
        img = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)   # works with non-ASCII paths
        if img is None:
            QMessageBox.warning(self, "Cannot open the photo", f"This file could not be read as a photo:\n{p}\n\n"
                                                               "Choose a JPG or PNG image.")
            return
        self.set_image(img, Path(p).name)

    def select_area(self):
        self._was_visible = self.isVisible()
        self.hide()
        if self.bubble: self.bubble.hide()
        QTimer.singleShot(250, self._open_selector)        # wait until our windows are gone

    def _open_selector(self):
        self.selector = AreaSelector()
        self.selector.selected.connect(lambda r: QTimer.singleShot(200, lambda: self._capture(r)))
        self.selector.cancelled.connect(self._restore)
        self.selector.show(); self.selector.activateWindow()

    def _capture(self, r):
        img = grab_screen_rect(r)
        self._restore()
        self.set_image(img, f"screen area {r.width()} × {r.height()}")

    def _restore(self):
        if self.bubble: self.bubble.show()
        self.show(); self.raise_(); self.activateWindow()

    def set_image(self, img, source):
        self.image, self.source = img, source
        self.report = None
        self._clear_results()
        self._set_pixmap(img)
        self.run_analysis()

    # ---------- analysis
    def run_analysis(self):
        if self.image is None:
            return
        if self.analyzer is None:
            self.status("Please wait, the AI model is still loading…")
            return
        s = self.settings()
        if not (s.do_defects or s.do_shade or s.do_skew):
            self.status("Tick at least one check: defects, shade or bow/skew.")
            return
        self.run_settings = s
        self._busy(True); self.status("Analysing…"); self._t0 = time.perf_counter()
        self.worker = Worker(self.analyzer.analyse, self.image, s)
        self.worker.done.connect(self._show_report)
        self.worker.failed.connect(lambda m: (self._busy(False), self.status(
            "The photo could not be analysed. Try again or choose another photo."), print(m, file=sys.stderr)))
        self.worker.start()

    @staticmethod
    def _clear(layout):
        while layout.count():
            it = layout.takeAt(0)
            w = it.widget()                      # keep our own reference: the layout item forgets the widget
            if w is not None:
                w.hide(); w.setParent(None); w.deleteLater()

    def _clear_results(self):
        for lay in (self.verdict_slot, self.tabs, self.tiles, self.findings):
            self._clear(lay)

    def _sub(self, r) -> str:
        """Second line of a finding card: size and confidence, or the measured value against its limit."""
        if "box" not in r:
            return r["severity_basis"]
        x1, y1, x2, y2 = r["box"]; longest = max(x2 - x1, y2 - y1)
        pxmm = self.run_settings.px_per_mm
        size = f"{longest / pxmm:.0f} mm" if pxmm else f"{longest:.0f} px"
        return f"{size} · conf {r['confidence']:.2f}"

    def _show_report(self, rep: Report):
        self.report = rep
        self._busy(False)
        self._clear_results()
        dt = (time.perf_counter() - self._t0) * 1000
        v = rep.verdict
        self.verdict_slot.addWidget(VerdictCard(v))

        names = list(rep.views)
        if len(names) > 1:
            for n in names:
                b = QPushButton(n.split(" (")[0]); b.setObjectName("tab"); b.setCheckable(True); b.setAutoExclusive(True)
                b.clicked.connect(lambda _=False, n=n: self.show_view(n)); self.tabs.addWidget(b)
            self.tabs.addStretch()
            self.tabs.itemAt(0).widget().setChecked(True)
        self.show_view(names[0])

        by = {r["defect"]: r for r in rep.items if "box" not in r}
        for key, label, fmt in (("shade_variation", "Shade ΔE CMC 2:1", "{:.2f}"), ("skewing", "Skew", "{:.1f} %"), ("bowing", "Bow", "{:.1f} %")):
            if key in by and by[key].get("value") is not None:
                ok = by[key]["severity"] == "acceptable"
                self.tiles.addWidget(Tile(label, fmt.format(by[key]["value"]), INK if ok else SEV_COLOR[by[key]["severity"]]))

        for i, r in enumerate(rep.items):
            self.findings.addWidget(FindingCard(r, self._sub(r), opened=(i == 0 and r["severity"] != "acceptable")))
        for n in rep.notes:
            if v["state"] == "none" and n.startswith("No local defects"):
                continue                                   # already said by the verdict
            self.findings.addWidget(wrap_label(n, "muted"))
        if rep.items:
            self.findings.addWidget(wrap_label("Causes and remedies come from the rule-based knowledge base (most common "
                                               "causes for this defect type). Confirm on the production line. "
                                               "Full lists are in the saved report.", "muted"))
        self.btn_save.setEnabled(True)
        self.scroll.verticalScrollBar().setValue(0)
        self.status(f"{self.source} · {dt / 1000:.1f} s")
        if self.bubble:
            self.bubble.badge = SEV_COLOR[v["severity"]] if v["severity"] else (INK2 if v["state"] == "cannot" else None)
            self.bubble.update()

    def _html(self, rep: Report) -> str:
        return report_html(rep)

    # ---------- view / output
    def _fit(self, img):
        pix = bgr_to_pixmap(img)
        w = max(self.scroll.viewport().width() - 12, 200)
        return pix.scaled(w, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def _set_pixmap(self, img):
        pix = self._fit(img)
        self.lb_img.setFixedHeight(pix.height() + 2)      # the whole picture is always visible (never cropped)
        self.lb_img.setPixmap(pix)

    def show_view(self, name):
        if self.report and name in self.report.views:
            self.current_view = name
            self._set_pixmap(self.report.views[name])

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.report:
            self.show_view(self.current_view)
        elif self.image is not None:
            self._set_pixmap(self.image)

    def open_full(self):
        img = self.report.views.get(self.current_view) if self.report else self.image
        if img is None:
            return
        self.full = QScrollArea(); self.full.setWindowTitle(self.current_view or "Photo")
        lb = QLabel(); lb.setPixmap(bgr_to_pixmap(img)); self.full.setWidget(lb)
        g = QGuiApplication.primaryScreen().availableGeometry()
        self.full.resize(min(img.shape[1] + 30, g.width() - 100), min(img.shape[0] + 30, g.height() - 100))
        self.full.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint); self.full.show()

    def save_report(self):
        if not self.report:
            return
        d = ROOT / "results" / "reports" / time.strftime("%Y%m%d_%H%M%S")
        d.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(d / "input.jpg"), self.image)
        for name, img in self.report.views.items():
            cv2.imwrite(str(d / (name.split(" (")[0].replace(" ", "_").lower() + ".jpg")), img)
        (d / "report.txt").write_text(f"Source: {self.source}\n" + report_to_text(self.report), encoding="utf-8")
        (d / "report.html").write_text(self._html(self.report), encoding="utf-8")
        self.status(f"Report saved to {d}")

    def status(self, msg):
        self.lb_status.setText(msg)

    def _busy(self, on):
        for b in (self.btn_upload, self.btn_area, self.btn_again):
            b.setEnabled(not on)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor) if on else QApplication.restoreOverrideCursor()

    def closeEvent(self, e):          # closing the panel only hides it; the bubble stays
        e.ignore(); self.hide()

    def toggle_near(self, bubble: QWidget):
        if self.isVisible():
            self.hide(); return
        g = (QGuiApplication.screenAt(bubble.geometry().center()) or QGuiApplication.primaryScreen()).availableGeometry()
        b = bubble.geometry()
        x = b.left() - self.width() - 10 if b.center().x() > g.center().x() else b.right() + 10
        y = min(max(b.top() - 100, g.top() + 10), g.bottom() - self.height() - 40)
        self.move(max(g.left(), x), max(g.top(), y))
        self.show(); self.raise_(); self.activateWindow()


def light_palette() -> QPalette:
    """One light theme on purpose (also when Windows is in dark mode), so text is always readable."""
    pal = QPalette()
    for role, col in ((QPalette.ColorRole.Window, SURFACE), (QPalette.ColorRole.WindowText, INK),
                      (QPalette.ColorRole.Base, PAPER), (QPalette.ColorRole.AlternateBase, SURFACE),
                      (QPalette.ColorRole.Text, INK), (QPalette.ColorRole.Button, PAPER),
                      (QPalette.ColorRole.ButtonText, INK), (QPalette.ColorRole.ToolTipBase, INK),
                      (QPalette.ColorRole.ToolTipText, "#ffffff"), (QPalette.ColorRole.Highlight, FERN),
                      (QPalette.ColorRole.HighlightedText, "#ffffff"), (QPalette.ColorRole.PlaceholderText, INK2)):
        pal.setColor(role, QColor(col))
    return pal


# ---------------------------------------------------------------- app
def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP); app.setStyle("Fusion"); app.setPalette(light_palette())
    app.setQuitOnLastWindowClosed(False)
    panel = Panel()

    def menu():
        m = QMenu(); m.setStyleSheet(QSS)
        for text, fn in (("Select screen area", panel.select_area),
                         ("Upload photo", lambda: (panel.toggle_near(bubble) if not panel.isVisible() else None,
                                                   panel.upload())),
                         ("Show / hide panel", lambda: panel.toggle_near(bubble))):
            a = QAction(text, m); a.triggered.connect(fn); m.addAction(a)
        m.addSeparator()
        q = QAction("Quit", m); q.triggered.connect(app.quit); m.addAction(q)
        return m

    bubble = Bubble(menu)
    panel.bubble = bubble
    bubble.clicked.connect(lambda: panel.toggle_near(bubble))
    bubble.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
