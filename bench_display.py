#!/usr/bin/env python3

import socket
import subprocess
import time

import gpiod
import st7789
from gpiod.line import Bias, Direction, Value
from PIL import Image, ImageDraw, ImageFont


WIDTH = 240
HEIGHT = 240

# Display pinout validated on the 1.3" ST7789 module used by this project.
# GPIO24 is intentionally NOT used as backlight: on this board it is BUTTON_B.
display = st7789.ST7789(
    height=HEIGHT,
    width=WIDTH,
    rotation=90,
    port=0,
    cs=0,
    dc=25,
    rst=27,
    spi_speed_hz=40_000_000,
)
display.begin()


# Palette
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


FONT_REGULAR_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def load_font(size, bold=False):
    path = FONT_BOLD_PATH if bold else FONT_REGULAR_PATH
    return ImageFont.truetype(path, size)


FONT_TITLE = load_font(22, True)
FONT_PAGE = load_font(12, True)
FONT_LABEL = load_font(15, True)
FONT_VALUE = load_font(35, True)
FONT_VALUE_SMALL = load_font(24, True)
FONT_MEDIUM = load_font(19, True)
FONT_NORMAL = load_font(15)
FONT_SMALL = load_font(12)


def cmd(command):
    try:
        return subprocess.check_output(
            command,
            shell=True,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return "-"


def get_cpu():
    try:
        return float(cmd("top -bn1 | awk '/Cpu/ {print 100-$8}'"))
    except Exception:
        return 0.0


def get_ram():
    try:
        return float(cmd("free | awk '/Mem:/ {print ($3/$2)*100}'"))
    except Exception:
        return 0.0


def get_temp():
    try:
        return float(cmd("vcgencmd measure_temp | cut -d= -f2 | tr -d \"'C\""))
    except Exception:
        return 0.0


def get_uptime():
    try:
        with open("/proc/uptime", "r", encoding="utf-8") as handle:
            seconds = float(handle.read().split()[0])
    except Exception:
        return "-"

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)

    if hours >= 24:
        days = hours // 24
        hours %= 24
        return f"{days}d {hours}h"

    return f"{hours}h {minutes:02d}m"


def get_ip(interface):
    value = cmd(
        f"ip -4 addr show {interface} "
        "| awk '/inet / {print $2}' "
        "| cut -d/ -f1"
    )
    return value if value else "-"


def get_tailscale_ip():
    value = cmd("tailscale ip -4 2>/dev/null | head -1")
    return value if value else "-"


def get_model():
    model = cmd("tr -d '\\0' < /proc/device-tree/model")
    return model.replace("Raspberry Pi ", "RPi ")


def get_kernel():
    return cmd("uname -r")


def get_usb_count():
    return cmd("lsusb | wc -l")


def spi_status():
    return cmd("test -e /dev/spidev0.0 && echo ON || echo OFF")


def card(draw, box):
    draw.rounded_rectangle(
        box,
        radius=10,
        fill=CARD,
        outline=CARD_BORDER,
        width=1,
    )


def header(draw, title, page):
    draw.text((10, 7), title, font=FONT_TITLE, fill=WHITE)
    draw.text((201, 12), f"{page}/3", font=FONT_PAGE, fill=GRAY)
    draw.line((10, 38, 230, 38), fill=CARD_BORDER, width=1)


def progress_bar(draw, x, y, width, value):
    height = 8

    draw.rounded_rectangle(
        (x, y, x + width, y + height),
        radius=4,
        fill=(42, 45, 52),
    )

    value = max(0, min(100, value))
    fill_width = int(width * value / 100)

    if fill_width > 0:
        draw.rounded_rectangle(
            (x, y, x + fill_width, y + height),
            radius=4,
            fill=BLUE,
        )


def draw_status_page():
    cpu = get_cpu()
    ram = get_ram()
    temp = get_temp()
    uptime = get_uptime()

    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    header(draw, "STATUS", 1)

    card(draw, (8, 48, 116, 132))
    draw.text((17, 57), "CPU", font=FONT_LABEL, fill=CYAN)
    draw.text((17, 78), f"{cpu:.0f}%", font=FONT_VALUE, fill=WHITE)
    progress_bar(draw, 17, 116, 88, cpu)

    card(draw, (124, 48, 232, 132))
    draw.text((133, 57), "TEMP", font=FONT_LABEL, fill=ORANGE)

    temp_color = WHITE
    if temp >= 70:
        temp_color = RED
    elif temp >= 60:
        temp_color = ORANGE

    draw.text((133, 78), f"{temp:.0f}°", font=FONT_VALUE, fill=temp_color)

    card(draw, (8, 144, 116, 228))
    draw.text((17, 153), "RAM", font=FONT_LABEL, fill=PURPLE)
    draw.text((17, 174), f"{ram:.0f}%", font=FONT_VALUE, fill=WHITE)
    progress_bar(draw, 17, 212, 88, ram)

    card(draw, (124, 144, 232, 228))
    draw.text((133, 153), "UPTIME", font=FONT_LABEL, fill=GREEN)
    draw.text((133, 183), uptime, font=FONT_VALUE_SMALL, fill=WHITE)

    return image


def draw_network_page():
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    header(draw, "REDE", 2)

    host = socket.gethostname()
    eth_ip = get_ip("eth0")
    wifi_ip = get_ip("wlan0")
    tailscale_ip = get_tailscale_ip()

    draw.text((12, 53), "HOSTNAME", font=FONT_LABEL, fill=CYAN)
    draw.text((12, 73), host, font=FONT_MEDIUM, fill=WHITE)

    draw.line((12, 102, 228, 102), fill=CARD_BORDER)

    draw.text((12, 111), "ETHERNET", font=FONT_LABEL, fill=GREEN)
    draw.text((12, 132), eth_ip, font=FONT_MEDIUM, fill=WHITE)

    draw.text((12, 160), "WI-FI", font=FONT_LABEL, fill=BLUE)
    draw.text((12, 181), wifi_ip, font=FONT_MEDIUM, fill=WHITE)

    draw.text((12, 209), "TAILSCALE", font=FONT_SMALL, fill=PURPLE)
    draw.text((90, 207), tailscale_ip, font=FONT_SMALL, fill=GRAY)

    return image


def draw_hardware_page():
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)

    header(draw, "HARDWARE", 3)

    model = get_model()
    kernel = get_kernel()
    usb_count = get_usb_count()
    spi = spi_status()

    draw.text((12, 52), "MODELO", font=FONT_LABEL, fill=CYAN)
    draw.text((12, 73), model, font=FONT_NORMAL, fill=WHITE)

    draw.line((12, 101, 228, 101), fill=CARD_BORDER)

    draw.text((12, 111), "KERNEL", font=FONT_LABEL, fill=PURPLE)
    draw.text((12, 132), kernel, font=FONT_NORMAL, fill=WHITE)

    card(draw, (8, 166, 112, 226))
    draw.text((18, 174), "USB", font=FONT_LABEL, fill=BLUE)
    draw.text((18, 195), usb_count, font=FONT_VALUE_SMALL, fill=WHITE)

    card(draw, (128, 166, 232, 226))
    draw.text((138, 174), "SPI", font=FONT_LABEL, fill=GREEN)

    spi_color = GREEN if spi == "ON" else RED
    draw.text((138, 195), spi, font=FONT_VALUE_SMALL, fill=spi_color)

    return image


GPIO_CHIP = "/dev/gpiochip0"
BUTTON_PREV = 23
BUTTON_NEXT = 24


gpio_config = {
    BUTTON_PREV: gpiod.LineSettings(
        direction=Direction.INPUT,
        bias=Bias.PULL_UP,
    ),
    BUTTON_NEXT: gpiod.LineSettings(
        direction=Direction.INPUT,
        bias=Bias.PULL_UP,
    ),
}


gpio_request = gpiod.request_lines(
    GPIO_CHIP,
    consumer="bench-display",
    config=gpio_config,
)


page = 0
last_state = {
    pin: gpio_request.get_value(pin)
    for pin in gpio_config
}
last_render = 0
last_button_time = 0


while True:
    now = time.time()

    states = {
        pin: gpio_request.get_value(pin)
        for pin in gpio_config
    }

    changed = False

    if now - last_button_time > 0.25:
        if (
            last_state[BUTTON_PREV] == Value.ACTIVE
            and states[BUTTON_PREV] == Value.INACTIVE
        ):
            page = (page - 1) % 3
            changed = True
            last_button_time = now

        if (
            last_state[BUTTON_NEXT] == Value.ACTIVE
            and states[BUTTON_NEXT] == Value.INACTIVE
        ):
            page = (page + 1) % 3
            changed = True
            last_button_time = now

    last_state = states

    if changed:
        last_render = 0

    if now - last_render >= 1:
        if page == 0:
            image = draw_status_page()
        elif page == 1:
            image = draw_network_page()
        else:
            image = draw_hardware_page()

        display.display(image)
        last_render = now

    time.sleep(0.03)
