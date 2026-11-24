# EventPlayer — Phần mềm phát nhạc sự kiện cho Windows

Viết bằng Python + PySide6 (Qt 6). Giải mã âm thanh bằng FFmpeg có sẵn trong Qt.

## Chạy
- Nháy đúp `run.bat`, hoặc chạy `python main.py`
- Đóng gói thành .exe: nháy đúp `build.bat` → `dist\EventPlayer\EventPlayer.exe`
  (cả thư mục `dist\EventPlayer` có thể chép sang máy khác, không cần cài Python)

## Tính năng
- **Nhiều danh sách phát** dạng tab; kéo thả file/thư mục/M3U từ Explorer; kéo để sắp xếp lại
- **4 chế độ phát**: Dừng sau mỗi bài (sự kiện) · Phát liên tục · Lặp 1 bài · Lặp danh sách
- **Crossfade** giữa 2 bài (2 deck phát song song), fade in / fade out tùy chỉnh
- **Dừng sau bài này** cho từng bài (⏹), **Đặt làm bài kế tiếp** (⏭ Cue)
- Đồng hồ thời gian **đã phát / còn lại** cỡ lớn, nhấp nháy đỏ khi sắp hết bài; đồng hồ giờ thực
- Hiện **bài tiếp theo**, tổng thời lượng và thời gian còn lại đến hết danh sách
- Bài đã phát hiện màu xám, file bị mất hiện màu đỏ
- **12 nút Jingle (F1–F12)**: gán file, đổi tên, đổi màu, lặp; tự **giảm nhạc nền** khi phát jingle
- **Nghe thử ra tai nghe** (chọn card âm thanh riêng cho loa chính / tai nghe / jingle)
- Tự lưu toàn bộ danh sách + jingle khi thoát, mở lại đúng như cũ
- Lưu/mở danh sách `.evpl` hoặc `.m3u8`

## Phím tắt
| Phím | Chức năng |
|---|---|
| Space | Phát / Tạm dừng (khi đang dừng: phát bài tiếp theo) |
| Esc | Dừng có fade out (bấm 2 lần = dừng ngay) |
| Enter / nháy đúp | Phát ngay bài đang chọn |
| Ctrl+→ / Ctrl+← | Bài tiếp / bài trước |
| Ctrl+E | Đặt bài đang chọn làm bài kế tiếp |
| Ctrl+L | Nghe thử ra tai nghe |
| Ctrl+↑ / Ctrl+↓ | Tăng / giảm âm lượng |
| F1 … F12 | Phát / dừng jingle |
| Delete | Xóa bài khỏi danh sách |
| Ctrl+Shift+Esc | Dừng mọi âm thanh ngay lập tức |

## Cấu trúc mã
- `main.py` — cửa sổ chính, logic phát, crossfade, cài đặt, lưu phiên
- `audio.py` — `Deck`: trình phát có fade, ducking, chọn thiết bị ra
- `playlist.py` — danh sách phát, đọc tag (mutagen), kéo thả
- `pads.py` — bảng nút jingle
