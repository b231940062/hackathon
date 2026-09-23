"""Демо өгөгдөлд зориулсан "өмнө / дараа" зургийг Pillow-оор процедураар зурна.

Интернетгүй орчинд ч демо бүрэн ажиллахын тулд гадны зургийн сервис ашиглахгүй.
Ангилал бүрт тохирсон энгийн дүрслэл (эвдэрсэн зам → шинэ асфальт гэх мэт).
"""
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H, S = 800, 520, 2  # S: supersampling (гөлгөр ирмэгтэй болгоно)

DAY_BUILDINGS = [(222, 208, 186), (206, 214, 222), (230, 196, 180), (196, 206, 190), (236, 226, 204),
                 (180, 196, 214), (214, 200, 214)]
NIGHT_BUILDINGS = [(34, 44, 74), (40, 50, 84), (30, 38, 64), (46, 52, 80)]


def darker(col, f=0.75):
    return tuple(int(v * f) for v in col[:3])


def lighter(col, f=0.25):
    return tuple(int(v + (255 - v) * f) for v in col[:3])


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class Canvas:
    def __init__(self, mode="RGB", bg=(255, 255, 255)):
        self.mode = mode
        self.img = Image.new(mode, (W * S, H * S), bg if mode == "RGB" else (0, 0, 0, 0))
        self.d = ImageDraw.Draw(self.img)

    @staticmethod
    def _pts(pts):
        return [(x * S, y * S) for x, y in pts]

    def rect(self, x0, y0, x1, y1, fill, r=0, outline=None, width=0):
        box = [min(x0, x1) * S, min(y0, y1) * S, max(x0, x1) * S, max(y0, y1) * S]
        if r:
            self.d.rounded_rectangle(box, radius=r * S, fill=fill, outline=outline, width=int(width * S))
        else:
            self.d.rectangle(box, fill=fill, outline=outline, width=int(width * S))

    def ellipse(self, cx, cy, rx, ry, fill, outline=None, width=0):
        self.d.ellipse([(cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S], fill=fill,
                       outline=outline, width=int(width * S))

    def poly(self, pts, fill):
        self.d.polygon(self._pts(pts), fill=fill)

    def line(self, pts, fill, width=2):
        self.d.line(self._pts(pts), fill=fill, width=max(1, int(width * S)), joint="curve")

    def gradient(self, y0, y1, top, bottom):
        y0s, y1s = int(y0 * S), int(y1 * S)
        for y in range(y0s, y1s):
            t = (y - y0s) / max(1, y1s - y0s - 1)
            self.d.line([(0, y), (W * S, y)], fill=lerp(top, bottom, t))

    def composite(self, layer: "Canvas", blur=0):
        top = layer.img.filter(ImageFilter.GaussianBlur(blur * S)) if blur else layer.img
        self.img = Image.alpha_composite(self.img.convert("RGBA"), top).convert("RGB")
        self.d = ImageDraw.Draw(self.img)

    def finish(self) -> Image.Image:
        # зөөлөн виньетка
        mask = Image.new("L", self.img.size, 0)
        ImageDraw.Draw(mask).ellipse([-W * S * 0.15, -H * S * 0.2, W * S * 1.15, H * S * 1.2], fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(60 * S))
        dark = Image.new("RGB", self.img.size, (15, 20, 30))
        out = Image.composite(self.img, dark, mask.point(lambda v: 150 + v * 105 // 255))
        return out.resize((W, H), Image.LANCZOS)


# ---------- Ерөнхий элементүүд ----------
def sky(c, top, bottom, hz):
    c.gradient(0, hz, top, bottom)


def mountains(c, rng, hz, color, amp=70):
    p1, p2 = rng.uniform(0, 6), rng.uniform(0, 6)
    pts = [(0, hz)]
    for x in range(0, W + 11, 10):
        y = hz - 20 - amp * 0.6 * (0.5 + 0.5 * math.sin(x / 140 + p1)) - 14 * math.sin(x / 45 + p2)
        pts.append((x, y))
    pts.append((W, hz))
    c.poly(pts, color)


def skyline(c, rng, hz, night=False, max_h=150, density=1.0):
    x = -10
    palette = NIGHT_BUILDINGS if night else DAY_BUILDINGS
    while x < W:
        bw, bh = rng.randint(55, 120), rng.randint(60, max_h)
        if rng.random() > density:
            x += bw
            continue
        col = rng.choice(palette)
        c.rect(x, hz - bh, x + bw, hz + 2, col)
        c.rect(x, hz - bh, x + bw, hz - bh + 5, darker(col, 0.85))
        for wy in range(int(hz - bh + 12), int(hz - 8), 14):
            for wx in range(int(x + 8), int(x + bw - 10), 13):
                if night:
                    wc = (255, 210, 120) if rng.random() < 0.4 else darker(col, 0.7)
                else:
                    wc = darker(col, 0.72) if rng.random() < 0.8 else (150, 185, 215)
                c.rect(wx, wy, wx + 6, wy + 7, wc)
        x += bw + rng.randint(2, 16)


def crack(c, rng, x, y, length, color=(38, 38, 40), width=1.6):
    pts = [(x, y)]
    ang = rng.uniform(0, math.pi * 2)
    for _ in range(int(length / 8)):
        ang += rng.uniform(-0.7, 0.7)
        x += math.cos(ang) * 8
        y += math.sin(ang) * 4
        pts.append((x, y))
        if rng.random() < 0.15:
            crack(c, rng, x, y, length * 0.35, color, width * 0.7)
    c.line(pts, color, width)


def tree(c, x, y, size, leaf=(62, 150, 72)):
    c.rect(x - size * 0.08, y - size * 0.9, x + size * 0.08, y, (110, 80, 52))
    c.ellipse(x, y - size * 1.2, size * 0.55, size * 0.55, leaf)
    c.ellipse(x - size * 0.3, y - size * 0.95, size * 0.38, size * 0.38, darker(leaf, 0.9))
    c.ellipse(x + size * 0.32, y - size * 1.0, size * 0.4, size * 0.4, lighter(leaf, 0.1))


def cone(c, x, y, s=1.0):
    c.poly([(x - 16 * s, y), (x + 16 * s, y), (x + 4 * s, y - 46 * s), (x - 4 * s, y - 46 * s)], (245, 110, 30))
    c.poly([(x - 10 * s, y - 18 * s), (x + 10 * s, y - 18 * s), (x + 7 * s, y - 28 * s), (x - 7 * s, y - 28 * s)],
           (250, 250, 250))
    c.rect(x - 22 * s, y - 4 * s, x + 22 * s, y + 2 * s, (220, 90, 20))


def day_backdrop(c, rng, hz, top=(125, 183, 238), bottom=(214, 233, 250), buildings=True, max_h=150):
    sky(c, top, bottom, hz)
    mountains(c, rng, hz, (139, 160, 178))
    if buildings:
        skyline(c, rng, hz, max_h=max_h)


# ---------- Ангиллын дүрслэлүүд ----------
def scene_road(rng, before):
    c = Canvas()
    hz = 250
    day_backdrop(c, rng, hz)
    c.gradient(hz, H, (196, 190, 178), (168, 161, 148))
    tl, tr, bl, br = 350, 450, -140, 940
    asphalt = (108, 107, 106) if before else (46, 48, 54)
    c.poly([(tl, hz), (tr, hz), (br, H), (bl, H)], asphalt)
    c.line([(tl, hz), (bl, H)], (222, 216, 204), 5)
    c.line([(tr, hz), (br, H)], (222, 216, 204), 5)

    def at(u, t):
        y = hz + t * (H - hz)
        left, right = tl + (bl - tl) * t, tr + (br - tr) * t
        return left + u * (right - left), y, right - left

    t = 0.03
    while t < 1:
        t2 = min(1.0, t + 0.04 + t * 0.1)
        (x1, y1, w1), (x2, y2, w2) = at(0.5, t), at(0.5, t2)
        if not before or rng.random() < 0.55:
            col = (245, 245, 240) if not before else (165, 162, 152)
            c.poly([(x1 - w1 * 0.011, y1), (x1 + w1 * 0.011, y1), (x2 + w2 * 0.011, y2), (x2 - w2 * 0.011, y2)], col)
        t = t2 + 0.035 + t * 0.09
    if before:
        for _ in range(45):
            u, t = rng.uniform(0.05, 0.95), rng.uniform(0.05, 1)
            x, y, w = at(u, t)
            shade = rng.choice([darker(asphalt, 0.85), lighter(asphalt, 0.12)])
            c.ellipse(x, y, w * rng.uniform(0.02, 0.06), w * 0.012 + 2, shade)
        for _ in range(10):
            x, y, w = at(rng.uniform(0.1, 0.9), rng.uniform(0.2, 1))
            crack(c, rng, x, y, rng.uniform(60, 160))
        for _ in range(rng.randint(4, 6)):
            x, y, w = at(rng.uniform(0.15, 0.85), rng.uniform(0.3, 0.92))
            rx = w * rng.uniform(0.045, 0.085)
            ry = rx * 0.36
            c.ellipse(x, y, rx * 1.18, ry * 1.25, (140, 134, 124))
            c.ellipse(x, y, rx, ry, (42, 42, 44))
            if rng.random() < 0.55:
                c.ellipse(x, y + ry * 0.12, rx * 0.72, ry * 0.55, (96, 124, 146))
    else:
        for u in (0.07, 0.93):
            (x1, y1, w1), (x2, y2, w2) = at(u, 0), at(u, 1)
            c.poly([(x1 - 1, y1), (x1 + 1, y1), (x2 + w2 * 0.006, y2), (x2 - w2 * 0.006, y2)], (240, 196, 40))
        layer = Canvas("RGBA")
        layer.poly([(420, hz), (440, hz), (620, H), (430, H)], (255, 255, 255, 28))
        c.composite(layer, blur=6)
        cone(c, 730, 470, 1.1)
        cone(c, 90, 490, 0.9)
    return c


def scene_garbage(rng, before):
    c = Canvas()
    hz = 255
    day_backdrop(c, rng, hz)
    c.gradient(hz, H, (182, 177, 168), (160, 154, 144))
    c.rect(0, 292, W, 372, (208, 202, 192))
    c.rect(0, 292, W, 299, (186, 180, 170))
    colors = [(46, 125, 50)] * 3 if before else [(46, 125, 50), (37, 99, 235), (234, 179, 8)]
    for i, bx in enumerate((250, 362, 474)):
        col = colors[i]
        c.rect(bx, 328, bx + 96, 432, col, r=6)
        c.rect(bx - 5, 318, bx + 101, 334, darker(col, 0.8), r=4)
        for k in range(3):
            c.rect(bx + 16 + k * 26, 348, bx + 22 + k * 26, 420, darker(col, 0.88))
        c.ellipse(bx + 16, 436, 7, 7, (40, 40, 40))
        c.ellipse(bx + 80, 436, 7, 7, (40, 40, 40))
    if before:
        bag_cols = [(30, 30, 32), (48, 84, 150), (225, 225, 225), (60, 60, 64), (140, 40, 40), (210, 190, 150)]
        for _ in range(60):
            x = rng.uniform(235, 580)
            y = 318 - rng.uniform(0, 48) * (1 - abs(x - 410) / 220)
            r = rng.uniform(12, 24)
            c.ellipse(x, y, r, r * 0.8, rng.choice(bag_cols))
        for _ in range(80):
            x, y = rng.uniform(120, 720), rng.uniform(415, 510)
            r = rng.uniform(6, 20)
            if rng.random() < 0.6:
                c.ellipse(x, y, r, r * 0.7, rng.choice(bag_cols))
            else:
                c.rect(x, y, x + r * 1.4, y + r * 0.6, rng.choice([(200, 60, 50), (240, 240, 230), (90, 150, 210),
                                                                  (230, 200, 60)]))
        c.ellipse(420, 490, 150, 16, (120, 112, 96))
        for _ in range(40):
            c.ellipse(rng.uniform(240, 600), rng.uniform(240, 330), 1.6, 1.6, (20, 20, 20))
    else:
        c.rect(0, 452, W, 470, (120, 170, 90))
        tree(c, 140, 440, 70)
        tree(c, 680, 445, 80)
        c.rect(590, 400, 700, 410, (150, 110, 70))
        c.rect(598, 410, 604, 440, (90, 90, 90))
        c.rect(686, 410, 692, 440, (90, 90, 90))
    return c


def scene_lighting(rng, before):
    c = Canvas()
    hz = 270
    sky(c, (8, 14, 38), (30, 42, 80), hz)
    for _ in range(80):
        c.ellipse(rng.uniform(0, W), rng.uniform(0, hz - 60), 1.1, 1.1, (230, 230, 255))
    c.ellipse(660, 70, 22, 22, (240, 240, 220))
    mountains(c, rng, hz, (20, 28, 50))
    skyline(c, rng, hz, night=True)
    c.gradient(hz, H, (32, 35, 45), (20, 22, 28))
    tl, tr, bl, br = 380, 470, 40, 1000
    c.poly([(tl, hz), (tr, hz), (br, H), (bl, H)], (40, 42, 50))
    lamps = [(0.12, 70), (0.3, 110), (0.58, 170), (0.95, 250)]
    glow = Canvas("RGBA")
    for t, height in lamps:
        x = tl + (bl - tl) * t - 30 * (0.3 + t)
        y = hz + t * (H - hz)
        top = y - height
        arm = 38 * (0.4 + t)
        broken = before and t > 0.5 and t < 0.7
        pole = (120, 126, 140)
        c.line([(x, y), (x, top)], pole, 3 + 4 * t)
        if broken:
            c.line([(x, top), (x + arm * 0.8, top + arm * 0.5)], pole, 2 + 2 * t)
            head = (x + arm * 0.8, top + arm * 0.5)
        else:
            c.line([(x, top), (x + arm, top - 6)], pole, 2 + 2 * t)
            head = (x + arm, top - 4)
        on = not before
        c.ellipse(head[0], head[1], 9 + 8 * t, 4 + 3 * t, (255, 236, 170) if on else (84, 88, 100))
        if on:
            glow.ellipse(head[0], head[1], 40 + 40 * t, 30 + 30 * t, (255, 214, 120, 150))
            gy = y + 4
            glow.poly([(head[0] - 6, head[1]), (head[0] + 6, head[1]), (head[0] + 90 * (0.4 + t), gy),
                       (head[0] - 90 * (0.4 + t), gy)], (255, 220, 140, 55))
            glow.ellipse(head[0], gy, 100 * (0.4 + t), 16 * (0.4 + t), (255, 214, 140, 70))
    if not before:
        c.composite(glow, blur=10)
    else:
        dim = Canvas("RGBA")
        dim.rect(0, hz, W, H, (0, 0, 0, 60))
        c.composite(dim)
    return c


def scene_water(rng, before, steam=False):
    c = Canvas()
    hz = 250
    day_backdrop(c, rng, hz, top=(160, 190, 220), bottom=(226, 234, 242))
    c.gradient(hz, H, (226, 229, 233), (200, 204, 210))
    for _ in range(25):
        c.ellipse(rng.uniform(0, W), rng.uniform(hz + 20, H), rng.uniform(20, 60), rng.uniform(4, 10),
                  (170, 160, 146))
    py0, py1 = 360, 396
    if before:
        pipe = (140, 94, 64) if not steam else (150, 146, 138)
    else:
        pipe = (56, 118, 190) if not steam else (204, 208, 214)
    for sx in range(60, W, 170):
        c.rect(sx, py1, sx + 14, 440, (120, 120, 124))
    c.rect(-10, py0, W + 10, py1, pipe)
    c.rect(-10, py0 + 5, W + 10, py0 + 11, lighter(pipe, 0.35))
    c.rect(-10, py1 - 6, W + 10, py1, darker(pipe, 0.8))
    if before:
        for _ in range(18):
            x = rng.uniform(0, W)
            c.ellipse(x, rng.uniform(py0 + 4, py1 - 4), rng.uniform(8, 22), rng.uniform(3, 8), darker(pipe, 0.7))
        lx = 420
        if steam:
            for _ in range(10):
                c.poly([(lx - 60 + rng.uniform(-20, 20), py0), (lx - 30, py0 - rng.uniform(4, 14)),
                        (lx + 40 + rng.uniform(-20, 20), py0)], (170, 170, 164))
            cloud = Canvas("RGBA")
            for i in range(22):
                cy = py0 - i * 13
                cloud.ellipse(lx + rng.uniform(-30, 30) + i * 4, cy, 26 + i * 3.4, 22 + i * 2.2,
                              (250, 250, 250, 150))
            c.composite(cloud, blur=9)
        c.ellipse(lx + 10, 470, 190, 32, (150, 190, 222))
        c.ellipse(lx - 20, 466, 110, 14, (196, 222, 240))
        spray = Canvas("RGBA")
        for _ in range(140):
            a = rng.uniform(-2.6, -0.5)
            dist = rng.uniform(5, 110)
            spray.ellipse(lx + math.cos(a) * dist, py0 + 6 + math.sin(a) * dist * 0.9 + dist * dist / 180,
                          rng.uniform(1.5, 3.5), rng.uniform(1.5, 3.5), (110, 170, 225, 220))
        c.composite(spray)
    else:
        for bx in range(40, W, 90):
            c.rect(bx, py0 - 2, bx + 8, py1 + 2, darker(pipe, 0.85))
        c.ellipse(610, 470, 44, 12, (90, 94, 100))
        c.ellipse(610, 470, 36, 9, (120, 124, 130))
        tree(c, 110, 450, 60, leaf=(90, 140, 90))
    return c


def scene_heating(rng, before):
    return scene_water(rng, before, steam=True)


def ger(c, x, y, size):
    w, h = size, size * 0.45
    c.rect(x - w / 2, y - h, x + w / 2, y, (242, 240, 234))
    c.line([(x - w / 2, y - h * 0.55), (x + w / 2, y - h * 0.55)], (150, 110, 70), 2)
    pts = [(x - w / 2 - 4, y - h)]
    for i in range(21):
        a = math.pi * i / 20
        pts.append((x - math.cos(a) * (w / 2 + 4), y - h - math.sin(a) * size * 0.28))
    c.poly(pts, (228, 225, 216))
    c.rect(x - w * 0.09, y - h * 0.72, x + w * 0.09, y, (214, 110, 40))
    c.rect(x + w * 0.12, y - h - size * 0.42, x + w * 0.16, y - h - size * 0.16, (60, 60, 62))
    return (x + w * 0.14, y - h - size * 0.42)


def scene_air(rng, before):
    c = Canvas()
    hz = 245
    if before:
        sky(c, (150, 146, 135), (198, 190, 174), hz)
        mountains(c, rng, hz, (150, 142, 124))
    else:
        sky(c, (100, 165, 235), (210, 232, 252), hz)
        mountains(c, rng, hz, (118, 148, 118))
    c.gradient(hz, H, (196, 182, 150), (160, 144, 112))
    for fy in (300, 380, 460):
        c.line([(0, fy), (W, fy - 12)], (130, 96, 60), 3)
        for fx in range(0, W, 26):
            c.line([(fx, fy - fx * 12 / W), (fx, fy - 22 - fx * 12 / W)], (130, 96, 60), 2)
    chimneys = []
    for gx, gy, gs in [(120, 292, 70), (330, 286, 60), (560, 290, 74), (720, 296, 56), (220, 372, 96),
                       (480, 372, 104), (680, 380, 92), (110, 458, 120), (400, 462, 128)]:
        chimneys.append(ger(c, gx, gy, gs))
    if before:
        haze = Canvas("RGBA")
        haze.rect(0, 0, W, H, (170, 160, 140, 80))
        c.composite(haze)
        for layer_no in range(2):
            smoke = Canvas("RGBA")
            for (cx, cy) in chimneys:
                drift = rng.uniform(0.6, 1.4)
                for i in range(layer_no * 7, layer_no * 7 + 9):
                    smoke.ellipse(cx + i * 8 * drift, cy - i * 15, 12 + i * 4, 9 + i * 3,
                                  (70, 64, 58, 170 - layer_no * 50))
            c.composite(smoke, blur=7 + layer_no * 6)
    else:
        wisps = Canvas("RGBA")
        for (cx, cy) in chimneys[:3]:
            for i in range(4):
                wisps.ellipse(cx + i * 6, cy - i * 10, 5 + i * 2, 4 + i * 2, (255, 255, 255, 70))
        c.composite(wisps, blur=4)
        c.rect(640, 330, 700, 350, (40, 60, 110))
        for k in range(4):
            c.line([(640 + k * 15, 330), (640 + k * 15, 350)], (120, 150, 200), 1)
    return c


def scene_transport(rng, before):
    c = Canvas()
    hz = 240
    day_backdrop(c, rng, hz)
    c.gradient(hz, 425, (206, 202, 194), (190, 186, 178))
    c.rect(0, 425, W, H, (58, 60, 66))
    c.rect(0, 420, W, 428, (220, 214, 204))
    for x in range(0, W, 90):
        c.rect(x, 474, x + 50, 480, (235, 235, 230) if not before else (140, 140, 136))
    roof = (32, 66, 124) if not before else (120, 116, 110)
    c.rect(222, 246, 578, 266, roof, r=4)
    for px in (236, 560):
        c.rect(px, 266, px + 8, 414, darker(roof, 0.8))
    glass = (190, 222, 238) if not before else (168, 182, 186)
    c.rect(248, 276, 552, 396, glass)
    c.rect(248, 276, 552, 280, lighter(glass, 0.4))
    if not before:
        c.rect(452, 282, 546, 390, (250, 250, 250))
        c.rect(458, 288, 540, 330, (37, 99, 235))
        c.rect(458, 336, 540, 384, (255, 196, 40))
    c.rect(300, 358, 500, 370, (150, 106, 64))
    if before:
        c.poly([(300, 358), (400, 358), (400, 370), (300, 382)], (150, 106, 64))
        for cx, cy in [(320, 310), (500, 300)]:
            for _ in range(9):
                a = rng.uniform(0, math.pi * 2)
                c.line([(cx, cy), (cx + math.cos(a) * rng.uniform(30, 70), cy + math.sin(a) * rng.uniform(20, 50))],
                       (90, 96, 100), 1.4)
        for _ in range(6):
            pts = [(rng.uniform(260, 540), rng.uniform(290, 390))]
            for _ in range(6):
                pts.append((pts[-1][0] + rng.uniform(-25, 25), pts[-1][1] + rng.uniform(-12, 12)))
            c.line(pts, rng.choice([(200, 40, 60), (40, 40, 40), (60, 120, 200)]), 3)
        c.poly([(400, 246), (470, 246), (452, 262), (410, 258)], (214, 233, 250))
    c.rect(612, 250, 618, 418, (90, 94, 100))
    c.rect(592, 238, 640, 280, (37, 99, 235) if not before else (110, 120, 140), r=4)
    c.rect(600, 250, 632, 268, (250, 250, 250))
    if not before:
        c.rect(-20, 398, 300, 500, (37, 99, 235), r=14)
        c.rect(-20, 398, 300, 414, (29, 78, 190), r=10)
        for wx in range(0, 290, 48):
            c.rect(wx, 420, wx + 38, 450, (200, 226, 244), r=3)
        c.ellipse(60, 500, 22, 22, (30, 30, 30))
        c.ellipse(240, 500, 22, 22, (30, 30, 30))
    return c


def scene_crosswalk(rng, before):
    c = Canvas()
    hz = 230
    day_backdrop(c, rng, hz)
    c.gradient(hz, 300, (208, 203, 194), (196, 190, 180))
    c.rect(0, 300, W, 470, (56, 58, 64) if not before else (98, 98, 98))
    c.gradient(470, H, (200, 195, 185), (184, 178, 168))
    c.rect(0, 296, W, 302, (230, 226, 218))
    c.rect(0, 468, W, 474, (230, 226, 218))
    for i in range(7):
        x = 250 + i * 44
        col = (246, 246, 242) if not before else (150, 150, 144)
        c.poly([(x, 304), (x + 26, 304), (x + 38, 466), (x + 12, 466)], col)
        if before:
            for _ in range(4):
                yy = rng.uniform(310, 460)
                c.ellipse(x + 18 + (yy - 304) * 0.074, yy, rng.uniform(6, 14), rng.uniform(4, 10), (98, 98, 98))
    if before:
        for _ in range(6):
            crack(c, rng, rng.uniform(40, 760), rng.uniform(320, 460), rng.uniform(40, 120), (60, 60, 60))
        c.ellipse(640, 420, 46, 14, (44, 44, 46))
    else:
        for i in range(16):
            c.poly([(40 + i * 12, 440), (52 + i * 12, 440), (52 + i * 12, 452), (40 + i * 12, 452)],
                   (240, 196, 40) if i % 2 == 0 else (30, 30, 30))
        c.rect(700, 250, 706, 480, (90, 94, 100))
        c.rect(676, 212, 730, 266, (37, 99, 235), r=4)
        c.poly([(703, 220), (726, 258), (680, 258)], (250, 250, 250))
        c.ellipse(703, 236, 4, 4, (30, 30, 30))
        c.line([(703, 240), (703, 252)], (30, 30, 30), 3)
        c.rect(120, 200, 126, 480, (60, 64, 70))
        c.rect(106, 150, 140, 214, (40, 44, 50), r=6)
        for k, col in enumerate([(80, 40, 40), (90, 80, 30), (60, 220, 110)]):
            c.ellipse(123, 162 + k * 20, 7, 7, col)
    return c


def scene_playground(rng, before):
    c = Canvas()
    hz = 250
    day_backdrop(c, rng, hz, max_h=110)
    leaf = (120, 118, 82) if before else (62, 150, 72)
    for x in range(20, W, 110):
        tree(c, x + rng.uniform(-20, 20), hz + 25, rng.uniform(40, 60), leaf)
    if before:
        c.gradient(hz + 20, H, (186, 164, 128), (160, 138, 104))
    else:
        c.gradient(hz + 20, H, (128, 192, 94), (98, 166, 70))
        c.ellipse(400, 430, 330, 70, (196, 98, 72))
    frame = (130, 92, 62) if before else (220, 52, 52)
    c.line([(170, 460), (215, 300)], frame, 6)
    c.line([(260, 460), (215, 300)], frame, 6)
    c.line([(390, 460), (345, 300)], frame, 6)
    c.line([(300, 460), (345, 300)], frame, 6)
    c.line([(210, 302), (350, 302)], frame, 7)
    if before:
        c.line([(245, 305), (245, 395)], (110, 110, 110), 2)
        c.line([(245, 395), (285, 420)], (110, 110, 110), 2)
        c.rect(236, 390, 274, 400, (120, 90, 60))
    else:
        for sx, col in ((250, (250, 196, 40)), (305, (37, 99, 235))):
            c.line([(sx - 14, 305), (sx - 14, 398)], (120, 120, 120), 2)
            c.line([(sx + 14, 305), (sx + 14, 398)], (120, 120, 120), 2)
            c.rect(sx - 18, 396, sx + 18, 404, col, r=2)
    base = (140, 140, 136) if before else (37, 99, 235)
    chute = (150, 146, 136) if before else (245, 190, 30)
    c.rect(520, 300, 600, 312, base)
    c.line([(526, 312), (526, 460)], base, 5)
    c.line([(594, 312), (594, 460)], base, 5)
    for ly in range(330, 460, 22):
        c.line([(526, ly), (594, ly)], base, 3)
    if before:
        c.poly([(600, 304), (650, 360), (636, 372), (596, 318)], chute)
        c.poly([(672, 400), (740, 450), (726, 462), (660, 412)], chute)
        for _ in range(30):
            c.ellipse(rng.uniform(100, 760), rng.uniform(430, 510), rng.uniform(3, 7), 2.5,
                      rng.choice([(230, 230, 220), (90, 140, 90), (200, 60, 50)]))
    else:
        c.poly([(600, 304), (740, 452), (722, 462), (596, 320)], chute)
        for _ in range(40):
            x, y = rng.uniform(20, 780), rng.uniform(470, 515)
            c.ellipse(x, y, 4, 4, rng.choice([(250, 90, 120), (250, 210, 60), (255, 255, 255), (180, 90, 220)]))
        c.rect(40, 420, 130, 428, (150, 110, 70))
    return c


def scene_building(rng, before, kind="other"):
    c = Canvas()
    hz = 380
    sky(c, (125, 183, 238), (214, 233, 250), hz)
    mountains(c, rng, hz - 150, (150, 170, 186), amp=40)
    c.rect(0, hz - 150, W, hz, (150, 170, 186))
    if kind == "health":
        wall = (228, 236, 244) if not before else (190, 194, 190)
    elif kind == "education":
        wall = (244, 226, 190) if not before else (196, 182, 160)
    else:
        wall = (230, 222, 206) if not before else (186, 178, 164)
    c.rect(130, 110, 670, hz, wall)
    c.rect(122, 100, 678, 116, darker(wall, 0.8))
    for row in range(4):
        for col in range(8):
            wx, wy = 158 + col * 64, 138 + row * 56
            if 3 <= col <= 4 and row == 3:
                continue
            broken = before and rng.random() < 0.3
            if broken:
                c.rect(wx, wy, wx + 36, wy + 36, (40, 44, 50))
                if rng.random() < 0.5:
                    c.rect(wx - 2, wy + 12, wx + 38, wy + 20, (140, 100, 60))
                else:
                    for _ in range(4):
                        a = rng.uniform(0, 6.28)
                        c.line([(wx + 18, wy + 18), (wx + 18 + math.cos(a) * 18, wy + 18 + math.sin(a) * 18)],
                               (170, 180, 190), 1)
            else:
                c.rect(wx, wy, wx + 36, wy + 36, (120, 170, 214) if not before else (110, 130, 146))
                c.poly([(wx, wy), (wx + 14, wy), (wx, wy + 14)], (190, 220, 244) if not before else (140, 156, 166))
            c.rect(wx - 3, wy + 36, wx + 39, wy + 40, darker(wall, 0.85))
    c.rect(356, 300, 444, hz, (90, 70, 50) if before else (70, 110, 160))
    c.rect(398, 300, 402, hz, darker(wall, 0.6))
    band = {"health": (250, 250, 250), "education": (37, 99, 235)}.get(kind, (80, 90, 110))
    c.rect(330, 262, 470, 292, band, r=4)
    if kind == "health":
        c.rect(392, 265, 408, 289, (220, 40, 50))
        c.rect(386, 271, 414, 283, (220, 40, 50))
    elif kind == "education":
        c.poly([(380, 270), (400, 276), (420, 270), (420, 286), (400, 290), (380, 286)], (250, 210, 60))
    c.gradient(hz, H, (200, 196, 188), (178, 172, 164))
    for i in range(3):
        c.rect(340 - i * 14, hz + i * 12, 460 + i * 14, hz + 12 + i * 12, (190, 186, 180) if not before
               else (160, 156, 150))
    if before:
        c.poly([(330, hz + 14), (370, hz + 12), (360, hz + 36), (322, hz + 38)], (120, 116, 108))
        for _ in range(12):
            x = rng.uniform(140, 660)
            c.rect(x, 120, x + rng.uniform(4, 10), rng.uniform(180, 360), darker(wall, 0.85))
        c.ellipse(560, 480, 120, 18, (140, 160, 176))
        for _ in range(5):
            pts = [(rng.uniform(160, 640), rng.uniform(320, 370))]
            for _ in range(5):
                pts.append((pts[-1][0] + rng.uniform(-20, 20), pts[-1][1] + rng.uniform(-10, 10)))
            c.line(pts, rng.choice([(200, 40, 60), (40, 40, 40), (60, 120, 200)]), 3)
    else:
        c.poly([(470, hz + 36), (560, hz + 36), (560, hz + 30), (470, hz)], (170, 166, 160))
        for fx in (150, 560):
            c.rect(fx, hz + 50, fx + 110, hz + 76, (90, 150, 70), r=6)
            for _ in range(10):
                c.ellipse(fx + rng.uniform(8, 102), hz + 56 + rng.uniform(0, 14), 4, 4,
                          rng.choice([(250, 90, 120), (250, 210, 60), (255, 255, 255)]))
        tree(c, 80, hz + 70, 70)
        tree(c, 720, hz + 70, 76)
    return c


SCENES = {
    "road": scene_road, "garbage": scene_garbage, "lighting": scene_lighting, "water": scene_water,
    "heating": scene_heating, "air": scene_air, "transport": scene_transport, "safety": scene_crosswalk,
    "green": scene_playground,
    "education": lambda rng, before: scene_building(rng, before, "education"),
    "health": lambda rng, before: scene_building(rng, before, "health"),
    "other": lambda rng, before: scene_building(rng, before, "other"),
}


def generate_image(category: str, before: bool, seed: int, dest: Path) -> None:
    rng = random.Random(seed)
    scene = SCENES.get(category, SCENES["other"])
    img = scene(rng, before).finish()
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=84, optimize=True)
