"""YouTube como fuente de canciones, mediante yt-dlp.
Solo se busca y se reproduce en streaming: no se guardan archivos de audio.
Úsalo con contenido que tengas derecho a reproducir (por ejemplo, tu propio canal)."""
import json
import shutil
import subprocess
import urllib.request

WATCH = "https://www.youtube.com/watch?v="


def available():
    return shutil.which("yt-dlp") is not None


def is_yt(uri):
    return uri.startswith(WATCH)


def download(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()
    except Exception:
        return None


def search(q, n=15):
    """Busca vídeos; devuelve pistas con el mismo formato que la biblioteca."""
    out = subprocess.run(["yt-dlp", "--flat-playlist", "--dump-json", "--no-warnings", f"ytsearch{n}:{q}"],
                         capture_output=True, text=True, timeout=45, check=True)
    res = []
    for line in out.stdout.splitlines():
        d = json.loads(line)
        if not d.get("id"):
            continue
        res.append({"uri": WATCH + d["id"], "title": d.get("title") or "Sin título",
                    "artist": d.get("channel") or d.get("uploader") or "YouTube", "album": "YouTube",
                    "duration": d.get("duration") or 0, "cover": None,
                    "thumb": f"https://i.ytimg.com/vi/{d['id']}/mqdefault.jpg"})
    return res


def stream_url(uri):
    """URL directa del mejor audio (caduca en horas; se resuelve cada vez que se reproduce)."""
    out = subprocess.run(["yt-dlp", "-f", "bestaudio/best", "-g", "--no-playlist", "--no-warnings", uri],
                         capture_output=True, text=True, timeout=45, check=True)
    return out.stdout.strip().splitlines()[0]


def thumbnail(uri):
    """Miniatura del vídeo en la mayor resolución disponible (bytes) o None."""
    vid = uri[len(WATCH):]
    for name in ("maxresdefault", "hqdefault"):
        data = download(f"https://i.ytimg.com/vi/{vid}/{name}.jpg")
        if data:
            return data
    return None
