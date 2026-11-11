# GlassPlayer para Ubuntu

Versión de escritorio (GTK4 + GStreamer) con la misma estética Apple Music "glass": portada desenfocada de fondo, tarjetas translúcidas con borde brillante.

## Instalar
```bash
cd desktop && ./install.sh
glassplayer
```
Sin instalar: `sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gst-plugins-base-1.0 gstreamer1.0-plugins-good gstreamer1.0-plugins-ugly gstreamer1.0-libav python3-mutagen` y luego `python3 -m glassplayer` dentro de `desktop/`.

## Pantalla de bloqueo
La app publica la canción por MPRIS (D-Bus). GNOME muestra título, artista, portada y controles en la pantalla de bloqueo y en el menú del sistema, y responde a las teclas multimedia. La pantalla de bloqueo la dibuja GNOME Shell: ninguna aplicación puede pintar su propia interfaz encima, así que el aspecto lo decide GNOME. El estilo glass completo solo es posible dentro de la ventana de la app.

## Deezer
API pública, sin claves ni anuncios. Permite buscar canciones y álbumes, usar portadas en alta resolución y añadir previews de 30 s (un álbum entero añade las previews de todas sus pistas). La API no ofrece canciones completas.
Las previews no se guardan entre sesiones (sus URLs caducan); las portadas descargadas sí.

Datos en `~/.local/share/glassplayer/`.
