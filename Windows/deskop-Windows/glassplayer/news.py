"""Novedades: tendencias de Deezer por género, emparejadas con YouTube y guardadas de forma temporal.

Flujo (parecido a «Novedades» de Spotify):
  1. Géneros: https://api.deezer.com/genre
  2. Tendencias de un género: https://api.deezer.com/chart/<id>/tracks (solo título, artista, portada y duración)
  3. Cada canción se busca en YouTube con yt-dlp (se elige el resultado cuya duración más se parece a la de Deezer)
  4. Todo se guarda en news.json como caché temporal: caduca solo y no se mezcla con la biblioteca.
     Una canción pasa a la biblioteca únicamente si la marcas como favorita o la añades a una lista.

La API pública de Deezer no necesita API key para estos datos (la autenticación OAuth solo sirve para datos
de una cuenta). Si más adelante quieres usar una cuenta, basta con añadir el token en _get().
"""
import json
import os
import threading
import time
import urllib.parse
import urllib.request

from . import paths, youtube

API = "https://api.deezer.com"
DATA = paths.DATA
CACHE = os.path.join(DATA, "news.json")

CHART_TTL = 6 * 3600          # pasado este tiempo se vuelve a pedir la lista a Deezer
GENRES_TTL = 7 * 24 * 3600
PURGE_AFTER = 3 * 24 * 3600   # lo que no se ha tocado en 3 días se borra de la caché
CHART_SIZE = 25
# Deezer mete mucho trap/reguetón latino en los charts de otros géneros (rap, pop…). Con esto, esas canciones solo
# salen en los géneros latinos; en el resto se descartan. Pon EXCLUDE_LATIN = False para desactivarlo.
EXCLUDE_LATIN = True
LATIN = ("197", "122", "67", "71")  # Latino, Reggaeton, Salsa, Cumbia
CHART_VERSION = 2                   # sube al cambiar cómo se construye una lista: invalida las cachés antiguas
DURATION_TOLERANCE = 15       # segundos de diferencia aceptados entre Deezer y YouTube

NAMES_ES = {
    "All": "Global", "Alternative": "Alternativa", "Electro": "Electrónica", "Classical": "Clásica",
    "Films/Games": "Cine y videojuegos", "Latin Music": "Música latina", "African Music": "Música africana",
    "Asian Music": "Música asiática", "Brazilian Music": "Música brasileña", "Indian Music": "Música india",
    "Kids": "Infantil", "Soul & Funk": "Soul y Funk", "Rap/Hip Hop": "Rap / Hip Hop", "Jazz": "Jazz",
}

_lock = threading.Lock()
_cache = None


# ------------------------------------------------------------------ caché temporal
def _load():
    global _cache
    if _cache is None:
        try:
            with open(CACHE, encoding="utf-8") as f:
                _cache = json.load(f)
        except Exception:
            _cache = {}
        _cache.setdefault("genres", {})
        _cache.setdefault("charts", {})
        now = time.time()
        _cache["charts"] = {k: v for k, v in _cache["charts"].items() if now - v.get("seen", 0) < PURGE_AFTER}
    return _cache


def save():
    """Guarda la caché en disco (escritura atómica; seguro llamarlo desde cualquier hilo)."""
    with _lock:
        os.makedirs(DATA, exist_ok=True)
        tmp = CACHE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_load(), f, ensure_ascii=False)
        os.replace(tmp, CACHE)


def clear():
    """Vacía todas las novedades temporales."""
    global _cache
    _cache = {"genres": {}, "charts": {}}
    save()


# ------------------------------------------------------------------ Deezer
def _get(path, **params):
    url = f"{API}/{path}" + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"User-Agent": "GlassPlayer/1.0"})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.loads(r.read().decode("utf-8"))
    if isinstance(data, dict) and "error" in data:
        raise RuntimeError(str(data["error"]))
    return data


def genres():
    """Lista de géneros de Deezer: [{id, name, picture}]. Usa la caché; si no hay red, devuelve la caducada."""
    c = _load()["genres"]
    if c.get("data") and time.time() - c.get("fetched", 0) < GENRES_TTL:
        return c["data"]
    try:
        out = [{"id": str(g["id"]), "name": NAMES_ES.get(g["name"], g["name"]),
                "picture": g.get("picture_medium") or g.get("picture") or ""}
               for g in _get("genre").get("data", [])]
        out.sort(key=lambda g: (g["id"] != "0", g["name"].lower()))  # «Global» primero
        _load()["genres"] = {"fetched": time.time(), "data": out}
        save()
        return out
    except Exception:
        if c.get("data"):
            return c["data"]
        raise


def _from_deezer(d):
    al = d.get("album") or {}
    return {"uri": None, "title": d.get("title_short") or d.get("title") or "Sin título",
            "artist": (d.get("artist") or {}).get("name") or "Artista desconocido",
            "album": al.get("title") or "", "duration": d.get("duration") or 0, "cover": None,
            "thumb": al.get("cover_medium") or "", "cover_url": al.get("cover_big") or al.get("cover_xl") or "",
            "dz_id": d.get("id")}


def chart(gid, limit=CHART_SIZE):
    """Tendencias de un género. Conserva las canciones ya emparejadas con YouTube de la consulta anterior."""
    gid = str(gid)
    charts = _load()["charts"]
    old = charts.get(gid)
    now = time.time()
    if old and old.get("v") == CHART_VERSION and now - old.get("fetched", 0) < CHART_TTL:
        old["seen"] = now
        return old["tracks"]
    exclude = EXCLUDE_LATIN and gid not in LATIN and gid != "0"
    try:
        raw = _get(f"chart/{gid}/tracks", limit=limit * 2 if exclude else limit).get("data", [])
    except Exception:
        if old:  # sin conexión: mejor la lista caducada que nada
            return old["tracks"]
        raise
    if exclude:
        banned = set()
        for lg in LATIN:
            try:
                banned |= {t["dz_id"] for t in chart(lg)}
            except Exception:
                pass
        raw = [d for d in raw if d.get("id") not in banned]
    raw = raw[:limit]
    known = {t["dz_id"]: t for t in (old or {}).get("tracks", [])}
    tracks = [known.get(d.get("id")) or _from_deezer(d) for d in raw]
    charts[gid] = {"v": CHART_VERSION, "fetched": now, "seen": now, "tracks": tracks}
    save()
    return tracks


# ------------------------------------------------------------------ YouTube
def pick_match(results, duration):
    """Elige el resultado de YouTube cuya duración se parece más a la de Deezer (o el primero si no hay dato)."""
    if not results:
        return None
    if duration:
        close = [r for r in results if r.get("duration") and abs(r["duration"] - duration) <= DURATION_TOLERANCE]
        if close:
            return min(close, key=lambda r: abs(r["duration"] - duration))
    return results[0]


def resolve(t, wait=None):
    """Busca la canción en YouTube y rellena t['uri']. Devuelve True si la encontró.
    wait: función opcional que espera mientras la reproducción esté cargando (no compite por la conexión)."""
    if t.get("uri"):
        return True
    if wait:
        wait()
    try:
        hit = pick_match(youtube.search(f"{t['artist']} {t['title']}", n=3, low_priority=True), t.get("duration"))
    except Exception:
        return False
    if not hit:
        return False
    t["uri"] = hit["uri"]
    return True
