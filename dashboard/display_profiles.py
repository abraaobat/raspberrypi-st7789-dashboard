"""Display capabilities kept separate from page data and rendering."""

from __future__ import annotations

from dataclasses import dataclass

from PIL import Image


@dataclass(frozen=True)
class DisplayProfile:
    id: str
    label: str
    width: int
    height: int
    color_mode: str
    rotation: int
    driver: str
    available: bool = False


PROFILES = (
    DisplayProfile(
        id="st7789-240x240",
        label="ST7789 240×240 colorido",
        width=240,
        height=240,
        color_mode="RGB",
        rotation=90,
        driver="st7789",
        available=True,
    ),
    DisplayProfile(
        id="ssd1306-128x64",
        label="SSD1306 128×64 monocromático (experimental)",
        width=128,
        height=64,
        color_mode="1",
        rotation=0,
        driver="ssd1306",
    ),
    DisplayProfile(
        id="ili9341-320x240",
        label="ILI9341 320×240 colorido (experimental)",
        width=320,
        height=240,
        color_mode="RGB",
        rotation=90,
        driver="ili9341",
    ),
)

PROFILE_BY_ID = {profile.id: profile for profile in PROFILES}
DEFAULT_PROFILE_ID = "st7789-240x240"


def profile(profile_id: str | None = None) -> DisplayProfile:
    return PROFILE_BY_ID.get(profile_id or DEFAULT_PROFILE_ID, PROFILE_BY_ID[DEFAULT_PROFILE_ID])


def public_profiles() -> list[dict]:
    return [
        {
            "id": item.id,
            "label": item.label,
            "width": item.width,
            "height": item.height,
            "colorMode": item.color_mode,
            "driver": item.driver,
            "available": item.available,
        }
        for item in PROFILES
    ]


def adapt_image(image: Image.Image, target: DisplayProfile) -> Image.Image:
    """Fit the canonical square canvas into a target framebuffer."""

    if image.size != (target.width, target.height):
        contained = image.copy()
        contained.thumbnail((target.width, target.height), Image.Resampling.LANCZOS)
        mode = "RGB" if target.color_mode == "RGB" else "L"
        background = Image.new(mode, (target.width, target.height), 0)
        converted = contained.convert(mode)
        offset = ((target.width - converted.width) // 2, (target.height - converted.height) // 2)
        background.paste(converted, offset)
        image = background
    if target.color_mode == "1":
        return image.convert("L").point(lambda value: 255 if value >= 112 else 0, mode="1")
    return image.convert("RGB")
