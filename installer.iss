; Trình cài đặt Starkid Event Player (Inno Setup 6)
; Biên dịch:  ISCC.exe /DAppVer=2.0 installer.iss   (make_installer.bat làm tự động)

#ifndef AppVer
  #define AppVer "2.0"
#endif
#define AppName "Starkid Event Player"
#define AppExe "StarkidEventPlayer.exe"

[Setup]
AppId={{EC785013-84CA-4076-BC5B-1DE7BF1A42C4}
AppName={#AppName}
AppVersion={#AppVer}
AppVerName={#AppName} {#AppVer}
AppPublisher=Starkid
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
; mặc định cài cho riêng người dùng (không cần quyền admin); có hộp chọn cài cho mọi người
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
WizardSmallImageFile=assets\logo_round.png
OutputDir=release
OutputBaseFilename=StarkidEventPlayer-Setup-{#AppVer}
Compression=lzma2/max
SolidCompression=yes
; tự đóng app đang mở khi cài bản mới
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "vi"; MessagesFile: "compiler:Default.isl"

[Messages]
; --- tiếng Việt cho các màn hình chính ---
SetupAppTitle=Cài đặt
SetupWindowTitle=Cài đặt %1
UninstallAppTitle=Gỡ cài đặt
UninstallAppFullTitle=Gỡ cài đặt %1
ButtonBack=< &Quay lại
ButtonNext=&Tiếp >
ButtonInstall=&Cài đặt
ButtonOK=Đồng ý
ButtonCancel=Hủy
ButtonYes=&Có
ButtonYesToAll=Có với &tất cả
ButtonNo=&Không
ButtonNoToAll=K&hông với tất cả
ButtonFinish=&Xong
ButtonBrowse=&Chọn...
ButtonWizardBrowse=C&họn...
ButtonNewFolder=&Tạo thư mục mới
ExitSetupTitle=Thoát cài đặt
ExitSetupMessage=Cài đặt chưa xong. Nếu thoát bây giờ, phần mềm sẽ không được cài.%n%nBạn có thể chạy lại trình cài đặt sau.%n%nThoát cài đặt?
PrivilegesRequiredOverrideTitle=Chọn kiểu cài đặt
PrivilegesRequiredOverrideInstruction=Cài cho ai?
PrivilegesRequiredOverrideText1=%1 có thể cài cho mọi người dùng trên máy (cần quyền quản trị), hoặc chỉ cho bạn.
PrivilegesRequiredOverrideText2=%1 có thể cài chỉ cho bạn, hoặc cho mọi người dùng trên máy (cần quyền quản trị).
PrivilegesRequiredOverrideAllUsers=Cài cho &mọi người dùng
PrivilegesRequiredOverrideAllUsersRecommended=Cài cho &mọi người dùng (khuyên dùng)
PrivilegesRequiredOverrideCurrentUser=Chỉ cài cho &tôi
PrivilegesRequiredOverrideCurrentUserRecommended=Chỉ cài cho &tôi (khuyên dùng)
WelcomeLabel1=Chào mừng đến với trình cài đặt [name]
WelcomeLabel2=Trình này sẽ cài [name/ver] vào máy tính của bạn.%n%nNên đóng các chương trình khác trước khi tiếp tục.
WizardSelectDir=Chọn nơi cài đặt
SelectDirDesc=Cài [name] vào đâu?
SelectDirLabel3=[name] sẽ được cài vào thư mục dưới đây.
SelectDirBrowseLabel=Bấm Tiếp để tiếp tục. Muốn chọn thư mục khác, bấm Chọn.
DiskSpaceGBLabel=Cần ít nhất [gb] GB dung lượng trống.
DiskSpaceMBLabel=Cần ít nhất [mb] MB dung lượng trống.
DirExistsTitle=Thư mục đã có
DirExists=Thư mục:%n%n%1%n%nđã tồn tại. Vẫn cài vào thư mục này?
WizardSelectTasks=Tùy chọn thêm
SelectTasksDesc=Bạn muốn làm thêm gì?
SelectTasksLabel2=Chọn các mục muốn làm khi cài [name], rồi bấm Tiếp.
WizardReady=Sẵn sàng cài đặt
ReadyLabel1=Đã sẵn sàng cài [name] vào máy.
ReadyLabel2a=Bấm Cài đặt để bắt đầu, hoặc Quay lại để xem/đổi lựa chọn.
ReadyLabel2b=Bấm Cài đặt để bắt đầu.
ReadyMemoDir=Thư mục cài đặt:
ReadyMemoTasks=Tùy chọn thêm:
WizardPreparing=Đang chuẩn bị
PreparingDesc=Đang chuẩn bị cài [name].
ApplicationsFound=Các chương trình sau đang dùng file cần cập nhật. Nên để trình cài đặt tự đóng chúng.
ApplicationsFound2=Các chương trình sau đang dùng file cần cập nhật. Nên để trình cài đặt tự đóng chúng. Cài xong sẽ thử mở lại.
CloseApplications=&Tự động đóng các chương trình
DontCloseApplications=&Không đóng
WizardInstalling=Đang cài đặt
InstallingLabel=Vui lòng chờ trong lúc cài [name]...
StatusExtractFiles=Đang chép file...
StatusCreateIcons=Đang tạo lối tắt...
StatusSavingUninstall=Đang lưu thông tin gỡ cài đặt...
FinishedHeadingLabel=Đã cài xong [name]
FinishedLabelNoIcons=[name] đã được cài vào máy.
FinishedLabel=[name] đã được cài vào máy. Có thể mở bằng lối tắt đã tạo.
ClickFinish=Bấm Xong để đóng trình cài đặt.
RunEntryExec=Mở %1
ConfirmUninstall=Gỡ hoàn toàn %1 khỏi máy?%n%n(Dự án, cài đặt và phím tắt của bạn vẫn được giữ lại.)
UninstallStatusLabel=Đang gỡ %1, vui lòng chờ...
UninstalledAll=Đã gỡ %1 khỏi máy.
SetupAlreadyRunning=Trình cài đặt đang chạy.
WindowsVersionNotSupported=Phần mềm cần Windows 10 hoặc 11 (64-bit).

[CustomMessages]
vi.CreateDesktopIcon=Tạo lối tắt ngoài &màn hình Desktop
vi.AdditionalIcons=Lối tắt:
vi.LaunchProgram=Mở %1 ngay

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "stage\StarkidEventPlayer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; bản cài mới thay sạch thư viện cũ (tránh sót file của phiên bản trước)
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autoprograms}\Gỡ cài đặt {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
