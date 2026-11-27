#pragma codepage 65001
; Inno Setup definition for the PyInstaller onedir build in dist\FileSense.

[Setup]
AppId={{B145BE18-7421-4D69-A3AA-052FAC410B9C}
AppName=ProSoft - FileSense
AppVersion=2.0.0
AppVerName=ProSoft - FileSense 2.0.0
AppPublisher=ProSoft
LicenseFile=..\legal\EULA.txt
DisableWelcomePage=no
DefaultDirName={autopf}\ProSoft\FileSense
DefaultGroupName=ProSoft\FileSense
DisableProgramGroupPage=yes
UninstallDisplayName=ProSoft - FileSense
UninstallDisplayIcon={app}\FileSense.exe

; This is a 64-bit PyInstaller build. Keep its internal folder structure intact.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin

WizardStyle=modern dark
SetupIconFile=..\assets\FSICO.ico
WizardImageFile=..\assets\WizardWelcomePanel.png
WizardSmallImageFile=
OutputDir=..\installer
OutputBaseFilename=ProSoft-FileSense-Setup
Compression=lzma2/max
SolidCompression=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
WelcomeLabel1=Welcome to the installation of%nProSoft - FileSense
WelcomeLabel2=One smarter way to manage your PC.%n%nSetup will guide you through the installation.

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
; Install the complete onedir output, including PySide6 and other bundled runtime files.
Source: "..\dist\FileSense\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\legal\EULA.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\ProSoft - FileSense"; Filename: "{app}\FileSense.exe"
Name: "{autodesktop}\ProSoft - FileSense"; Filename: "{app}\FileSense.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\FileSense.exe"; Description: "Launch ProSoft - FileSense"; Flags: nowait postinstall skipifsilent

[Code]
var
  CraftedByLabel: TNewStaticText;

procedure InitializeWizard();
begin
  WizardForm.WelcomeLabel2.Height := ScaleY(120);

  CraftedByLabel := TNewStaticText.Create(WizardForm);
  CraftedByLabel.Parent := WizardForm.WelcomeLabel2.Parent;
  CraftedByLabel.AutoSize := False;
  CraftedByLabel.Caption := 'Crafted by Ankur © ProSoft';
  CraftedByLabel.Left := WizardForm.WelcomeLabel2.Left;
  CraftedByLabel.Width := WizardForm.WelcomeLabel2.Width;
  CraftedByLabel.Height := ScaleY(24);
  CraftedByLabel.Top := CraftedByLabel.Parent.ClientHeight - CraftedByLabel.Height - ScaleY(40);
  CraftedByLabel.Font.Name := WizardForm.WelcomeLabel2.Font.Name;
  CraftedByLabel.Font.Size := WizardForm.WelcomeLabel2.Font.Size;
  CraftedByLabel.Font.Color := WizardForm.WelcomeLabel2.Font.Color;
end;
