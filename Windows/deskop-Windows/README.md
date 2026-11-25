# GlassPlayer para Windows

Versión de escritorio para Windows de GlassPlayer, escrita con **Qt (PySide6)**. Sale como un instalador normal
(`GlassPlayer-Setup.exe`): doble clic, «Siguiente», y listo. No hace falta instalar Python ni nada más.

La versión de Linux (`desktop/`, GTK) no se toca. Esta carpeta es independiente.

## Qué incluye

- Biblioteca: Recientes, Canciones, Favoritos, listas propias (crear, eliminar, añadir y quitar canciones) y cola
  («Reproducir a continuación», «Añadir a la cola»).
- **Novedades**: cajas de géneros (Deezer) con favoritos ★. Dentro de cada género salen las canciones en tendencia,
  buscadas en YouTube. Los géneros no latinos descartan lo que está en Latino/Reggaeton/Salsa/Cumbia.
- Búsqueda en YouTube.
- **Reproducción sin cortes**: la canción se descarga entera antes de sonar (se ve el porcentaje) y la siguiente se
  prepara mientras suena la actual.
- Botón **Aleatorio** (interruptor) en las listas propias.
- Descarga de canciones como **MP3** con etiquetas y portada, guardadas en `Música\GlassPlayer` y en la lista
  «Descargadas sin conexión» (suenan sin internet).
- Añadir MP3 del equipo, paletas de color, volumen, icono en la bandeja y atajos (Espacio, Ctrl+F, teclas multimedia
  con la ventana activa).

No incluye (a diferencia de la de Linux): imagen de fondo y transparencia de ventana, controles MPRIS y modo móvil.

## Conseguir el instalador (sin tener Windows): GitHub Actions

1. Copia esta carpeta al repositorio como `deskop-Windows/`.
2. Copia `packaging/build-windows.yml` a `.github/workflows/build-windows.yml` (en la raíz del repositorio).
3. Sube los cambios (`git add`, `git commit`, `git push`).
4. En GitHub: pestaña **Actions → Build Windows installer → Run workflow**. Tarda unos 10 minutos.
5. Cuando termine, entra en la ejecución y descarga **GlassPlayer-Windows-Setup** (Artifacts). Dentro está
   `GlassPlayer-Setup.exe`.

La construcción descarga yt-dlp, ffmpeg y deno, empaqueta con PyInstaller, **arranca el programa empaquetado y
comprueba que decodifica audio** (si algo falta, la construcción falla y te lo dice), y crea el instalador con Inno
Setup.

## Pasárselo a los amigos

- Envíales `GlassPlayer-Setup.exe` (Drive, Telegram…). Se instala para el usuario actual, sin pedir permisos de
  administrador, con icono en el escritorio y en el menú Inicio. Windows 10/11 de 64 bits.
- **Windows mostrará «Windows protegió su PC»** porque el instalador no está firmado (firmar cuesta dinero cada año).
  Hay que pulsar **«Más información» → «Ejecutar de todas formas»**. Algún antivirus puede marcarlo como sospechoso
  por error (pasa con muchos programas hechos con PyInstaller).
- yt-dlp se actualiza solo una vez al día, porque YouTube cambia a menudo y, si no, las canciones dejan de cargar.
- Datos del usuario: `%APPDATA%\GlassPlayer` (biblioteca, ajustes, caché de audio temporal de las últimas 40
  canciones). Desinstalar desde «Aplicaciones» de Windows no borra esos datos ni la música descargada.
- Si algo falla, se escribe en `%APPDATA%\GlassPlayer\error.log`: pídeles ese archivo.

## Desarrollo en Windows

```powershell
cd deskop-Windows
py -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File packaging\fetch_tools.ps1   # descarga yt-dlp, ffmpeg y deno a tools\
py run_glassplayer.py
```

Generar el `.exe` y el instalador en local (necesita [Inno Setup 6](https://jrsoftware.org/isinfo.php)):

```powershell
py -m pip install -r requirements-build.txt
pyinstaller packaging\glassplayer.spec --noconfirm
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" packaging\installer.iss
```

## Pruebas

```bash
python tests/test_app.py     # interfaz sin pantalla: vistas, listas, aleatorio, cola, Novedades, descargas, audio
python tests/test_logic.py   # Deezer, filtro latino, caché de audio (usa bash: Linux/macOS/WSL)
```

Las pruebas simulan Deezer, YouTube y las descargas; no necesitan internet. Guardan capturas en `tests/out/`.

## Estructura

```
glassplayer/      código (window.py = ventana; news.py, youtube.py, audiocache.py, downloader.py = lógica)
assets/           icono
packaging/        glassplayer.spec (PyInstaller), installer.iss (Inno Setup), fetch_tools.ps1, build-windows.yml
tests/            pruebas
```

## Aviso

yt-dlp y la API pública de Deezer se usan con fines personales. Descargar o reproducir contenido de YouTube puede
incumplir sus condiciones de uso: úsalo solo con contenido que tengas derecho a reproducir o descargar y no distribuyas
la aplicación públicamente.
