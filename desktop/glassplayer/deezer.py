"""API pública de Deezer: búsqueda de canciones y álbumes, portadas y previews de 30 s.
No requiere claves y no devuelve anuncios. Las canciones completas no se pueden obtener por aquí."""
import json
import urllib.parse
import urllib.request

API = "https://api.deezer.com"


def api(path, **params):
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.load(r)


def download(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.read()
    except Exception:
        return None


def _best_cover(al):
    return al.get("cover_xl") or al.get("cover_big") or al.get("cover_medium")


def search_tracks(q):
    return [{"kind": "track", "id": d["id"], "title": d["title"], "artist": d["artist"]["name"],
             "album": d["album"]["title"], "thumb": d["album"]["cover_medium"],
             "cover": _best_cover(d["album"]), "preview": d.get("preview", "")}
            for d in api("/search", q=q, limit=20)["data"]]


def search_albums(q):
    return [{"kind": "album", "id": d["id"], "title": d["title"], "artist": d["artist"]["name"],
             "album": d["title"], "thumb": d["cover_medium"], "cover": _best_cover(d)}
            for d in api("/search/album", q=q, limit=20)["data"]]


def album_tracks(album_id):
    """Devuelve (título del álbum, url de portada, lista de pistas con preview)."""
    info = api(f"/album/{album_id}")
    tracks = [{"title": d["title"], "artist": d["artist"]["name"], "preview": d.get("preview", "")}
              for d in info.get("tracks", {}).get("data", []) if d.get("preview")]
    return info["title"], _best_cover(info), tracks
