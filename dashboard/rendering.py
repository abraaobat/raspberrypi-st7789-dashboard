"""Pillow renderer shared by physical display, previews and tests."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

WIDTH = 240
HEIGHT = 240

BG = (5, 6, 9)
CARD = (18, 20, 25)
CARD_BORDER = (55, 60, 70)
WHITE = (245, 245, 245)
GRAY = (145, 150, 160)
GREEN = (70, 220, 130)
BLUE = (70, 150, 255)
CYAN = (60, 210, 235)
ORANGE = (255, 170, 70)
RED = (245, 90, 90)
PURPLE = (175, 120, 255)

FONT_REGULAR_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
)
FONT_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
)


@lru_cache(maxsize=64)
def load_font(size: int, bold: bool = False):
    for candidate in FONT_BOLD_CANDIDATES if bold else FONT_REGULAR_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def text_width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def fit_text(
    draw: ImageDraw.ImageDraw,
    text,
    max_width: int,
    preferred_size: int,
    minimum_size: int = 10,
    bold: bool = False,
):
    value = "-" if text is None or text == "" else str(text)
    for size in range(preferred_size, minimum_size - 1, -1):
        font = load_font(size, bold)
        if text_width(draw, value, font) <= max_width:
            return value, font

    font = load_font(minimum_size, bold)
    ellipsis = "..."
    while value and text_width(draw, value + ellipsis, font) > max_width:
        value = value[:-1]
    return (value + ellipsis) if value else ellipsis, font


def percent_label(value) -> str:
    return "-" if value is None else f"{value:.0f}%"


def temperature_label(value, unit: str) -> str:
    if value is None:
        return "-"
    if unit == "fahrenheit":
        return f"{(value * 9 / 5) + 32:.0f}°"
    return f"{value:.0f}°"


def card(draw: ImageDraw.ImageDraw, box):
    draw.rounded_rectangle(box, radius=10, fill=CARD, outline=CARD_BORDER, width=1)


def header(draw: ImageDraw.ImageDraw, title: str, page_number: int, page_count: int):
    title_value, title_font = fit_text(draw, title, 165, 22, 16, True)
    draw.text((10, 7), title_value, font=title_font, fill=WHITE)
    marker = f"{page_number}/{page_count}"
    marker_font = load_font(12, True)
    draw.text((230 - text_width(draw, marker, marker_font), 12), marker, font=marker_font, fill=GRAY)
    draw.line((10, 38, 230, 38), fill=CARD_BORDER, width=1)


def progress_bar(draw: ImageDraw.ImageDraw, x: int, y: int, width: int, value, color=BLUE):
    height = 8
    draw.rounded_rectangle((x, y, x + width, y + height), radius=4, fill=(42, 45, 52))
    if value is None:
        return
    bounded = max(0.0, min(100.0, float(value)))
    fill_width = int(width * bounded / 100)
    if fill_width > 0:
        draw.rounded_rectangle((x, y, x + fill_width, y + height), radius=4, fill=color)


def _draw_value(draw, position, value, max_width, size=35, minimum=20, color=WHITE):
    text, font = fit_text(draw, value, max_width, size, minimum, True)
    draw.text(position, text, font=font, fill=color)


def draw_status_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    cpu = snapshot.get("cpuPercent")
    ram = snapshot.get("ramPercent")
    temp = snapshot.get("temperatureC")
    uptime = snapshot.get("uptime") or "-"
    thresholds = config["thresholds"]

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "STATUS", page_number, page_count)

    card(draw, (8, 48, 116, 132))
    draw.text((17, 57), "CPU", font=load_font(15, True), fill=CYAN)
    _draw_value(draw, (17, 78), percent_label(cpu), 92)
    progress_bar(draw, 17, 116, 88, cpu)

    card(draw, (124, 48, 232, 132))
    draw.text((133, 57), "TEMP", font=load_font(15, True), fill=ORANGE)
    temp_color = WHITE
    if temp is not None and temp >= thresholds["temperatureCritical"]:
        temp_color = RED
    elif temp is not None and temp >= thresholds["temperatureWarning"]:
        temp_color = ORANGE
    _draw_value(
        draw,
        (133, 78),
        temperature_label(temp, config["temperatureUnit"]),
        92,
        color=temp_color,
    )

    card(draw, (8, 144, 116, 228))
    draw.text((17, 153), "RAM", font=load_font(15, True), fill=PURPLE)
    _draw_value(draw, (17, 174), percent_label(ram), 92)
    progress_bar(draw, 17, 212, 88, ram)

    card(draw, (124, 144, 232, 228))
    draw.text((133, 153), "UPTIME", font=load_font(15, True), fill=GREEN)
    _draw_value(draw, (133, 183), uptime, 92, 24, 16)
    return image


def _network_value(draw, label_y, value_y, label, value, label_color, suffix=None):
    draw.text((12, label_y), label, font=load_font(15, True), fill=label_color)
    shown = value or "-"
    if suffix and value:
        shown = f"{value}  {suffix}"
    text, font = fit_text(draw, shown, 216, 19, 13, True)
    draw.text((12, value_y), text, font=font, fill=WHITE if value else GRAY)


def draw_network_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    del config
    network = snapshot.get("network") or {}
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "REDE", page_number, page_count)

    _network_value(draw, 53, 73, "HOSTNAME", snapshot.get("hostname"), CYAN)
    draw.line((12, 102, 228, 102), fill=CARD_BORDER)

    ethernet_suffix = network.get("ethernetInterface")
    _network_value(draw, 111, 132, "ETHERNET", network.get("ethernetIp"), GREEN, ethernet_suffix)

    wifi_detail = network.get("wifiInterface")
    if network.get("wifiSsid"):
        wifi_detail = f"{wifi_detail or ''} {network['wifiSsid']}".strip()
    _network_value(draw, 160, 181, "WI-FI", network.get("wifiIp"), BLUE, wifi_detail)

    draw.text((12, 209), "TAILSCALE", font=load_font(12, True), fill=PURPLE)
    value, font = fit_text(draw, network.get("tailscaleIp") or "-", 136, 12, 10)
    draw.text((90, 207), value, font=font, fill=GRAY)
    return image


def draw_hardware_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    del config
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "HARDWARE", page_number, page_count)

    draw.text((12, 52), "MODELO", font=load_font(15, True), fill=CYAN)
    model, model_font = fit_text(draw, snapshot.get("model"), 216, 15, 10)
    draw.text((12, 73), model, font=model_font, fill=WHITE)
    draw.line((12, 101, 228, 101), fill=CARD_BORDER)

    draw.text((12, 111), "KERNEL", font=load_font(15, True), fill=PURPLE)
    kernel, kernel_font = fit_text(draw, snapshot.get("kernel"), 216, 15, 10)
    draw.text((12, 132), kernel, font=kernel_font, fill=WHITE)

    card(draw, (8, 166, 112, 226))
    draw.text((18, 174), "USB", font=load_font(15, True), fill=BLUE)
    _draw_value(draw, (18, 195), snapshot.get("usbCount"), 82, 24, 18)

    card(draw, (128, 166, 232, 226))
    draw.text((138, 174), "SPI", font=load_font(15, True), fill=GREEN)
    spi = snapshot.get("spi")
    spi_label = "ON" if spi else "OFF"
    _draw_value(draw, (138, 195), spi_label, 82, 24, 18, GREEN if spi else RED)
    return image


RENDERERS = {
    "status": draw_status_page,
    "network": draw_network_page,
    "hardware": draw_hardware_page,
}


def render_page(page_id: str, snapshot: dict, config: dict):
    enabled = [page["id"] for page in config["pages"] if page.get("enabled")]
    if page_id not in enabled:
        raise ValueError(f"página não habilitada: {page_id}")
    try:
        renderer = RENDERERS[page_id]
    except KeyError as exc:
        raise ValueError(f"página desconhecida: {page_id}") from exc
    return renderer(snapshot, config, enabled.index(page_id) + 1, len(enabled))
