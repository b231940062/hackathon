"""Серверт SVG графикийн геометр тооцоолох энгийн туслах (JS сангүй, офлайн ажиллана)."""
import math

SERIES = {"created": "#2a78d6", "resolved": "#1baf7a"}  # категори палитрын 1, 3-р слот (CVD шалгасан)


def nice_scale(value: float, max_ticks: int = 5) -> tuple[int, int]:
    """Бүхэл тоон тэнхлэг: (дээд утга, алхам). Тоолол учир бутархай шугам гаргахгүй."""
    value = max(1.0, value)
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000):
        top = int(math.ceil(value / step) * step)
        if top / step <= max_ticks:
            return top, step
    return int(value), int(value)


def _top_rounded(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    """Суурь шугамд тулсан, дээд үзүүр нь 4px бөөрөнхий багана."""
    if h <= 0:
        return ""
    r = min(r, w / 2, h)
    base = y + h
    return (f"M{x:.1f},{base:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} "
            f"H{x + w - r:.1f} Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{base:.1f} Z")


def grouped_columns(buckets: list[dict], keys=("created", "resolved"), width=640, height=240) -> dict:
    left, right, top, bottom = 34, 8, 14, 30
    plot_w, plot_h = width - left - right, height - top - bottom
    vmax, step = nice_scale(max([b[k] for b in buckets for k in keys] + [1]))
    n = max(1, len(buckets))
    gw = plot_w / n
    bw = min(18.0, gw * 0.32)
    gap = 2.0
    base_y = top + plot_h
    groups = []
    for i, b in enumerate(buckets):
        gx = left + i * gw
        total_w = bw * len(keys) + gap * (len(keys) - 1)
        x0 = gx + (gw - total_w) / 2
        bars = []
        for j, k in enumerate(keys):
            h = plot_h * b[k] / vmax
            x = x0 + j * (bw + gap)
            bars.append({"key": k, "color": SERIES[k], "path": _top_rounded(x, base_y - h, bw, h),
                         "value": b[k], "label_x": x + bw / 2, "label_y": base_y - h - 4})
        groups.append({"x": gx, "w": gw, "cx": gx + gw / 2, "label": b["label"], "bars": bars,
                       "tip": b.get("tip", "")})
    ticks = [{"y": base_y - plot_h * v / vmax, "label": v} for v in range(0, vmax + 1, step)]
    return {"width": width, "height": height, "left": left, "right": width - right, "base_y": base_y,
            "top": top, "groups": groups, "ticks": ticks, "label_y": height - 10}
