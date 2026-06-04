"""Generate the podcast cover art (1500x1500 PNG) programmatically.

Minimal, modern: dark navy background with a subtle vertical gradient, the
lowercase wordmark "earworm" in San Francisco, and a single coral accent dot as
the period. The Daily meets Stratechery — no clip art, lots of negative space.

Usage: uv run python scripts/make_cover.py [out_path]
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 1500
NAVY_TOP = (22, 33, 62)     # #16213e
NAVY_BOTTOM = (26, 26, 46)  # #1a1a2e
TEXT = (245, 245, 247)      # near-white
ACCENT = (233, 69, 96)      # #e94560 coral

FONT_PATH = "/System/Library/Fonts/SFNS.ttf"


def _gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """Vertical top->bottom linear gradient."""
    base = Image.new("RGB", (1, size))
    px = base.load()
    for y in range(size):
        t = y / (size - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return base.resize((size, size))


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(FONT_PATH, size)
    try:  # SFNS is a variable font; nudge toward a confident medium weight.
        font.set_variation_by_axes([560])
    except Exception:  # noqa: BLE001 - non-variable fallback is fine
        pass
    return font


def make_cover(out_path: Path) -> Path:
    img = _gradient(SIZE, NAVY_TOP, NAVY_BOTTOM)
    draw = ImageDraw.Draw(img)

    word = "earworm"
    font = _load_font(380)  # leaves generous margins — negative space is the look

    # Center the wordmark on its real ink bounds. "earworm" has no descenders, so
    # the bbox bottom is the baseline.
    bbox = draw.textbbox((0, 0), word, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (SIZE - text_w) / 2 - bbox[0]
    y = (SIZE - text_h) / 2 - bbox[1]
    draw.text((x, y), word, font=font, fill=TEXT)

    # Coral accent dot as the period: sit on the baseline, just past the final "f".
    word_right = x + bbox[2]
    baseline = y + bbox[3]
    dot_r = 26
    gap = 30
    dot_cx = word_right + gap + dot_r
    dot_cy = baseline - dot_r
    draw.ellipse(
        [dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r],
        fill=ACCENT,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config/cover.png")
    p = make_cover(out)
    print(f"wrote {p} ({Image.open(p).size[0]}x{Image.open(p).size[1]})")
