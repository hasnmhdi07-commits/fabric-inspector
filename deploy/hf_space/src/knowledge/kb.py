"""Rule-based knowledge base: turns a detection/measurement into severity + cause + remedy.

Why rule-based (for the defence): every cause and remedy comes from a written, checkable source
(knowledge_base.yaml, based on textile standards and textbooks). The result is explainable and
repeatable - the same input always gives the same answer. An optional LLM may only REPHRASE this text.
"""
from pathlib import Path
import yaml

KB_PATH = Path(__file__).with_name("knowledge_base.yaml")
MM_PER_INCH = 25.4
SEVERITY_ORDER = ["acceptable", "minor", "major", "critical"]


def load_kb(path=KB_PATH) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def four_point(length_mm: float, is_hole: bool = False) -> int:
    """ASTM D5430 4-point system penalty points for one defect."""
    inch = round(length_mm / MM_PER_INCH, 6)   # round: 76.2/25.4 = 3.0000000000000004 in floating point
    if is_hole:
        return 2 if inch <= 1 else 4
    if inch <= 3: return 1
    if inch <= 6: return 2
    if inch <= 9: return 3
    return 4


def points_per_100_sq_yd(total_points: float, length_yd: float, width_in: float) -> float:
    """Fabric grade: points per 100 square yards = points x 3600 / (yards inspected x width in inches)."""
    return total_points * 3600.0 / (length_yd * width_in)


def _points_to_severity(points: int) -> str:
    return {1: "minor", 2: "minor", 3: "major", 4: "critical"}[points]


def assess(defect: str, *, box_wh_px=None, image_wh_px=None, px_per_mm=None, confidence=None,
           delta_e=None, shade_tolerance=1.0, skew_pct=None, bow_pct=None,
           skew_limit=3.0, bow_limit=2.0, kb=None) -> dict:
    """Return a full report for ONE defect.

    YOLO defects: give box_wh_px (w, h) and image_wh_px; give px_per_mm if the image scale is known
                  (e.g. a ruler in the photo) -> real 4-point score. Without scale, a relative-size
                  fallback is used and clearly marked.
    shade_variation: give delta_e (CMC 2:1) and shade_tolerance.
    bowing / skewing: give bow_pct / skew_pct and limits.
    """
    kb = kb or load_kb()
    entry = kb["defects"][defect]
    rule = entry["severity"]["rule"]
    severity, points, basis = entry["severity"]["default"], None, ""

    if rule in ("hole", "length") and box_wh_px is not None:
        longest_px = max(box_wh_px)
        if px_per_mm:
            length_mm = longest_px / px_per_mm
            points = four_point(length_mm, is_hole=(rule == "hole"))
            severity = _points_to_severity(points)
            basis = f"4-point system (ASTM D5430): defect length {length_mm:.0f} mm -> {points} point(s)"
        elif image_wh_px is not None:
            frac = (box_wh_px[0] * box_wh_px[1]) / (image_wh_px[0] * image_wh_px[1])
            if rule == "hole":
                severity = "critical" if frac > 0.02 else "major"
            else:
                severity = "minor" if frac < 0.01 else "major" if frac < 0.10 else "critical"
            basis = (f"relative size {frac * 100:.1f}% of image (no scale given - add a ruler / set px per mm "
                     f"for a real 4-point score)")
        if rule == "hole":  # a hole is never less than major
            severity = max(severity, "major", key=SEVERITY_ORDER.index)
        if defect == "broken_pick_end":
            # shape tells the type (assumes weft runs left-right in the photo):
            # long horizontal line = weft missing = broken PICK; long vertical line = warp = broken END
            bw, bh = box_wh_px
            if bw >= 3 * bh:
                basis += "; horizontal line -> likely broken/missing PICK (weft): check weft insertion and weft stop motion"
            elif bh >= 3 * bw:
                basis += "; vertical line -> likely broken END (warp): check sizing, warp tension and warp stop motion"

    elif rule == "delta_e" and delta_e is not None:
        t = shade_tolerance
        severity = ("acceptable" if delta_e <= t else "minor" if delta_e <= 1.5 * t
                    else "major" if delta_e <= 3 * t else "critical")
        basis = f"dE CMC(2:1) = {delta_e:.2f} vs tolerance {t}"

    elif rule == "skew" and skew_pct is not None:
        s, lim = abs(skew_pct), skew_limit
        severity = "acceptable" if s <= lim else "major" if s <= 2 * lim else "critical"
        basis = f"skew {s:.2f}% vs limit {lim}%"

    elif rule == "bow" and bow_pct is not None:
        b, lim = abs(bow_pct), bow_limit
        severity = "acceptable" if b <= lim else "major" if b <= 2 * lim else "critical"
        basis = f"bow {b:.2f}% vs limit {lim}%"

    return {
        "defect": defect,
        "name": entry["name"],
        "description": entry["description"],
        "severity": severity,
        "points": points,
        "severity_basis": basis or "default severity for this defect type",
        "confidence": confidence,
        "causes": entry["causes"],
        "remedy": entry["remedy"],
        "prevention": entry["prevention"],
    }


def format_report(r: dict, max_items: int = 3) -> str:
    """Short plain-text report (used by the app)."""
    lines = [f"{r['name']} - severity: {r['severity'].upper()}"
             + (f" (conf {r['confidence']:.0%})" if r.get("confidence") is not None else ""),
             f"  basis: {r['severity_basis']}",
             "  Likely causes:"]
    lines += [f"   - [{c['stage']}] {c['cause']}" for c in r["causes"][:max_items]]
    lines += ["  Remedy:"] + [f"   - {x}" for x in r["remedy"][:max_items]]
    lines += ["  Prevention:"] + [f"   - {x}" for x in r["prevention"][:max_items]]
    return "\n".join(lines)


if __name__ == "__main__":
    print(format_report(assess("hole_tear", box_wh_px=(60, 40), image_wh_px=(1280, 960), px_per_mm=2.0, confidence=0.87)))
    print()
    print(format_report(assess("shade_variation", delta_e=1.8)))
