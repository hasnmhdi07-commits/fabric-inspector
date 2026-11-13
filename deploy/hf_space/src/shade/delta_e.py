"""Shade variation measurement with CIELAB colour difference (delta E).

How it works (plain language, for the defence):
1. The photo is converted from RGB to CIELAB. In CIELAB, L* = lightness, a* = red(+)/green(-),
   b* = yellow(+)/blue(-), and equal distances roughly match equal visible differences.
2. Fabric texture (individual yarns) is removed by averaging colours over a region / grid cell,
   because we want the colour of the fabric, not of single yarns.
3. The colour of a TEST area is compared with a REFERENCE area (the standard / "approved" shade):
     - delta E CMC(2:1): the textile-industry standard (lightness weighted half, because the eye is
       less sensitive to lightness than to hue differences on textiles), used for PASS/FAIL.
     - delta E 2000 and delta E*ab (1976) are also reported for comparison.
     - dL, dC, dH tell the DIRECTION: darker/lighter, duller/brighter, hue shift.
4. Heat map: the image is divided into cells; every cell's delta E against the reference is
   coloured (blue = same shade, red = different), showing WHERE the shade changes
   (e.g. side-centre-side "listing" or end-to-end shading).
5. The delta E*ab value is also converted into an approximate ISO 105-A02 grey-scale grade.

Limitation (state in the thesis): a phone camera is not a spectrophotometer. Absolute L*a*b*
values depend on lighting and camera, so we only compare areas INSIDE THE SAME PHOTO
(same light, same camera). Uneven lighting can look like shading -> use even, diffuse light.
"""
from dataclasses import dataclass, field
import cv2
import numpy as np
from skimage.color import rgb2lab, deltaE_ciede2000, deltaE_cmc, deltaE_cie76

# ISO 105-A02 grey scale for colour change: nominal delta E*ab per grade.
# Thresholds below are midpoints between neighbouring nominal values.
_GREY_SCALE = [(0.4, "5"), (1.25, "4-5"), (2.1, "4"), (2.95, "3-4"), (4.1, "3"),
               (5.8, "2-3"), (8.2, "2"), (11.6, "1-2")]


def grey_scale_grade(de_ab: float) -> str:
    for limit, grade in _GREY_SCALE:
        if de_ab < limit:
            return grade
    return "1"


def white_balance(img_bgr: np.ndarray, white_rect) -> np.ndarray:
    """Correct the camera's colour cast using a white paper placed in the photo.
    Each colour channel is scaled (in linear light) so the white patch becomes neutral grey/white."""
    x, y, w, h = map(int, white_rect)
    lin = (img_bgr.astype(np.float64) / 255.0) ** 2.2
    patch = lin[y:y + h, x:x + w].reshape(-1, 3).mean(axis=0)
    gains = patch.mean() / np.maximum(patch, 1e-6)
    out = np.clip(lin * gains, 0, 1) ** (1 / 2.2)
    return (out * 255).round().astype(np.uint8)


def to_lab(img_bgr: np.ndarray, blur: int = 5) -> np.ndarray:
    """BGR uint8 image -> CIELAB float image (sRGB / D65 assumed). Light blur removes yarn noise."""
    if blur:
        img_bgr = cv2.GaussianBlur(img_bgr, (blur | 1, blur | 1), 0)
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).astype(np.float64) / 255.0
    return rgb2lab(rgb)


def region_mean(lab: np.ndarray, rect) -> np.ndarray:
    """Mean L*a*b* inside rect = (x, y, w, h)."""
    x, y, w, h = map(int, rect)
    return lab[y:y + h, x:x + w].reshape(-1, 3).mean(axis=0)


def color_difference(ref: np.ndarray, test: np.ndarray) -> dict:
    """All delta E metrics + direction components between two L*a*b* colours (ref = standard)."""
    r, t = ref.reshape(1, 1, 3), test.reshape(1, 1, 3)
    dL, da, db = (test - ref).tolist()
    c_ref, c_test = np.hypot(ref[1], ref[2]), np.hypot(test[1], test[2])
    dC = float(c_test - c_ref)
    de_ab = float(deltaE_cie76(r, t)[0, 0])
    dH = float(np.sqrt(max(de_ab ** 2 - dL ** 2 - dC ** 2, 0.0)))
    direction = []
    if abs(dL) > 0.3: direction.append("darker" if dL < 0 else "lighter")
    if abs(dC) > 0.3: direction.append("duller" if dC < 0 else "brighter")
    if abs(da) > 0.3: direction.append("greener" if da < 0 else "redder")
    if abs(db) > 0.3: direction.append("bluer" if db < 0 else "yellower")
    return {
        "dE_cmc21": float(deltaE_cmc(r, t, kL=2, kC=1)[0, 0]),
        "dE2000": float(deltaE_ciede2000(r, t)[0, 0]),
        "dE_ab": de_ab,
        "dL": dL, "da": da, "db": db, "dC": dC, "dH": dH,
        "direction": ", ".join(direction) or "no visible direction",
        "grey_scale": grey_scale_grade(de_ab),
    }


def delta_e_map(lab: np.ndarray, ref: np.ndarray, cell: int, metric: str = "cmc") -> np.ndarray:
    """Per-cell delta E against reference colour. Returns array (rows, cols)."""
    h, w = lab.shape[:2]
    rows, cols = max(1, h // cell), max(1, w // cell)
    cells = cv2.resize(lab.astype(np.float32), (cols, rows), interpolation=cv2.INTER_AREA).astype(np.float64)
    refimg = np.broadcast_to(ref, cells.shape)
    if metric == "cmc":
        return deltaE_cmc(refimg, cells, kL=2, kC=1)
    if metric == "2000":
        return deltaE_ciede2000(refimg, cells)
    return deltaE_cie76(refimg, cells)


@dataclass
class ShadeResult:
    passed: bool
    tolerance: float
    metric: str
    value: float                    # the delta E used for pass/fail
    details: dict                   # full colour-difference breakdown
    pct_cells_over_tol: float       # % of image area beyond tolerance
    heatmap: np.ndarray = field(repr=False)   # per-cell delta E
    overlay: np.ndarray = field(repr=False)   # BGR visualisation

    def summary(self) -> str:
        d = self.details
        return (f"Shade {'PASS' if self.passed else 'FAIL'}: dE CMC(2:1) = {d['dE_cmc21']:.2f} "
                f"(tolerance {self.tolerance}), dE2000 = {d['dE2000']:.2f}, grey scale ~{d['grey_scale']}; "
                f"test area is {d['direction']}. {self.pct_cells_over_tol:.0f}% of the image exceeds tolerance.")


def _cell_mask(shape_hw, grid_rc, exclude_rects):
    """True = cell is used; False = cell overlaps an excluded rectangle (e.g. a detected stain/hole)."""
    (h, w), (rows, cols) = shape_hw, grid_rc
    keep = np.ones((rows, cols), bool)
    for x, y, rw, rh in exclude_rects or []:
        c0, c1 = int(np.floor(x * cols / w)), int(np.ceil((x + rw) * cols / w))
        r0, r1 = int(np.floor(y * rows / h)), int(np.ceil((y + rh) * rows / h))
        keep[max(r0, 0):r1, max(c0, 0):c1] = False
    return keep


def analyse_shade(img_bgr: np.ndarray, ref_rect=None, test_rect=None, tolerance: float = 1.0,
                  cell: int | None = None, heat_max: float | None = None, white_rect=None,
                  exclude_rects=None) -> ShadeResult:
    """
    ref_rect / test_rect: (x, y, w, h). If ref_rect is None, the reference is the MEDIAN colour of all
    cells (= the typical shade of the piece). If test_rect is None, the worst 5% of cells are the test
    (= the most off-shade area). Pass/fail uses delta E CMC(2:1) <= tolerance
    (1.0 is a common commercial tolerance; use the buyer's value if known).
    exclude_rects: areas to ignore, e.g. boxes of detected stains/holes - otherwise a stain would also be
    reported as shade variation (double counting).
    """
    h, w = img_bgr.shape[:2]
    cell = cell or max(8, min(h, w) // 24)
    if white_rect is not None:
        img_bgr = white_balance(img_bgr, white_rect)
    lab = to_lab(img_bgr)
    rows, cols = max(1, h // cell), max(1, w // cell)
    cells = cv2.resize(lab.astype(np.float32), (cols, rows), interpolation=cv2.INTER_AREA).astype(np.float64)
    keep = _cell_mask((h, w), (rows, cols), exclude_rects)
    if keep.mean() < 0.2:            # defects cover almost everything -> no reliable shade reference
        keep[:] = True

    if ref_rect is not None:
        ref = region_mean(lab, ref_rect)
    else:
        ref = np.median(cells[keep], axis=0)

    heat = delta_e_map(lab, ref, cell, "cmc")
    if test_rect is not None:
        test = region_mean(lab, test_rect)
    else:  # mean colour of the most different 5% of the (non-excluded) cells
        vals, cand = heat[keep], cells[keep]
        k = max(1, int(0.05 * len(vals)))
        test = cand[np.argsort(vals)[-k:]].mean(axis=0)

    details = color_difference(ref, test)
    value = details["dE_cmc21"]
    pct = float((heat[keep] > tolerance).mean() * 100)
    heat_disp = np.where(keep, heat, 0.0)
    overlay = _draw_overlay(img_bgr, heat_disp, tolerance, heat_max or 3 * tolerance, ref_rect, test_rect)
    for x, y, rw, rh in exclude_rects or []:
        cv2.rectangle(overlay, (int(x), int(y)), (int(x + rw), int(y + rh)), (200, 200, 200), 1)
    return ShadeResult(value <= tolerance, tolerance, "CMC(2:1)", value, details, pct, heat_disp, overlay)


def _draw_overlay(img, heat, tol, vmax, ref_rect, test_rect):
    h, w = img.shape[:2]
    norm = np.clip(heat / vmax * 255, 0, 255).astype(np.uint8)
    color = cv2.applyColorMap(cv2.resize(norm, (w, h), interpolation=cv2.INTER_NEAREST), cv2.COLORMAP_JET)
    out = cv2.addWeighted(img, 0.45, color, 0.55, 0)
    # outline cells beyond tolerance
    mask = cv2.resize((heat > tol).astype(np.uint8) * 255, (w, h), interpolation=cv2.INTER_NEAREST)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cv2.drawContours(out, contours, -1, (255, 255, 255), max(1, w // 400))
    for rect, label, col in ((ref_rect, "REF", (0, 255, 0)), (test_rect, "TEST", (0, 0, 255))):
        if rect is not None:
            x, y, rw, rh = map(int, rect)
            cv2.rectangle(out, (x, y), (x + rw, y + rh), col, max(2, w // 300))
            cv2.putText(out, label, (x + 4, y + 22), cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
    # colour bar legend
    bar = cv2.applyColorMap(np.linspace(0, 255, 256, dtype=np.uint8).reshape(1, -1).repeat(14, 0), cv2.COLORMAP_JET)
    bw = min(w - 20, 256)
    out[h - 30:h - 16, 10:10 + bw] = cv2.resize(bar, (bw, 14))
    cv2.putText(out, f"0", (10, h - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    cv2.putText(out, f"dE {vmax:.1f}", (bw - 40, h - 34), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1)
    return out


if __name__ == "__main__":
    import sys
    img = cv2.imread(sys.argv[1])
    res = analyse_shade(img)
    print(res.summary())
    out = sys.argv[2] if len(sys.argv) > 2 else "shade_overlay.jpg"
    cv2.imwrite(out, res.overlay)
    print("overlay saved to", out)
