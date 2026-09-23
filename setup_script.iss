; Script Inno Setup dành cho DUCTAM24VN FACTORY MEME
#define MyAppName "DUCTAM24VN FACTORY MEME"
#define MyAppVersion "1.0"
#define MyAppPublisher "DUCTAM24VN TOOLS"
#define MyAppExeName "DUCTAM24VN FACTORY MEME.exe"
#define MyProjectPath "C:\Users\DUCTAM24VN\Desktop\SOUND FX FACTORY"
#define MySourcePath "C:\Users\DUCTAM24VN\Desktop\SOUND FX FACTORY\dist\DUCTAM24VN FACTORY MEME"

[Setup]
AppId={{D847B3C1-9A2E-4E7B-A536-123456789ABC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir={#MyProjectPath}\Output_Installer
OutputBaseFilename=DUCTAM24VN_FACTORY_MEME_Setup_v1.0
SetupIconFile={#MyProjectPath}\app_icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "{#MySourcePath}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MyProjectPath}\app_icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\app_icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent