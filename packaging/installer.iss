#define MyAppName "消除车牌"
#define MyAppVersion "0.2.0-rc.7"
#define MyNumericVersion "0.2.0.7"
#define MyAppPublisher "SARSfang"
#define MyAppExeName "消除车牌.exe"

[Setup]
AppId={{FEF18DF0-60F9-4097-8F51-1EEE085A7051}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
UsePreviousAppDir=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist\installer
OutputBaseFilename=消除车牌-Setup-v{#MyAppVersion}-win64
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
VersionInfoVersion={#MyNumericVersion}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} 安装程序
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyNumericVersion}
MinVersion=10.0.17763
CloseApplications=force
RestartApplications=no
AppMutex=RemoveNumberPlate-FEF18DF0-60F9-4097-8F51-1EEE085A7051
SetupMutex=RemoveNumberPlate-Setup-FEF18DF0-60F9-4097-8F51-1EEE085A7051

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Files]
Source: "..\dist\消除车牌\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "vendor\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall; Check: not IsWebView2RuntimeInstalled

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "正在安装界面运行环境…"; Flags: waituntilterminated; Check: not IsWebView2RuntimeInstalled
Filename: "{app}\{#MyAppExeName}"; Description: "启动 {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  WebView2ClientId = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}';
  CurrentNumericVersion = '{#MyNumericVersion}';
  UninstallKey =
    'Software\Microsoft\Windows\CurrentVersion\Uninstall\' +
    '{FEF18DF0-60F9-4097-8F51-1EEE085A7051}_is1';

function NextVersionPart(var Version: String): Integer;
var
  Separator: Integer;
  Value: String;
begin
  Separator := Pos('.', Version);
  if Separator = 0 then
  begin
    Value := Version;
    Version := '';
  end
  else
  begin
    Value := Copy(Version, 1, Separator - 1);
    Delete(Version, 1, Separator);
  end;
  Result := StrToIntDef(Value, 0);
end;

function CompareNumericVersions(LeftVersion, RightVersion: String): Integer;
var
  Index: Integer;
  LeftPart: Integer;
  RightPart: Integer;
begin
  Result := 0;
  for Index := 1 to 4 do
  begin
    LeftPart := NextVersionPart(LeftVersion);
    RightPart := NextVersionPart(RightVersion);
    if LeftPart < RightPart then
    begin
      Result := -1;
      Exit;
    end;
    if LeftPart > RightPart then
    begin
      Result := 1;
      Exit;
    end;
  end;
end;

function InitializeSetup: Boolean;
var
  InstallLocation: String;
  InstalledVersion: String;
begin
  Result := True;
  if
    RegQueryStringValue(HKCU, UninstallKey, 'InstallLocation', InstallLocation) and
    GetVersionNumbersString(
      AddBackslash(InstallLocation) + '{#MyAppExeName}',
      InstalledVersion
    ) and
    (CompareNumericVersions(InstalledVersion, CurrentNumericVersion) > 0)
  then
  begin
    MsgBox(
      '电脑上已经安装了更新版本。为保护任务数据，本安装程序不会执行降级。',
      mbError,
      MB_OK
    );
    Result := False;
  end;
end;

function HasValidWebViewVersion(RootKey: Integer; KeyPath: String): Boolean;
var
  Version: String;
begin
  Result :=
    RegQueryStringValue(RootKey, KeyPath, 'pv', Version) and
    (Version <> '') and
    (CompareText(Version, '0.0.0.0') <> 0);
end;

function IsWebView2RuntimeInstalled: Boolean;
begin
  Result :=
    HasValidWebViewVersion(
      HKLM32,
      'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId
    ) or
    HasValidWebViewVersion(
      HKCU,
      'Software\Microsoft\EdgeUpdate\Clients\' + WebView2ClientId
    );
end;
