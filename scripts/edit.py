"""Light, honest photo edits for social posts.

Makes a 4:5 feed version (1080x1350) and a 9:16 vertical version (1080x1920)
of one photo. Only crops, straightens, corrects perspective and adjusts light
and colour: it never adds, removes or changes anything in the picture. Strips
all metadata, including GPS location, so a customer's address never leaves in
a file.

Usage:
  python scripts/edit.py INPUT --name hammersmith-bifold \
      [--focus 0.5,0.5] [--rotate 0] [--keystone 0] [--auto 1] \
      [--brightness 1.0] [--contrast 1.0] [--shadows 0] [--highlights 0] \
      [--clarity 0] [--saturation 1.0] [--warmth 0.0] [--sharpen 0] \
      [--tall crop] [--out ready]

--focus      the subject's centre as x,y fractions of the photo (0 to 1);
             each crop is centred on it as far as the photo allows
--rotate     degrees to straighten, positive = anticlockwise (keep within 5)
--keystone   fixes leaning verticals from tilting the phone (keep within 0.15):
             positive when the building narrows towards the TOP (phone tilted
             up), negative when it narrows towards the bottom
--auto       1 = automatic levels and white balance first (default), 0 = off
--brightness 1.0 = unchanged; 1.15 = 15% brighter (keep within 0.8 to 1.3)
--contrast   1.0 = unchanged (keep within 0.9 to 1.2)
--shadows    0 = unchanged; 0.3 = lift dark areas (keep within 0 to 0.5)
--highlights 0 = unchanged; 0.3 = recover bright sky/glass (keep within 0 to 0.5)
--clarity    0 = unchanged; 0.5 = more local contrast, crisper frames (0 to 1)
--saturation 1.0 = unchanged (keep within 0.9 to 1.15)
--warmth     0 = unchanged; +0.04 warmer, -0.04 cooler (keep within 0.08)
--sharpen    0 = off, 1 = light
--tall       how the 9:16 version is made:
             crop = fill the frame by cropping (default; best for upright photos)
             blur = show the whole 4:5 picture on a blurred copy of itself, so
                    a wide subject is not cut off
"""
import argparse
import math
import os
import sys

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps, ImageStat

try:
    from pillow_heif import register_heif_opener  # iPhone HEIC photos
    register_heif_opener()
except ImportError:
    pass

SIZES = {'4x5': (1080, 1350), '9x16': (1080, 1920)}
LIMITS = {
    'rotate': 5, 'keystone': 0.15, 'brightness': (0.8, 1.3), 'contrast': (0.9, 1.2),
    'shadows': (0, 0.5), 'highlights': (0, 0.5), 'clarity': (0, 1),
    'saturation': (0.9, 1.15), 'warmth': 0.08,
}


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


def keystone(img, k):
    """Make converging verticals parallel. Takes a trapezoid of the photo and
    stretches it to the full frame, so the corners it leaves out are trimmed
    rather than filled in."""
    if abs(k) < 0.005:
        return img
    w, h = img.size
    inset = abs(k) * w / 2
    if k > 0:   # narrower at the top: widen the top
        quad = (inset, 0, 0, h, w, h, w - inset, 0)
    else:       # narrower at the bottom: widen the bottom
        quad = (0, 0, inset, h, w - inset, h, w, 0)
    out = img.transform((w, h), Image.QUAD, quad, resample=Image.BICUBIC)
    # Widening one end also stretches it sideways; trim the height a little so
    # the proportions of doors and windows stay natural.
    trim = int(h * abs(k) * 0.25)
    return out.crop((0, trim, w, h)) if k > 0 else out.crop((0, 0, w, h - trim))


def auto_tone(img):
    """Gentle automatic levels and white balance, blended with the original so
    it corrects a dull or colour-cast phone photo without looking processed."""
    levelled = ImageOps.autocontrast(img, cutoff=(0.5, 0.5), preserve_tone=True)
    img = Image.blend(img, levelled, 0.6)
    # Grey-world white balance, applied at 50% and capped, so it removes a
    # yellow or blue cast but keeps the light of the moment.
    r, g, b = ImageStat.Stat(img).mean
    grey = (r + g + b) / 3
    gains = [min(max(grey / max(c, 1), 0.9), 1.1) for c in (r, g, b)]
    gains = [1 + (x - 1) * 0.5 for x in gains]
    channels = [ch.point(lambda v, f=f: min(255, int(v * f + 0.5))) for ch, f in zip(img.split(), gains)]
    return Image.merge('RGB', channels)


def tone_curve(img, shadows, highlights):
    """Lift shadows and pull down highlights with a smooth curve, leaving the
    mid-tones where they are."""
    if shadows < 0.001 and highlights < 0.001:
        return img
    lut = []
    for v in range(256):
        x = v / 255
        y = x + shadows * 1.6 * x * (1 - x) ** 2 - highlights * 1.6 * x ** 2 * (1 - x)
        lut.append(min(255, max(0, int(y * 255 + 0.5))))
    return img.point(lut * 3)


def clarity(img, amount):
    """Local contrast: makes frames, glazing bars and brickwork read crisper."""
    if amount < 0.01:
        return img
    radius = max(img.size) / 80
    return img.filter(ImageFilter.UnsharpMask(radius=radius, percent=int(45 * amount), threshold=2))


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


def blur_frame(picture, whole, size):
    """The picture, centred, on a softly blurred and dimmed copy of the whole photo."""
    tw, th = size
    back = ImageOps.fit(whole, size, Image.LANCZOS)
    back = back.filter(ImageFilter.GaussianBlur(45))
    back = ImageEnhance.Brightness(back).enhance(0.8)
    front = picture.resize((tw, round(picture.height * tw / picture.width)), Image.LANCZOS)
    back.paste(front, (0, (th - front.height) // 2))
    return back


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
    p.add_argument('--keystone', type=float, default=0)
    p.add_argument('--auto', type=int, default=1)
    p.add_argument('--brightness', type=float, default=1.0)
    p.add_argument('--contrast', type=float, default=1.0)
    p.add_argument('--shadows', type=float, default=0)
    p.add_argument('--highlights', type=float, default=0)
    p.add_argument('--clarity', type=float, default=0)
    p.add_argument('--saturation', type=float, default=1.0)
    p.add_argument('--warmth', type=float, default=0.0)
    p.add_argument('--sharpen', type=int, default=0)
    p.add_argument('--tall', choices=['crop', 'blur'], default='crop')
    p.add_argument('--out', default='ready')
    a = p.parse_args()

    fx, fy = (min(max(float(v), 0.0), 1.0) for v in a.focus.split(','))
    img = ImageOps.exif_transpose(Image.open(a.input)).convert('RGB')  # upright, no metadata carried over
    img = straighten(img, clamp('rotate', a.rotate))
    img = keystone(img, clamp('keystone', a.keystone))
    if a.auto:
        img = auto_tone(img)
    img = tone_curve(img, clamp('shadows', a.shadows), clamp('highlights', a.highlights))
    img = ImageEnhance.Brightness(img).enhance(clamp('brightness', a.brightness))
    img = ImageEnhance.Contrast(img).enhance(clamp('contrast', a.contrast))
    img = clarity(img, clamp('clarity', a.clarity))
    img = ImageEnhance.Color(img).enhance(clamp('saturation', a.saturation))
    img = warm(img, clamp('warmth', a.warmth))
    if a.sharpen:
        img = img.filter(ImageFilter.UnsharpMask(radius=1.2, percent=60, threshold=3))

    os.makedirs(a.out, exist_ok=True)
    feed = crop_to(img, 4 / 5, fx, fy)
    for label, (tw, th) in SIZES.items():
        if label == '9x16' and a.tall == 'blur':
            out = blur_frame(feed, img, (tw, th))
            source_width = feed.width
        else:
            crop = feed if label == '4x5' else crop_to(img, tw / th, fx, fy)
            out = crop.resize((tw, th), Image.LANCZOS)
            source_width = crop.width
        if source_width < tw * 0.6:
            print(f'warning: {label} uses only {source_width}px of width, so it will look soft when enlarged')
        path = os.path.join(a.out, f'{a.name}-{label}.jpg')
        # 4:4:4 colour keeps thin frame edges crisp; saved without EXIF.
        out.save(path, 'JPEG', quality=92, subsampling=0, optimize=True, progressive=True)
        print(path)


if __name__ == '__main__':
    sys.exit(main())
