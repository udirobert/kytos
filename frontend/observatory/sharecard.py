"""Per-run Open Graph share cards — 1200×630 PNGs rendered at build time.

Each card shows the run id, headline, overall score, leaderboard rank, and
the score trajectory, so a link unfurl on Twitter/Slack carries the actual
result instead of the generic site image.

Pillow is optional: when it is missing (e.g. a minimal environment) the
caller falls back to the site-level default OG image. Nothing here should
ever block the build.
"""

from __future__ import annotations

from typing import Any

BG = (10, 10, 15)  # --bg
PANEL = (18, 18, 26)  # --bg-panel
LINE = (38, 38, 52)  # --line
INK = (235, 235, 242)  # --ink
MUTED = (140, 140, 158)  # --muted
ACCENT = (45, 212, 191)  # --accent
WARN = (245, 158, 11)  # --warn

W, H = 1200, 630


def _font(size: int) -> Any:
    """Best available font — bundled Pillow default scales cleanly; if a
    real DejaVu install is present prefer it for sharper text."""
    from PIL import ImageFont

    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/SFNSMono.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default(size=size)


def _wrap(text: str, max_chars: int = 46) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 > max_chars:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = f"{cur} {w}".strip()
    if cur:
        lines.append(cur)
    return lines[:4]


def _sparkline(draw: Any, values: list[float], box: tuple[int, int, int, int]) -> None:
    """Tiny trajectory inside the card — same story as the site chart."""
    if len(values) < 2:
        return
    x0, y0, x1, y1 = box
    lo, hi = min(values), max(values)
    span = hi - lo or 1.0
    n = len(values)

    def pt(i: int, v: float) -> tuple[float, float]:
        return (
            x0 + i * (x1 - x0) / (n - 1),
            y1 - (v - lo) / span * (y1 - y0),
        )

    pts = [pt(i, v) for i, v in enumerate(values)]
    draw.line(pts, fill=ACCENT, width=3)
    r = 5
    x, y = pts[-1]
    draw.ellipse((x - r, y - r, x + r, y + r), fill=ACCENT)


def render_share_card(
    run_id: str,
    headline: str,
    scores: dict,
    trajectory: list[float],
    dest: Any,
) -> bool:
    """Render a 1200×630 OG card for one run. Returns False when Pillow is
    unavailable so the caller can keep the default site OG image."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return False

    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # Panel + hairline
    d.rounded_rectangle((40, 40, W - 40, H - 40), radius=28, fill=PANEL, outline=LINE, width=2)

    f_eyebrow = _font(26)
    f_runid = _font(30)
    f_head = _font(52)
    f_score = _font(120)
    f_label = _font(24)
    f_rank = _font(44)
    f_foot = _font(24)

    y = 92
    d.text(
        (92, y),
        "KYTOS OBSERVATORY  ·  VIRTUAL CELL CHALLENGE 2026",
        font=f_eyebrow,
        fill=ACCENT,
    )
    y += 58
    d.text((92, y), run_id, font=f_runid, fill=MUTED)
    y += 64

    for line in _wrap(headline):
        d.text((92, y), line, font=f_head, fill=INK)
        y += 62

    # Score block — bottom left
    overall = scores.get("overall")
    rank = scores.get("rank")
    if overall is not None:
        d.text((92, H - 250), f"{float(overall):+.3f}", font=f_score, fill=ACCENT)
        d.text((96, H - 118), "OVERALL SCORE", font=f_label, fill=MUTED)
    if rank:
        d.text((430, H - 215), f"#{rank}", font=f_rank, fill=INK)
        d.text((432, H - 150), "LEADERBOARD RANK", font=f_label, fill=MUTED)

    # Trajectory — right side
    if trajectory:
        d.text((W - 420, H - 258), "SCORE TRAJECTORY", font=f_label, fill=MUTED)
        _sparkline(d, trajectory, (W - 420, H - 220, W - 100, H - 120))

    d.text((92, H - 74), "kytosapp.netlify.app", font=f_foot, fill=MUTED)
    d.text((W - 340, H - 74), "build in public", font=f_foot, fill=WARN)

    img.save(dest, "PNG", optimize=True)
    return True
