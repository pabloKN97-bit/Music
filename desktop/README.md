# GlassPlayer para Ubuntu

Reproductor (GTK4 + GStreamer) con estética Apple Music "glass": degradado gris, portada desenfocada de fondo, paneles translúcidos con brillo superior y acento coral `#ff5d8f`.

## Instalar y ejecutar
```bash
cd desktop && ./install.sh
glassplayer
```
El instalador también deja GlassPlayer **fijado en la barra de tareas** (dock). Clic derecho sobre su icono: Reproducir/Pausa, Siguiente, Anterior y Salir. Si cierras la ventana (la X) mientras suena, la música sigue en segundo plano y se controla desde la barra superior, el panel del sistema o la pantalla de bloqueo (la primera vez avisa con una notificación). Se vuelve a abrir desde el dock o desde el icono de la barra superior. **Para salir del todo** (y detener la música): botón **Salir** de la barra superior de la app, **Ctrl+Q**, o «Salir» en el icono. Con la música en pausa, la X sí cierra la app.

Sin instalar: instala las dependencias de `install.sh` con apt y ejecuta `python3 -m glassplayer` dentro de `desktop/`.

## Uso
- **Canciones**: tus MP3 (botón **+** de la barra superior). **Favoritos**: pulsa el corazón de cualquier fila.
- **Listas**: escribe un nombre en "Nueva lista…" (barra lateral). Dentro de cada lista creada hay un botón **＋ Añadir canciones**: abre un selector con tu biblioteca (con filtro y casillas) para meter varias de golpe, y **Desde archivos MP3…** para añadir MP3 del equipo directamente a esa lista. Menú **⋯** de cada fila: añadir a una lista, quitar, eliminar.
- **YouTube**: pincha el buscador superior (o pulsa **Ctrl+F**, o empieza a escribir) desde cualquier lista y la app pasa sola a la lista YouTube; escribe y pulsa Intro para ver los resultados. Se reproduce en streaming, sin guardar audio, y la miniatura del vídeo se usa como portada. Con **⋯ → Añadir a la biblioteca** (o con el corazón) se guarda el enlace.
- **Cola de canciones**: en **⋯** de cualquier canción: **Añadir a la cola** (al final) o **Reproducir a continuación** (la primera). Se ve en **Cola** (barra lateral o botón de lista junto al volumen, con el contador): *Sonando ahora*, *En cola* (se quitan con ✕ o «Vaciar cola») y *A continuación* (lo que queda de la lista que sonaba). Las canciones de la cola suenan primero y después la lista sigue por donde iba, aunque cambies de lista; pinchar una fila de la cola la reproduce al instante. Si no suena nada, «Añadir a la cola» empieza por esa canción.
- **Portada**: haz clic en la portada de la barra inferior para elegir una imagen.

## Personalizar estilo
Botón **paleta** de la barra superior. Los cambios se ven al instante y se guardan en `settings.json`:
- **Paletas** predefinidas y 4 colores a medida (acento, fondo arriba, fondo abajo, texto).
- **Fondo**: elige una imagen de tu equipo (se copia y reduce a ≤1920 px); «Quitar imagen» vuelve a la portada desenfocada.
- **Transparencia** (0–85 %): con 0 % la ventana se ve igual que siempre; al subirla se ve lo que hay detrás (otras ventanas, escritorio) a través del fondo y las capas. Nunca llega al 100 %: queda siempre un mínimo del 15 % de fondo, y se añade un tinte oscuro y un filo claro suaves para que el texto siga legible. El texto no se vuelve transparente. Necesita un escritorio con composición (GNOME y KDE lo traen de serie, también en Ubuntu).
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
- **Barra superior estilo Spotify** (junto al reloj): el **nombre de la canción** y, a su lado, tres botones de **un solo clic**: ⏮ Anterior · ⏯ Pausa/Reproducir (el icono cambia solo) · ⏭ Siguiente. No hace falta abrir ningún menú. El nombre también tiene menú (Abrir, Salir) y el clic central pausa/reanuda. Al pasar el ratón por un botón se ve la canción actual.
- **Título de la ventana** = «Canción — Artista» (como Spotify): se ve en el dock, en Actividades y en Alt+Tab.
- Lo lanza la app sola (`tray.py`, proceso aparte) y desaparece al cerrarla. En Ubuntu funciona de serie; en GNOME "puro" hace falta la extensión *AppIndicator and KStatusNotifierItem Support*. GNOME coloca cada icono nuevo a la izquierda del anterior; si en tu equipo el orden sale distinto, no afecta al funcionamiento. Para desactivar solo los botones: `GLASSPLAYER_NO_TRAY_BUTTONS=1 glassplayer`; todo el icono: `GLASSPLAYER_NO_TRAY=1 glassplayer`.
- El dock de GNOME no permite mostrar texto ni botones propios en el icono; por eso el título y los botones viven en la barra superior (y también en el menú del sistema y la pantalla de bloqueo, vía MPRIS).

## YouTube
Usa `yt-dlp`. Si deja de funcionar: `yt-dlp -U`. Las versiones recientes pueden pedir un runtime de JavaScript (deno o nodejs; el instalador pone nodejs); consulta la documentación de yt-dlp si te lo indica. Úsalo con contenido que tengas derecho a reproducir (p. ej. tu propio canal).

## Panel multimedia del sistema y pantalla de bloqueo
La canción se publica por MPRIS: GNOME muestra **una sola tarjeta con la canción que suena** (título, artista, portada y botones Anterior / Pausa / Siguiente) en el menú del sistema y al bloquear, y responde a las teclas multimedia.
- Los botones Anterior/Siguiente están siempre disponibles mientras suena algo (con una sola canción en la lista la reinician); antes GNOME los ocultaba.
- La portada es la de la canción; si es de YouTube y aún no tiene portada guardada se usa su miniatura, y si no hay ninguna, el icono de la app.
- La pista tiene un identificador estable (ya no depende de su posición en la lista) y la app nunca publica la lista de canciones, solo la actual.
Esa pantalla la dibuja GNOME Shell, así que su aspecto lo decide el sistema.

Datos en `~/.local/share/glassplayer/` (biblioteca, portadas, fondos, ajustes). Descargas en `~/Música/GlassPlayer/`.
