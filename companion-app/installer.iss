; WhatsGPU Installer - Inno Setup Script
; Compila com: ISCC.exe installer.iss

#define MyAppName "WhatsGPU"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "WhatsGPU"
#define MyAppExeName "Whats GPU.exe"

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={userdocs}\WhatsGPU
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=WhatsGPU-Setup
SetupIconFile=icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
; Atalhos
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: checkedonce
Name: "autostart"; Description: "Iniciar com o Windows"; GroupDescription: "Opções:"; Flags: checkedonce
; Modelos Whisper
Name: "model_small"; Description: "small (466 MB) — Rápido e leve (Recomendado)"; GroupDescription: "Baixar modelos Whisper (após instalação):"; Flags: checkedonce
Name: "model_large"; Description: "large-v3 (3.1 GB) — Melhor precisão (RTX 4070+)"; GroupDescription: "Baixar modelos Whisper (após instalação):"
Name: "model_medium"; Description: "medium (1.5 GB) — Bom equilíbrio (RTX 3060/4060)"; GroupDescription: "Baixar modelos Whisper (após instalação):"
Name: "model_base"; Description: "base (142 MB) — Precisão básica, muito rápido"; GroupDescription: "Baixar modelos Whisper (após instalação):"
Name: "model_tiny"; Description: "tiny (75 MB) — Apenas para testes"; GroupDescription: "Baixar modelos Whisper (após instalação):"

[Files]
; App principal
Source: "dist\Whats GPU.exe"; DestDir: "{app}"; Flags: ignoreversion
; Extensão Chrome
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "WhatsGPU"; ValueData: """{app}\{#MyAppExeName}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
; Iniciar app com download de modelos selecionados
Filename: "{app}\{#MyAppExeName}"; Parameters: "--download-models {code:GetSelectedModels}"; Description: "Iniciar WhatsGPU e baixar modelos selecionados"; Flags: nowait postinstall skipifsilent
; Abrir Chrome na página de extensões
Filename: "cmd"; Parameters: "/c start chrome://extensions"; Description: "Abrir Chrome para instalar extensão (Carregar sem compactação → {app}\extension)"; Flags: nowait postinstall skipifsilent unchecked runhidden

[UninstallRun]
Filename: "taskkill"; Parameters: "/F /IM ""Whats GPU.exe"""; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
; Limpar pasta de instalação
Type: filesandordirs; Name: "{app}\extension"
Type: filesandordirs; Name: "{app}"

[Messages]
FinishedLabel=WhatsGPU foi instalado com sucesso!%n%nPara instalar a extensão no Chrome:%n1. Abra chrome://extensions%n2. Ative o Modo Desenvolvedor%n3. Clique em "Carregar sem compactação"%n4. Selecione a pasta: %n   {app}\extension

[Code]
function GetSelectedModels(Param: String): String;
var
  Models: String;
begin
  Models := '';
  if WizardIsTaskSelected('model_small') then
  begin
    if Models <> '' then Models := Models + ',';
    Models := Models + 'small';
  end;
  if WizardIsTaskSelected('model_large') then
  begin
    if Models <> '' then Models := Models + ',';
    Models := Models + 'large-v3';
  end;
  if WizardIsTaskSelected('model_medium') then
  begin
    if Models <> '' then Models := Models + ',';
    Models := Models + 'medium';
  end;
  if WizardIsTaskSelected('model_base') then
  begin
    if Models <> '' then Models := Models + ',';
    Models := Models + 'base';
  end;
  if WizardIsTaskSelected('model_tiny') then
  begin
    if Models <> '' then Models := Models + ',';
    Models := Models + 'tiny';
  end;
  Result := Models;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
  ModelsDir: String;
  WhatsGPUDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    // 1. Matar processo
    Exec('taskkill', '/F /IM "Whats GPU.exe"', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);

    // 2. Remover registro de auto-start
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'WhatsGPU');

    // 3. Perguntar se quer remover modelos baixados
    ModelsDir := ExpandConstant('{userdocs}\WhatsGPU\Modelos');
    WhatsGPUDir := ExpandConstant('{userdocs}\WhatsGPU');
    if DirExists(ModelsDir) then
    begin
      if MsgBox(
        'Deseja remover todos os modelos Whisper baixados?' + #13#10 +
        '(Pasta: ' + ModelsDir + ')' + #13#10 + #13#10 +
        'Isso liberará espaço em disco, mas será necessário baixar novamente se reinstalar.',
        mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(WhatsGPUDir, True, True, True);
      end;
    end;
  end;

  if CurUninstallStep = usPostUninstall then
  begin
    // 4. Mostrar tutorial de remoção da extensão no Chrome
    MsgBox(
      'WhatsGPU foi removido com sucesso!' + #13#10 + #13#10 +
      'Para remover a extensão do Chrome:' + #13#10 +
      '1. Abra o Chrome e acesse chrome://extensions' + #13#10 +
      '2. Encontre "Whats GPU" na lista' + #13#10 +
      '3. Clique em "Remover"' + #13#10 +
      '4. Confirme clicando em "Remover" novamente' + #13#10 + #13#10 +
      'Ou clique com botao direito no icone da extensão > Remover do Chrome',
      mbInformation, MB_OK);
  end;
end;
