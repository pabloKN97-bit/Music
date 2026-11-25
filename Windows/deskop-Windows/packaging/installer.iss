; Instalador de GlassPlayer (Inno Setup 6). Se compila después de PyInstaller:
;   ISCC.exe packaging\installer.iss          (opcional: /DMyAppVersion=1.2.3)
#define MyAppName "GlassPlayer"
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{B7C0A3D2-6E41-4C1B-9A55-5F0C7A1E2D10}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Pablo
; Instalación para el usuario actual (no pide permisos de administrador) y permite que yt-dlp se actualice solo
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\installer_output
OutputBaseFilename=GlassPlayer-Setup
SetupIconFile=..\assets\glassplayer.ico
UninstallDisplayIcon={app}\GlassPlayer.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\GlassPlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\GlassPlayer.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\GlassPlayer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\GlassPlayer.exe"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
