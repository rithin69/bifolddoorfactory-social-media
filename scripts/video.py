"""Honest, clip-by-clip edits for social video, the companion of edit.py.

Every clip is measured first (length, shape, rotation, frame rate, sound,
brightness, dark and blown-out areas, grain, sharpness) and the edit is
built for that clip alone. It only reframes, trims, corrects light and
colour, levels the sound and strips metadata (including GPS). It never
adds, removes or changes what is in the picture.

Makes two files:
  <name>-feed.mp4  4:5 (1080x1350), up to 60 seconds: for the Instagram
                   carousel (where it sits beside the 4:5 photos) and for
                   Facebook.
  <name>-9x16.mp4  vertical (1080x1920), up to 3 minutes: for TikTok and
                   the Instagram Reel.
plus three JPEG frames of each (start, middle, end) so the result can be
looked at like a photo: <name>-feed-1.jpg ... <name>-9x16-3.jpg.

A landscape clip is never cropped to make it tall: it is shown whole on a
softly blurred, darkened copy of itself. A clip is only cropped when the
crop removes 10% or less of its width or height.

1. Measure:  python scripts/video.py INPUT --analyse
2. Edit:     python scripts/video.py INPUT --name ealing-bifold-v1 --out images/2026-11-24 \
                 [--feed auto|crop|fit] [--tall auto|crop|fit] [--start s] [--length s] \
                 [--brightness n] [--contrast n] [--saturation n] [--gamma n] \
                 [--denoise n] [--sharpen n] [--deshake 0|1] [--audio level|keep|mute]

--start      seconds into the clip to start from (default 0)
--length     seconds to keep (default: the whole clip, within the platform limits)
--brightness -0.1 to 0.1 (0 = unchanged)
--contrast   0.9 to 1.2 (1.0 = unchanged)
--saturation 0.9 to 1.2 (1.0 = unchanged)
--gamma      0.8 to 1.3 (1.0 = unchanged; above 1 lifts the shadows)
--denoise    0 to 6 for grainy low-light clips (0 = off)
--sharpen    0 to 1 (a little output sharpening is always applied)
--deshake    1 = steady a hand-held clip (crops the edges slightly)
--audio      level = even out the volume (default), keep = as recorded, mute = no sound
"""
import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys

import cv2
import numpy as np

try:
    import imageio_ffmpeg
    FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    FFMPEG = shutil.which('ffmpeg')

FEED_SIZE, FEED_MAX = (1080, 1350), 60.0      # Instagram carousel videos are capped at 60 s
TALL_SIZE, TALL_MAX = (1080, 1920), 180.0     # Reels: 3 minutes; TikTok allows longer
CROP_TOLERANCE = 0.10
LIMITS = {
    'brightness': (-0.1, 0.1), 'contrast': (0.9, 1.2), 'saturation': (0.9, 1.2),
    'gamma': (0.8, 1.3), 'denoise': (0, 6), 'sharpen': (0, 1),
}
NEUTRAL = {
    'brightness': 0.0, 'contrast': 1.0, 'saturation': 1.0, 'gamma': 1.0,
    'denoise': 0.0, 'sharpen': 0.0, 'deshake': 0, 'audio': 'level', 'feed': 'auto', 'tall': 'auto',
}
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)


def run(args, **kw):
    return subprocess.run([FFMPEG, '-hide_banner', '-y', *args], capture_output=True, text=True, **kw)


# ── measuring ──────────────────────────────────────────────────────────────

def probe(path):
    """Length, stored size, rotation, frame rate and sound, read from
    ffmpeg's own description of the file."""
    info = subprocess.run([FFMPEG, '-hide_banner', '-i', path], capture_output=True, text=True).stderr
    m = re.search(r'Duration: (\d+):(\d+):(\d+\.?\d*)', info)
    duration = (int(m[1]) * 3600 + int(m[2]) * 60 + float(m[3])) if m else 0.0
    v = re.search(r'Video: .*?(\d{2,5})x(\d{2,5})', info)
    w, h = (int(v[1]), int(v[2])) if v else (0, 0)
    fps = re.search(r'(\d+\.?\d*) fps', info)
    rot = re.search(r'rotation of (-?\d+\.?\d*)', info) or re.search(r'rotate\s*:\s*(-?\d+)', info)
    rotation = int(round(float(rot[1]))) % 360 if rot else 0
    if rotation in (90, 270):
        w, h = h, w   # ffmpeg shows the clip upright, so measure the upright shape
    return {
        'duration': round(duration, 2), 'width': w, 'height': h, 'rotation': rotation,
        'fps': round(float(fps[1]), 2) if fps else 30.0, 'has_audio': 'Audio:' in info,
    }


def frames_of(path, count=12):
    """A spread of frames across the clip, upright, as RGB float arrays."""
    cap = cv2.VideoCapture(path)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    out = []
    for i in range(count):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int((i + 0.5) * max(n, 1) / count))
        ok, bgr = cap.read()
        if not ok:
            continue
        s = 720 / max(bgr.shape[:2])
        if s < 1:
            bgr = cv2.resize(bgr, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        out.append(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0)
    cap.release()
    return out


def content_box(frames):
    """Black bars baked into a clip (letterbox or pillarbox from an earlier
    export): rows and columns at the edges that stay near-black in every
    sampled frame. Returns the picture area as fractions x0, y0, x1, y1."""
    if not frames:
        return [0.0, 0.0, 1.0, 1.0]
    rows = np.max([(f @ LUMA).mean(1) for f in frames], 0)   # brightest a row ever gets
    cols = np.max([(f @ LUMA).mean(0) for f in frames], 0)
    lit_r, lit_c = np.nonzero(rows > 0.06)[0], np.nonzero(cols > 0.06)[0]
    if len(lit_r) < 0.3 * len(rows) or len(lit_c) < 0.3 * len(cols):
        return [0.0, 0.0, 1.0, 1.0]
    y0, y1 = lit_r[0] / len(rows), (lit_r[-1] + 1) / len(rows)
    x0, x1 = lit_c[0] / len(cols), (lit_c[-1] + 1) / len(cols)
    box = [x0, y0, x1, y1]
    return [0.0, 0.0, 1.0, 1.0] if (x0 < 0.01 and y0 < 0.01 and x1 > 0.99 and y1 > 0.99) else [round(v, 4) for v in box]


def measure(path):
    m = probe(path)
    frames = frames_of(path)
    if not frames:
        m.update(content_box=[0.0, 0.0, 1.0, 1.0], content_width=m['width'], content_height=m['height'],
                 median_brightness=0.5, dark_share=0.0, clipped_share=0.0, noise=0.0, sharpness=999.0, saturation=0.3, frames_read=0)
        return m
    box = content_box(frames)
    m['content_box'] = box
    m['content_width'] = int(round(m['width'] * (box[2] - box[0])))
    m['content_height'] = int(round(m['height'] * (box[3] - box[1])))
    if box != [0.0, 0.0, 1.0, 1.0]:
        fh, fw = frames[0].shape[:2]
        frames = [f[int(box[1] * fh):int(box[3] * fh), int(box[0] * fw):int(box[2] * fw)] for f in frames]
    L = np.concatenate([f @ LUMA for f in frames]).ravel()
    p2, p50, p98 = np.percentile(L, [2, 50, 98])
    greys = [(f @ LUMA) for f in frames]
    k = np.array([[1, -2, 1], [-2, 4, -2], [1, -2, 1]], np.float32)
    noise = np.mean([math.sqrt(math.pi / 2) / (6 * (g.shape[1] - 2) * (g.shape[0] - 2)) * np.abs(cv2.filter2D(g * 255, -1, k)[1:-1, 1:-1]).sum() for g in greys])
    sharp = np.mean([cv2.Laplacian((g * 255).astype(np.float32), cv2.CV_32F).var() for g in greys])
    sat = np.mean([cv2.cvtColor((f * 255).astype(np.uint8), cv2.COLOR_RGB2HSV)[..., 1].mean() / 255 for f in frames])
    r, g, b = np.mean([f.reshape(-1, 3).mean(0) for f in frames], 0)
    cw, ch = m['content_width'], m['content_height']
    m.update({
        'shape': 'landscape' if cw > ch * 1.1 else 'portrait' if ch > cw * 1.1 else 'square',
        'median_brightness': round(float(p50), 3), 'range': round(float(p98 - p2), 3),
        'dark_share': round(float((L < 0.1).mean()), 3), 'clipped_share': round(float((L > 0.98).mean()), 3),
        'cast_red_blue': round(float(r - b), 3), 'saturation': round(float(sat), 3),
        'noise': round(float(noise), 2), 'sharpness': round(float(sharp), 1), 'frames_read': len(frames),
    })
    return m


def plan(m, size):
    """crop or fit, and how much a crop would remove."""
    tw, th = size
    w, h = m['content_width'], m['content_height']
    if not w or not h:
        return 'fit', 0.0
    target = tw / th
    if w / h > target:      # wider than the target: a crop trims the sides
        removed = 1 - (h * target) / w
    else:                   # taller than the target: a crop trims top and bottom
        removed = 1 - (w / target) / h
    return ('crop' if removed <= CROP_TOLERANCE else 'fit'), round(float(removed), 3)


def suggest(m):
    s, why = dict(NEUTRAL), {}
    p50 = m['median_brightness']
    if m['content_box'] != [0.0, 0.0, 1.0, 1.0]:
        why['bars'] = (f"black bars baked into the clip (picture is {m['content_width']}x{m['content_height']} inside {m['width']}x{m['height']}): "
                       'they are cut away and the picture is reframed on our blurred background')
    if p50 < 0.32:
        s['gamma'] = round(min(1.3, 1 + (0.4 - p50) * 1.2), 2)
        s['brightness'] = round(min(0.04, (0.36 - p50) * 0.15), 3)
        why['light'] = f"dark clip (median brightness {p50}): midtones lifted gently, blacks kept black"
    elif p50 > 0.7:
        s['brightness'] = -0.04
        why['light'] = 'very bright clip'
    if m['clipped_share'] > 0.03:
        s['gamma'] = round(min(s['gamma'], 0.95), 2)
        why['highlights'] = f"{round(m['clipped_share'] * 100)}% of the picture is blown out; tone pulled back a little"
    if m['range'] < 0.55:
        s['contrast'] = 1.08
        why['contrast'] = f"flat or hazy (tonal range {m['range']})"
    if m['saturation'] < 0.16:
        s['saturation'] = 1.08
        why['saturation'] = 'washed-out colour'
    elif m['saturation'] < 0.24:
        s['saturation'] = 1.04
        why['saturation'] = 'slightly muted colour'
    if m['noise'] > 4.0 and p50 < 0.45:
        s['denoise'] = round(min(6, (m['noise'] - 2.5) * 1.2), 1)
        why['denoise'] = f"grainy (noise {m['noise']}) and dark"
    if m['sharpness'] < 60:
        s['sharpen'] = 0.5
        why['sharpen'] = f"soft (sharpness {m['sharpness']})"
    if not m['has_audio']:
        s['audio'] = 'mute'
        why['audio'] = 'no sound in the clip'
    for key, size in (('feed', FEED_SIZE), ('tall', TALL_SIZE)):
        mode, removed = plan(m, size)
        s[key] = mode
        why[key] = (f"{'4:5' if key == 'feed' else '9:16'}: a crop would remove {round(removed * 100)}% of the picture, so the whole clip is shown on a blurred background"
                    if mode == 'fit' else f"{'4:5' if key == 'feed' else '9:16'}: a crop removes only {round(removed * 100)}%, so it is cropped to fill the frame")
    if m['duration'] > FEED_MAX:
        why['length'] = f"{m['duration']} s long: the feed version keeps the first {int(FEED_MAX)} s (use --start to choose where it begins)"
    if m['rotation']:
        why['rotation'] = f"recorded with a {m['rotation']} degree rotation flag; shown upright"
    return s, why


# ── editing ────────────────────────────────────────────────────────────────

def tone_filters(s):
    f = []
    if s['deshake']:
        f.append('deshake=rx=32:ry=32:edge=mirror')
    if s['denoise'] > 0.25:
        d = s['denoise']
        f.append(f'hqdn3d={d:.1f}:{d * 0.75:.1f}:{d * 1.5:.1f}:{d:.1f}')
    eq = []
    if abs(s['brightness']) > 0.001:
        eq.append(f'brightness={s["brightness"]:.3f}')
    if abs(s['contrast'] - 1) > 0.001:
        eq.append(f'contrast={s["contrast"]:.3f}')
    if abs(s['saturation'] - 1) > 0.001:
        eq.append(f'saturation={s["saturation"]:.3f}')
    if abs(s['gamma'] - 1) > 0.001:
        eq.append(f'gamma={s["gamma"]:.3f}')
    if eq:
        f.append('eq=' + ':'.join(eq))
    amount = 0.35 + 0.6 * s['sharpen']
    f.append(f'unsharp=5:5:{amount:.2f}:5:5:0.0')
    return f


def bars_crop(m):
    """An ffmpeg crop that removes baked-in black bars, or nothing."""
    box = m['content_box']
    if box == [0.0, 0.0, 1.0, 1.0]:
        return ''
    w, h = m['width'], m['height']
    cw, ch = int(w * (box[2] - box[0])) // 2 * 2, int(h * (box[3] - box[1])) // 2 * 2
    return f'crop={cw}:{ch}:{int(w * box[0]) // 2 * 2}:{int(h * box[1]) // 2 * 2},'


def graph(mode, size, s, m):
    tw, th = size
    tone = bars_crop(m) + ','.join(tone_filters(s))
    if mode == 'crop':
        return f'[0:v]{tone},scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},fps=30,format=yuv420p[v]'
    return (f'[0:v]{tone},split=2[bg][fg];'
            f'[bg]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},gblur=sigma=40,eq=brightness=-0.12[bgb];'
            f'[fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[fgs];'
            f'[bgb][fgs]overlay=(W-w)/2:(H-h)/2,fps=30,format=yuv420p[v]')


def encode(src, dst, mode, size, s, m, start, length, has_audio):
    args = ['-ss', f'{start:.2f}', '-i', src, '-t', f'{length:.2f}',
            '-filter_complex', graph(mode, size, s, m), '-map', '[v]',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '22', '-maxrate', '6M', '-bufsize', '12M',
            '-map_metadata', '-1', '-movflags', '+faststart']
    if has_audio and s['audio'] != 'mute':
        args += ['-map', '0:a:0', '-c:a', 'aac', '-b:a', '128k', '-ar', '48000']
        if s['audio'] == 'level':
            args += ['-af', 'loudnorm=I=-16:TP=-1.5:LRA=11']
    else:
        args += ['-an']
    r = run(args + [dst])
    if r.returncode != 0:
        raise SystemExit('ffmpeg failed:\n' + r.stderr[-2000:])


def save_frames(video, prefix, length):
    paths = []
    for i, at in enumerate((0.1, 0.5, 0.9), 1):
        p = f'{prefix}-{i}.jpg'
        run(['-ss', f'{max(0.0, min(at * length, length - 0.1)):.2f}', '-i', video, '-frames:v', '1', '-q:v', '3', p])
        paths.append(p)
    return paths


def clamp(name, value):
    lo, hi = LIMITS[name]
    if value < lo or value > hi:
        print(f'note: {name} {value} is outside the honest-edit range, using {min(max(value, lo), hi)}')
    return min(max(value, lo), hi)


def main():
    if not FFMPEG:
        raise SystemExit('ffmpeg not found: pip install imageio-ffmpeg')
    p = argparse.ArgumentParser()
    p.add_argument('input')
    p.add_argument('--analyse', action='store_true')
    p.add_argument('--name')
    p.add_argument('--out', default='ready')
    p.add_argument('--feed', choices=['auto', 'crop', 'fit'])
    p.add_argument('--tall', choices=['auto', 'crop', 'fit'])
    p.add_argument('--start', type=float, default=0.0)
    p.add_argument('--length', type=float)
    for k in ('brightness', 'contrast', 'saturation', 'gamma', 'denoise', 'sharpen'):
        p.add_argument(f'--{k}', type=float)
    p.add_argument('--deshake', type=int, choices=[0, 1])
    p.add_argument('--audio', choices=['level', 'keep', 'mute'])
    a = p.parse_args()

    m = measure(a.input)
    suggested, why = suggest(m)
    if a.analyse:
        print(json.dumps({'measured': m, 'suggested': suggested, 'why': why}, indent=1))
        return 0
    if not a.name:
        p.error('--name is required unless --analyse is used')

    s = dict(suggested)
    for k in s:
        if getattr(a, k) is not None:
            s[k] = getattr(a, k)
    for k in LIMITS:
        s[k] = clamp(k, s[k])
    for key in ('feed', 'tall'):
        if s[key] == 'auto':
            s[key] = suggested[key]
    if s['audio'] != 'mute' and not m['has_audio']:
        s['audio'] = 'mute'

    start = max(0.0, min(a.start, max(0.0, m['duration'] - 1)))
    available = max(0.5, m['duration'] - start)
    os.makedirs(a.out, exist_ok=True)
    report = {k: s[k] for k in s if s[k] != NEUTRAL[k]} | {'start': start}
    for label, size, cap in (('feed', FEED_SIZE, FEED_MAX), ('9x16', TALL_SIZE, TALL_MAX)):
        length = min(available, cap, a.length) if a.length else min(available, cap)
        dst = os.path.join(a.out, f'{a.name}-{label}.mp4')
        encode(a.input, dst, s[label if label == 'feed' else 'tall'], size, s, m, start, length, m['has_audio'])
        mb = os.path.getsize(dst) / 1e6
        report[f'{label}_used'] = f"{'cropped to fill' if s[label if label == 'feed' else 'tall'] == 'crop' else 'whole clip on a blurred background'}, {length:.1f} s, {mb:.1f} MB"
        if mb > 45:
            print(f'warning: {dst} is {mb:.0f} MB; keep files under 45 MB (shorten with --length)')
        print(dst)
        for f in save_frames(dst, os.path.join(a.out, f'{a.name}-{label}'), length):
            print(f)
    print('settings: ' + json.dumps(report))
    return 0


if __name__ == '__main__':
    sys.exit(main())
