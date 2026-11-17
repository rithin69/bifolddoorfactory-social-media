"""Take people out of a photo, honestly.

Finds every person (Mask R-CNN), then decides, person by person:

  remove  only when the person stands against plain background (lawn, sky,
          paving, a plain wall): no door frame, glazing bar, window, edge or
          other straight structure touches them or sits right next to them,
          and they cover a small part of the photo. The gap is filled with
          LaMa from the surrounding background. The fill is then checked: if
          it contains any new straight line (an invented frame, bar or edge)
          the removal is thrown away and the face is blurred instead.
  blur    everyone else: the face and head are blurred so nobody can be
          recognised, and nothing is invented. People behind glass, in a
          doorway, in front of the doors or in a reflection are always
          blurred, never removed.
  ignore  people too small to recognise (under 6% of the photo's height).

The doors, frames and glass are never filled in or redrawn.

Usage:
  python scripts/people.py INPUT --name NAME --out DIR [--mode auto|blur|off]

Writes DIR/NAME-clean.jpg (full size, no metadata) to pass on to edit.py,
DIR/NAME-people-check.jpg (original and result side by side, green box =
removed, orange box = face blurred) to look at, and prints a JSON report.
--mode blur never removes anyone; --mode off only reports.
Needs requirements-people.txt (PyTorch, CPU build).
"""
import argparse
import json
import math
import os
import sys
import urllib.request

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

LAMA_URL = 'https://github.com/enesmsahin/simple-lama-inpainting/releases/download/v0.1.0/big-lama.pt'
CACHE = os.path.join(os.path.expanduser('~'), '.cache', 'bdf-people')
MIN_HEIGHT = 0.06     # people shorter than this share of the photo are not recognisable
MAX_REMOVE_AREA = 0.06  # never remove a person covering more than this share of the photo
WORK = 1600           # working size for detection and the structure checks


def load_detector():
    import torchvision
    m = torchvision.models.detection.maskrcnn_resnet50_fpn_v2(weights='DEFAULT')
    return m.eval()


def load_lama():
    import torch
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, 'big-lama.pt')
    if not os.path.exists(path) or os.path.getsize(path) < 100_000_000:
        urllib.request.urlretrieve(LAMA_URL, path)
    return torch.jit.load(path, map_location='cpu').eval()


def detect_people(model, img):
    import torch
    arr = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255.0).permute(2, 0, 1)
    with torch.no_grad():
        out = model([arr])[0]
    people = []
    for label, score, mask, box in zip(out['labels'], out['scores'], out['masks'], out['boxes']):
        if int(label) == 1 and float(score) >= 0.6:
            people.append({'score': round(float(score), 2),
                           'mask': (mask[0].numpy() > 0.5).astype(np.uint8),
                           'box': [int(v) for v in box.tolist()]})
    return people


def long_lines(grey, min_len):
    edges = cv2.Canny(cv2.GaussianBlur(grey, (3, 3), 0), 50, 150)
    found = cv2.HoughLinesP(edges, 1, np.pi / 360, threshold=60, minLineLength=min_len, maxLineGap=6)
    return found.reshape(-1, 4) if found is not None else np.zeros((0, 4), int), edges


def line_map(shape, lines, extend=0.1, width=3):
    """Every straight line, extended a little at both ends: an extended line
    shows where a frame or bar runs on behind a person."""
    out = np.zeros(shape, np.uint8)
    for x1, y1, x2, y2 in lines:
        dx, dy = x2 - x1, y2 - y1
        cv2.line(out, (int(x1 - dx * extend), int(y1 - dy * extend)), (int(x2 + dx * extend), int(y2 + dy * extend)), 1, width)
    return out


def judge(person, grey, lines_mask, edges, shape):
    """remove, blur or ignore, with the reason."""
    h, w = shape
    x0, y0, x1, y1 = person['box']
    ph = y1 - y0
    if ph < MIN_HEIGHT * h:
        return 'ignore', f'too small to recognise ({round(ph / h * 100)}% of the photo height)'
    area = person['mask'].sum() / (h * w)
    if area > MAX_REMOVE_AREA:
        return 'blur', f'covers {round(area * 100)}% of the photo: too much to fill without inventing'
    pad = max(6, int(ph * 0.12))
    grown = cv2.dilate(person['mask'], cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pad + 1, 2 * pad + 1)))
    if (grown & lines_mask).any():
        return 'blur', 'a frame, glazing bar or straight edge runs through or right beside them'
    ring = cv2.dilate(grown, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * pad + 1, 2 * pad + 1))) & (1 - grown)
    if ring.sum() == 0:
        return 'blur', 'no background around them to fill from'
    busy = float((edges[ring > 0] > 0).mean())
    if busy > 0.08:
        return 'blur', f'busy background around them ({round(busy * 100)}% edges): a fill would be guesswork'
    spread = float(grey[ring > 0].std())
    if spread > 38:
        return 'blur', 'uneven background around them: a fill would be guesswork'
    return 'remove', 'plain background with no structure nearby'


def head_mask(person, shape, protect):
    """The head and shoulders of this person only, never the frames, bars
    or edges around them (those are left exactly as photographed)."""
    x0, y0, x1, y1 = person['box']
    ph, pw = y1 - y0, x1 - x0
    m = person['mask'].copy()
    m[int(y0 + max(ph * 0.32, pw * 0.6)):, :] = 0      # the top of the figure: head and shoulders
    k = max(2, int(ph * 0.015))
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
    return m & (1 - protect)


def blur_region(arr, mask, protect):
    """Blur inside the mask only: the average colour of the person's own
    pixels, so nothing from the frames around them is smeared in, and the
    protected structure is restored pixel for pixel afterwards."""
    if not mask.any():
        return arr
    ys, xs = np.nonzero(mask)
    size = max(ys.max() - ys.min(), xs.max() - xs.min())
    k = max(9, int(size * 0.25)) | 1
    m = mask.astype(np.float32)
    num = cv2.GaussianBlur(arr.astype(np.float32) * m[..., None], (k, k), 0)
    den = cv2.GaussianBlur(m, (k, k), 0)[..., None]
    blurred = np.where(den > 1e-3, num / np.maximum(den, 1e-3), arr).astype(np.float32)
    small = cv2.resize(blurred, None, fx=0.1, fy=0.1, interpolation=cv2.INTER_AREA)   # coarse, so no features survive
    blurred = cv2.resize(small, (arr.shape[1], arr.shape[0]), interpolation=cv2.INTER_LINEAR)
    soft = cv2.GaussianBlur(m, (7, 7), 0) * m      # feather inward only, never outside the person
    out = arr * (1 - soft[..., None]) + blurred * soft[..., None]
    out = np.where(protect[..., None] > 0, arr, out)
    return np.clip(out, 0, 255).astype(np.uint8)


def lama_fill(lama, arr, mask):
    """Fill the masked area from the surrounding photo, working on a crop
    around it so the result stays sharp."""
    import torch
    ys, xs = np.nonzero(mask)
    y0, y1, x0, x1 = ys.min(), ys.max(), xs.min(), xs.max()
    m = int(max(y1 - y0, x1 - x0) * 0.8) + 32
    Y0, Y1 = max(0, y0 - m), min(arr.shape[0], y1 + m)
    X0, X1 = max(0, x0 - m), min(arr.shape[1], x1 + m)
    crop, cmask = arr[Y0:Y1, X0:X1], mask[Y0:Y1, X0:X1]
    ch, cw = crop.shape[:2]
    s = min(1.0, 1024 / max(ch, cw))
    tw, th = max(8, int(cw * s) // 8 * 8), max(8, int(ch * s) // 8 * 8)
    img_t = torch.from_numpy(cv2.resize(crop, (tw, th), interpolation=cv2.INTER_AREA).astype(np.float32) / 255).permute(2, 0, 1)[None]
    msk_t = torch.from_numpy((cv2.resize(cmask, (tw, th), interpolation=cv2.INTER_NEAREST) > 0).astype(np.float32))[None, None]
    with torch.no_grad():
        out = lama(img_t, msk_t)[0].permute(1, 2, 0).numpy()
    out = cv2.resize(np.clip(out * 255, 0, 255).astype(np.uint8), (cw, ch), interpolation=cv2.INTER_CUBIC)
    soft = cv2.GaussianBlur(cmask.astype(np.float32), (9, 9), 0)[..., None]
    soft = np.maximum(soft, cmask[..., None].astype(np.float32))
    res = arr.copy()
    res[Y0:Y1, X0:X1] = (crop * (1 - soft) + out * soft).astype(np.uint8)
    return res


def invented_lines(before, after, mask, min_len):
    """Straight lines in the filled area that weren't in the photo: a sign
    the fill made up structure."""
    a, _ = long_lines(cv2.cvtColor(after, cv2.COLOR_RGB2GRAY), min_len)
    inside = 0
    for x1, y1, x2, y2 in a:
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 3))
        xs = np.linspace(x1, x2, n).astype(int).clip(0, mask.shape[1] - 1)
        ys = np.linspace(y1, y2, n).astype(int).clip(0, mask.shape[0] - 1)
        if mask[ys, xs].mean() > 0.5:
            inside += 1
    return inside


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('--name', required=True)
    p.add_argument('--out', default='ready')
    p.add_argument('--mode', choices=['auto', 'blur', 'off'], default='auto')
    a = p.parse_args()

    full = ImageOps.exif_transpose(Image.open(a.input)).convert('RGB')
    s = min(1.0, WORK / max(full.size))
    work = full.resize((round(full.width * s), round(full.height * s)), Image.LANCZOS) if s < 1 else full
    arr = np.asarray(work).copy()
    h, w = arr.shape[:2]
    grey = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    lines, edges = long_lines(grey, int(min(h, w) * 0.08))
    lmask = line_map((h, w), lines)
    # Frames and bars are wider than a line: protect a band around every
    # straight structure line so a blur can't soften or smear them.
    fw = max(3, int(w * 0.006))
    protect = cv2.dilate(line_map((h, w), lines, extend=0.0, width=1),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (2 * fw + 1, 2 * fw + 1)))

    people = detect_people(load_detector(), work)
    report = {'people_found': len(people), 'removed': 0, 'blurred': 0, 'ignored': 0, 'people': []}
    if a.mode == 'off' or not people:
        print(json.dumps(report, indent=1))
        return 0

    lama = None
    result = arr.copy()
    draw_boxes = []
    for n, person in enumerate(people, 1):
        action, why = judge(person, grey, lmask, edges, (h, w))
        if action == 'remove' and a.mode == 'blur':
            action, why = 'blur', 'blur-only mode'
        if action == 'remove':
            lama = lama or load_lama()
            k = max(5, int((person['box'][3] - person['box'][1]) * 0.05))
            hole = cv2.dilate(person['mask'], cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * k + 1, 2 * k + 1)))
            filled = lama_fill(lama, result, hole)
            made_up = invented_lines(result, filled, hole, int(min(h, w) * 0.05))
            if made_up:
                action, why = 'blur', f'the fill drew {made_up} straight line(s) that were not in the photo, so it was discarded'
            else:
                result = filled
        if action == 'blur':
            result = blur_region(result, head_mask(person, (h, w), protect), protect)
        report[{'remove': 'removed', 'blur': 'blurred', 'ignore': 'ignored'}[action]] += 1
        report['people'].append({'n': n, 'action': action, 'why': why, 'score': person['score'],
                                 'box': [round(v / (w if i % 2 == 0 else h), 3) for i, v in enumerate(person['box'])]})
        if action != 'ignore':
            draw_boxes.append((person['box'], (60, 200, 90) if action == 'remove' else (255, 150, 0)))

    os.makedirs(a.out, exist_ok=True)
    # Apply the result at full size: only the changed pixels are replaced.
    changed = (np.abs(result.astype(int) - arr.astype(int)).sum(2) > 0).astype(np.uint8)
    full_arr = np.asarray(full).copy()
    if s < 1:
        up = cv2.resize(result, full.size, interpolation=cv2.INTER_CUBIC)
        cm = cv2.resize(changed, full.size, interpolation=cv2.INTER_LINEAR).astype(np.float32)[..., None]
        cm = cv2.GaussianBlur(cm, (5, 5), 0)[..., None] if cm.ndim == 2 else cm
        full_arr = (full_arr * (1 - cm) + up * cm).astype(np.uint8)
    else:
        full_arr = result
    clean = os.path.join(a.out, f'{a.name}-clean.jpg')
    Image.fromarray(full_arr).save(clean, 'JPEG', quality=95, subsampling=0)
    before, after = Image.fromarray(arr), Image.fromarray(result)
    d = ImageDraw.Draw(before)
    for box, colour in draw_boxes:
        d.rectangle(box, outline=colour, width=max(3, w // 300))
    sheet = Image.new('RGB', (w * 2 + 10, h), (30, 30, 30))
    sheet.paste(before, (0, 0))
    sheet.paste(after, (w + 10, 0))
    sheet.thumbnail((2400, 2400))
    check = os.path.join(a.out, f'{a.name}-people-check.jpg')
    sheet.save(check, 'JPEG', quality=85)
    report.update(clean=clean, check=check)
    print(json.dumps(report, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
