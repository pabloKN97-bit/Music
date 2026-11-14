"""Biblioteca: etiquetas MP3, portadas, listas de canciones y favoritos en ~/.local/share/glassplayer."""
import json
import os
import time

import gi
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, Gio, GLib
import mutagen
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TIT2, TPE1

DATA = os.path.join(GLib.get_user_data_dir(), "glassplayer")
COVERS = os.path.join(DATA, "covers")
BACKGROUNDS = os.path.join(DATA, "backgrounds")
LIB = os.path.join(DATA, "library.json")
os.makedirs(COVERS, exist_ok=True)

# Lista que existe siempre: aquí van los MP3 que genera el botón de descarga.
DOWNLOADS_PLAYLIST = "DescargadasSinConexion"


def _downloads_dir():
    """<carpeta Música del usuario>/GlassPlayer (si no hay carpeta Música configurada, ~/Music)."""
    home = os.path.expanduser("~")
    music = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_MUSIC)
    if not music or os.path.abspath(music) == os.path.abspath(home):
        music = os.path.join(home, "Music")
    return os.path.join(music, "GlassPlayer")


DOWNLOADS = _downloads_dir()


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


def save_background(src_path):
    """Copia propia (máx. 1920 px, JPEG) de la imagen de fondo elegida; devuelve la ruta o None."""
    try:
        os.makedirs(BACKGROUNDS, exist_ok=True)
        pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(src_path, 1920, 1920, True)
        path = os.path.join(BACKGROUNDS, f"bg{time.time_ns()}.jpg")
        pb.savev(path, "jpeg", ["quality"], ["88"])
        return path
    except Exception:
        return None


def drop_background(path):
    if path and path.startswith(BACKGROUNDS):
        try:
            os.remove(path)
        except OSError:
            pass


def tag_file(path, title, artist, album="", cover=None):
    """Escribe título, artista, álbum y portada (JPEG, bytes) en las etiquetas ID3 del MP3."""
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    for frame, cls, text in (("TIT2", TIT2, title), ("TPE1", TPE1, artist), ("TALB", TALB, album)):
        tags.delall(frame)
        if text:
            tags.add(cls(encoding=3, text=text))
    if cover:
        tags.delall("APIC")
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
    tags.save(path, v2_version=3)


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
    """Devuelve {"tracks": [...], "playlists": {nombre: [uri]}, "favorites": [uri],
    "downloads": {enlace de YouTube: uri del MP3 descargado}}."""
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
    data.setdefault("downloads", {})
    data["playlists"].setdefault(DOWNLOADS_PLAYLIST, [])
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
