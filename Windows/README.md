# Instalar MusicPlayer en Windows
Insalar MusicPlayer para Windows.
No necesitas instalar Python ni nada más: el instalador ya lo incluye todo.

**Requisitos:** Windows 10 u 11 de 64 bits y conexión a internet para buscar y reproducir canciones debido a que ciertas funcionalidades del linux se encuentran temporalmente bloqueadas en Windows.

## Pasos

1. En la página principal de este repositorio, mira la columna derecha y pulsa en **Releases**
   (o abre directamente la pestaña *Releases*).
2. Entra en la versión más reciente (arriba del todo, marcada como **Latest**).
3. En la sección **Assets**, pulsa sobre **`GlassPlayer-Setup.exe`** para descargarlo.
4. Abre el archivo descargado (normalmente está en la carpeta *Descargas*).
5. Si Windows muestra **«Windows protegió su PC»**:
   1. Pulsa **Más información**.
   2. Pulsa **Ejecutar de todas formas**.

   Es normal: el instalador no está firmado digitalmente. Algún antivirus puede avisar por error.
6. Sigue el asistente (**Siguiente → Instalar → Finalizar**). Se instala solo para tu usuario y **no pide permisos de
   administrador**.
7. Abre **GlassPlayer** desde el icono del escritorio o desde el menú Inicio.

## Uso básico (TODAS LAS FUNCIONALIDADES SON GRATUITAS)

- **Espacio:** pausa o reanuda la canción.
- **X de la ventana:** cierra la aplicación del todo.
- Puedes añadir tus propios MP3 desde la propia aplicación.
- Acceso a listas actuales con las Top Hits del momento por género. 
- Creación de listas propias y modificación de las mismas.
- Posibilidad de establecer la reproducción de las listas de forma aleatoria.
## Desinstalar

*Configuración → Aplicaciones → GlassPlayer → Desinstalar*.
Tus datos y la música descargada se conservan en `%APPDATA%\GlassPlayer`; bórrala a mano si quieres eliminarlos.

## Si algo falla

Envía el archivo `%APPDATA%\GlassPlayer\error.log` a quien te pasó la aplicación.
