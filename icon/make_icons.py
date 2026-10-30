"""Draws Vinutes' icon — a brown calligraphic V with a quill, on cream card — for the Mac, iOS and the web.

  python3 icon/make_icons.py          (needs Pillow and numpy; run it again after changing glyph.png)

icon/glyph.png is the V and the quill as a mask (white ink on black). Everything else is drawn here, the same
way every run, so the files below change only when the drawing does:
  macos/AppIcon.icns                           for macOS 26 and later: the card edge to edge, square; macOS rounds
                                               it itself (an icon drawn with its own corners and margin is shown
                                               small, on a grey tile)
  macos/AppIcon-legacy.icns, AppIcon-1024.png  for macOS 15 and earlier, which show an icon as drawn: Apple's
                                               template, an 824 px card with 185 px corners and a soft shadow on a
                                               clear 1024 px canvas; install.sh copies the one that suits the Mac
  ios/AppIcon.appiconset/                      one 1024 px square with no corners and no transparency (iOS
                                               rounds it); drop the folder into an Xcode asset catalogue
  web/                                         favicon.ico (16, 32, 48), favicon-32.png, apple-touch-icon.png
                                               (180, square), icon-192.png and icon-512.png (rounded),
                                               icon-maskable-512.png (square, for Android's own shapes)
At 64 px and under, the strokes are drawn thicker and the V larger, or the swash and the quill's slit vanish.
"""
import json
import os
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
INK = np.array([86, 54, 34.])
PAPER_TOP, PAPER_BOTTOM = np.array([248, 239, 222.]), np.array([238, 224, 197.])


def glyph(bold=False):
    g = Image.open(os.path.join(HERE, 'glyph.png')).convert('L')
    if bold:   # spread the edge outwards, then make it crisp again
        a = np.asarray(g.filter(ImageFilter.GaussianBlur(g.width / 130))).astype(float)
        g = Image.fromarray((np.clip((a - 40) / 24, 0, 1) * 255).astype(np.uint8))
    return g


def rounded_mask(side, radius):
    big = Image.new('L', (side * 4, side * 4), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, side * 4 - 1, side * 4 - 1), radius=int(side * 4 * radius), fill=255)
    return big.resize((side, side), Image.LANCZOS)


def card(side, small=False):
    """The square card, edge to edge: paper, then the ink, a little uneven like letterpress."""
    rng = np.random.default_rng(7)
    shade = np.linspace(0, 1, side)[:, None, None]
    img = PAPER_TOP + (PAPER_BOTTOM - PAPER_TOP) * shade * np.ones((1, side, 1))
    if not small:
        grain = rng.normal(0, 3.2, (side, side))
        n = max(side // 8, 2)
        mottle = Image.fromarray(rng.normal(128, 40, (n, n)).clip(0, 255).astype(np.uint8))
        mottle = np.asarray(mottle.resize((side, side), Image.BICUBIC).filter(ImageFilter.GaussianBlur(side / 60)))
        img = img + (grain + (mottle.astype(float) - 128) * 0.10)[..., None]
    g = glyph(bold=small)
    width = 0.74 if small else 0.64     # of the card's width; the V sits a little right of and above the middle
    gw = int(side * width)
    gh = int(g.height * gw / g.width)
    a = np.zeros((side, side))
    x, y = int((side - gw) / 2 + 0.012 * side), int((side - gh) / 2 - 0.022 * side)
    a[y:y + gh, x:x + gw] = np.asarray(g.resize((gw, gh), Image.LANCZOS)) / 255.
    ink = INK * np.ones((side, side, 3))
    if not small:
        ink = ink * (1 + rng.normal(0, 0.035, (side, side)))[..., None]
    img = img * (1 - a[..., None]) + ink * a[..., None]
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))


def square(px, small=None):
    small = px <= 64 if small is None else small
    side = max(px, 256) if small else 1024
    return card(side, small).resize((px, px), Image.LANCZOS)


def rounded(px, radius=0.225):
    im = square(px).convert('RGBA')
    im.putalpha(rounded_mask(px, radius))
    return im


def mac(px):
    """Apple's macOS template, drawn at 1024 and scaled: 824 px card, 185 px corners, shadow below."""
    side, inner = 1024, 824
    off = (side - inner) // 2
    small = px <= 64
    mask = rounded_mask(inner, 185 / 824)
    face = np.asarray(card(inner, small)).astype(float)
    # the card's thickness: its edge a little lighter at the top and darker toward the bottom
    m = np.asarray(mask) / 255.
    edge = np.clip(m - np.asarray(mask.filter(ImageFilter.MinFilter(9)).filter(ImageFilter.GaussianBlur(3))) / 255., 0, 1)
    rows = np.linspace(-1, 1, inner)[:, None]
    face = face + (edge * (-28 * np.clip(rows, 0, 1) + 14 * np.clip(-rows, 0, 1)))[..., None]
    front = Image.fromarray(np.clip(face, 0, 255).astype(np.uint8)).convert('RGBA')
    front.putalpha(mask)
    shade = Image.new('L', (side, side), 0)
    shade.paste(mask.point(lambda v: int(v * 0.32)), (off, off + 12))
    shadow = Image.new('RGBA', (side, side), (40, 25, 10, 255))
    shadow.putalpha(shade.filter(ImageFilter.GaussianBlur(16)))
    out = Image.new('RGBA', (side, side), (0, 0, 0, 0))
    out = Image.alpha_composite(out, shadow)
    out.alpha_composite(front, (off, off))
    return out.resize((px, px), Image.LANCZOS)


def icns(draw, out):
    with tempfile.TemporaryDirectory() as tmp:
        iconset = os.path.join(tmp, 'AppIcon.iconset')
        os.makedirs(iconset)
        for pt in (16, 32, 128, 256, 512):
            draw(pt).save(os.path.join(iconset, f'icon_{pt}x{pt}.png'))
            draw(pt * 2).save(os.path.join(iconset, f'icon_{pt}x{pt}@2x.png'))
        subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', out], check=True)


def build_mac(folder):
    os.makedirs(folder, exist_ok=True)
    mac(1024).save(os.path.join(folder, 'AppIcon-1024.png'))
    icns(lambda px: square(px).convert('RGBA'), os.path.join(folder, 'AppIcon.icns'))
    icns(mac, os.path.join(folder, 'AppIcon-legacy.icns'))


def build_ios(folder):
    shutil.rmtree(folder, ignore_errors=True)
    os.makedirs(folder)
    square(1024).convert('RGB').save(os.path.join(folder, 'AppIcon-1024.png'))
    contents = {'images': [{'filename': 'AppIcon-1024.png', 'idiom': 'universal', 'platform': 'ios', 'size': '1024x1024'}],
                'info': {'author': 'xcode', 'version': 1}}
    with open(os.path.join(folder, 'Contents.json'), 'w') as f:
        json.dump(contents, f, indent=2)
        f.write('\n')


def build_web(folder):
    os.makedirs(folder, exist_ok=True)
    fav = [rounded(px) for px in (16, 32, 48)]
    fav[2].save(os.path.join(folder, 'favicon.ico'), sizes=[(16, 16), (32, 32), (48, 48)], append_images=fav[:2])
    fav[1].save(os.path.join(folder, 'favicon-32.png'))
    square(180).convert('RGB').save(os.path.join(folder, 'apple-touch-icon.png'))
    rounded(192).save(os.path.join(folder, 'icon-192.png'))
    rounded(512).save(os.path.join(folder, 'icon-512.png'))
    square(512).convert('RGB').save(os.path.join(folder, 'icon-maskable-512.png'))


if __name__ == '__main__':
    build_mac(os.path.join(HERE, 'macos'))
    build_ios(os.path.join(HERE, 'ios', 'AppIcon.appiconset'))
    build_web(os.path.join(HERE, 'web'))
    print('icon/: macos, ios, web written')
