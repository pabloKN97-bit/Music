"""Pruebas de la lógica sin interfaz: Deezer + filtro latino + caché temporal y descarga de audio (yt-dlp simulado).
Ejecutar:  python tests/test_logic.py"""
import os
import stat
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["GLASSPLAYER_DATA"] = tempfile.mkdtemp()
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from glassplayer import audiocache, news, youtube  # noqa: E402

# ---- news: géneros, tendencias, emparejado con YouTube, caché y filtro latino
calls = []


def tr(i):
    return {"id": i, "title": f"T{i}", "duration": 200, "artist": {"name": "A"},
            "album": {"title": "", "cover_big": "", "cover_xl": ""}}


def fake(path, **p):
    calls.append((path, p.get("limit")))
    if path == "genre":
        return {"data": [{"id": 132, "name": "Pop", "picture_medium": "p"}, {"id": 0, "name": "All", "picture_medium": "a"},
                         {"id": 116, "name": "Rap/Hip Hop", "picture_medium": "r"}]}
    return {"data": {"chart/116/tracks": [tr(i) for i in range(1, 11)], "chart/0/tracks": [tr(i) for i in range(1, 11)],
                     "chart/197/tracks": [tr(1), tr(2)], "chart/122/tracks": [tr(5)],
                     "chart/67/tracks": [], "chart/71/tracks": []}[path]}


news._get = fake
g = news.genres()
assert [x["name"] for x in g] == ["Global", "Pop", "Rap / Hip Hop"], g
r = [t["dz_id"] for t in news.chart("116", limit=5)]
assert r == [3, 4, 6, 7, 8], r                                  # sin las que están en Latino/Reggaeton
assert [t["dz_id"] for t in news.chart("0", limit=5)] == [1, 2, 3, 4, 5]
assert [t["dz_id"] for t in news.chart("197")] == [1, 2]
n = len(calls)
assert [t["dz_id"] for t in news.chart("116", limit=5)] == r and len(calls) == n   # caché

youtube.search = lambda q, n=15, low_priority=False: [{"uri": youtube.WATCH + "bad", "duration": 400},
                                                      {"uri": youtube.WATCH + "ok", "duration": 205}]
t = news.chart("116", limit=5)[0]
assert news.resolve(t) and t["uri"].endswith("ok")               # elige la de duración parecida
assert news.pick_match([], 100) is None

# ---- audiocache con un yt-dlp falso (script) para comprobar progreso, caché, cancelación y errores
tools = tempfile.mkdtemp()
fake_exe = os.path.join(tools, "yt-dlp")
open(fake_exe, "w").write("""#!/bin/bash
while [ $# -gt 0 ]; do case "$1" in -o) OUT="$2"; shift;; *) URL="$1";; esac; shift; done
ID="${URL##*v=}"; F="${OUT//%(id)s/$ID}"; F="${F//%(ext)s/webm}"
[ "$ID" = "fail" ] && { echo "ERROR: boom"; exit 1; }
for p in 10.0 55.5 100; do echo "[download]  $p% of 3.00MiB"; sleep 0.05; done
head -c 1000 /dev/zero > "$F"
""")
os.chmod(fake_exe, os.stat(fake_exe).st_mode | stat.S_IEXEC)
os.environ["GLASSPLAYER_TOOLS"] = tools
import importlib  # noqa: E402
importlib.reload(youtube)
assert youtube.available()
W, pcts = youtube.WATCH, []
p = audiocache.fetch(W + "abc", on_progress=pcts.append)
assert p.endswith("abc.webm") and pcts == [10.0, 55.5, 100.0]
pcts.clear()
assert audiocache.fetch(W + "abc", on_progress=pcts.append) == p and pcts == []
for bad, exc in ((("zzz",), audiocache.Cancelled), (("fail",), RuntimeError)):
    try:
        audiocache.fetch(W + bad[0], cancel=(lambda: True) if exc is audiocache.Cancelled else None)
        raise SystemExit("debía fallar")
    except exc:
        pass
for i in range(5):
    q = os.path.join(audiocache.DIR, f"f{i}.webm")
    open(q, "w").write("x")
    os.utime(q, (i, i))
audiocache.trim(keep=2)
assert len(os.listdir(audiocache.DIR)) == 2
print("PRUEBAS DE LÓGICA OK")
