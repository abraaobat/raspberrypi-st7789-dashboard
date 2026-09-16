"""Nonsecret, closed settings for the offline desk modules."""
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class DeskError(ValueError):
    pass


def clock_settings(payload):
    if not isinstance(payload, dict) or set(payload) - {"timezone", "showSeconds", "hour24"}:
        raise DeskError("ajustes do relógio inválidos")
    name = payload.get("timezone", "")
    if not isinstance(name, str) or len(name) > 80:
        raise DeskError("fuso horário inválido")
    name = name.strip()
    if name:
        if not re.fullmatch(r"[A-Za-z0-9_+/-]+", name) or ".." in name:
            raise DeskError("use um fuso IANA, como America/Boa_Vista")
        try:
            ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            raise DeskError("fuso não instalado; use o fuso do sistema ou instale tzdata") from None
    result = {"timezone": name}
    for option in ("showSeconds", "hour24"):
        value = payload.get(option, True)
        if not isinstance(value, bool):
            raise DeskError("opções do relógio devem ser verdadeiro ou falso")
        result[option] = value
    return result


def pomodoro_settings(payload):
    if not isinstance(payload, dict) or set(payload) - {"minutes"}:
        raise DeskError("ajustes do Pomodoro inválidos")
    minutes = payload.get("minutes", 25)
    if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 120:
        raise DeskError("a duração deve ser um inteiro entre 1 e 120 minutos")
    return {"minutes": minutes}
