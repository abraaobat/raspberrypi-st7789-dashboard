"""Lazy physical drivers. The web panel never opens SPI, I2C or GPIO."""

from __future__ import annotations

from .display_profiles import runtime_profile


def create_display(config):
    target = runtime_profile(config)
    try:
        if target.driver == "st7789":
            import st7789

            device = st7789.ST7789(height=240, width=240, rotation=90, port=0, cs=0,
                                   dc=25, rst=27, spi_speed_hz=40_000_000)
            device.begin()
            return device
        if target.driver == "ssd1306":
            from luma.core.interface.serial import i2c
            from luma.oled.device import ssd1306

            serial = i2c(port=1, address=0x3C)
            try:
                return ssd1306(serial, width=128, height=64, rotate=0)
            except Exception:
                serial.cleanup()
                raise
        if target.driver == "ili9341":
            from luma.core.interface.serial import spi
            from luma.lcd.device import ili9341

            serial = spi(port=0, device=0, gpio_DC=25, gpio_RST=27, bus_speed_hz=16_000_000)
            try:
                # Luma ILI9341's native canvas is already landscape 320×240.
                return ili9341(serial, width=320, height=240, rotate=0)
            except Exception:
                serial.cleanup()
                raise
    except ImportError as exc:
        raise RuntimeError("dependência do driver ausente; consulte docs/DISPLAY_COMPATIBILITY.md") from exc
    raise RuntimeError("driver de display não implementado")
