#!/usr/bin/env bash
# Instala GlassPlayer en Ubuntu (usuario actual) y crea el acceso directo del menú.
set -e
sudo apt update
sudo apt install -y python3-gi gir1.2-gtk-4.0 gir1.2-gstreamer-1.0 gir1.2-gst-plugins-base-1.0 \
    gstreamer1.0-plugins-base gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly gstreamer1.0-libav python3-mutagen

DEST="$HOME/.local/share/glassplayer/app"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications"
rm -rf "$DEST/glassplayer"
cp -r "$(dirname "$0")/glassplayer" "$DEST/"

cat > "$HOME/.local/bin/glassplayer" <<LAUNCH
#!/bin/sh
exec env PYTHONPATH="$DEST" python3 -m glassplayer "\$@"
LAUNCH
chmod +x "$HOME/.local/bin/glassplayer"

# El nombre del .desktop debe coincidir con el application_id para que GNOME asocie la app al reproductor
cat > "$HOME/.local/share/applications/com.pablo.glassplayer.desktop" <<ENTRY
[Desktop Entry]
Type=Application
Name=GlassPlayer
Comment=Reproductor de MP3 con estilo glass
Exec=$HOME/.local/bin/glassplayer
Icon=multimedia-audio-player
Categories=AudioVideo;Audio;Player;
Terminal=false
ENTRY
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Listo. Ejecuta 'glassplayer' (o ábrelo desde el menú de aplicaciones)."
