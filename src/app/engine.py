"""Analysis engine: one image in -> one combined report out.

Pipeline (hybrid system):
  1. YOLO detects local defects (hole_tear, stain, slub_neps, broken_pick_end) -> boxes + confidence
  2. (optional) CIELAB delta E shade check -> heat map + pass/fail
  3. (optional) weft-angle bow/skew check -> % bow, % skew + pass/fail
  4. Every finding goes through the rule-based knowledge base -> severity, causes, remedy, prevention
No GUI code here, so it can be tested and reused (e.g. batch processing for the thesis).
"""
from dataclasses import dataclass, field, asdict
from pathlib import Path
import time
import cv2
import numpy as np

from src.knowledge.kb import load_kb, assess, SEVERITY_ORDER
from src.shade.delta_e import analyse_shade
from src.skew.bow_skew import analyse_skew_bow

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = ROOT / "models" / "best.pt"
CLASSES = ["hole_tear", "stain", "slub_neps", "broken_pick_end"]
# categorical colours for class identity (BGR); severity uses separate status colours in the UI
CLASS_COLORS = {"hole_tear": (214, 120, 42), "stain": (52, 104, 235),
                "slub_neps": (122, 175, 27), "broken_pick_end": (0, 161, 237)}


@dataclass
class Settings:
    conf: float = 0.23            # best mean-F1 threshold found on the test set (R1)
    iou: float = 0.5
    imgsz: int = 640
    px_per_mm: float = 0.0        # 0 = unknown scale (relative-size severity fallback)
    shade_tol: float = 1.0        # dE CMC(2:1)
    skew_limit: float = 3.0
    bow_limit: float = 2.0
    weft: str = "horizontal"
    do_defects: bool = True
    do_shade: bool = False
    do_skew: bool = False


@dataclass
class Report:
    items: list                   # list of dicts (kb.assess output + box/conf/index)
    views: dict                   # name -> BGR image
    notes: list = field(default_factory=list)
    timings_ms: dict = field(default_factory=dict)
    image_size: tuple = (0, 0)

    @property
    def worst(self) -> str:
        sev = [i["severity"] for i in self.items]
        return max(sev, key=SEVERITY_ORDER.index) if sev else "acceptable"


class Analyzer:
    def __init__(self, model_path=DEFAULT_MODEL):
        from ultralytics import YOLO          # imported here so the GUI starts fast
        self.model_path = Path(model_path)
        self.model = YOLO(str(self.model_path))
        self.kb = load_kb()
        self.model.predict(np.zeros((64, 64, 3), np.uint8), verbose=False)   # warm-up

    def analyse(self, img_bgr: np.ndarray, s: Settings) -> Report:
        h, w = img_bgr.shape[:2]
        items, views, notes, t = [], {}, [], {}

        if s.do_defects:
            t0 = time.perf_counter()
            res = self.model.predict(img_bgr, conf=s.conf, iou=s.iou, imgsz=s.imgsz, verbose=False)[0]
            t["detection"] = (time.perf_counter() - t0) * 1000
            names = res.names
            for b in res.boxes:
                x1, y1, x2, y2 = b.xyxy[0].tolist()
                cls = names[int(b.cls)]
                r = assess(cls, box_wh_px=(x2 - x1, y2 - y1), image_wh_px=(w, h),
                           px_per_mm=s.px_per_mm or None, confidence=float(b.conf), kb=self.kb)
                r["box"] = [x1, y1, x2, y2]
                items.append(r)
            if not items:
                notes.append(f"No local defects found at confidence >= {s.conf:.2f}.")

        if s.do_shade:
            t0 = time.perf_counter()
            # ignore areas where YOLO found a local defect, so a stain is not counted twice as "shade"
            excl = [(b[0], b[1], b[2] - b[0], b[3] - b[1]) for b in (r["box"] for r in items if "box" in r)]
            sh = analyse_shade(img_bgr, tolerance=s.shade_tol, exclude_rects=excl)
            t["shade"] = (time.perf_counter() - t0) * 1000
            r = assess("shade_variation", delta_e=sh.value, shade_tolerance=s.shade_tol, kb=self.kb)
            r["measure"] = sh.summary()
            items.append(r)
            views["Shade heat map"] = sh.overlay

        if s.do_skew:
            t0 = time.perf_counter()
            try:
                sk = analyse_skew_bow(img_bgr, weft=s.weft, skew_tol=s.skew_limit, bow_tol=s.bow_limit)
                for name, kw in (("skewing", {"skew_pct": sk.skew_pct, "skew_limit": s.skew_limit}),
                                 ("bowing", {"bow_pct": sk.bow_pct, "bow_limit": s.bow_limit})):
                    r = assess(name, kb=self.kb, **kw)
                    r["measure"] = sk.summary()
                    items.append(r)
                views["Weft line (bow/skew)"] = sk.overlay
            except Exception as e:  # e.g. image too small
                notes.append(f"Bow/skew check skipped: {e}")
            t["bow_skew"] = (time.perf_counter() - t0) * 1000

        # most severe first, then highest confidence
        items.sort(key=lambda r: (-SEVERITY_ORDER.index(r["severity"]), -(r.get("confidence") or 0)))
        for i, r in enumerate(items, 1):
            r["index"] = i
        views = {"Defects": self._draw(img_bgr, items), **views}
        if s.do_shade or s.do_skew:
            notes.append("Shade and bow/skew need a flat fabric photo taken straight from above in even light; "
                         "screenshots of other photos give only indicative values.")
        return Report(items, views, notes, t, (w, h))

    @staticmethod
    def _draw(img, items):
        out = img.copy()
        h, w = out.shape[:2]
        th = max(2, round(max(h, w) / 400))
        fs = max(0.45, max(h, w) / 1400)
        for r in items:
            if "box" not in r:
                continue
            x1, y1, x2, y2 = map(int, r["box"])
            col = CLASS_COLORS.get(r["defect"], (255, 255, 255))
            cv2.rectangle(out, (x1, y1), (x2, y2), col, th)
            label = f"{r['index']} {r['defect']} {r['confidence']:.0%}"
            (tw, tht), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, fs, max(1, th // 2))
            ty = y1 - 4 if y1 - tht - 8 > 0 else y2 + tht + 4
            cv2.rectangle(out, (x1, ty - tht - 4), (x1 + tw + 6, ty + 3), col, -1)
            cv2.putText(out, label, (x1 + 3, ty), cv2.FONT_HERSHEY_SIMPLEX, fs, (255, 255, 255), max(1, th // 2),
                        cv2.LINE_AA)
        return out


def report_to_text(rep: Report) -> str:
    lines = [f"Fabric inspection report - overall: {rep.worst.upper()}",
             f"Image {rep.image_size[0]}x{rep.image_size[1]} px", ""]
    for r in rep.items:
        lines.append(f"#{r['index']} {r['name']} - {r['severity'].upper()}"
                     + (f" (confidence {r['confidence']:.0%})" if r.get("confidence") is not None else ""))
        lines.append(f"   basis: {r['severity_basis']}")
        if r.get("measure"):
            lines.append(f"   measurement: {r['measure']}")
        lines.append("   likely causes:")
        lines += [f"     - [{c['stage']}] {c['cause']}" for c in r["causes"]]
        lines.append("   remedy:")
        lines += [f"     - {x}" for x in r["remedy"]]
        lines.append("   prevention:")
        lines += [f"     - {x}" for x in r["prevention"]]
        lines.append("")
    lines += [f"note: {n}" for n in rep.notes]
    lines.append("Timings (ms): " + ", ".join(f"{k} {v:.0f}" for k, v in rep.timings_ms.items()))
    return "\n".join(lines)
