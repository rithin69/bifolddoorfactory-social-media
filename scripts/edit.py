"""Honest, photo-by-photo edits for social posts.

Every photo is measured first: its size and shape, exposure, clipped
highlights, dark areas, colour cast, saturation, sharpness, noise, how
tilted its vertical lines are, and where the structure (door frames,
glazing bars, walls) sits. The edit is then built for that photo alone.
It only crops, straightens, corrects perspective, reduces noise and adjusts
light and colour: it never adds, removes or changes anything in the picture.
All metadata, including GPS location, is stripped.

Makes a feed version for Instagram and Facebook (<name>-feed.jpg) and a
9:16 vertical version for TikTok (<name>-9x16.jpg, 1080x1920).

The feed version is 4:5 (1080x1350) when the doors and frames fit inside a
4:5 crop. When they don't, nothing is cut off: the whole photo is shown on
a softly blurred background ("fit"), or, for a post whose photos are all
landscape, the photo is kept at its own shape ("native", 1080 wide).
Crops are chosen by looking for the structure in the photo and never cut
through a door frame or mullion when they can avoid it.

1. Measure a photo and see the suggested settings, with the reason for each:
     python scripts/edit.py INPUT --analyse

2. Edit it. Every setting you leave out uses the suggestion for this photo;
   anything you pass overrides it. (--preset none starts from no changes.)
     python scripts/edit.py INPUT --name ealing-bifold-1 \
         [--feed auto|crop|fit|native] [--tall auto|crop|fit] [--focus x,y] \
         [--rotate n] [--keystone n] [--auto 0|1] [--denoise n] \
         [--shadows n] [--highlights n] [--brightness n] [--contrast n] \
         [--clarity n] [--saturation n] [--warmth n] [--sharpen 0|1] \
         [--out images/2026-11-16]

--feed       auto (default) = 4:5 crop when the structure fits, else fit;
             crop = always crop to 4:5 around the structure; fit = whole
             photo on a blurred 4:5 background; native = the photo's own
             shape, 1080 wide (landscape or square photos only)
--tall       auto (default) = 9:16 crop when the structure fits, else fit
--focus      only if the automatic crop chose badly: the subject's centre as
             x,y fractions of the photo (0 to 1)
--rotate     degrees to straighten, positive = anticlockwise (within 5)
--keystone   fixes walls and frames leaning in because the phone was tilted
             (within 0.2): positive when they narrow towards the top
--auto       1 = automatic levels and white balance, 0 = off (keep warm light)
--denoise    0 = off, up to 10 for grainy low-light photos
--shadows    0 to 0.5: lift dark areas
--highlights 0 to 0.5: recover bright sky, windows and glare
--brightness 0.8 to 1.3 (1.0 = unchanged)
--contrast   0.9 to 1.2 (1.0 = unchanged)
--clarity    0 to 1: local contrast on detailed areas (frames, brickwork);
             smooth areas such as sky and plain walls are left alone
--saturation 0.9 to 1.15 (1.0 = unchanged)
--warmth     -0.08 to 0.08 (0 = unchanged)
--sharpen    1 = extra sharpening for a soft photo (output sharpening is always on)
"""
import argparse
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    from pillow_heif import register_heif_opener  # iPhone HEIC photos
    register_heif_opener()
except ImportError:
    pass

FEED_RATIO = 4 / 5
TALL_RATIO = 9 / 16
FEED_SIZE = (1080, 1350)
TALL_SIZE = (1080, 1920)
KEEP = 0.97          # a crop must keep this share of the structure, or we don't crop
LIMITS = {
    'rotate': (-5, 5), 'keystone': (-0.2, 0.2), 'denoise': (0, 10),
    'shadows': (0, 0.5), 'highlights': (0, 0.5), 'brightness': (0.8, 1.3),
    'contrast': (0.9, 1.2), 'clarity': (0, 1), 'saturation': (0.9, 1.15),
    'warmth': (-0.08, 0.08),
}
NEUTRAL = {
    'rotate': 0.0, 'keystone': 0.0, 'auto': 1, 'denoise': 0.0, 'shadows': 0.0,
    'highlights': 0.0, 'brightness': 1.0, 'contrast': 1.0, 'clarity': 0.0,
    'saturation': 1.0, 'warmth': 0.0, 'sharpen': 0, 'feed': 'auto', 'tall': 'auto',
}
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def as_array(img):
    return np.asarray(img, dtype=np.float32) / 255.0


def as_image(arr):
    return Image.fromarray((np.clip(arr, 0, 1) * 255 + 0.5).astype(np.uint8))


def small(img, long_side=1000):
    s = long_side / max(img.size)
    return img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS) if s < 1 else img


# ── measuring ──────────────────────────────────────────────────────────────

def find_lines(img):
    """Long straight lines at a working size: the frames, mullions, walls and
    floor lines that give a glazing photo its structure. Brick courses,
    rubble and foliage are too short to count."""
    g = np.asarray(small(img).convert('L'))
    h, w = g.shape
    edges = cv2.Canny(cv2.GaussianBlur(g, (3, 3), 0), 50, 150)
    found = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=60, minLineLength=int(min(h, w) * 0.1), maxLineGap=6)
    lines = found.reshape(-1, 4).astype(float) if found is not None else np.zeros((0, 4))
    return g.shape, lines


def measure_lines(shape, lines):
    """Fits the lean of near-vertical lines across the photo:
    lean = tilt + convergence * position. Tilt gives the rotation,
    convergence gives the keystone."""
    h, w = shape
    leans, pos, weight = [], [], []
    for x1, y1, x2, y2 in lines:
        if abs(y2 - y1) < 3 * abs(x2 - x1) or y1 == y2:
            continue  # not within about 18 degrees of vertical
        if y1 > y2:
            x1, y1, x2, y2 = x2, y2, x1, y1  # (x1, y1) is the top end
        lean = (x1 - x2) / (y2 - y1)
        if abs(lean) > 0.21:
            continue  # leans more than 12 degrees: a diagonal, not a vertical
        leans.append(lean)
        pos.append(((x1 + x2) / 2 - w / 2) / w)
        weight.append(math.hypot(x2 - x1, y2 - y1))
    n = len(leans)
    lean, u, wt = np.array(leans), np.array(pos), np.array(weight)
    left, right = int((u < -0.12).sum()), int((u > 0.12).sum())
    result = {
        'vertical_lines': n,
        'lines_found_on': 'none' if n == 0 else 'both sides' if left and right else 'left side only' if left else 'right side only' if right else 'centre only',
        'rotate': 0.0, 'keystone': 0.0, 'lines_reliable': False,
    }
    # Tilt and perspective can only be told apart with lines on both sides:
    # lines on one side may lean because of the lens, not because the photo
    # is rotated.
    if n < 4 or not (left >= 2 and right >= 2):
        return result
    keep = np.ones(n, bool)
    for _ in range(3):   # fit, drop lines that disagree by over 1.5 degrees, refit
        A = np.stack([np.ones(keep.sum()), u[keep]], 1) * np.sqrt(wt[keep])[:, None]
        a, b = np.linalg.lstsq(A, lean[keep] * np.sqrt(wt[keep]), rcond=None)[0]
        keep = np.abs(lean - (a + b * u)) < 0.026
        if keep.sum() < 4:
            return result
    if wt[keep].sum() < 0.5 * wt.sum() or (u[keep] < -0.12).sum() < 2 or (u[keep] > 0.12).sum() < 2:
        return result
    result.update(rotate=round(math.degrees(math.atan(a)), 2), keystone=round(float(-b * h / w), 3), lines_reliable=True)
    return result


def structure_maps(shape, lines):
    """Two maps at the working size: where the near-vertical structure is
    (frames, mullions, jambs) and where the near-horizontal structure is
    (heads, thresholds, floor and ceiling lines), each line weighted by its
    length. Diagonals (roofs, perspective lines) are left out."""
    h, w = shape
    vmap, hmap = np.zeros((h, w), np.float32), np.zeros((h, w), np.float32)
    for x1, y1, x2, y2 in lines:
        dx, dy, n = x2 - x1, y2 - y1, math.hypot(x2 - x1, y2 - y1)
        if abs(dy) >= 3 * abs(dx):
            cv2.line(vmap, (int(x1), int(y1)), (int(x2), int(y2)), float(n), 2)
        elif abs(dx) >= 3 * abs(dy):
            cv2.line(hmap, (int(x1), int(y1)), (int(x2), int(y2)), float(n), 2)
    return vmap, hmap


def span(profile, lo=0.01, hi=0.99):
    """Where the weight of a 1-D profile sits, as fractions, ignoring the
    outer 1% at each end so a stray line doesn't stretch it."""
    total = profile.sum()
    if total <= 0:
        return 0.0, 1.0
    c = np.cumsum(profile) / total
    return float(np.searchsorted(c, lo) / len(profile)), float((np.searchsorted(c, hi) + 1) / len(profile))


def best_window(profile, win, cut):
    """The offset of a window of `win` samples that keeps the most structure
    and whose two edges fall where there is the least structure to cut
    through. Returns (offset, share of the structure kept)."""
    n = len(profile)
    if win >= n:
        return 0, 1.0
    total = profile.sum()
    if total <= 0:
        return (n - win) // 2, 1.0
    cs = np.concatenate([[0.0], np.cumsum(profile)])
    offs = np.arange(0, n - win + 1)
    inside = cs[offs + win] - cs[offs]
    penalty = cut[offs] + cut[offs + win - 1]
    score = inside - 2.0 * penalty - 0.02 * total * np.abs(offs - (n - win) / 2) / max(1, n - win)
    off = int(offs[np.argmax(score)])
    return off, float(inside[off] / total)


def crop_plan(shape, vmap, hmap, ratio):
    """Plans a crop of the given width:height ratio around the structure.
    Returns the crop box as fractions and the share of structure it keeps."""
    h, w = shape
    if w / h > ratio:            # too wide: choose where to cut left and right
        win = int(round(h * ratio))
        col = vmap.sum(0) + 0.3 * hmap.sum(0)
        cut = cv2.blur(vmap.sum(0).reshape(1, -1), (max(3, int(w * 0.015)), 1)).ravel()
        off, kept = best_window(col, win, cut)
        return (off / w, 0.0, (off + win) / w, 1.0), kept
    if w / h < ratio:            # too tall: choose where to cut top and bottom
        win = int(round(w / ratio))
        row = hmap.sum(1) + 0.3 * vmap.sum(1)
        cut = cv2.blur(hmap.sum(1).reshape(-1, 1), (1, max(3, int(h * 0.015)))).ravel()
        off, kept = best_window(row, win, cut)
        return (0.0, off / h, 1.0, (off + win) / h), kept
    return (0.0, 0.0, 1.0, 1.0), 1.0


def measure(img):
    arr = as_array(small(img))
    L = arr @ LUMA
    p2, p50, p98 = np.percentile(L, [2, 50, 98])
    mid = (L > 0.2) & (L < 0.85)
    r, g, b = (arr[mid].mean(0) if mid.sum() > 500 else arr.reshape(-1, 3).mean(0))
    hsv = cv2.cvtColor((arr * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)
    grey = (L * 255).astype(np.float32)
    # Immerkaer's fast noise estimate, at full resolution (a centre crop, for
    # speed), because downsizing hides grain.
    full = np.asarray(img.convert('L'), dtype=np.float32)
    fh, fw = full.shape
    cy, cx, half = fh // 2, fw // 2, 750
    full = full[max(0, cy - half):cy + half, max(0, cx - half):cx + half]
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    hh, ww = full.shape
    noise = math.sqrt(math.pi / 2) / (6 * (ww - 2) * (hh - 2)) * np.abs(cv2.filter2D(full, -1, k)[1:-1, 1:-1]).sum()
    shape, lines = find_lines(img)
    vmap, hmap = structure_maps(shape, lines)
    x0, x1 = span(vmap.sum(0))
    y0, y1 = span(hmap.sum(1) + vmap.sum(1))
    feed_box, feed_kept = crop_plan(shape, vmap, hmap, FEED_RATIO)
    tall_box, tall_kept = crop_plan(shape, vmap, hmap, TALL_RATIO)
    m = {
        'width': img.width, 'height': img.height,
        'shape': 'landscape' if img.width > img.height * 1.1 else 'portrait' if img.height > img.width * 1.1 else 'square',
        'median_brightness': round(float(p50), 3),
        'range': round(float(p98 - p2), 3),
        'dark_share': round(float((L < 0.1).mean()), 3),
        'clipped_share': round(float((L > 0.98).mean()), 3),
        'cast_red_blue': round(float(r - b), 3),
        'cast_green': round(float(g - (r + b) / 2), 3),
        'saturation': round(float(hsv[..., 1].mean() / 255), 3),
        'sharpness': round(float(cv2.Laplacian(grey, cv2.CV_32F).var()), 1),
        'noise': round(float(noise), 2),
        'structure_lines': int(len(lines)),
        'structure_box': [round(x0, 2), round(y0, 2), round(x1, 2), round(y1, 2)],
        'feed_crop': {'box': [round(v, 3) for v in feed_box], 'keeps': round(feed_kept, 3)},
        'tall_crop': {'box': [round(v, 3) for v in tall_box], 'keeps': round(tall_kept, 3)},
    }
    m.update(measure_lines(shape, lines))
    return m


def suggest(m):
    """Settings for this photo, each with the reason."""
    s, why = dict(NEUTRAL), {}
    if not m['lines_reliable']:
        why['lines'] = f"straightening not measured (vertical lines: {m['lines_found_on']}); judge it by eye"
    if m['lines_reliable'] and abs(m['rotate']) >= 0.4:
        s['rotate'] = round(max(-5, min(5, m['rotate'] * 0.9)), 2)
        why['rotate'] = f"vertical lines lean {m['rotate']} degrees on average"
    if m['lines_reliable'] and abs(m['keystone']) >= 0.025:
        s['keystone'] = round(max(-0.15, min(0.15, m['keystone'] * 0.8)), 3)
        why['keystone'] = f"verticals converge (measured {m['keystone']}); corrected at 80%, up to 0.15, so it still looks natural"
    p50 = m['median_brightness']
    if p50 < 0.35 and m['cast_red_blue'] > 0.06:
        s['auto'] = 0
        why['auto'] = 'warm low light (evening or interior lamps): levels and white balance left alone'
    if m['noise'] > 4.5 and p50 < 0.45:
        s['denoise'] = round(min(10, (m['noise'] - 3) * 1.5), 1)
        why['denoise'] = f"grainy (noise {m['noise']}) and dark"
    if p50 < 0.38 or m['dark_share'] > 0.18:
        s['shadows'] = round(min(0.45, 0.15 + max(0, 0.38 - p50) * 1.5 + max(0, m['dark_share'] - 0.18)), 2)
        why['shadows'] = f"dark photo (median {p50}, {round(m['dark_share'] * 100)}% near black)"
    if p50 < 0.33:
        s['brightness'] = round(1 + min(0.12, (0.4 - p50) * 0.5), 2)
        why['brightness'] = 'underexposed overall'
    elif p50 > 0.68:
        s['brightness'] = 0.95
        why['brightness'] = 'very bright overall'
    if m['clipped_share'] > 0.015:
        s['highlights'] = round(min(0.4, 0.15 + m['clipped_share'] * 3), 2)
        why['highlights'] = f"{round(m['clipped_share'] * 100, 1)}% of the photo is blown out (sky, windows or glare)"
    if m['range'] < 0.6:
        s['contrast'] = 1.06
        why['contrast'] = f"flat or hazy (tonal range {m['range']})"
    s['clarity'] = 0.15 if m['noise'] > 5 else 0.4
    why['clarity'] = 'kept low because the photo is grainy' if m['noise'] > 5 else 'standard crispness for frames and brickwork; sky and plain walls are left smooth'
    if m['saturation'] < 0.15:
        s['saturation'] = 1.08
        why['saturation'] = 'washed-out colour'
    elif m['saturation'] < 0.25:
        s['saturation'] = 1.04
        why['saturation'] = 'slightly muted colour'
    if m['sharpness'] < 120:
        s['sharpen'] = 1
        why['sharpen'] = f"soft (sharpness {m['sharpness']})"
    fk, tk = m['feed_crop']['keeps'], m['tall_crop']['keeps']
    if fk >= KEEP:
        s['feed'] = 'crop'
        why['feed'] = f"a 4:5 crop keeps {round(fk * 100)}% of the frames and glazing"
    else:
        s['feed'] = 'fit'
        why['feed'] = f"a 4:5 crop would cut off {round((1 - fk) * 100)}% of the frames and glazing, so the whole photo is shown on a blurred background (or use --feed native if every photo in the post is landscape)"
    if tk >= KEEP:
        s['tall'] = 'crop'
        why['tall'] = f"a 9:16 crop keeps {round(tk * 100)}% of the structure"
    else:
        s['tall'] = 'fit'
        why['tall'] = f"a 9:16 crop would cut off {round((1 - tk) * 100)}% of the structure, so the whole photo is shown on a blurred background"
    short = min(m['width'], m['height'])
    if short < 1080:
        why['size'] = f"small photo ({m['width']}x{m['height']}): it will be enlarged and may look soft"
    return s, why


# ── editing ────────────────────────────────────────────────────────────────

def largest_rotated_rect(w, h, angle):
    if w <= 0 or h <= 0:
        return 0, 0
    long_side, short_side = (w, h) if w >= h else (h, w)
    sin_a, cos_a = abs(math.sin(angle)), abs(math.cos(angle))
    if short_side <= 2.0 * sin_a * cos_a * long_side or abs(sin_a - cos_a) < 1e-10:
        x = 0.5 * short_side
        wr, hr = (x / sin_a, x / cos_a) if w >= h else (x / cos_a, x / sin_a)
    else:
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr, hr = (w * cos_a - h * sin_a) / cos_2a, (h * cos_a - w * sin_a) / cos_2a
    return int(wr), int(hr)


def straighten(img, degrees):
    if abs(degrees) < 0.05:
        return img
    w, h = img.size
    rotated = img.rotate(degrees, resample=Image.BICUBIC, expand=False)
    cw, ch = largest_rotated_rect(w, h, math.radians(degrees))
    left, top = (w - cw) // 2, (h - ch) // 2
    return rotated.crop((left, top, left + cw, top + ch))


def keystone(img, k):
    """Stretches a trapezoid of the photo to the full frame, so converging
    verticals become parallel; the corners left out are trimmed, not filled."""
    if abs(k) < 0.005:
        return img
    w, h = img.size
    inset = abs(k) * w / 2
    quad = (inset, 0, 0, h, w, h, w - inset, 0) if k > 0 else (0, 0, inset, h, w - inset, h, w, 0)
    out = img.transform((w, h), Image.QUAD, quad, resample=Image.BICUBIC)
    trim = int(h * abs(k) * 0.25)  # keeps doors and windows in natural proportion
    return out.crop((0, trim, w, h)) if k > 0 else out.crop((0, 0, w, h - trim))


def denoise(img, strength):
    if strength < 0.5:
        return img
    arr = np.asarray(img)
    out = cv2.fastNlMeansDenoisingColored(arr, None, strength, strength, 7, 21)
    return Image.fromarray(out)


def auto_tone(img, m):
    """Gentle levels, then a white balance whose strength follows how strong
    the measured colour cast is, so neutral photos are left alone."""
    levelled = ImageOps.autocontrast(img, cutoff=(0.5, 0.5), preserve_tone=True)
    arr = as_array(Image.blend(img, levelled, 0.6))
    cast = abs(m['cast_red_blue']) + abs(m['cast_green'])
    if cast > 0.02:
        L = arr @ LUMA
        mid = (L > 0.2) & (L < 0.85)
        means = arr[mid].mean(0) if mid.sum() > 500 else arr.reshape(-1, 3).mean(0)
        gains = np.clip(means.mean() / np.maximum(means, 1e-3), 0.88, 1.12)
        strength = min(0.75, cast * 10)
        arr = arr * (1 + (gains - 1) * strength)
    return as_image(arr)


def shadows_highlights(img, shadows, highlights):
    """Tone curve on brightness only, so colours keep their hue."""
    if shadows < 0.001 and highlights < 0.001:
        return img
    arr = as_array(img)
    L = arr @ LUMA
    curve = L + shadows * 1.8 * L * (1 - L) ** 2 - highlights * 1.8 * L ** 2 * (1 - L)
    ratio = np.where(L > 1e-4, curve / np.maximum(L, 1e-4), 1.0)
    return as_image(arr * ratio[..., None])


def clarity(img, amount):
    """Local contrast with CLAHE on the lightness channel, blended in only
    where there is detail. Smooth areas (sky, plain walls, glass) keep their
    even tone instead of turning blotchy."""
    if amount < 0.01:
        return img
    lab = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2LAB)
    l = lab[..., 0].astype(np.float32)
    tiles = max(4, round(max(img.size) / 400))
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(tiles, tiles))
    l2 = clahe.apply(lab[..., 0]).astype(np.float32)
    k = max(9, int(max(img.size) / 60) | 1)
    mean = cv2.blur(l, (k, k))
    std = np.sqrt(np.maximum(cv2.blur(l * l, (k, k)) - mean * mean, 0)) / 255.0
    detail = np.clip((std - 0.025) / 0.07, 0, 1)      # 0 on smooth areas, 1 on detailed ones
    a = amount * 0.6 * detail
    lab[..., 0] = np.clip(l * (1 - a) + l2 * a, 0, 255).astype(np.uint8)
    return Image.fromarray(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB))


def warm(img, amount):
    if abs(amount) < 0.001:
        return img
    arr = as_array(img)
    arr[..., 0] *= 1 + amount
    arr[..., 2] *= 1 - amount
    return as_image(arr)


def crop_box(img, box):
    w, h = img.size
    return img.crop((int(box[0] * w), int(box[1] * h), int(box[2] * w), int(box[3] * h)))


def crop_focus(img, ratio, fx, fy):
    w, h = img.size
    cw, ch = (int(h * ratio), h) if w / h > ratio else (w, int(w / ratio))
    left = min(max(int(fx * w - cw / 2), 0), w - cw)
    top = min(max(int(fy * h - ch / 2), 0), h - ch)
    return img.crop((left, top, left + cw, top + ch))


def fit_frame(whole, size):
    """The whole photo, as large as it fits, on a softly blurred and darkened
    copy of itself, so nothing is cut off."""
    tw, th = size
    back = ImageOps.fit(whole, size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(45))
    back = ImageEnhance.Brightness(back).enhance(0.75)
    s = min(tw / whole.width, th / whole.height)
    front = whole.resize((round(whole.width * s), round(whole.height * s)), Image.LANCZOS)
    back.paste(front, ((tw - front.width) // 2, (th - front.height) // 2))
    return back


def output_sharpen(img, extra):
    """Downsizing softens edges; restore them, a little more if the photo was soft."""
    return img.filter(ImageFilter.UnsharpMask(radius=0.8 if not extra else 1.1, percent=35 if not extra else 70, threshold=2))


def clamp(name, value):
    lo, hi = LIMITS[name]
    if value < lo or value > hi:
        print(f'note: {name} {value} is outside the honest-edit range, using {min(max(value, lo), hi)}')
    return min(max(value, lo), hi)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('--analyse', action='store_true')
    p.add_argument('--preset', choices=['auto', 'none'], default='auto')
    p.add_argument('--name')
    p.add_argument('--focus')
    for k in ('rotate', 'keystone', 'denoise', 'shadows', 'highlights', 'brightness', 'contrast', 'clarity', 'saturation', 'warmth'):
        p.add_argument(f'--{k}', type=float)
    p.add_argument('--auto', type=int, choices=[0, 1])
    p.add_argument('--sharpen', type=int, choices=[0, 1])
    p.add_argument('--feed', choices=['auto', 'crop', 'fit', 'native'])
    p.add_argument('--tall', choices=['auto', 'crop', 'fit', 'blur'])
    p.add_argument('--out', default='ready')
    a = p.parse_args()

    img = ImageOps.exif_transpose(Image.open(a.input)).convert('RGB')  # upright, no metadata carried over
    m = measure(img)
    suggested, why = suggest(m)
    if a.analyse:
        print(json.dumps({'measured': m, 'suggested': suggested, 'why': why}, indent=1))
        return 0
    if not a.name:
        p.error('--name is required unless --analyse is used')

    s = dict(suggested if a.preset == 'auto' else NEUTRAL)
    for k in s:
        if getattr(a, k) is not None:
            s[k] = getattr(a, k)
    for k in LIMITS:
        s[k] = clamp(k, s[k])
    if s['tall'] == 'blur':
        s['tall'] = 'fit'
    if s['feed'] == 'auto':
        s['feed'] = suggested['feed'] if suggested['feed'] != 'auto' else 'crop'
    if s['tall'] == 'auto':
        s['tall'] = suggested['tall'] if suggested['tall'] != 'auto' else 'crop'
    if s['feed'] == 'native' and m['height'] > m['width'] * 1.25:
        print('note: native is for landscape or square photos; this one is portrait, using a 4:5 crop')
        s['feed'] = 'crop'

    img = straighten(img, s['rotate'])
    img = keystone(img, s['keystone'])
    # The crop plan is re-measured after straightening, because the frame moved.
    shape, lines = find_lines(img)
    vmap, hmap = structure_maps(shape, lines)
    img = denoise(img, s['denoise'])
    if s['auto']:
        img = auto_tone(img, m)
    img = shadows_highlights(img, s['shadows'], s['highlights'])
    img = ImageEnhance.Brightness(img).enhance(s['brightness'])
    img = ImageEnhance.Contrast(img).enhance(s['contrast'])
    img = clarity(img, s['clarity'])
    img = ImageEnhance.Color(img).enhance(s['saturation'])
    img = warm(img, s['warmth'])

    os.makedirs(a.out, exist_ok=True)
    report = {k: s[k] for k in s if s[k] != NEUTRAL[k]}
    outputs = []

    # Feed version (Instagram and Facebook)
    if s['feed'] == 'native':
        ratio = max(FEED_RATIO, min(1.91, img.width / img.height))
        feed = img if abs(img.width / img.height - ratio) < 0.01 else crop_box(img, crop_plan(shape, vmap, hmap, ratio)[0])
        size = (1080, round(1080 * feed.height / feed.width))
        report['feed_used'] = f'native {feed.width}:{feed.height}, nothing cut off'
    elif s['feed'] == 'fit':
        feed, size = fit_frame(img, FEED_SIZE), FEED_SIZE
        report['feed_used'] = 'fit: whole photo on a blurred 4:5 background'
    else:
        if a.focus:
            fx, fy = (min(max(float(v), 0.0), 1.0) for v in a.focus.split(','))
            feed, note = crop_focus(img, FEED_RATIO, fx, fy), f'4:5 crop around focus {fx},{fy}'
        else:
            box, kept = crop_plan(shape, vmap, hmap, FEED_RATIO)
            feed, note = crop_box(img, box), f'4:5 crop keeping {round(kept * 100)}% of the structure'
            if kept < KEEP:
                print(f'warning: the 4:5 crop cuts off {round((1 - kept) * 100)}% of the frames and glazing; consider --feed fit or native')
        size = FEED_SIZE
        report['feed_used'] = note
    outputs.append(('feed', feed, size))

    # 9:16 version (TikTok)
    if s['tall'] == 'fit':
        tall, note = fit_frame(img, TALL_SIZE), 'fit: whole photo on a blurred 9:16 background'
    elif a.focus:
        fx, fy = (min(max(float(v), 0.0), 1.0) for v in a.focus.split(','))
        tall, note = crop_focus(img, TALL_RATIO, fx, fy), f'9:16 crop around focus {fx},{fy}'
    else:
        box, kept = crop_plan(shape, vmap, hmap, TALL_RATIO)
        tall, note = crop_box(img, box), f'9:16 crop keeping {round(kept * 100)}% of the structure'
        if kept < KEEP:
            print(f'warning: the 9:16 crop cuts off {round((1 - kept) * 100)}% of the structure; consider --tall fit')
    report['tall_used'] = note
    outputs.append(('9x16', tall, TALL_SIZE))

    for label, picture, (tw, th) in outputs:
        if picture.width < tw * 0.6:
            print(f'warning: {label} uses only {picture.width}px of width, so it will look soft when enlarged')
        out = picture.resize((tw, th), Image.LANCZOS) if picture.size != (tw, th) else picture
        out = output_sharpen(out, s['sharpen'])
        path = os.path.join(a.out, f'{a.name}-{label}.jpg')
        out.save(path, 'JPEG', quality=92, subsampling=0, optimize=True, progressive=True)  # no EXIF
        print(path)
    print('settings: ' + json.dumps(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
