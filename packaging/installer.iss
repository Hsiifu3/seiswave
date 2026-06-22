; SeisWave Windows 安装器 (Inno Setup)
; 由 CI 调用：ISCC.exe /DAppVersion=<tag> packaging\installer.iss
; 打包 PyInstaller onedir 产物 dist\SeisWave\ 为安装向导 Setup.exe。

#ifndef AppVersion
  #define AppVersion "1.0"
#endif

[Setup]
AppId={{B7E2B1C0-5E2A-4C77-9E2D-A1B2C3D4E5F6}
AppName=SeisWave
AppVersion={#AppVersion}
AppPublisher=SeisWave
SourceDir=..
DefaultDirName={autopf}\SeisWave
DefaultGroupName=SeisWave
DisableProgramGroupPage=yes
OutputDir=installer_out
OutputBaseFilename=SeisWave-v{#AppVersion}-windows-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
UninstallDisplayName=SeisWave {#AppVersion}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "dist\SeisWave\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\SeisWave"; Filename: "{app}\SeisWave.exe"
Name: "{group}\卸载 SeisWave"; Filename: "{uninstallexe}"
Name: "{autodesktop}\SeisWave"; Filename: "{app}\SeisWave.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Run]
Filename: "{app}\SeisWave.exe"; Description: "立即运行 SeisWave"; Flags: nowait postinstall skipifsilent
