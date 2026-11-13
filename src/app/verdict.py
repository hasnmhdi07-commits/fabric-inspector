"""Verdict rules (spec v2, section 4): every check ends in exactly ONE of three states.

  1. "defects" - something was found            -> highest severity + "N defects - P points"
  2. "none"    - nothing was found              -> "No defects detected" + reminder to check visually.
                                                   The app never says the fabric is "acceptable": the AI can miss defects.
  3. "cannot"  - the photo cannot be analysed   -> the reason + what to do about it

The same rules are implemented in JavaScript (web_static/js/verdict.js) and must give the same answer.
"""
import numpy as np

# Limits chosen on 747 real fabric photos (v3 test + validation) so that good photos are not rejected:
# mean grey there is 31-218 for 99 % of photos (a few very dark ones go down to 12), brightest 237,
# least sharp 1.5. Exact count of rejected real photos: tests/test_verdict.py.
DARK_BELOW = 25.0        # mean grey level 0-255
BRIGHT_ABOVE = 245.0
BLUR_BELOW = 1.2         # variance of the Laplacian (edge strength); strongly blurred photos are below ~1
MIN_SIDE = 64            # pixels

SEV_LABEL = {"acceptable": "Within limit", "minor": "Minor", "major": "Major", "critical": "Critical"}
MEASURE_FAIL = {"shade_variation": "shade out of tolerance", "skewing": "skew over limit", "bowing": "bow over limit"}
VISUAL_CHECK = "The AI can miss defects, so check the fabric visually."


def photo_metrics(bgr: np.ndarray):
    """(mean grey, Laplacian variance) - plain arithmetic so the JavaScript version gives the same numbers."""
    b, g, r = (bgr[..., i].astype(np.float64) for i in range(3))
    grey = np.floor(0.299 * r + 0.587 * g + 0.114 * b + 0.5)
    lap = grey[:-2, 1:-1] + grey[2:, 1:-1] + grey[1:-1, :-2] + grey[1:-1, 2:] - 4 * grey[1:-1, 1:-1]
    return float(grey.mean()), float(lap.var())


def photo_problem(bgr: np.ndarray):
    """None if the photo can be analysed, else {code, title, fix}."""
    h, w = bgr.shape[:2]
    if min(h, w) < MIN_SIDE:
        return {"code": "too_small", "title": "Image too small to analyse",
                "fix": f"Select a larger area or move closer: at least {MIN_SIDE} x {MIN_SIDE} pixels."}
    mean, sharp = photo_metrics(bgr)
    if mean < DARK_BELOW:
        return {"code": "too_dark", "title": "Photo too dark to analyse",
                "fix": "Retake it in even daylight, straight from above."}
    if mean > BRIGHT_ABOVE:
        return {"code": "too_bright", "title": "Photo too bright to analyse",
                "fix": "Retake it without glare or flash, in even daylight."}
    if sharp < BLUR_BELOW:
        return {"code": "blurred", "title": "Photo too blurred to analyse",
                "fix": "Hold the camera still, tap to focus on the fabric and retake the photo."}
    return None


def make_verdict(items, problem=None, defects_checked=True) -> dict:
    """items: findings from kb.assess (+ 'box' for local defects). Returns the one verdict shown to the user."""
    if problem:
        return {"state": "cannot", "severity": None, "title": problem["title"], "detail": problem["fix"],
                "n_defects": 0, "points": None}
    found = [r for r in items if r["severity"] != "acceptable"]
    if not found:
        if defects_checked:
            return {"state": "none", "severity": None, "title": "No defects detected", "detail": VISUAL_CHECK,
                    "n_defects": 0, "points": None}
        return {"state": "none", "severity": None, "title": "Measurements within limits",
                "detail": "Defect detection was switched off for this check.", "n_defects": 0, "points": None}
    order = ["acceptable", "minor", "major", "critical"]
    severity = max((r["severity"] for r in found), key=order.index)
    boxes = [r for r in found if "box" in r]
    n = len(boxes)
    points = sum(r["points"] for r in boxes) if n and all(r.get("points") is not None for r in boxes) else None
    parts = []
    if n:
        parts.append(f"{n} defect{'s' if n != 1 else ''}")
        if points is not None:
            parts.append(f"{points} point{'s' if points != 1 else ''}")
    parts += [MEASURE_FAIL[r["defect"]] for r in found if r["defect"] in MEASURE_FAIL]
    title = " · ".join(parts)
    title = title[0].upper() + title[1:]
    if n and points is None:
        detail = "Severity from relative size. Set the image scale (px/mm) for ASTM D5430 points."
    elif n:
        detail = "ASTM D5430 4-point system. Highest severity first."
    else:
        detail = "No local defects found. " + VISUAL_CHECK if defects_checked else "Highest severity first."
    return {"state": "defects", "severity": severity, "title": title, "detail": detail, "n_defects": n, "points": points}
