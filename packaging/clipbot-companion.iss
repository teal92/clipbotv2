#ifndef AppVersion
#error AppVersion must be passed from the verified release manifest
#endif
[Setup]
AppId=ClipBotCompanion
AppName=ClipBot Companion
AppVersion={#AppVersion}
#ifdef PatchFromVersion
AppVerName=ClipBot Companion {#AppVersion} beta patch
AppComments=Beta patch update from {#PatchFromVersion}. Pairing and local data are preserved.
#else
AppVerName=ClipBot Companion {#AppVersion} beta
#endif
AppPublisher=YOUR COMPANY NAME
DefaultDirName={localappdata}\Programs\ClipBotCompanion
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=ClipBotCompanionSetup
Compression=lzma2/fast
SolidCompression=yes
SetupLogging=no
UninstallDisplayIcon={app}\ClipBotCompanion.exe
WizardStyle=modern
[Tasks]
Name: "startup"; Description: "Start ClipBot Companion in the background when I sign in to Windows"; Flags: unchecked
[Files]
Source: "dist\ClipBotCompanion\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{userprograms}\ClipBot Companion"; Filename: "{app}\ClipBotCompanion.exe"
[Registry]
Root: HKCU; Subkey: "Software\Classes\clipbot-companion"; ValueType: string; ValueName: ""; ValueData: "URL:ClipBot Companion"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\clipbot-companion"; ValueType: string; ValueName: "URL Protocol"; ValueData: ""
Root: HKCU; Subkey: "Software\Classes\clipbot-companion\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\ClipBotCompanion.exe"" --handoff ""%1"""
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: none; ValueName: "ClipBotCompanion"; Flags: deletevalue uninsdeletevalue
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "ClipBotCompanion"; ValueData: """{app}\ClipBotCompanion.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue
[Run]
Filename: "{app}\ClipBotCompanion.exe"; Description: "Open ClipBot Companion to connect this computer"; Flags: nowait postinstall skipifsilent
