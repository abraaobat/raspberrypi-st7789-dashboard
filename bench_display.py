#!/usr/bin/env python3
"""Physical ST7789 runtime.

Hardware-only imports intentionally live inside this entry point so rendering,
configuration and the web preview remain testable on computers without GPIO.
"""

from __future__ import annotations

import signal
import time

from dashboard.config import ConfigStore, enabled_pages
from dashboard.display_profiles import profile
from dashboard.providers import DataHub
from dashboard.rendering import render_page
from dashboard.runtime import RuntimeStore

GPIO_CHIP = "/dev/gpiochip0"
BUTTON_PREV = 23
BUTTON_NEXT = 24


def create_display(config):
    import st7789

    target = profile(config.get("displayProfile"))
    if target.driver != "st7789" or not target.available:
        raise RuntimeError(f"driver de display indisponível: {target.driver}")
    display = st7789.ST7789(
        height=target.height,
        width=target.width,
        rotation=target.rotation,
        port=0,
        cs=0,
        dc=25,
        rst=27,
        spi_speed_hz=40_000_000,
    )
    display.begin()
    return display


def create_buttons():
    import gpiod
    from gpiod.line import Bias, Direction

    settings = {
        BUTTON_PREV: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP),
        BUTTON_NEXT: gpiod.LineSettings(direction=Direction.INPUT, bias=Bias.PULL_UP),
    }
    return gpiod.request_lines(GPIO_CHIP, consumer="bench-display", config=settings)


def pressed_transition(previous, current):
    from gpiod.line import Value

    return previous == Value.ACTIVE and current == Value.INACTIVE


def main():
    config_store = ConfigStore()
    initial_config = config_store.load(force=True)
    display = create_display(initial_config)
    buttons = create_buttons()
    runtime = RuntimeStore()
    data = DataHub()
    running = True

    def stop(_signum, _frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    last_button_state = {
        BUTTON_PREV: buttons.get_value(BUTTON_PREV),
        BUTTON_NEXT: buttons.get_value(BUTTON_NEXT),
    }
    current_page = None
    page_changed_at = 0.0
    last_button_at = 0.0
    last_render_at = 0.0
    last_control_update = None

    try:
        while running:
            now = time.monotonic()
            config = config_store.load()
            pages = enabled_pages(config)
            page_ids = [page["id"] for page in pages]
            if not page_ids:
                time.sleep(1)
                continue

            if current_page not in page_ids:
                current_page = page_ids[0]
                page_changed_at = now
                last_render_at = 0

            control = runtime.read_control()
            if control.get("updatedAt") != last_control_update:
                last_control_update = control.get("updatedAt")
                requested = control.get("requestedPage")
                if requested in page_ids and requested != current_page:
                    current_page = requested
                    page_changed_at = now
                    last_render_at = 0

            current_button_state = {
                BUTTON_PREV: buttons.get_value(BUTTON_PREV),
                BUTTON_NEXT: buttons.get_value(BUTTON_NEXT),
            }

            if now - last_button_at > 0.25:
                direction = 0
                if pressed_transition(last_button_state[BUTTON_PREV], current_button_state[BUTTON_PREV]):
                    direction = -1
                elif pressed_transition(last_button_state[BUTTON_NEXT], current_button_state[BUTTON_NEXT]):
                    direction = 1
                if direction:
                    current_page = page_ids[(page_ids.index(current_page) + direction) % len(page_ids)]
                    last_button_at = now
                    page_changed_at = now
                    last_render_at = 0

            last_button_state = current_button_state

            carousel = config["carousel"]
            resume_after = carousel["resumeAfterSeconds"]
            manual_pause_over = last_button_at == 0 or now - last_button_at >= resume_after
            if (
                carousel["enabled"]
                and len(page_ids) > 1
                and manual_pause_over
                and now - page_changed_at >= carousel["intervalSeconds"]
            ):
                current_page = page_ids[(page_ids.index(current_page) + 1) % len(page_ids)]
                page_changed_at = now
                last_render_at = 0

            page_config = next(page for page in pages if page["id"] == current_page)
            refresh_seconds = page_config["refreshSeconds"]
            if now - last_render_at >= refresh_seconds:
                try:
                    snapshot = data.get(config, current_page, refresh_seconds)
                    image = render_page(current_page, snapshot, config)
                    display.display(image)
                    runtime.update_display(current_page)
                    provider_key = current_page if current_page in {"weather", "sysops", "pihole", "homeassistant", "docker"} else "custom"
                    provider_state = snapshot.get(provider_key)
                except Exception as exc:  # keep service alive and report the fault
                    runtime.update_display(current_page, str(exc))
                    provider_state = None
                last_render_at = now - refresh_seconds + 1 if provider_state and provider_state.get("loading") else now

            time.sleep(0.03)
    finally:
        try:
            buttons.release()
        except Exception:
            pass


if __name__ == "__main__":
    main()
