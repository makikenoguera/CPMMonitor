[Setup]
AppName=SumarteRed Monitor
AppVersion=1.0.0
AppPublisher=SumarteRed
AppPublisherURL=https://sumartered.com
AppSupportURL=https://sumartered.com
DefaultDirName={autopf}\SumarteRed Monitor
DefaultGroupName=SumarteRed Monitor
OutputDir=Output
OutputBaseFilename=SumarteRedMonitor_Setup
SetupIconFile=assets\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0.17763
UninstallDisplayIcon={app}\SumarteRedMonitor.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Íconos adicionales:"; Flags: unchecked
Name: "startupicon"; Description: "Iniciar automáticamente con Windows"; GroupDescription: "Inicio automático:"

[Files]
Source: "dist\SumarteRedMonitor.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SumarteRed Monitor"; Filename: "{app}\SumarteRedMonitor.exe"
Name: "{group}\Desinstalar SumarteRed Monitor"; Filename: "{uninstallexe}"
Name: "{commondesktop}\SumarteRed Monitor"; Filename: "{app}\SumarteRedMonitor.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "SumarteRedMonitor"; ValueData: "{app}\SumarteRedMonitor.exe"; Flags: uninsdeletevalue; Tasks: startupicon

[Run]
Filename: "{app}\SumarteRedMonitor.exe"; Description: "Iniciar SumarteRed Monitor"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM SumarteRedMonitor.exe"; Flags: runhidden
