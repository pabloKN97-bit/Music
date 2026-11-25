"""Ajustes de estilo del usuario (paleta de colores) en %APPDATA%\\GlassPlayer\\settings.json."""
import json
import os
import re

from . import paths

FILE = os.path.join(paths.DATA, "settings.json")

DEFAULT_THEME = {
    "accent": "#ff5d8f",     # color de acento (corazón, canción activa, barras)
    "bg_top": "#4d4d4f",     # degradado de fondo, parte superior
    "bg_bottom": "#0e0e10",  # degradado de fondo, parte inferior
    "text": "#f6f8fb",       # color del texto
    "volume": 80,            # volumen 0..100
}
COLOR_KEYS = ("accent", "bg_top", "bg_bottom", "text")

PRESETS = [
    {"name": "Coral", "accent": "#ff5d8f", "bg_top": "#4d4d4f", "bg_bottom": "#0e0e10", "text": "#f6f8fb"},
    {"name": "Océano", "accent": "#4cc9f0", "bg_top": "#1d3557", "bg_bottom": "#0b1320", "text": "#f1faff"},
    {"name": "Bosque", "accent": "#52d681", "bg_top": "#2d4a3a", "bg_bottom": "#0b1410", "text": "#f2fbf5"},
    {"name": "Violeta", "accent": "#b388ff", "bg_top": "#3b2a5c", "bg_bottom": "#120c1f", "text": "#f7f2ff"},
    {"name": "Ámbar", "accent": "#ffb454", "bg_top": "#5a3d1e", "bg_bottom": "#160f08", "text": "#fff8ee"},
    {"name": "Rubí", "accent": "#ff5252", "bg_top": "#4a1c1c", "bg_bottom": "#140808", "text": "#fff3f3"},
]

_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def is_hex(value):
    return isinstance(value, str) and bool(_HEX.match(value))


def rgb_of(hex_color):
    """'#ff5d8f' -> '255,93,143' (para rgba(...) en QSS)."""
    h = hex_color.lstrip("#")
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def load():
    """Devuelve siempre un tema válido (valores erróneos o ausentes -> los de fábrica)."""
    try:
        with open(FILE, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        raw = {}
    if not isinstance(raw, dict):
        raw = {}
    theme = dict(DEFAULT_THEME)
    for k in COLOR_KEYS:
        if is_hex(raw.get(k)):
            theme[k] = raw[k].lower()
    try:
        theme["volume"] = max(0, min(100, int(raw.get("volume", theme["volume"]))))
    except (TypeError, ValueError):
        pass
    return theme


def save(theme):
    os.makedirs(paths.DATA, exist_ok=True)
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(theme, f, ensure_ascii=False, indent=1)
