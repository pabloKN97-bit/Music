"""Requisitos: Python 3.9+, ffmpeg instalado en el sistema.
Instalar:   pip install flask yt-dlp
Ejecutar:   python convertidor.py   y abrir http://127.0.0.1:5000
GlassPlayer (escritorio) lo lanza solo en segundo plano, en un puerto libre que le pasa con la
variable de entorno CONVERTIDOR_PORT, y le envía los enlaces de las canciones a /convert.
"""
import os
import re
import shutil
import tempfile
from urllib.parse import quote, urlparse

from flask import Flask, jsonify, request, send_file, render_template_string
import yt_dlp

app = Flask(__name__)

HTML = """<!doctype html><meta charset="utf-8"><title>Convertidor MP3</title>
<body style="font-family:sans-serif;max-width:560px;margin:3em auto">
<h2>YouTube &rarr; MP3</h2>
<input id="u" placeholder="https://www.youtube.com/watch?v=..." style="width:100%;padding:8px">
<p><button id="b" style="padding:8px 16px">Convertir</button> <span id="m"></span></p>
<script>
document.getElementById("b").onclick = async () => {
  const m = document.getElementById("m"); m.textContent = "Convirtiendo...";
  const r = await fetch("/convert", {method: "POST", headers: {"Content-Type": "application/json"},
                                     body: JSON.stringify({url: document.getElementById("u").value})});
  if (!r.ok) { m.textContent = (await r.json()).error; return; }
  const a = document.createElement("a");
  a.href = URL.createObjectURL(await r.blob());
  a.download = decodeURIComponent(r.headers.get("X-Filename") || "audio.mp3");
  a.click(); m.textContent = "Listo";
};
</script></body>"""

ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be",
}

def url_valida(url: str) -> bool:
    try:
        p = urlparse(url)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and (p.hostname or "").lower() in ALLOWED_HOSTS


def nombre_seguro(titulo: str) -> str:
    limpio = re.sub(r'[\\/:*?"<>|]+', "_", titulo).strip()
    return (limpio or "audio")[:120]


@app.get("/")
def index():
    return render_template_string(HTML)


@app.post("/convert")
def convert():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    calidad = str(data.get("quality", "192"))
    if calidad not in {"128", "192", "320"}:
        calidad = "192"

    if not url_valida(url):
        return jsonify(error="Introduce un enlace de YouTube."), 400
    if shutil.which("ffmpeg") is None:
        return jsonify(error="ffmpeg no está instalado en el servidor."), 500

    tmp = tempfile.mkdtemp(prefix="ytmp3_")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(tmp, "%(id)s.%(ext)s"),
        "noplaylist": True,
        # yt-dlp solo activa deno por defecto; también se admite node (lo instala install.sh)
        "js_runtimes": {"deno": {}, "node": {}},
        "quiet": True,
        "no_warnings": True,
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": calidad,
        }],
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        titulo = nombre_seguro(info.get("title", "audio"))
        mp3 = os.path.join(tmp, f"{info['id']}.mp3")
        if not os.path.exists(mp3):
            raise FileNotFoundError("No se generó el MP3.")
    except Exception as e:  # yt_dlp lanza varios tipos de error
        shutil.rmtree(tmp, ignore_errors=True)
        return jsonify(error=f"No se pudo procesar el vídeo: {str(e)[:200]}"), 400

    resp = send_file(mp3, mimetype="audio/mpeg", as_attachment=True,
                     download_name=f"{titulo}.mp3")
    resp.headers["X-Filename"] = quote(f"{titulo}.mp3")
    resp.call_on_close(lambda: shutil.rmtree(tmp, ignore_errors=True))
    return resp


if __name__ == "__main__":
    # Solo accesible desde tu propio equipo
    app.run(host="127.0.0.1", port=int(os.environ.get("CONVERTIDOR_PORT", "5000")), debug=False)
