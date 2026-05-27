[Setup]
AppName=CPM Monitor
AppVersion=4.5
AppPublisher=CPM Tracks
AppPublisherURL=https://monitor.cpmtracks.com
DefaultDirName={localappdata}\CPMTracks\App
DefaultGroupName=CPM Monitor
DisableProgramGroupPage=yes
OutputBaseFilename=CPMMonitor_Setup_v4.5
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\CPMMonitor.exe
CloseApplications=yes

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Files]
Source: "dist\CPMMonitor\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userstartup}\CPM Monitor"; Filename: "{app}\CPMMonitor.exe"; Parameters: "--background"

[Run]
Filename: "{app}\CPMMonitor.exe"; Description: "Iniciar CPM Monitor ahora"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/f /im CPMMonitor.exe"; Flags: runhidden

[UninstallDelete]
Type: filesandordirs; Name: "{localappdata}\CPMTracks\App"
