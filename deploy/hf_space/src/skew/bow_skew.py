"""Bowing and skewing measurement from a fabric photo (weft-line angle detection).

Definitions (ASTM D3882 / ISO 13015 style):
  SKEW: the weft is straight but slanted.        skew % = d / W x 100
        (d = how much higher/lower one selvedge end of the weft is than the other, W = width)
  BOW:  the weft is curved (arc / bow shape).    bow %  = depth / W x 100
        (depth = largest distance between the curved weft and the straight line joining its ends)

Main method - projection profile (a Radon-transform-type method), explained simply:
  If we add up the brightness of every image ROW, the weft yarns make a sharp stripe pattern
  (bright yarn, dark gap, bright yarn ...) - but ONLY when the weft lines are exactly horizontal.
  If they are tilted, rows mix yarn and gap and the stripe pattern gets blurry.
  So we tilt (shear) the image by many small angles and keep the angle where the stripe
  pattern is sharpest. That angle = the weft angle.
  We do this separately in several vertical STRIPS across the width. From the angle in each strip
  we rebuild the shape of one weft line across the fabric: a straight slanted line = skew,
  a curve = bow.

Cross-check - FFT (Fourier transform): the regular yarn spacing gives a bright peak in the 2-D
  frequency spectrum; its direction gives the global weft angle independently.

Assumptions: photo taken straight from above, weft running roughly left-right (or set
weft="vertical"), the camera not rotated relative to the fabric edge (selvedge / table edge).
For a real measurement, align the camera with the selvedge - the module measures the weft
angle relative to the image frame.
"""
from dataclasses import dataclass, field
import cv2
import numpy as np


def _prep(img_bgr, weft="horizontal", max_side=1200):
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY) if img_bgr.ndim == 3 else img_bgr
    if weft == "vertical":
        gray = cv2.rotate(gray, cv2.ROTATE_90_COUNTERCLOCKWISE)
    s = max_side / max(gray.shape)
    if s < 1:
        gray = cv2.resize(gray, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
    gray = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    return gray.astype(np.float32)


def _sharpness(gray, angle_deg, margin):
    """Shear so that a line at angle_deg becomes horizontal; return stripe sharpness of row profile."""
    h, w = gray.shape
    t = np.tan(np.radians(angle_deg))
    M = np.float32([[1, 0, 0], [-t, 1, t * w / 2]])   # y' = y - t (x - w/2)
    sh = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    prof = sh[margin:h - margin].mean(axis=1)
    return float(np.var(np.diff(prof)))


def weft_angle(gray, max_angle=12.0):
    """Angle (degrees) of weft lines in this image/strip. + = line goes DOWN to the right (image coords)."""
    h, w = gray.shape
    margin = int(np.ceil(np.tan(np.radians(max_angle)) * w / 2)) + 2
    if h - 2 * margin < 20:
        raise ValueError("strip too short for the angle range")
    coarse = np.arange(-max_angle, max_angle + 1e-9, 0.25)
    scores = [_sharpness(gray, a, margin) for a in coarse]
    best = coarse[int(np.argmax(scores))]
    fine = np.arange(best - 0.3, best + 0.3 + 1e-9, 0.02)
    scores = np.array([_sharpness(gray, a, margin) for a in fine])
    i = int(np.argmax(scores))
    if 0 < i < len(fine) - 1:  # parabolic refinement of the peak
        y0, y1, y2 = scores[i - 1:i + 2]
        den = y0 - 2 * y1 + y2
        off = 0.5 * (y0 - y2) / den if den != 0 else 0
        return float(fine[i] + off * 0.02)
    return float(fine[i])


def fft_angle(gray, max_angle=20.0):
    """Global weft angle from the 2-D FFT peak (independent cross-check)."""
    g = gray - gray.mean()
    g *= np.outer(np.hanning(g.shape[0]), np.hanning(g.shape[1]))
    n = 2048
    F = np.abs(np.fft.fftshift(np.fft.fft2(g, s=(n, n))))
    fy, fx = np.meshgrid(np.fft.fftshift(np.fft.fftfreq(n)), np.fft.fftshift(np.fft.fftfreq(n)), indexing="ij")
    r = np.hypot(fx, fy)
    ang = np.degrees(np.arctan2(np.abs(fx), np.abs(fy)))       # 0 = frequency vector vertical = horizontal lines
    mask = (ang <= max_angle) & (r > 4.0 / min(gray.shape)) & (r < 0.45)
    F = np.where(mask, F, 0)
    iy, ix = np.unravel_index(np.argmax(F), F.shape)
    vy, vx = fy[iy, ix], fx[iy, ix]
    if vy < 0:
        vy, vx = -vy, -vx
    return float(np.degrees(np.arctan(-vx / vy)))               # line slope dy/dx = -fx/fy


@dataclass
class SkewBowResult:
    skew_pct: float
    bow_pct: float
    skew_pct_fft: float
    strip_angles: list
    weft_profile: list            # (x, y) points of the reconstructed weft line, in pixels of analysed image
    passed: bool
    tolerances: dict
    overlay: np.ndarray = field(repr=False)

    def summary(self):
        side = "right side lower" if self.skew_pct > 0 else "left side lower"
        bow_type = "bow (centre lagging / sagging)" if self.bow_dir > 0 else "bow (centre leading)"
        return (f"Skew {abs(self.skew_pct):.2f}% ({side}), Bow {abs(self.bow_pct):.2f}% {bow_type} -> "
                f"{'PASS' if self.passed else 'FAIL'} (limits: skew {self.tolerances['skew']}%, "
                f"bow {self.tolerances['bow']}%). FFT cross-check skew: {abs(self.skew_pct_fft):.2f}%.")

    @property
    def bow_dir(self):
        return np.sign(self.bow_pct) or 1


def analyse_skew_bow(img_bgr, weft="horizontal", n_strips=7, skew_tol=3.0, bow_tol=2.0,
                     max_angle=12.0) -> SkewBowResult:
    """skew_tol / bow_tol: typical buyer limits for woven solids (stricter for checks/stripes)."""
    gray = _prep(img_bgr, weft)
    h, w = gray.shape
    edges = np.linspace(0, w, n_strips + 1).astype(int)
    angles = [weft_angle(gray[:, a:b], max_angle) for a, b in zip(edges[:-1], edges[1:])]
    # rebuild the weft line: y increases by tan(angle) * strip width in each strip
    ys = [0.0]
    for (a, b), ang in zip(zip(edges[:-1], edges[1:]), angles):
        ys.append(ys[-1] + np.tan(np.radians(ang)) * (b - a))
    xs, ys = edges.astype(float), np.array(ys)
    W = xs[-1] - xs[0]
    skew = (ys[-1] - ys[0]) / W * 100
    chord = ys[0] + (ys[-1] - ys[0]) * (xs - xs[0]) / W
    dev = ys - chord
    k = int(np.argmax(np.abs(dev)))
    bow = dev[k] / W * 100                     # + = middle of weft lower in image than its ends
    skew_fft = np.tan(np.radians(fft_angle(gray))) * 100
    passed = abs(skew) <= skew_tol and abs(bow) <= bow_tol

    # visualisation (in the analysed, possibly resized/rotated image)
    vis = cv2.cvtColor(gray.astype(np.uint8), cv2.COLOR_GRAY2BGR)
    y_mid = h / 2 - (ys.max() + ys.min()) / 2
    pts = np.stack([xs, ys + y_mid], 1).astype(np.int32)
    for a in edges[1:-1]:
        cv2.line(vis, (int(a), 0), (int(a), h), (90, 90, 90), 1)
    cv2.line(vis, tuple(pts[0]), tuple(pts[-1]), (0, 255, 255), 2)        # chord (skew)
    cv2.polylines(vis, [pts], False, (0, 0, 255), 3)                      # weft shape (bow)
    col = (0, 200, 0) if passed else (0, 0, 255)
    cv2.putText(vis, f"skew {abs(skew):.2f}%  bow {abs(bow):.2f}%  {'PASS' if passed else 'FAIL'}",
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, col, 2)
    return SkewBowResult(float(skew), float(bow), float(skew_fft), [float(a) for a in angles],
                         pts.tolist(), passed, {"skew": skew_tol, "bow": bow_tol}, vis)


if __name__ == "__main__":
    import sys
    r = analyse_skew_bow(cv2.imread(sys.argv[1]))
    print(r.summary())
    cv2.imwrite(sys.argv[2] if len(sys.argv) > 2 else "skew_overlay.jpg", r.overlay)
