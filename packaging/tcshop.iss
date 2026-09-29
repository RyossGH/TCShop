; Installeur Windows de TCShop (Inno Setup 6)
; Compilation :  ISCC.exe packaging\tcshop.iss   (après la construction PyInstaller dans dist\TCShop)

#define AppName "TCShop"
#define AppVersion "2.4.0"
#define AppExe "TCShop.exe"

[Setup]
AppId={{8F2B6C1E-5A4D-4E1B-9C3F-7D2E1A6B4C90}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=TCShop
AppComments=Caisse et gestion de boutique de jeux, TCG et collection
VersionInfoVersion={#AppVersion}
; installation pour l'utilisateur courant : pas besoin de droits administrateur
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist\installer
OutputBaseFilename=TCShop-Setup-{#AppVersion}
SetupIconFile=..\app\resources\tcshop.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardImageFile=wizard_large.bmp
WizardSmallImageFile=wizard_small.bmp
Compression=lzma2/max
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\TCShop\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent

; Les données (base, photos, sauvegardes) sont dans %LOCALAPPDATA%\TCShop et sont conservées
; à la désinstallation, pour ne jamais perdre le stock ni l'historique des ventes.
