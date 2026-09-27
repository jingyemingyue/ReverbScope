; Inno Setup installer for the unsigned Windows one-directory bundle
; (ARCHITECTURE_V1.md §6.2). Signing is a maintainer decision.
;
; Build from the repository root after PyInstaller has produced dist\roomscope:
;   iscc /DMyAppVersion=<pyproject version> packaging\windows\roomscope.iss
; The installer is written to dist\RoomScope-setup.exe.
#define MyAppName "RoomScope"
#ifndef MyAppVersion
  #define MyAppVersion "0.0.0.dev0"
#endif
#define MyAppPublisher "RoomScope contributors"
#define MyAppURL "https://github.com/jingyemingyue/RoomScope"
; Windowed launcher: opens the GUI without a console window. The console
; roomscope.exe next to it is the CLI.
#define MyAppExeName "roomscope-gui.exe"

[Setup]
AppId={{8E0C2B3A-6F41-4C7D-9A11-7C2E1A0B4D5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\..\dist
OutputBaseFilename=RoomScope-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
LicenseFile=..\..\LICENSE
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName} {#MyAppVersion}
; English and Simplified Chinese (an official Inno Setup translation, bundled
; from Inno Setup 6.5). Setup picks the language of the Windows UI and asks
; only when it is neither; the uninstaller keeps the language chosen here.
LanguageDetectionMethod=uilanguage
ShowLanguageDialog=auto
; Authenticode, once the maintainer has a code-signing certificate (not yet):
; sign dist\roomscope\*.exe first, then compile with
;   iscc "--signtool=signtool=signtool.exe sign /fd sha256 /tr <timestamp URL> /td sha256 $f"
;        /DSignToolName=signtool ...
; so Inno Setup signs the installer and its uninstaller. Without the define
; nothing changes (docs/RELEASE_PLAN.md §3b).
#ifdef SignToolName
SignTool={#SignToolName}
SignedUninstaller=yes
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[CustomMessages]
english.ThirdPartyLicenses=Third-party licenses
chinesesimplified.ThirdPartyLicenses=第三方许可证

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Replace the whole previous version so no stale library survives an upgrade.
Source: "..\..\dist\roomscope\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:ThirdPartyLicenses}"; Filename: "{app}\THIRD_PARTY_LICENSES"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
