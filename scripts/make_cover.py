"""Generate the podcast cover art (1500x1500 PNG) programmatically.

Minimal, modern: dark navy background with a subtle vertical gradient, the
lowercase wordmark "earworm" in a clean sans-serif, and a single coral accent dot
as the period. The Daily meets Stratechery — no clip art, lots of negative space.

Usage: uv run python scripts/make_cover.py [out_path]
Font:  set EARWORM_COVER_FONT to a .ttf/.otf path to override the auto-detected one.
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 1500
NAVY_TOP = (22, 33, 62)     # #16213e
NAVY_BOTTOM = (26, 26, 46)  # #1a1a2e
TEXT = (245, 245, 247)      # near-white
ACCENT = (233, 69, 96)      # #e94560 coral

WORD = "earworm"
LOCKUP_WIDTH_FRAC = 0.84    # wordmark + accent dot span this fraction of the canvas
DOT_R_FRAC = 0.068          # accent dot radius, as a fraction of the font size
GAP_FRAC = 0.078            # space between the word and the dot, as a fraction of size

# Common bold/medium sans-serif faces, in preference order across platforms.
# Bare filenames are resolved by Pillow's font search; absolute paths cover the
# usual macOS/Linux/Windows locations. The bundled DejaVu fallback (below) means
# at least one always renders, so cover generation never depends on the OS.
FONT_CANDIDATES = (
    "/System/Library/Fonts/SFNS.ttf",                                 # macOS (San Francisco)
    "/System/Library/Fonts/Helvetica.ttc",                            # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",           # Debian/Ubuntu
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",   # Fedora/RHEL
    "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf",               # Noto
    "DejaVuSans-Bold.ttf",                                            # Pillow font search
    "Arial Bold.ttf",
    "arialbd.ttf",                                                    # Windows (Arial Bold)
    "C:\\Windows\\Fonts\\arialbd.ttf",                                # Windows (absolute)
)


def _gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    """Vertical top->bottom linear gradient."""
    base = Image.new("RGB", (1, size))
    px = base.load()
    for y in range(size):
        t = y / (size - 1)
        px[0, y] = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    return base.resize((size, size))


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a sans-serif face at `size`, trying an env override, then a list of
    common system fonts, then Pillow's bundled scalable DejaVu (always present).
    """
    override = os.environ.get("EARWORM_COVER_FONT")
    candidates = (override, *FONT_CANDIDATES) if override else FONT_CANDIDATES
    for path in candidates:
        try:
            font = ImageFont.truetype(path, size)
        except OSError:
            continue
        try:  # variable fonts (e.g. SFNS): nudge toward a confident medium weight.
            font.set_variation_by_axes([560])
        except Exception:  # noqa: BLE001 - static fonts don't support axes; fine
            pass
        return font
    # Guaranteed fallback: Pillow ships DejaVuSans; load_default(size) is scalable
    # (Pillow >= 10.1), so this is a real TrueType render, not a bitmap.
    return ImageFont.load_default(size=size)


def _fit_font(draw: ImageDraw.ImageDraw) -> tuple[ImageFont.FreeTypeFont, int]:
    """Pick a font size so the wordmark + accent dot span LOCKUP_WIDTH_FRAC of the
    canvas. Measured per-font (advance width scales linearly with size), so the
    layout self-adjusts to the word length and whichever font was resolved —
    no hardcoded size that only fit one word on one OS.
    """
    base = 200
    word_w = draw.textlength(WORD, font=_load_font(base))
    # lockup width per unit of font size, size-independent (dot/gap are fractions of size)
    per_size = (word_w + (GAP_FRAC + 2 * DOT_R_FRAC) * base) / base
    size = int(SIZE * LOCKUP_WIDTH_FRAC / per_size)
    return _load_font(size), size


def make_cover(out_path: Path) -> Path:
    img = _gradient(SIZE, NAVY_TOP, NAVY_BOTTOM)
    draw = ImageDraw.Draw(img)

    font, size = _fit_font(draw)
    dot_r = round(size * DOT_R_FRAC)
    gap = round(size * GAP_FRAC)

    # Center the whole lockup (word + gap + dot) on the word's real ink bounds.
    bbox = draw.textbbox((0, 0), WORD, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    lockup_w = text_w + gap + 2 * dot_r
    x = (SIZE - lockup_w) / 2 - bbox[0]
    y = (SIZE - text_h) / 2 - bbox[1]
    draw.text((x, y), WORD, font=font, fill=TEXT)

    # Coral accent dot as the period: on the baseline, just past the final letter.
    word_right = x + bbox[2]
    baseline = y + bbox[3]
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
