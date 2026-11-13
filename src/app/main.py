"""Fabric Defect Inspector - floating bubble app (Windows, PyQt6).

 - A small round bubble floats on top of all windows (like AssistiveTouch). Drag it anywhere;
   it snaps to the nearest screen edge. Click = open/close the panel. Right-click = quick menu.
 - Panel: [Upload image] or [Select screen area] -> analysis -> image with boxes + a list of findings
   with severity, likely causes, remedy and prevention (from the rule-based knowledge base).
Run:  venv\\Scripts\\pythonw.exe -m src.app.main     (from C:\\thesis)  or double-click run_app.bat
"""
import sys, time, html
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np
from PyQt6.QtCore import Qt, QPoint, QRect, QSettings, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import (QAction, QColor, QCursor, QGuiApplication, QImage, QPainter, QPainterPath,
                         QPalette, QPen, QPixmap, QFont)
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                             QGroupBox, QHBoxLayout, QLabel, QMenu, QMessageBox, QPushButton, QSlider,
                             QTextBrowser, QToolButton, QVBoxLayout, QWidget, QScrollArea)

from src.app.engine import Analyzer, Settings, Report, DEFAULT_MODEL, ROOT, report_to_text

APP, ORG = "Inspector", "ThesisFabric"
from src.app.report_html import report_html, SEV_COLOR, SEV_ICON


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
    SIZE = 58

    def __init__(self, menu_factory):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
                         | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setToolTip("Fabric Defect Inspector\nclick: open panel - drag: move - right-click: menu")
        self.menu_factory = menu_factory
        self._press, self._start, self._dragged = None, None, False
        self.badge = None                     # colour of last result (severity)
        self.setWindowOpacity(0.75)
        s = QSettings(ORG, APP)
        pos = s.value("bubble_pos")
        if isinstance(pos, QPoint) and QGuiApplication.screenAt(pos + QPoint(10, 10)):
            self.move(pos)
        else:
            g = QGuiApplication.primaryScreen().availableGeometry()
            self.move(g.right() - self.SIZE - 6, g.center().y())

    def paintEvent(self, _):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(3, 3, -3, -3)
        p.setPen(QPen(QColor(255, 255, 255, 230), 2)); p.setBrush(QColor(28, 30, 34, 225))
        p.drawEllipse(r)
        # icon: woven fabric grid with a magnifier ring
        c = r.center(); p.setPen(QPen(QColor(220, 225, 235), 1.6))
        for d in (-8, 0, 8):
            p.drawLine(c.x() - 13, c.y() + d, c.x() + 13, c.y() + d)
            p.drawLine(c.x() + d, c.y() - 13, c.x() + d, c.y() + 13)
        p.setPen(QPen(QColor("#3987e5"), 3)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPoint(c.x() + 4, c.y() - 4), 9, 9)
        p.drawLine(c.x() + 11, c.y() + 3, c.x() + 17, c.y() + 9)
        if self.badge:
            p.setPen(QPen(QColor(255, 255, 255), 2)); p.setBrush(QColor(self.badge))
            p.drawEllipse(QPoint(r.right() - 7, r.top() + 7), 7, 7)

    def enterEvent(self, _): self.setWindowOpacity(1.0)
    def leaveEvent(self, _): self.setWindowOpacity(0.75)

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
        p = QPainter(self)
        full = QPainterPath(); full.addRect(self.rect().toRectF())
        hole = QPainterPath(); hole.addRect(self.sel.toRectF())
        p.fillPath(full.subtracted(hole), QColor(0, 0, 0, 110))
        p.fillRect(self.sel, QColor(0, 0, 0, 1))          # alpha 1: still receives mouse events
        if not self.sel.isNull():
            p.setPen(QPen(QColor("#3987e5"), 2)); p.drawRect(self.sel)
            p.setPen(QColor("white"))
            p.drawText(self.sel.bottomLeft() + QPoint(4, 18), f"{self.sel.width()} x {self.sel.height()}")
        else:
            p.setPen(QColor("white")); p.setFont(QFont("Segoe UI", 14))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Drag to select the fabric area  -  Esc to cancel")

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


# ---------------------------------------------------------------- main panel
class Panel(QWidget):
    def __init__(self):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle("Fabric Defect Inspector")
        self.resize(470, 760)
        self.qs = QSettings(ORG, APP)
        self.analyzer, self.image, self.report, self.worker = None, None, None, None
        self.bubble = None
        self._build()
        self._load_settings()
        self.load_model(self.qs.value("model_path", str(DEFAULT_MODEL)))

    # ---------- UI
    def _build(self):
        v = QVBoxLayout(self); v.setSpacing(6)
        row = QHBoxLayout()
        self.btn_upload = QPushButton("📂  Upload image"); self.btn_upload.clicked.connect(self.upload)
        self.btn_area = QPushButton("⬚  Select screen area"); self.btn_area.clicked.connect(self.select_area)
        self.btn_again = QPushButton("↻"); self.btn_again.setToolTip("Analyse again with current settings")
        self.btn_again.setFixedWidth(36); self.btn_again.clicked.connect(self.run_analysis)
        for b in (self.btn_upload, self.btn_area):
            b.setMinimumHeight(34)
        row.addWidget(self.btn_upload); row.addWidget(self.btn_area); row.addWidget(self.btn_again)
        v.addLayout(row)

        row = QHBoxLayout()
        self.cb_def = QCheckBox("Local defects (AI)"); self.cb_shade = QCheckBox("Shade (ΔE)")
        self.cb_skew = QCheckBox("Bow / skew")
        for cb in (self.cb_def, self.cb_shade, self.cb_skew):
            row.addWidget(cb); cb.toggled.connect(self._save_settings)
        row.addStretch()
        self.btn_cfg = QToolButton(); self.btn_cfg.setText("⚙"); self.btn_cfg.setCheckable(True)
        self.btn_cfg.setToolTip("Settings"); row.addWidget(self.btn_cfg)
        v.addLayout(row)

        self.cfg = QGroupBox("Settings"); f = QFormLayout(self.cfg)
        self.sl_conf = QSlider(Qt.Orientation.Horizontal); self.sl_conf.setRange(5, 90)
        self.lb_conf = QLabel()
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
        mrow = QHBoxLayout(); self.lb_model = QLabel(); self.lb_model.setWordWrap(True)
        b = QPushButton("Change…"); b.clicked.connect(self.choose_model)
        mrow.addWidget(self.lb_model, 1); mrow.addWidget(b)
        f.addRow("YOLO model", mrow)
        for wdg in (self.sl_conf, self.sp_scale, self.sp_tol, self.sp_skew, self.sp_bow):
            wdg.valueChanged.connect(self._save_settings)
        self.cmb_weft.currentIndexChanged.connect(self._save_settings)
        self.cfg.setVisible(False); self.btn_cfg.toggled.connect(self.cfg.setVisible)
        v.addWidget(self.cfg)

        row = QHBoxLayout(); row.addWidget(QLabel("View:"))
        self.cmb_view = QComboBox(); self.cmb_view.currentTextChanged.connect(self.show_view)
        row.addWidget(self.cmb_view, 1); v.addLayout(row)
        self.lb_img = QLabel("Upload an image or select a screen area to start.")
        self.lb_img.setAlignment(Qt.AlignmentFlag.AlignCenter); self.lb_img.setMinimumHeight(250)
        self.lb_img.setStyleSheet("background:#202226;color:#c3c2b7;border-radius:6px;")
        self.lb_img.setToolTip("Double-click to open full size")
        self.lb_img.mouseDoubleClickEvent = lambda e: self.open_full()
        v.addWidget(self.lb_img, 3)

        self.txt = QTextBrowser(); self.txt.setOpenExternalLinks(False)
        v.addWidget(self.txt, 4)

        row = QHBoxLayout()
        self.lb_status = QLabel(""); self.lb_status.setWordWrap(True)
        self.btn_save = QPushButton("💾 Save report"); self.btn_save.clicked.connect(self.save_report)
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
            self.lb_model.setText(f"not found: {path.name}")
            self.status("⚠ Model file not found - open ⚙ Settings → Change…")
            return
        self.lb_model.setText(path.name)
        self.status("Loading AI model…")
        self._busy(True)
        self.worker = Worker(Analyzer, path)
        self.worker.done.connect(self._model_loaded)
        self.worker.failed.connect(lambda m: (self._busy(False), self.status(f"⚠ Model error: {m}")))
        self.worker.start()

    def _model_loaded(self, analyzer):
        self.analyzer = analyzer
        self.qs.setValue("model_path", str(analyzer.model_path))
        self._busy(False)
        self.status(f"Ready - model {analyzer.model_path.name}")
        if self.image is not None:
            self.run_analysis()

    def choose_model(self):
        p, _ = QFileDialog.getOpenFileName(self, "Choose YOLO weights", str(ROOT / "models"), "YOLO weights (*.pt)")
        if p:
            self.load_model(p)

    # ---------- input
    def upload(self):
        start = self.qs.value("last_dir", str(Path.home() / "Pictures"))
        p, _ = QFileDialog.getOpenFileName(self, "Choose a fabric image", start,
                                           "Images (*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp)")
        if not p:
            return
        self.qs.setValue("last_dir", str(Path(p).parent))
        img = cv2.imdecode(np.fromfile(p, np.uint8), cv2.IMREAD_COLOR)   # works with non-ASCII paths
        if img is None:
            QMessageBox.warning(self, "Cannot open", f"Could not read {p}")
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
        self.set_image(img, f"screen area {r.width()}x{r.height()}")

    def _restore(self):
        if self.bubble: self.bubble.show()
        self.show(); self.raise_(); self.activateWindow()

    def set_image(self, img, source):
        self.image, self.source = img, source
        self.report = None
        self.cmb_view.clear()
        self.lb_img.setPixmap(self._fit(img))
        self.run_analysis()

    # ---------- analysis
    def run_analysis(self):
        if self.image is None:
            return
        if self.analyzer is None:
            self.status("Waiting for model to load…")
            return
        s = self.settings()
        if not (s.do_defects or s.do_shade or s.do_skew):
            self.status("Tick at least one check (defects / shade / bow-skew).")
            return
        self._busy(True); self.status("Analysing…"); self._t0 = time.perf_counter()
        self.worker = Worker(self.analyzer.analyse, self.image, s)
        self.worker.done.connect(self._show_report)
        self.worker.failed.connect(lambda m: (self._busy(False), self.status(f"⚠ Analysis error: {m}")))
        self.worker.start()

    def _show_report(self, rep: Report):
        self.report = rep
        self._busy(False)
        self.cmb_view.blockSignals(True); self.cmb_view.clear(); self.cmb_view.addItems(list(rep.views))
        self.cmb_view.blockSignals(False); self.show_view(self.cmb_view.currentText())
        self.txt.setHtml(self._html(rep))
        self.btn_save.setEnabled(True)
        dt = (time.perf_counter() - self._t0) * 1000
        n = sum(1 for i in rep.items if "box" in i)
        self.status(f"{self.source}: {n} local defect(s), overall {rep.worst.upper()} - {dt:.0f} ms")
        if self.bubble:
            self.bubble.badge = SEV_COLOR[rep.worst]; self.bubble.update()

    def _html(self, rep: Report) -> str:
        dark = self.palette().color(QPalette.ColorRole.Base).lightness() < 128   # Windows dark mode?
        # secondary / muted text colours readable on the current background
        return report_html(rep, sec="#b5b4ab" if dark else "#52514e", mut="#9a9993" if dark else "#6d6c66")

    # ---------- view / output
    def _fit(self, img):
        pix = bgr_to_pixmap(img)
        return pix.scaled(self.lb_img.width() - 4, max(self.lb_img.height() - 4, 200),
                          Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)

    def show_view(self, name):
        if self.report and name in self.report.views:
            self.lb_img.setPixmap(self._fit(self.report.views[name]))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.report:
            self.show_view(self.cmb_view.currentText())
        elif self.image is not None:
            self.lb_img.setPixmap(self._fit(self.image))

    def open_full(self):
        img = self.report.views.get(self.cmb_view.currentText()) if self.report else self.image
        if img is None:
            return
        self.full = QScrollArea(); self.full.setWindowTitle(self.cmb_view.currentText() or "Image")
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
        self.status(f"Saved to {d}")

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
        self.move(max(g.left(), x), y)
        self.show(); self.raise_(); self.activateWindow()


# ---------------------------------------------------------------- app
def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP); app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    panel = Panel()

    def menu():
        m = QMenu()
        for text, fn in (("📂 Upload image", lambda: (panel.toggle_near(bubble) if not panel.isVisible() else None,
                                                      panel.upload())),
                         ("⬚ Select screen area", panel.select_area),
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
