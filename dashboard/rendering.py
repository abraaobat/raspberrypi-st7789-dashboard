"""Pillow renderer shared by physical display, previews and tests."""

from __future__ import annotations

from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from .catalog import catalog_by_id
from .display_profiles import adapt_image, profile

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
YELLOW = (255, 215, 80)

ACCENT_COLORS = {
    "blue": BLUE,
    "cyan": CYAN,
    "green": GREEN,
    "orange": ORANGE,
    "purple": PURPLE,
    "red": RED,
}

FONT_REGULAR_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "DejaVuSans.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
)
FONT_BOLD_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "DejaVuSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
)


@lru_cache(maxsize=64)
def load_font(size: int, bold: bool = False):
    for candidate in FONT_BOLD_CANDIDATES if bold else FONT_REGULAR_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


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


def _state_message(title: str, message: str, page_number: int, page_count: int):
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, title, page_number, page_count)
    card(draw, (8, 53, 232, 220))
    draw.text((22, 83), "SEM DADOS", font=load_font(15, True), fill=ORANGE)
    lines = []
    remaining = message
    while remaining and len(lines) < 4:
        text, font = fit_text(draw, remaining, 190, 15, 12)
        if not text.endswith("..."):
            lines.append((text, font))
            break
        cut = max(1, len(text) - 3)
        space = remaining.rfind(" ", 0, cut)
        if space <= 0:
            lines.append((text, font))
            break
        lines.append((remaining[:space], font))
        remaining = remaining[space + 1 :]
    for index, (line, font) in enumerate(lines):
        draw.text((22, 116 + index * 23), line, font=font, fill=GRAY)
    return image


def _weather_condition(code) -> str:
    if code is None:
        return "SEM DADOS"
    code = int(code)
    if code == 0:
        return "CÉU LIMPO"
    if code in {1, 2}:
        return "PARCIAL"
    if code == 3:
        return "NUBLADO"
    if code in {45, 48}:
        return "NEBLINA"
    if code in {51, 53, 55, 56, 57}:
        return "GAROA"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "CHUVA"
    if code in {71, 73, 75, 77, 85, 86}:
        return "NEVE"
    if code in {95, 96, 99}:
        return "TEMPESTADE"
    return "VARIÁVEL"


def _weather_icon(draw: ImageDraw.ImageDraw, code, is_day: bool):
    code = int(code) if code is not None else -1
    rainy = code in {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
    cloudy = code not in {0, -1}
    if not cloudy:
        if is_day:
            draw.ellipse((30, 72, 84, 126), fill=YELLOW)
            for line in ((57, 58, 57, 68), (57, 130, 57, 140), (16, 99, 26, 99), (88, 99, 98, 99)):
                draw.line(line, fill=YELLOW, width=3)
        else:
            draw.ellipse((31, 70, 86, 125), fill=PURPLE)
            draw.ellipse((48, 63, 93, 108), fill=BG)
        return
    draw.ellipse((24, 84, 69, 122), fill=(105, 115, 135))
    draw.ellipse((49, 70, 94, 122), fill=(125, 135, 155))
    draw.rounded_rectangle((22, 99, 98, 127), radius=13, fill=(125, 135, 155))
    if rainy:
        for x in (35, 57, 79):
            draw.line((x, 134, x - 4, 146), fill=BLUE, width=3)


def draw_weather_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    weather = snapshot.get("weather") or {}
    if not weather.get("configured", True):
        return _state_message("CLIMA", "Configure localização e coordenadas no painel web.", page_number, page_count)
    if weather.get("loading") and weather.get("temperatureC") is None:
        return _state_message("CLIMA", "Buscando a primeira previsão meteorológica.", page_number, page_count)
    if weather.get("temperatureC") is None:
        return _state_message("CLIMA", weather.get("error") or "Previsão indisponível.", page_number, page_count)

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "CLIMA", page_number, page_count)
    location, location_font = fit_text(draw, weather.get("locationName"), 150, 14, 10, True)
    draw.text((12, 48), location.upper(), font=location_font, fill=CYAN)
    if weather.get("stale") or weather.get("error"):
        draw.text((185, 49), "CACHE", font=load_font(10, True), fill=ORANGE)

    _weather_icon(draw, weather.get("weatherCode"), weather.get("isDay", True))
    _draw_value(
        draw,
        (112, 72),
        temperature_label(weather.get("temperatureC"), config["temperatureUnit"]),
        112,
        48,
        32,
    )
    condition, condition_font = fit_text(draw, _weather_condition(weather.get("weatherCode")), 112, 13, 10, True)
    draw.text((112, 124), condition, font=condition_font, fill=GRAY)
    apparent = temperature_label(weather.get("apparentC"), config["temperatureUnit"])
    draw.text((112, 143), f"SEN {apparent}", font=load_font(11, True), fill=PURPLE)

    card(draw, (8, 161, 76, 226))
    draw.text((17, 170), "MIN", font=load_font(12, True), fill=BLUE)
    _draw_value(draw, (17, 193), temperature_label(weather.get("minimumC"), config["temperatureUnit"]), 50, 22, 17)

    card(draw, (86, 161, 154, 226))
    draw.text((95, 170), "MAX", font=load_font(12, True), fill=ORANGE)
    _draw_value(draw, (95, 193), temperature_label(weather.get("maximumC"), config["temperatureUnit"]), 50, 22, 17)

    card(draw, (164, 161, 232, 226))
    draw.text((173, 170), "CHUVA", font=load_font(11, True), fill=CYAN)
    probability = weather.get("precipitationProbability")
    _draw_value(draw, (173, 193), percent_label(probability), 50, 22, 16)
    draw.text((174, 229), "OPEN-METEO", font=load_font(7, True), fill=GRAY)
    return image


def draw_sysops_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    del config
    values = snapshot.get("sysops") or {}
    if values.get("loading") and values.get("diskPercent") is None:
        return _state_message("SYSOPS", "Coletando saúde da rede e dos serviços.", page_number, page_count)

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "SYSOPS", page_number, page_count)

    card(draw, (8, 49, 114, 117))
    draw.text((17, 57), "DISCO", font=load_font(13, True), fill=CYAN)
    _draw_value(draw, (17, 78), percent_label(values.get("diskPercent")), 88, 25, 18)
    progress_bar(draw, 17, 103, 88, values.get("diskPercent"))

    card(draw, (124, 49, 232, 117))
    draw.text((133, 57), "GATEWAY", font=load_font(13, True), fill=GREEN)
    ping = values.get("pingMs")
    ping_label = "OFF" if ping is None else f"{ping:.0f}ms"
    _draw_value(draw, (133, 79), ping_label, 90, 24, 17, GREEN if ping is not None else RED)

    throttle = values.get("throttling")
    draw.text((12, 128), "ALIMENTAÇÃO", font=load_font(12, True), fill=PURPLE)
    power = throttle or "SEM DADOS"
    power_color = GREEN if power == "OK" else (GRAY if throttle is None else ORANGE)
    power_value, power_font = fit_text(draw, power, 90, 13, 10, True)
    power_x = 228 - text_width(draw, power_value, power_font)
    draw.text((power_x, 127), power_value, font=power_font, fill=power_color)
    draw.line((12, 150, 228, 150), fill=CARD_BORDER)

    services = values.get("services") or []
    if not services:
        draw.text((12, 162), "SERVIÇOS", font=load_font(12, True), fill=BLUE)
        draw.text((12, 184), "Configure até 4 no painel", font=load_font(13), fill=GRAY)
    for index, service in enumerate(services[:3]):
        y = 160 + index * 23
        active = service.get("status") == "active"
        draw.ellipse((12, y + 4, 20, y + 12), fill=GREEN if active else RED)
        name, name_font = fit_text(draw, service.get("name"), 135, 13, 10, True)
        draw.text((27, y), name, font=name_font, fill=WHITE)
        label = "ON" if active else "OFF"
        draw.text((202, y), label, font=load_font(11, True), fill=GREEN if active else RED)
    return image


def draw_custom_page(snapshot: dict, config: dict, page_id: str, page_number: int, page_count: int):
    definition = next(item for item in config["customPages"] if item["id"] == page_id)
    custom = snapshot.get("custom") or {}
    title = definition["title"].upper()
    if custom.get("loading") and "value" not in custom:
        return _state_message(title, "Consultando a fonte HTTP/JSON.", page_number, page_count)
    if "value" not in custom:
        return _state_message(title, custom.get("error") or "Fonte personalizada indisponível.", page_number, page_count)

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, title, page_number, page_count)
    accent = ACCENT_COLORS[definition["accent"]]
    if custom.get("stale") or custom.get("error"):
        draw.text((181, 46), "CACHE", font=load_font(10, True), fill=ORANGE)

    label = definition.get("valueLabel") or "VALOR"
    draw.text((14, 59), label.upper(), font=load_font(14, True), fill=accent)
    value = custom.get("value")
    if isinstance(value, bool):
        value = "ON" if value else "OFF"
    shown = f"{value}{definition.get('unit') or ''}"
    shown, value_font = fit_text(draw, shown, 212, 46, 22, True)
    draw.text((14, 88), shown, font=value_font, fill=WHITE)

    secondary = custom.get("secondary")
    card(draw, (8, 157, 232, 226))
    if definition["layout"] == "status":
        active = str(value).strip().lower() in {"1", "true", "on", "ok", "online", "active", "ativo"}
        draw.ellipse((20, 177, 50, 207), fill=GREEN if active else RED)
        status = "OPERACIONAL" if active else "ATENÇÃO"
        draw.text((65, 178), status, font=load_font(18, True), fill=GREEN if active else RED)
    elif secondary is not None:
        draw.text((18, 168), "DETALHE", font=load_font(11, True), fill=GRAY)
        detail, detail_font = fit_text(draw, secondary, 202, 22, 14, True)
        draw.text((18, 189), detail, font=detail_font, fill=accent)
    else:
        draw.text((18, 170), "FONTE PERSONALIZADA", font=load_font(12, True), fill=GRAY)
        draw.text((18, 194), "HTTP / JSON", font=load_font(18, True), fill=accent)
    return image


def _compact_count(value):
    if value is None:
        return "-"
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1000:.1f}k"
    return f"{value:.0f}"


def _integration_frame(snapshot, key, title, page_number, page_count):
    values = snapshot.get(key) or {}
    if values.get("configured") is False:
        return values, _state_message(title, values.get("error") or "Configure a integração no painel.", page_number, page_count)
    if values.get("loading"):
        return values, _state_message(title, "Consultando a integração.", page_number, page_count)
    if "configured" not in values:
        return values, _state_message(title, values.get("error") or "Integração indisponível.", page_number, page_count)
    return values, None


def draw_pihole_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    del config
    values, unavailable = _integration_frame(snapshot, "pihole", "PI-HOLE", page_number, page_count)
    if unavailable is not None:
        return unavailable
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "PI-HOLE", page_number, page_count)
    draw.text((14, 54), "CONSULTAS BLOQUEADAS", font=load_font(12, True), fill=CYAN)
    if values.get("stale") or values.get("error"):
        draw.text((184, 46), "CACHE", font=load_font(9, True), fill=ORANGE)
    percent = values.get("blockedPercent")
    _draw_value(draw, (14, 75), "-" if percent is None else f"{percent:.1f}%", 212, 46, 30, GREEN)
    for box, label, value, color in [
        ((8, 130, 114, 179), "BLOQUEIOS", values.get("blockedQueries"), GREEN),
        ((124, 130, 232, 179), "CONSULTAS", values.get("totalQueries"), BLUE),
    ]:
        card(draw, box)
        x, y = box[:2]
        draw.text((x + 9, y + 5), label, font=load_font(10, True), fill=color)
        _draw_value(draw, (x + 9, y + 21), _compact_count(value), 89, 21, 15)
    card(draw, (8, 188, 232, 230))
    draw.text((17, 194), "CLIENTES", font=load_font(9, True), fill=CYAN)
    draw.text((125, 194), "DOMÍNIOS", font=load_font(9, True), fill=PURPLE)
    _draw_value(draw, (17, 207), _compact_count(values.get("activeClients")), 90, 17, 12)
    _draw_value(draw, (125, 207), _compact_count(values.get("blockedDomains")), 94, 17, 12)
    return image


def draw_homeassistant_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    del config
    values, unavailable = _integration_frame(snapshot, "homeassistant", "CASA", page_number, page_count)
    if unavailable is not None:
        return unavailable
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "CASA", page_number, page_count)
    if values.get("stale") or values.get("error"):
        draw.text((184, 43), "CACHE", font=load_font(9, True), fill=ORANGE)
    for index, entity in enumerate((values.get("entities") or [])[:4]):
        y = 54 + index * 42
        card(draw, (8, y, 232, y + 37))
        label, font = fit_text(draw, entity.get("label"), 196, 10, 9, True)
        draw.text((15, y + 3), label, font=font, fill=CYAN)
        state = entity.get("state")
        available = entity.get("available", False)
        text = f"{state}{entity.get('unit') or ''}" if available else "SEM DADOS"
        color = GREEN if available and state == "on" else (WHITE if available else GRAY)
        _draw_value(draw, (15, y + 16), text.upper() if state in {"on", "off"} else text, 201, 16, 11, color)
    draw.text((14, 227), "HOME ASSISTANT · LEITURA", font=load_font(8, True), fill=GRAY)
    return image


def draw_clock_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    del config
    values = snapshot.get("clock") or {}
    if not values.get("time"):
        return _state_message("RELÓGIO", "Hora indisponível.", page_number, page_count)
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "RELÓGIO", page_number, page_count)
    weekday, weekday_font = fit_text(draw, values.get("weekday"), 212, 14, 11, True)
    draw.text((14, 58), weekday, font=weekday_font, fill=CYAN)
    shown, shown_font = fit_text(draw, values["time"], 212, 44, 28, True)
    draw.text(((WIDTH - text_width(draw, shown, shown_font)) / 2, 91), shown, font=shown_font, fill=WHITE)
    draw.text((14, 149), values.get("date") or "-", font=load_font(20, True), fill=WHITE)
    if values.get("period"):
        draw.text((194, 152), values["period"], font=load_font(11, True), fill=GREEN)
    card(draw, (8, 187, 232, 228))
    zone, zone_font = fit_text(draw, values.get("timezone"), 205, 12, 9, True)
    draw.text((16, 199), zone, font=zone_font, fill=GRAY)
    return image


def draw_pomodoro_page(snapshot: dict, config: dict, page_number: int, page_count: int):
    del config
    values = snapshot.get("pomodoro") or {}
    if values.get("error") or not values.get("status"):
        return _state_message("POMODORO", values.get("error") or "Cronômetro indisponível.", page_number, page_count)
    labels = {"idle": "PRONTO PARA FOCAR", "running": "FOCO EM ANDAMENTO", "paused": "PAUSADO",
              "completed": "CICLO CONCLUÍDO", "interrupted": "PI REINICIADO"}
    status = values["status"]
    color = GREEN if status == "completed" else (ORANGE if status in {"paused", "interrupted"} else CYAN)
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    header(draw, "POMODORO", page_number, page_count)
    label, label_font = fit_text(draw, labels.get(status, "SEM DADOS"), 212, 13, 11, True)
    draw.text((14, 58), label, font=label_font, fill=color)
    remaining = values.get("remainingSeconds")
    text = "--:--" if remaining is None else f"{int(remaining) // 60:02}:{int(remaining) % 60:02}"
    shown, shown_font = fit_text(draw, text, 212, 54, 36, True)
    draw.text(((WIDTH - text_width(draw, shown, shown_font)) / 2, 88), shown, font=shown_font, fill=WHITE)
    draw.rounded_rectangle((14, 158, 226, 170), radius=6, fill=CARD_BORDER)
    progress = max(0, min(1, values.get("progress") or 0))
    if progress:
        draw.rounded_rectangle((14, 158, 14 + max(2, 212 * progress), 170), radius=6, fill=color)
    card(draw, (8, 188, 232, 228))
    hint = "INICIE OUTRO CICLO" if status in {"completed", "interrupted"} else "CONTROLE PELO PAINEL"
    draw.text((16, 199), hint, font=load_font(11, True), fill=GRAY)
    return image


RENDERERS = {
    "status": draw_status_page,
    "network": draw_network_page,
    "hardware": draw_hardware_page,
    "sysops": draw_sysops_page,
    "weather": draw_weather_page,
    "pihole": draw_pihole_page,
    "homeassistant": draw_homeassistant_page,
    "clock": draw_clock_page,
    "pomodoro": draw_pomodoro_page,
}


def render_page(page_id: str, snapshot: dict, config: dict):
    enabled = [page["id"] for page in config["pages"] if page.get("enabled")]
    if page_id not in enabled:
        raise ValueError(f"página não habilitada: {page_id}")
    if page_id not in catalog_by_id(config.get("customPages")):
        raise ValueError(f"página desconhecida: {page_id}")
    if page_id.startswith("custom:"):
        image = draw_custom_page(snapshot, config, page_id, enabled.index(page_id) + 1, len(enabled))
    else:
        image = RENDERERS[page_id](snapshot, config, enabled.index(page_id) + 1, len(enabled))
    return adapt_image(image, profile(config.get("displayProfile")))
