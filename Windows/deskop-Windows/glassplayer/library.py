"""Biblioteca: etiquetas MP3, portadas, listas de canciones y favoritos (en %APPDATA%\\GlassPlayer)."""
import json
import os
import time

import mutagen
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TIT2, TPE1
from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QImage

from . import paths

DATA = paths.DATA
COVERS = paths.COVERS
LIB = os.path.join(DATA, "library.json")
DOWNLOADS = paths.MUSIC

# Lista que existe siempre: aquí van los MP3 que genera el botón de descarga.
DOWNLOADS_PLAYLIST = "DescargadasSinConexion"
DOWNLOADS_LABEL = "Descargadas sin conexión"
RECENT_MAX = 50


def fmt(sec):
    sec = int(sec or 0)
    return f"{sec // 60}:{sec % 60:02d}"


def uri_of(path):
    return QUrl.fromLocalFile(path).toString()


def path_of(uri):
    return QUrl(uri).toLocalFile()


def save_cover(data: bytes):
    """Recorta la imagen en cuadrado (máx. 800 px), la guarda como JPEG y devuelve la ruta."""
    try:
        img = QImage.fromData(data)
        if img.isNull():
            return None
        s = min(img.width(), img.height())
        img = img.copy((img.width() - s) // 2, (img.height() - s) // 2, s, s)
        if s > 800:
            img = img.scaled(800, 800, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        os.makedirs(COVERS, exist_ok=True)
        path = os.path.join(COVERS, f"c{time.time_ns()}.jpg")
        return path if img.save(path, "JPG", 90) else None
    except Exception:
        return None


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


def read_track(path):
    t = {"uri": uri_of(path), "title": os.path.splitext(os.path.basename(path))[0],
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
    """{"tracks": [...], "playlists": {nombre: [uri]}, "favorites": [uri], "downloads": {enlace YouTube: uri MP3},
    "recent": [pista, ...], "news_genres": [id]}"""
    try:
        with open(LIB, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("tracks", [])
    data.setdefault("playlists", {})
    data.setdefault("favorites", [])
    data.setdefault("downloads", {})
    data.setdefault("recent", [])
    data.setdefault("news_genres", [])
    data["playlists"].setdefault(DOWNLOADS_PLAYLIST, [])
    return data


def save(lib):
    tmp = LIB + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False)
    os.replace(tmp, LIB)


def push_recent(lib, track):
    """Pone la pista la primera de «Recientes» (sin duplicados, máximo RECENT_MAX)."""
    rec = lib["recent"]
    rec[:] = [t for t in rec if t["uri"] != track["uri"]]
    rec.insert(0, dict(track))
    del rec[RECENT_MAX:]


def drop_cover(path, tracks):
    """Borra el fichero de portada solo si ya no lo usa ninguna pista."""
    if path and path.startswith(COVERS) and not any(t.get("cover") == path for t in tracks):
        try:
            os.remove(path)
        except OSError:
            pass
