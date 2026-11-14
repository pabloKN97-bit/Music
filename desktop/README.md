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

## Personalizar estilo
Botón **paleta** de la barra superior. Los cambios se ven al instante y se guardan en `settings.json`:
- **Paletas** predefinidas y 4 colores a medida (acento, fondo arriba, fondo abajo, texto).
- **Fondo**: elige una imagen de tu equipo (se copia y reduce a ≤1920 px); «Quitar imagen» vuelve a la portada desenfocada.
- **Transparencia** (0–90 %): aclara el fondo y las capas para ver las ventanas que hay detrás. El texto no se vuelve transparente. Necesita un escritorio con composición (GNOME y KDE lo traen).
- **Restablecer** devuelve el estilo original.

## Modo móvil
Botón **teléfono** de la barra superior: la app pasa a una ventana con forma de móvil (portada, título, Anterior, Pausa/Reproducir y Siguiente). Se mueve arrastrando cualquier zona libre; el botón **Escritorio** (esquina superior derecha) vuelve al modo escritorio. La música no se interrumpe al cambiar de modo.

## Descargar canciones
Las canciones de YouTube tienen un botón **⬇** en su fila (y en la barra inferior si suena una); la cabecera tiene **Descargar** para toda la lista que estés viendo.
Todo ocurre en segundo plano y con tus permisos de usuario: la app toma el enlace de la canción, arranca `convertidor.py` (servidor local solo en `127.0.0.1`, en un puerto libre, dentro del entorno virtual `~/.local/share/glassplayer/venv`) y este genera el MP3 con yt-dlp + ffmpeg. El MP3 se guarda con título, artista y portada en **`~/Música/GlassPlayer/`** y se añade a la lista **DescargadasSinConexion** (se crea sola y no se puede borrar). Una canción ya descargada no se descarga dos veces.
- Si falla: `~/.local/share/glassplayer/venv/bin/pip install -U yt-dlp` y revisa `convertidor.log` en `~/.local/share/glassplayer/`.
- «Eliminar de la biblioteca» no borra el archivo MP3 del disco.

## Barra de tareas y barra superior
- **Icono fijado en el dock**: clic derecho → Reproducir/Pausa, Siguiente, Anterior, Salir.
- **Icono en la barra superior** (junto al reloj): muestra el **nombre de la canción** y su menú tiene **Anterior · Pausa/Reproducir · Siguiente**, Abrir y Salir; el clic central pausa/reanuda. Lo lanza la app sola (`tray.py`, proceso aparte con AppIndicator) y desaparece al cerrarla. En Ubuntu funciona de serie; en GNOME "puro" hace falta la extensión *AppIndicator and KStatusNotifierItem Support*. Para desactivarlo: `GLASSPLAYER_NO_TRAY=1 glassplayer`.
- El dock de GNOME no permite mostrar texto ni botones propios en el icono; por eso el título y los controles viven en la barra superior (y también en el menú del sistema y la pantalla de bloqueo, vía MPRIS).

## YouTube
Usa `yt-dlp`. Si deja de funcionar: `yt-dlp -U`. Las versiones recientes pueden pedir un runtime de JavaScript (deno o nodejs; el instalador pone nodejs); consulta la documentación de yt-dlp si te lo indica. Úsalo con contenido que tengas derecho a reproducir (p. ej. tu propio canal).

## Pantalla de bloqueo
La canción se publica por MPRIS: GNOME muestra título, artista, portada y controles al bloquear y responde a las teclas multimedia. Esa pantalla la dibuja GNOME Shell, así que su aspecto lo decide el sistema.

Datos en `~/.local/share/glassplayer/` (biblioteca, portadas, fondos, ajustes). Descargas en `~/Música/GlassPlayer/`.
