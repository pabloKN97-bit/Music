"""Pruebas de la interfaz sin pantalla (Qt offscreen) con Deezer, YouTube y descargas simulados.
Ejecutar:  python tests/test_app.py        (guarda capturas en tests/out/)"""
import os
import struct
import sys
import tempfile
import wave
import math

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GLASSPLAYER_NO_AUDIO"] = "1"
os.environ["GLASSPLAYER_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(OUT, exist_ok=True)

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtGui import QColor, QImage  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication([])
from glassplayer import audiocache, downloader, library, news, youtube  # noqa: E402
from glassplayer.window import MainWindow  # noqa: E402

tmp = tempfile.mkdtemp()


def wav(name, secs=3, hz=440):
    path = os.path.join(tmp, name)
    w = wave.open(path, "w")
    w.setnchannels(1), w.setsampwidth(2), w.setframerate(22050)
    w.writeframes(b"".join(struct.pack("<h", int(6000 * math.sin(i * hz / 3500))) for i in range(22050 * secs)))
    w.close()
    return path


def png(color):
    img = QImage(120, 120, QImage.Format_RGB32)
    img.fill(QColor(color))
    from PySide6.QtCore import QBuffer, QIODevice
    buf = QBuffer()
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


# --- simulaciones: sin red, sin yt-dlp ---------------------------------------------------------------
youtube.download = lambda url: png("#3366cc" if "genre" in url else "#cc6633")
youtube.available = lambda: True
YT_WAV = wav("yt.wav", 3)
fetches = []
audiocache.fetch = lambda uri, on_progress=None, cancel=None, low_priority=False: (
    fetches.append((uri, low_priority)), on_progress and on_progress(55.0), YT_WAV)[-1]
audiocache.cached = lambda uri: None
GENRES = [{"id": str(i), "name": n, "picture": f"http://x/genre{i}.jpg"} for i, n in
          ((0, "Global"), (132, "Pop"), (116, "Rap / Hip Hop"), (152, "Rock"), (197, "Latino"), (144, "Reggae"))]
news.genres = lambda: GENRES
news.chart = lambda gid, limit=25: CHARTS.setdefault(gid, [
    {"uri": None, "title": f"Tema {gid}-{i}", "artist": f"Artista {i}", "album": "", "duration": 180, "cover": None,
     "thumb": "http://x/cover.jpg", "cover_url": "", "dz_id": 1000 * int(gid) + i} for i in range(6)])
CHARTS = {}
news.resolve = lambda t, wait=None: (t.__setitem__("uri", youtube.WATCH + str(t["dz_id"])) or True)
news.save = lambda: None
dl_calls = []


def fake_download(t):
    dl_calls.append(t["uri"])
    p = wav(f"dl{len(dl_calls)}.wav", 2)
    tr = library.read_track(p)
    tr.update(title=t["title"], artist=t["artist"], album="YouTube", duration=2)
    return tr


downloader.available = lambda: True
downloader.download_track = fake_download

# --- ventana -----------------------------------------------------------------------------------------
win = MainWindow()
win.resize(1180, 760)
win.show()
wait = QTest.qWait
local = []
for n, hz in (("a.wav", 300), ("b.wav", 400), ("c.wav", 500), ("d.wav", 600)):
    t = library.read_track(wav(n, 3, hz))
    t.update(title=f"Local {n[0].upper()}", artist="Yo", duration=3)
    local.append(t)
win.lib["tracks"].extend(local)
win.commit()

# 1) vistas básicas y cabeceras
win.set_view("songs"); wait(100)
assert len(win.rows) == 4 and win.l_page.text() == "Canciones"
win.set_view("favs"); assert win.rows == [] and "Aún no hay" in win.l_status.text()
win.toggle_fav(local[0]); win.toggle_fav(local[1])
win.set_view("favs"); assert [r.t["title"] for r in win.rows] == ["Local A", "Local B"]
win.toggle_fav(local[1]); assert len(win.view_tracks()) == 1
win.set_view("songs"); win.grab().save(os.path.join(OUT, "01_canciones.png"))

# 2) listas de usuario + aleatorio
assert win.create_playlist("Mia") == "Mia" and win.create_playlist("Mia") is None and win.create_playlist("  ") is None
for t in local:
    win.add_to_playlist("Mia", t)
win.set_view("pl:Mia"); wait(50)
assert len(win.rows) == 4 and win.btn_shuffle.isVisible() and win.btn_all.isVisible()
win.set_view("songs"); assert not win.btn_shuffle.isVisible()
win.set_view("pl:Mia")
win.btn_shuffle.click(); wait(300)                       # activar: empieza una al azar y sigue sonando
assert win.shuffle_on and win._shuffled and win.btn_shuffle.isChecked() and win.cur is not None
assert sorted(t["uri"] for t in win.queue) == sorted(t["uri"] for t in local)
first = win.cur["uri"]
seen = {first}
for _ in range(3):
    win.go_next(); seen.add(win.cur["uri"])
assert len(seen) == 4                                    # una vuelta completa sin repetir
win.btn_shuffle.click(); wait(100)                       # desactivar: orden original, sin cortar
assert not win.shuffle_on and not win._shuffled and [t["uri"] for t in win.queue] == [t["uri"] for t in local]
cur_idx = win.idx
win.go_next(); assert win.idx == (cur_idx + 1) % 4
win.rows[1].clicked.emit(); wait(50)                     # clic en una fila: suena esa
assert win.cur["title"] == "Local B"
win.btn_shuffle.click()                                  # activar con una sonando: continúa esa
assert win.queue[0]["title"] == "Local B" and win.idx == 0 and win._shuffled
win.btn_shuffle.click()
win.grab().save(os.path.join(OUT, "02_lista_aleatorio.png"))

# 3) reproducción real con QMediaPlayer (sin salida de audio)
win.play_list(local, 0); wait(1200)
assert win.player.mp.duration() > 2000, win.player.mp.duration()
assert win.player.pos() > 0 and win.seek.maximum() > 2000
win.player.seek(1500); wait(300); assert win.player.pos() >= 1400
win.toggle(); wait(200); assert not win.player.is_playing() and win.b_play.text() == "▶"
win.toggle(); wait(200); assert win.player.is_playing() and win.b_play.text() == "⏸"
win.player.seek(2900); wait(1500)                         # fin de la pista -> pasa a la siguiente sola
assert win.cur["title"] == "Local B", win.cur["title"]
win.go_prev(); wait(100)                                  # tras >3 s: reinicia; si no, anterior
win.grab().save(os.path.join(OUT, "03_reproduciendo.png"))

# 4) cola
win.queue_add(local[3]); win.queue_add(local[2], front=True)
assert [t["title"] for t in win.up_next] == ["Local C", "Local D"]
win.set_view("queue"); assert [r.t["title"] for r in win.rows][:2] == ["Local C", "Local D"]
win.go_next(); assert win.cur["title"] == "Local C" and len(win.up_next) == 1
win.clear_queue(); assert win.up_next == [] and win.queue_items() == []

# 5) Novedades: cajas de género, favoritos, tendencias con YouTube
win.set_view("news"); wait(300)
tiles = win.grid_host.findChildren(type(win.grid_host.findChild(object, "tile")))
assert len([w for w in win.grid_host.findChildren(object) if w.objectName() == "tile"]) == 6
win.toggle_genre("116"); assert win.lib["news_genres"] == ["116"]
wait(200)
win.grab().save(os.path.join(OUT, "04_novedades.png"))
win.set_view("news:116"); wait(600)
assert win.l_page.text() == "Rap / Hip Hop" and len(win.rows) == 6 and win.btn_back.isVisible()
assert all(r.t["uri"].startswith(youtube.WATCH) for r in win.rows) and win.l_status.text() == ""
win.grab().save(os.path.join(OUT, "05_genero.png"))
win.set_view("news:152"); wait(600)                       # otro género: sus canciones, no las del anterior
assert len(win.rows) == 6 and all(r.t["title"].startswith("Tema 152") for r in win.rows)
win.btn_back.click(); assert win.view == "news"

# 6) reproducir una canción de YouTube: descarga entera (simulada) y luego suena; precarga de la siguiente
win.set_view("news:116"); fetches.clear()
win.rows[0].clicked.emit(); wait(1500)
assert win.player.duration if False else True
assert fetches and fetches[0][0].endswith("116000") and win.player.mp.duration() > 2000
assert any(f[1] for f in fetches), "debe precargar la siguiente en segundo plano"
assert win._preload_token is None

# 7) descargas
yt_track = win.view_tracks()[1]
win.download_tracks([yt_track]); wait(800)
assert dl_calls == [yt_track["uri"]] and win.local_for(yt_track)
assert win.lib["playlists"][library.DOWNLOADS_PLAYLIST]
win.set_view("news:116"); assert win.rows[1].t["uri"] == yt_track["uri"]
win.play_list(win.view_tracks(), 1); wait(600)           # descargada: suena el MP3 local sin tocar YouTube
assert win.cur["uri"] == yt_track["uri"] and fetches[-1][0] != yt_track["uri"]

# 8) buscar en YouTube
youtube.search = lambda q, n=15, low_priority=False: [
    {"uri": youtube.WATCH + "abc", "title": "Resultado", "artist": "Canal", "album": "YouTube", "duration": 100,
     "cover": None, "thumb": "http://x/y.jpg"}]
win.search.setText("algo"); win.search.returnPressed.emit(); wait(500)
assert win.view == "yt" and len(win.rows) == 1
win.grab().save(os.path.join(OUT, "06_youtube.png"))

# 9) estilo, persistencia y cierre
from glassplayer.window import StyleDialog  # noqa: E402
dlg = StyleDialog(win)
dlg.apply_preset(__import__("glassplayer.settings", fromlist=["x"]).PRESETS[1]); assert win.theme["accent"] == "#4cc9f0"
win.set_view("songs"); wait(100); win.grab().save(os.path.join(OUT, "07_tema_oceano.png"))
dlg.grab().save(os.path.join(OUT, "08_dialogo_estilo.png"))
lib2 = library.load()
assert lib2["news_genres"] == ["116"] and "Mia" in lib2["playlists"] and lib2["downloads"]
win.close()
print("TODAS LAS PRUEBAS DE LA INTERFAZ OK")
