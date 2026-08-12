"""Social media poster/carousel slide generation, two ways:

- render_template_poster: draws the slide onto a fixed on-brand PNG template with Pillow.
  Precise, consistent text every time — the exact headline/bullets you gave it come back
  exactly as given, just laid out.
- generate_ai_poster: asks Gemini 2.5 Flash Image to draw the whole slide from a prompt.
  More varied/designed look, but image models aren't reliable at rendering exact multi-line
  text — treat output as a draft to review, not a guaranteed-accurate render.

Both take the same slide dict ({headline, bullets}) and return PNG bytes."""

import functools
import math
from io import BytesIO

from PIL import Image, ImageChops, ImageDraw, ImageFont

import config
from services import imagen_service

_CANVAS_SIZE = (1080, 1350)  # Instagram portrait (4:5)
_MARGIN = 80
_LOGO_WIDTH = 220
_LOGO_POSITION = (_MARGIN, 50)
_INK = (13, 25, 43)
_MUTED = (92, 104, 121)
_PAPER = (255, 255, 252)
_WARM = (238, 229, 211)
_GOLD = (194, 154, 88)
_TEAL = (22, 116, 121)


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))


def _font(pixel_size: int, weight: int, optical_size: int = 24) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(config.FONT_PATH, pixel_size)
    font.set_variation_by_axes([optical_size, weight])
    return font


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont) -> float:
    return draw.textlength(text, font=font)


def _break_long_word(draw: ImageDraw.ImageDraw, word: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    if _text_width(draw, word, font) <= max_width:
        return [word]
    chunks = []
    current = ""
    for char in word:
        candidate = current + char
        if current and _text_width(draw, candidate, font) > max_width:
            chunks.append(current)
            current = char
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        broken = _break_long_word(draw, word, font, max_width)
        if len(broken) > 1:
            if current:
                lines.append(current)
                current = ""
            lines.extend(broken[:-1])
            word = broken[-1]
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _fit_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    max_height: int,
    *,
    start_size: int,
    min_size: int,
    weight: int,
    optical_size: int = 24,
    line_ratio: float = 1.2,
) -> tuple[ImageFont.FreeTypeFont, list[str], int]:
    for size in range(start_size, min_size - 1, -2):
        font = _font(size, weight, optical_size)
        lines = _wrap_text(draw, text, font, max_width)
        line_height = int(size * line_ratio)
        if len(lines) * line_height <= max_height:
            return font, lines, line_height
    font = _font(min_size, weight, optical_size)
    return font, _wrap_text(draw, text, font, max_width), int(min_size * line_ratio)


def _vertical_gradient(top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = _CANVAS_SIZE
    img = Image.new("RGB", _CANVAS_SIZE, top)
    pix = img.load()
    for y in range(height):
        t = y / max(1, height - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(width):
            pix[x, y] = color
    return img


def _draw_editorial_background(draw: ImageDraw.ImageDraw, index: int) -> None:
    width, height = _CANVAS_SIZE
    primary = _hex_to_rgb(config.POSTER_PRIMARY_COLOR)
    accent = _hex_to_rgb(config.POSTER_ACCENT_COLOR)
    draw.rectangle([0, 0, width, 190], fill=primary)
    draw.polygon([(0, 190), (width, 120), (width, 230), (0, 300)], fill=(19, 47, 78))
    draw.rectangle([0, height - 128, width, height], fill=_INK)
    draw.line([_MARGIN, 255, width - _MARGIN, 255], fill=_GOLD, width=4)
    for x in range(-80, width, 90):
        y = 310 + int(18 * math.sin((x + index * 35) / 85))
        draw.line([x, y, x + 52, y - 52], fill=(226, 219, 204), width=3)
    draw.ellipse([width - 300, 250, width + 170, 720], outline=(219, 211, 194), width=22)
    draw.ellipse([-180, 770, 220, 1170], outline=(225, 232, 232), width=18)
    draw.rounded_rectangle([_MARGIN, 315, width - _MARGIN, height - 190], radius=36, fill=_PAPER)
    draw.rectangle([_MARGIN, 315, _MARGIN + 18, height - 190], fill=_GOLD if index % 2 == 0 else accent)


def _draw_kicker(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, fill: tuple[int, int, int]) -> None:
    font = _font(28, 700, optical_size=14)
    text = text.upper()
    w = draw.textlength(text, font=font)
    draw.rounded_rectangle([x, y, x + w + 34, y + 46], radius=23, fill=fill)
    draw.text((x + 17, y + 8), text, font=font, fill=(255, 255, 255))


def _draw_footer(draw: ImageDraw.ImageDraw, index: int, total: int, cta: str | None = None) -> None:
    width, height = _CANVAS_SIZE
    footer_font = _font(30, 650, optical_size=14)
    small_font = _font(24, 500, optical_size=14)
    if cta:
        draw.text((_MARGIN, height - 92), cta, font=footer_font, fill=(255, 255, 255))
    else:
        draw.text((_MARGIN, height - 92), config.FIRM_NAME, font=footer_font, fill=(255, 255, 255))
    if total > 1:
        label = f"{index + 1:02d}/{total:02d}"
        draw.text((width - _MARGIN - draw.textlength(label, font=small_font), height - 88), label, font=small_font, fill=(230, 235, 240))


@functools.lru_cache(maxsize=1)
def _load_logo(target_width: int) -> Image.Image:
    """Loads the vendored logo and keys out its background — the source PNG is RGBA but
    fully opaque (solid white behind the navy artwork, no real alpha), which left a visible
    white box when pasted onto the poster's off-white canvas. Deriving alpha from how far
    each pixel is from white makes the background transparent while keeping the navy
    artwork solid."""
    logo = Image.open(config.LOGO_PATH).convert("RGBA")
    r, g, b, _ = logo.split()
    min_rgb = ImageChops.darker(ImageChops.darker(r, g), b)
    alpha = ImageChops.invert(min_rgb)
    logo = Image.merge("RGBA", (r, g, b, alpha))
    ratio = target_width / logo.width
    return logo.resize((target_width, int(logo.height * ratio)), Image.LANCZOS)


def _draw_logo(img: Image.Image) -> None:
    """Composites the real firm logo (vendored from the live site) onto the canvas. Falls
    back to a plain text wordmark if the logo asset is ever missing, so a deploy hiccup
    degrades gracefully instead of crashing poster generation."""
    try:
        logo = _load_logo(_LOGO_WIDTH)
        draw = ImageDraw.Draw(img)
        x, y = _LOGO_POSITION
        draw.rounded_rectangle(
            [x - 18, y - 14, x + logo.width + 18, y + logo.height + 14],
            radius=18,
            fill=(250, 248, 242),
        )
        img.paste(logo, _LOGO_POSITION, logo)
    except Exception:  # noqa: BLE001
        primary = _hex_to_rgb(config.POSTER_PRIMARY_COLOR)
        ImageDraw.Draw(img).text(
            _LOGO_POSITION, config.FIRM_NAME, font=_font(32, 700), fill=primary
        )


def render_template_poster(slide: dict, index: int, total: int) -> bytes:
    primary = _hex_to_rgb(config.POSTER_PRIMARY_COLOR)
    accent = _hex_to_rgb(config.POSTER_ACCENT_COLOR)
    white = (255, 255, 255)

    width, height = _CANVAS_SIZE
    img = _vertical_gradient((246, 248, 250), _WARM)
    draw = ImageDraw.Draw(img)

    _draw_editorial_background(draw, index)
    _draw_logo(img)

    headline = slide.get("headline", "")
    bullets = [b for b in (slide.get("bullets") or []) if b.strip()]
    is_title_slide = index == 0 and not bullets
    panel_x = _MARGIN + 54
    panel_w = width - panel_x - _MARGIN - 42
    panel_top = 355
    panel_bottom = height - 220

    _draw_kicker(
        draw,
        "Legal Guide" if is_title_slide else f"Key Point {index}",
        panel_x,
        panel_top,
        accent if index % 2 else _TEAL,
    )

    headline_max_h = 430 if is_title_slide else 230
    headline_font, headline_lines, headline_line_height = _fit_wrapped_text(
        draw,
        headline,
        panel_w,
        headline_max_h,
        start_size=86 if is_title_slide else 64,
        min_size=42,
        weight=760,
        optical_size=20,
        line_ratio=1.12,
    )
    y = panel_top + 88
    for line in headline_lines:
        if is_title_slide:
            draw.rounded_rectangle(
                [
                    panel_x - 12,
                    y - 5,
                    panel_x + draw.textlength(line, font=headline_font) + 24,
                    y + headline_line_height - 6,
                ],
                radius=12,
                fill=primary,
            )
            draw.text((panel_x, y), line, font=headline_font, fill=white)
        else:
            draw.text((panel_x, y), line, font=headline_font, fill=primary)
        y += headline_line_height

    if bullets:
        y += 32
        bullet_area_h = max(180, panel_bottom - y)
        bullet_font, _, bullet_line_height = _fit_wrapped_text(
            draw,
            " ".join(bullets),
            panel_w - 92,
            bullet_area_h,
            start_size=40,
            min_size=28,
            weight=450,
            optical_size=16,
            line_ratio=1.24,
        )
        bullet_gap = 24
        for bullet_index, bullet in enumerate(bullets, start=1):
            wrapped = _wrap_text(draw, bullet, bullet_font, panel_w - 108)
            if y + len(wrapped) * bullet_line_height > panel_bottom:
                break
            marker_y = y + 4
            draw.rounded_rectangle(
                [panel_x, marker_y, panel_x + 52, marker_y + 52],
                radius=16,
                fill=(236, 241, 244),
            )
            draw.text(
                (panel_x + 18, marker_y + 9),
                str(bullet_index),
                font=_font(24, 720, optical_size=14),
                fill=accent,
            )
            for wline in wrapped:
                draw.text((panel_x + 78, y), wline, font=bullet_font, fill=_INK)
                y += bullet_line_height
            y += bullet_gap

    if not bullets and not is_title_slide:
        draw.line([panel_x, y + 36, panel_x + 230, y + 36], fill=_GOLD, width=8)
        draw.text((panel_x, y + 78), "Save this before you need it.", font=_font(36, 550, optical_size=16), fill=_MUTED)

    _draw_footer(draw, index, total)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_ai_poster(slide: dict, index: int, total: int) -> bytes:
    bullets = [b for b in (slide.get("bullets") or []) if b.strip()]
    bullets_block = "\n".join(f"- {b}" for b in bullets)
    prompt = (
        f"Design a clean, modern social media carousel slide (portrait, 4:5 aspect ratio) "
        f"for {config.FIRM_NAME}, a personal injury law firm. This is slide {index + 1} of "
        f"{total}.\n\n"
        f'Headline text to display prominently: "{slide.get("headline", "")}"\n'
        + (f"Bullet points to display below it:\n{bullets_block}\n\n" if bullets_block else "\n")
        + "Style: premium editorial legal marketing graphic, layered paper texture, subtle "
        "courthouse or document silhouettes, confident typography, navy, ivory, muted gold, "
        "and restrained teal accents. Use real visual composition, not plain text on a flat "
        "background. Render the headline and bullet text exactly as given, spelled correctly, "
        "large and legible. Do not add any other text, logos, or watermarks."
    )
    return imagen_service.generate_from_prompt(prompt)


def render_single_poster(content: dict) -> bytes:
    primary = _hex_to_rgb(config.POSTER_PRIMARY_COLOR)
    accent = _hex_to_rgb(config.POSTER_ACCENT_COLOR)

    width, height = _CANVAS_SIZE
    img = _vertical_gradient((247, 248, 246), (229, 236, 235))
    draw = ImageDraw.Draw(img)

    _draw_editorial_background(draw, 0)
    _draw_logo(img)

    headline = content.get("headline", "")
    supporting = content.get("supporting_text", "")
    cta = content.get("cta", "")

    panel_x = _MARGIN + 54
    panel_w = width - panel_x - _MARGIN - 42
    y = 360
    _draw_kicker(draw, "Know This", panel_x, y, accent)
    y += 100

    headline_font, headline_lines, headline_line_height = _fit_wrapped_text(
        draw,
        headline,
        panel_w,
        430,
        start_size=84,
        min_size=42,
        weight=780,
        optical_size=20,
        line_ratio=1.1,
    )

    for line in headline_lines:
        draw.text((panel_x, y), line, font=headline_font, fill=primary)
        y += headline_line_height

    support_font, support_lines, support_line_height = _fit_wrapped_text(
        draw,
        supporting,
        panel_w,
        170,
        start_size=42,
        min_size=30,
        weight=430,
        optical_size=16,
        line_ratio=1.24,
    )
    if supporting:
        y += 38
        draw.line([panel_x, y, panel_x + 240, y], fill=_GOLD, width=7)
        y += 34
        for line in support_lines:
            draw.text((panel_x, y), line, font=support_font, fill=_MUTED)
            y += support_line_height

    _draw_footer(draw, 0, 1, cta or None)

    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def generate_ai_single_poster(content: dict) -> bytes:
    prompt = (
        f"Design a clean, modern single social media graphic (portrait, 4:5 aspect ratio) "
        f"for {config.FIRM_NAME}, a personal injury law firm — a single bold-statement post, "
        "not a multi-slide carousel.\n\n"
        f'Headline text to display prominently: "{content.get("headline", "")}"\n'
        f'Supporting line below it: "{content.get("supporting_text", "")}"\n'
        f'Call-to-action text near the bottom: "{content.get("cta", "")}"\n\n'
        "Style: premium editorial legal marketing graphic, layered paper texture, subtle "
        "courthouse/document silhouettes, navy, ivory, muted gold, and restrained teal accents. "
        "It should look like a polished law-firm campaign asset, not text on a flat color. "
        "Render all three text elements exactly as given, spelled correctly, large and legible. "
        "Do not add any other text, logos, or watermarks."
    )
    return imagen_service.generate_from_prompt(prompt)
