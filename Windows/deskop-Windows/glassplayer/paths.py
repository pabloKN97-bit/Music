"""Rutas de la aplicación. En Windows los datos van a %APPDATA%\\GlassPlayer; las descargas a Música\\GlassPlayer."""
import os
import sys

APP = "GlassPlayer"


def _default_data():
    if os.name == "nt":
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP)
    return os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), "glassplayer-qt")


DATA = os.environ.get("GLASSPLAYER_DATA") or _default_data()  # GLASSPLAYER_DATA: para pruebas
COVERS = os.path.join(DATA, "covers")
AUDIO = os.path.join(DATA, "audio")
MUSIC = os.path.join(os.path.expanduser("~"), "Music", APP)  # MP3 descargados

for _d in (DATA, COVERS):
    os.makedirs(_d, exist_ok=True)


def resource(*parts):
    """Ruta de un recurso: dentro del paquete PyInstaller o, en desarrollo, junto al proyecto."""
    base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)
