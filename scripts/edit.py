"""Light, honest photo edits for social posts.

Makes a 4:5 feed version (1080x1350) and a 9:16 vertical version (1080x1920)
of one photo. Only crops, straightens and adjusts light and colour: it never
adds, removes or changes anything in the picture. Strips all metadata,
including GPS location, so a customer's address never leaves in a file.

Usage:
  python scripts/edit.py INPUT --name hammersmith-bifold \
      [--focus 0.5,0.5] [--rotate 0] [--brightness 1.0] [--contrast 1.0] \
      [--saturation 1.0] [--warmth 0.0] [--sharpen 0] [--out ready]

--focus      the subject's centre as x,y fractions of the photo (0 to 1);
             each crop is centred on it as far as the photo allows
--rotate     degrees to straighten, positive = anticlockwise (keep within 5)
--brightness 1.0 = unchanged; 1.15 = 15% brighter (keep within 0.8 to 1.3)
--contrast   1.0 = unchanged (keep within 0.9 to 1.2)
--saturation 1.0 = unchanged (keep within 0.9 to 1.15)
--warmth     0 = unchanged; +0.04 warmer, -0.04 cooler (keep within 0.08)
--sharpen    0 = off, 1 = light
"""
import argparse
import math
import os
import sys

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

try:
    from pillow_heif import register_heif_opener  # iPhone HEIC photos
    register_heif_opener()
except ImportError:
    pass

SIZES = {'4x5': (1080, 1350), '9x16': (1080, 1920)}
LIMITS = {'rotate': 5, 'brightness': (0.8, 1.3), 'contrast': (0.9, 1.2), 'saturation': (0.9, 1.15), 'warmth': 0.08}


def largest_rotated_rect(w, h, angle):
    """Width and height of the largest upright rectangle inside a w x h image rotated by angle (radians)."""
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


def crop_to(img, ratio, fx, fy):
    """Largest crop of the given width/height ratio, centred on (fx, fy) as far as the edges allow."""
    w, h = img.size
    if w / h > ratio:
        cw, ch = int(h * ratio), h
    else:
        cw, ch = w, int(w / ratio)
    left = min(max(int(fx * w - cw / 2), 0), w - cw)
    top = min(max(int(fy * h - ch / 2), 0), h - ch)
    return img.crop((left, top, left + cw, top + ch))


def warm(img, amount):
    if abs(amount) < 0.001:
        return img
    r, g, b = img.split()
    r = r.point(lambda v: min(255, int(v * (1 + amount))))
    b = b.point(lambda v: min(255, int(v * (1 - amount))))
    return Image.merge('RGB', (r, g, b))


def clamp(name, value):
    lim = LIMITS[name]
    lo, hi = (-lim, lim) if not isinstance(lim, tuple) else lim
    if value < lo or value > hi:
        print(f'note: {name} {value} is outside the light-edit range, using {min(max(value, lo), hi)}')
    return min(max(value, lo), hi)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('--name', required=True)
    p.add_argument('--focus', default='0.5,0.5')
    p.add_argument('--rotate', type=float, default=0)
    p.add_argument('--brightness', type=float, default=1.0)
    p.add_argument('--contrast', type=float, default=1.0)
    p.add_argument('--saturation', type=float, default=1.0)
    p.add_argument('--warmth', type=float, default=0.0)
    p.add_argument('--sharpen', type=int, default=0)
    p.add_argument('--out', default='ready')
    a = p.parse_args()

    fx, fy = (min(max(float(v), 0.0), 1.0) for v in a.focus.split(','))
    img = ImageOps.exif_transpose(Image.open(a.input)).convert('RGB')  # upright, no metadata carried over
    img = straighten(img, clamp('rotate', a.rotate))
    img = ImageEnhance.Brightness(img).enhance(clamp('brightness', a.brightness))
    img = ImageEnhance.Contrast(img).enhance(clamp('contrast', a.contrast))
    img = ImageEnhance.Color(img).enhance(clamp('saturation', a.saturation))
    img = warm(img, clamp('warmth', a.warmth))
    if a.sharpen:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=3))

    os.makedirs(a.out, exist_ok=True)
    for label, (tw, th) in SIZES.items():
        crop = crop_to(img, tw / th, fx, fy)
        if crop.width < tw * 0.6:
            print(f'warning: {label} crop is only {crop.width}px wide, so it will look soft when enlarged')
        out = crop.resize((tw, th), Image.LANCZOS)
        path = os.path.join(a.out, f'{a.name}-{label}.jpg')
        out.save(path, 'JPEG', quality=88, optimize=True, progressive=True)  # saved without EXIF
        print(path)


if __name__ == '__main__':
    sys.exit(main())
