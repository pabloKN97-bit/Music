"""Biblioteca: etiquetas MP3, portadas, listas de canciones y favoritos en ~/.local/share/glassplayer."""
import json
import os
import time

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib
import mutagen
from mutagen.id3 import ID3

DATA = os.path.join(GLib.get_user_data_dir(), "glassplayer")
COVERS = os.path.join(DATA, "covers")
LIB = os.path.join(DATA, "library.json")
os.makedirs(COVERS, exist_ok=True)


def fmt(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def save_cover(data: bytes):
    """Recorta la imagen en cuadrado (máx. 800 px), la guarda como JPEG y devuelve la ruta."""
    try:
        ld = GdkPixbuf.PixbufLoader()
        ld.write(data)
        ld.close()
        pb = ld.get_pixbuf()
        s = min(pb.get_width(), pb.get_height())
        pb = pb.new_subpixbuf((pb.get_width() - s) // 2, (pb.get_height() - s) // 2, s, s)
        if s > 800:
            pb = pb.scale_simple(800, 800, GdkPixbuf.InterpType.BILINEAR)
        path = os.path.join(COVERS, f"c{time.time_ns()}.jpg")
        pb.savev(path, "jpeg", ["quality"], ["90"])
        return path
    except Exception:
        return None


def blur(pb):
    """Efecto cristal barato: reducir mucho y reescalar con filtro."""
    small = pb.scale_simple(16, 16, GdkPixbuf.InterpType.HYPER)
    return small.scale_simple(256, 256, GdkPixbuf.InterpType.BILINEAR)


def read_track(path):
    t = {"uri": Gio.File.new_for_path(path).get_uri(),
         "title": os.path.splitext(os.path.basename(path))[0],
         "artist": "Artista desconocido", "album": "", "duration": 0, "cover": None}
    try:
        f = mutagen.File(path, easy=True)
        if f is not None:
            t["title"] = (f.get("title") or [t["title"]])[0]
            t["artist"] = (f.get("artist") or [t["artist"]])[0]
            t["album"] = (f.get("album") or [""])[0]
            t["duration"] = f.info.length
        pics = ID3(path).getall("APIC")
        if pics:
            t["cover"] = save_cover(pics[0].data)
    except Exception:
        pass
    return t


def load():
    """Devuelve {"tracks": [...], "playlists": {nombre: [uri]}, "favorites": [uri]}."""
    try:
        with open(LIB, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if isinstance(data, list):  # formato antiguo: solo la lista de pistas
        data = {"tracks": data}
    data.setdefault("tracks", [])
    data.setdefault("playlists", {})
    data.setdefault("favorites", [])
    return data


def save(lib):
    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False)


def drop_cover(path, tracks):
    """Borra el fichero de portada solo si ya no lo usa ninguna pista."""
    if path and path.startswith(COVERS) and not any(t.get("cover") == path for t in tracks):
        try:
            os.remove(path)
        except OSError:
            pass
