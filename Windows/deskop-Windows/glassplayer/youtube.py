"""YouTube como fuente de canciones, mediante yt-dlp (búsqueda y obtención del audio).
Úsalo con contenido que tengas derecho a reproducir."""
import json
import urllib.request

from . import tools

WATCH = "https://www.youtube.com/watch?v="


def available():
    return tools.which("yt-dlp") is not None


def is_yt(uri):
    return uri.startswith(WATCH)


def download(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "GlassPlayer/1.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read()
    except Exception:
        return None


def search(q, n=15, low_priority=False):
    """Busca vídeos; devuelve pistas con el mismo formato que la biblioteca."""
    out = tools.run([tools.which("yt-dlp"), "--flat-playlist", "--dump-json", "--no-warnings", f"ytsearch{n}:{q}"],
                    low=low_priority, capture_output=True, text=True, timeout=60, check=True)
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
    """URL directa del mejor audio (plan B si falla la descarga completa)."""
    out = tools.run([tools.which("yt-dlp"), "-f", "bestaudio/best", "-g", "--no-playlist", "--no-warnings", uri],
                    capture_output=True, text=True, timeout=60, check=True)
    return out.stdout.strip().splitlines()[0]


def thumbnail(uri):
    """Miniatura del vídeo en la mayor resolución disponible (bytes) o None."""
    vid = uri[len(WATCH):]
    for name in ("maxresdefault", "hqdefault"):
        data = download(f"https://i.ytimg.com/vi/{vid}/{name}.jpg")
        if data:
            return data
    return None
