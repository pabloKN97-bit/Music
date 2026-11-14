#!/usr/bin/env bash
# Instala GlassPlayer en Ubuntu (usuario actual): dependencias, yt-dlp, convertidor MP3, icono, lanzador y barra de tareas.
set -e
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly gstreamer1.0-libav \
    python3-mutagen curl nodejs fonts-inter \
    ffmpeg python3-venv gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.local/share/glassplayer/app"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications" "$HOME/.local/share/icons/hicolor/scalable/apps"
rm -rf "$DEST/glassplayer"
cp -r "$HERE/glassplayer" "$DEST/"
cp "$HERE/../convertidor.py" "$DEST/convertidor.py"
find "$DEST" -name __pycache__ -type d -prune -exec rm -rf {} +

# yt-dlp: el paquete de apt suele estar desactualizado y YouTube cambia a menudo
curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o "$HOME/.local/bin/yt-dlp"
chmod +x "$HOME/.local/bin/yt-dlp"

# Convertidor MP3 (convertidor.py): entorno virtual propio del usuario con flask + yt-dlp, sin tocar el sistema.
# La app lo lanza en segundo plano al pulsar «Descargar»; no hace falta ejecutarlo a mano.
VENV="$HOME/.local/share/glassplayer/venv"
[ -x "$VENV/bin/python" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q --upgrade -r "$HERE/requirements.txt"

cp "$HERE/data/com.pablo.glassplayer.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/"
gtk-update-icon-cache -q -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true

cat > "$HOME/.local/bin/glassplayer" <<LAUNCH
#!/bin/sh
export PATH="\$HOME/.local/bin:\$PATH"
exec env PYTHONPATH="$DEST" python3 -m glassplayer "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/glassplayer"

# El nombre del .desktop = application_id; StartupWMClass agrupa la ventana con el icono fijado en la barra.
cat > "$HOME/.local/share/applications/com.pablo.glassplayer.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=GlassPlayer
Comment=Reproductor con estilo Apple Music glass
Exec=$HOME/.local/bin/glassplayer
Icon=com.pablo.glassplayer
Categories=AudioVideo;Audio;Player;
Terminal=false
StartupNotify=true
StartupWMClass=com.pablo.glassplayer
Actions=PlayPause;Next;Previous;Quit;

[Desktop Action PlayPause]
Name=Reproducir / Pausa
Exec=gapplication action com.pablo.glassplayer play-pause

[Desktop Action Next]
Name=Siguiente
Exec=gapplication action com.pablo.glassplayer next

[Desktop Action Previous]
Name=Anterior
Exec=gapplication action com.pablo.glassplayer prev

[Desktop Action Quit]
Name=Salir
Exec=gapplication action com.pablo.glassplayer quit
ENTRY
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true

# Fijar en la barra de tareas (dock de Ubuntu / GNOME)
if command -v gsettings >/dev/null 2>&1 && gsettings get org.gnome.shell favorite-apps >/dev/null 2>&1; then
python3 - <<'PY'
import ast, subprocess
cur = ast.literal_eval(subprocess.check_output(["gsettings", "get", "org.gnome.shell", "favorite-apps"], text=True).replace("@as ", ""))
app = "com.pablo.glassplayer.desktop"
if app not in cur:
    subprocess.run(["gsettings", "set", "org.gnome.shell", "favorite-apps", str(cur + [app])])
PY
fi
echo "Listo. GlassPlayer está fijado en la barra de tareas; también puedes ejecutar 'glassplayer'."
