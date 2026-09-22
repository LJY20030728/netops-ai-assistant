; NetOps AI Assistant 安装脚本
; 用 Inno Setup 6 编译

#define MyAppName "NetOps AI Assistant"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "LJY"
#define MyAppExeName "NetOpsLauncher.exe"

[Setup]
AppId={{8F3A2B1C-4D5E-6F70-8A9B-0C1D2E3F4A5B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\NetOpsAssistant
DefaultGroupName=NetOps AI Assistant
DisableProgramGroupPage=yes
DisableDirPage=no
OutputDir=installer
OutputBaseFilename=NetOpsAssistant-Setup
SetupIconFile=frontend\assets\nahida.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "dist\NetOpsLauncher\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\NetOps AI Assistant"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 NetOps AI Assistant"; Filename: "{uninstallexe}"
Name: "{commondesktop}\NetOps AI Assistant"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch NetOps AI Assistant now"; Flags: nowait postinstall skipifsilent

[Code]
// Check Docker Desktop before install
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  if not FileExists(ExpandConstant('{pf}\Docker\Docker\Docker Desktop.exe')) then
  begin
    if MsgBox('Docker Desktop not detected.' #13#10 #13#10 +
      'The FRR network lab needs Docker Desktop to run three FRR containers.' #13#10 +
      'Open the Docker download page now?' #13#10 #13#10 +
      '(Choose No to continue; FRR topology will be unavailable)',
      mbConfirmation, MB_YESNO) = IDYES then
    begin
      ShellExec('open', 'https://www.docker.com/products/docker-desktop/', '', '', SW_SHOW, ewNoWait, ResultCode);
    end;
  end;
end;
