"""Hide faces in a photo, honestly. Nothing is ever removed or invented.

Finds every person (Mask R-CNN), then, person by person:

  blur    the face only is blurred, from the person's own pixels, so nobody
          can be recognised. A protected band around every frame, glazing bar
          and straight edge keeps the doors exactly as photographed.
  ignore  people too small to recognise (under 6% of the photo's height).

A person who is large or central is marked PROMINENT: a blurred face there
is still the first thing anyone sees, so the report's verdict is "drop this
photo". People are never taken out of a photo: tests showed that filling the
gap always means inventing what was behind them (a doorway, a wall, part of
another person), which these posts must never do.

Usage:
  python scripts/people.py INPUT --name NAME --out DIR [--mode blur|off]

Writes DIR/NAME-clean.jpg (full size, no metadata) to pass on to edit.py,
DIR/NAME-people-check.jpg (original and result side by side, orange box =
face blurred, red box = prominent) to look at, and prints a JSON report with
a verdict. --mode off only reports.
Needs requirements-people.txt (PyTorch).
"""
import argparse
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

MIN_HEIGHT = 0.06     # people shorter than this share of the photo are not recognisable
PROMINENT_HEIGHT = 0.35  # a person taller than this share of the photo is too prominent to post blurred
PROMINENT_AREA = 0.04    # or covering more than this share of the photo
WORK = 1600           # working size for detection and the structure checks


def load_detector():
    import torchvision
    m = torchvision.models.detection.maskrcnn_resnet50_fpn_v2(weights='DEFAULT')
    return m.eval()




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




def head_mask(person, shape, protect):
    """The head and shoulders of this person only, never the frames, bars
    or edges around them (those are left exactly as photographed)."""
    x0, y0, x1, y1 = person['box']
    ph, pw = y1 - y0, x1 - x0
    m = person['mask'].copy()
    m[int(y0 + min(ph * 0.17, max(pw * 0.5, ph * 0.12))):, :] = 0      # the head only, not the body
    k = max(2, int(ph * 0.02))
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






def main():
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('--name', required=True)
    p.add_argument('--out', default='ready')
    p.add_argument('--mode', choices=['blur', 'off'], default='blur')
    a = p.parse_args()

    full = ImageOps.exif_transpose(Image.open(a.input)).convert('RGB')
    s = min(1.0, WORK / max(full.size))
    work = full.resize((round(full.width * s), round(full.height * s)), Image.LANCZOS) if s < 1 else full
    arr = np.asarray(work).copy()
    h, w = arr.shape[:2]
    grey = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    lines, edges = long_lines(grey, int(min(h, w) * 0.08))
    # Frames and bars are wider than a line: protect a band around every
    # straight structure line so a blur can't soften or smear them.
    fw = max(3, int(w * 0.006))
    protect = cv2.dilate(line_map((h, w), lines, extend=0.0, width=1),
                         cv2.getStructuringElement(cv2.MORPH_RECT, (2 * fw + 1, 2 * fw + 1)))

    people = detect_people(load_detector(), work)
    report = {'people_found': len(people), 'blurred': 0, 'ignored': 0, 'people': []}
    if a.mode == 'off' or not people:
        print(json.dumps(report, indent=1))
        return 0

    result = arr.copy()
    draw_boxes = []
    report['prominent'] = 0
    for n, person in enumerate(people, 1):
        x0, y0, x1, y1 = person['box']
        ph = y1 - y0
        cx = (x0 + x1) / 2 / w
        area = person['mask'].sum() / (h * w)
        if ph < MIN_HEIGHT * h:
            action, why = 'ignore', f'too small to recognise ({round(ph / h * 100)}% of the photo height)'
        else:
            action, why = 'blur', 'face blurred; nothing else changed'
        # A large or central person stays the first thing anyone sees even
        # with a blurred face: the photo should be dropped, not posted.
        prominent = action == 'blur' and (ph > PROMINENT_HEIGHT * h or area > PROMINENT_AREA or (0.3 < cx < 0.7 and ph > 0.18 * h))
        if prominent:
            report['prominent'] += 1
            why += '; PROMINENT: a large or central figure, so drop this photo'
        if action == 'blur':
            result = blur_region(result, head_mask(person, (h, w), protect), protect)
        report[{'blur': 'blurred', 'ignore': 'ignored'}[action]] += 1
        report['people'].append({'n': n, 'action': action, 'why': why, 'score': person['score'], 'prominent': bool(prominent),
                                 'box': [round(v / (w if i % 2 == 0 else h), 3) for i, v in enumerate(person['box'])]})
        if action != 'ignore':
            draw_boxes.append((person['box'], (220, 40, 40) if prominent else (255, 150, 0)))
    report['verdict'] = 'drop this photo' if report['prominent'] else 'usable if the check image looks right'

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
