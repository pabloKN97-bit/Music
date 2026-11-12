"""Requisitos: Python 3.9+, ffmpeg instalado en el sistema.
Instalar:   pip install -r requirements.txt
Ejecutar:   python app.py   y abrir http://127.0.0.1:5000
"""
import os
import re
import shutil
import tempfile
from urllib.parse import quote, urlparse

from flask import Flask, jsonify, request, send_file, render_template_string
import yt_dlp

app = Flask(__name__)

ALLOWED_HOSTS = {
    "youtube.com", "www.youtube.com", "m.youtube.com",
    "music.youtube.com", "youtu.be",
}

HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>YouTube a MP3</title>
<style>
  :root { color-scheme: light dark; }
  body { font-family: system-ui, sans-serif; max-width: 560px; margin: 8vh auto; padding: 0 1rem; }
  h1 { font-size: 1.5rem; }
  form { display: flex; gap: .5rem; flex-wrap: wrap; }
  input[type=url] { flex: 1 1 280px; padding: .7rem; font-size: 1rem; border-radius: 8px; border: 1px solid #888; }
  select, button { padding: .7rem 1rem; font-size: 1rem; border-radius: 8px; border: 1px solid #888; }
  button { cursor: pointer; background: #c4302b; color: #fff; border-color: #c4302b; }
  button:disabled { opacity: .6; cursor: wait; }
  #msg { margin-top: 1rem; min-height: 1.5rem; }
  .err { color: #d33; }
  .ok { color: #2a8a3a; }
  small { opacity: .7; display: block; margin-top: 2rem; }
</style>
</head>
<body>
  <h1>YouTube a MP3</h1>
  <form id="f">
    <input type="url" id="url" placeholder="https://www.youtube.com/watch?v=..." required>
    <select id="q" title="Calidad">
      <option value="128">128 kbps</option>
      <option value="192" selected>192 kbps</option>
      <option value="320">320 kbps</option>
    </select>
    <button id="btn" type="submit">Convertir</button>
  </form>
  <div id="msg"></div>
  <small>Úsalo solo con contenido tuyo o con permiso de su autor.</small>
<script>
const f = document.getElementById('f'), btn = document.getElementById('btn'), msg = document.getElementById('msg');
f.addEventListener('submit', async (e) => {
  e.preventDefault();
  btn.disabled = true; msg.className = ''; msg.textContent = 'Descargando y convirtiendo… puede tardar un poco.';
  try {
    const r = await fetch('/convert', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({url: document.getElementById('url').value.trim(), quality: document.getElementById('q').value})
    });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      throw new Error(j.error || 'Error desconocido');
    }
    const name = decodeURIComponent(r.headers.get('X-Filename') || 'audio.mp3');
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
    msg.className = 'ok'; msg.textContent = '¡Listo! Descargado: ' + name;
  } catch (err) {
    msg.className = 'err'; msg.textContent = err.message;
  } finally { btn.disabled = false; }
});
</script>
</body>
</html>"""


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
    app.run(host="127.0.0.1", port=5000, debug=False)
