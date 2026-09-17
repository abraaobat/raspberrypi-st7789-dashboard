"""Native 128×64 monochrome summaries, not a shrunken 240×240 screenshot."""

from __future__ import annotations

from PIL import Image, ImageDraw

from .catalog import catalog_by_id
from .rendering import fit_text, load_font, percent_label, temperature_label


def compact_lines(page_id, snapshot, config):
    unit = config["temperatureUnit"]
    values = snapshot.get(page_id) or {}
    if page_id == "status":
        temperature = snapshot.get("temperatureC")
        thresholds = config["thresholds"]
        label = "CRIT" if temperature is not None and temperature >= thresholds["temperatureCritical"] else "ALERTA" if temperature is not None and temperature >= thresholds["temperatureWarning"] else "TEMP"
        return [f"CPU {percent_label(snapshot.get('cpuPercent'))}  RAM {percent_label(snapshot.get('ramPercent'))}",
                f"{label} {temperature_label(temperature, unit)}", f"UP {snapshot.get('uptime') or '-'}"]
    if page_id == "network":
        network = snapshot.get("network") or {}
        return [snapshot.get("hostname") or "-", f"ETH {network.get('ethernetIp') or '-'}",
                f"WI-FI {network.get('wifiIp') or '-'}", f"TAIL {network.get('tailscaleIp') or '-'}"]
    if page_id == "hardware":
        return [snapshot.get("model") or "-", snapshot.get("kernel") or "-",
                f"USB {snapshot.get('usbCount', '-')}  SPI {'ON' if snapshot.get('spi') else 'OFF'}"]
    if page_id == "sysops":
        return [f"DISCO {percent_label(values.get('diskPercent'))}  PING {values.get('pingMs', '-')}ms",
                f"ALIMENT. {values.get('throttling') or '-'}",
                *[f"{s['name']}: {s['status']}" for s in (values.get("services") or [])[:2]]]
    if page_id == "weather":
        return [config["weather"]["locationName"] or "CLIMA", f"TEMP {temperature_label(values.get('temperatureC'), unit)}",
                f"MIN {temperature_label(values.get('minimumC'), unit)} MAX {temperature_label(values.get('maximumC'), unit)}",
                f"CHUVA {values.get('precipitationProbability', '-')}%"]
    if page_id == "pihole":
        return [f"BLOQUEIOS {values.get('blockedPercent', '-')}%", f"CONSULTAS {values.get('totalQueries', '-')}",
                f"BLOQ. {values.get('blockedQueries', '-')}", f"CLIENTES {values.get('activeClients', '-')}"]
    if page_id == "homeassistant":
        return [f"{e.get('label') or e.get('entityId')}: {e.get('state') if e.get('available') else 'SEM DADOS'} {e.get('unit') or ''}" for e in (values.get("entities") or [])[:4]]
    if page_id == "mqtt":
        return [f"{s['label']}: {'ERRO' if s.get('error') else s.get('value') if s.get('value') is not None else 'SEM DADOS'} {s.get('unit') or ''}"
                for s in (values.get("sensors") or [])[:4]]
    if page_id == "docker":
        return [f"{c['name']}: {c.get('health') or c['state']}" for c in (values.get("containers") or [])[:4]] or ["Nenhum contêiner"]
    if page_id.startswith("custom:"):
        definition = next(item for item in config["customPages"] if item["id"] == page_id)
        custom = snapshot.get("custom") or {}
        return [definition.get("valueLabel") or "VALOR", f"{custom.get('value') if custom.get('value') is not None else '-'} {definition.get('unit') or ''}",
                str(custom.get("secondary") or "")]
    return []


def render_compact(page_id, snapshot, config, page_number, page_count):
    image = Image.new("1", (128, 64), 0)
    draw = ImageDraw.Draw(image)
    title = catalog_by_id(config.get("customPages"))[page_id]["title"].upper()
    shown, font = fit_text(draw, title, 92, 9, 8, True)
    draw.text((1, -1), shown, font=font, fill=1)
    draw.text((99, 0), f"{page_number}/{page_count}", font=load_font(8), fill=1)
    draw.line((0, 11, 127, 11), fill=1)
    values = snapshot.get("custom" if page_id.startswith("custom:") else page_id) or {}
    unavailable = values.get("loading") or values.get("error") and not values.get("stale") or values.get("configured") is False
    if unavailable:
        lines = ["CONSULTANDO..." if values.get("loading") else "SEM DADOS", values.get("error") or "Configure no painel"]
    elif page_id in {"clock", "pomodoro"}:
        remaining = values.get("remainingSeconds")
        text = values.get("time") if page_id == "clock" else "--:--" if remaining is None else f"{int(remaining) // 60:02}:{int(remaining) % 60:02}"
        text = f"{text or '--:--'} {values.get('period') or ''}".strip()
        shown, font = fit_text(draw, text, 126, 22, 15, True)
        draw.text((1, 12), shown, font=font, fill=1)
        detail = values.get("date") if page_id == "clock" else values.get("status") or "SEM DADOS"
        shown, font = fit_text(draw, detail, 126, 9, 8)
        draw.text((1, 41), shown, font=font, fill=1)
        if page_id == "pomodoro":
            progress = max(0, min(1, values.get("progress") or 0))
            draw.rectangle((1, 55, 126, 61), outline=1)
            if progress:
                draw.rectangle((2, 56, max(2, int(125 * progress)), 60), fill=1)
        return image
    else:
        lines = compact_lines(page_id, snapshot, config)
    for index, line in enumerate(lines[:4]):
        shown, font = fit_text(draw, line, 126, 9, 8)
        draw.text((1, 13 + index * 10), shown, font=font, fill=1)
    footer = "CACHE / SEM CONFIRMAÇÃO" if values.get("stale") else "RETIDO: HORA DESCONHECIDA" if page_id == "mqtt" and any(s.get("retained") for s in values.get("sensors", [])) else ""
    if footer:
        shown, font = fit_text(draw, footer, 126, 7, 7)
        draw.text((1, 55), shown, font=font, fill=1)
    return image
