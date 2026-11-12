# GlassPlayer para Ubuntu

Reproductor (GTK4 + GStreamer) con estética Apple Music "glass": degradado gris, portada desenfocada de fondo, paneles translúcidos con brillo superior y acento coral `#ff5d8f`.

## Instalar y ejecutar
```bash
cd desktop && ./install.sh
glassplayer
```
El instalador también deja GlassPlayer **fijado en la barra de tareas** (dock). Clic derecho sobre su icono: Reproducir/Pausa, Siguiente, Anterior y Salir. Si lo cierras mientras suena, la música sigue en segundo plano y se controla desde ese menú o desde la pantalla de bloqueo.

Sin instalar: instala las dependencias de `install.sh` con apt y ejecuta `python3 -m glassplayer` dentro de `desktop/`.

## Uso
- **Canciones**: tus MP3 (botón **+** de la barra superior). **Favoritos**: pulsa el corazón de cualquier fila.
- **Listas**: escribe un nombre en "Nueva lista…" (barra lateral). Menú **⋯** de cada fila: añadir a una lista, quitar, eliminar.
- **YouTube**: escribe en el buscador superior y pulsa Intro. Se reproduce en streaming, sin guardar audio, y la miniatura del vídeo se usa como portada. Con **⋯ → Añadir a la biblioteca** (o con el corazón) se guarda el enlace.
- **Portada**: haz clic en la portada de la barra inferior para elegir una imagen.

## YouTube
Usa `yt-dlp`. Si deja de funcionar: `yt-dlp -U`. Las versiones recientes pueden pedir un runtime de JavaScript (deno o nodejs; el instalador pone nodejs); consulta la documentación de yt-dlp si te lo indica. Úsalo con contenido que tengas derecho a reproducir (p. ej. tu propio canal).

## Pantalla de bloqueo
La canción se publica por MPRIS: GNOME muestra título, artista, portada y controles al bloquear y responde a las teclas multimedia. Esa pantalla la dibuja GNOME Shell, así que su aspecto lo decide el sistema.

Datos en `~/.local/share/glassplayer/`.
