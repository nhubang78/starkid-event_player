# Starkid Event Player

Phần mềm phát nhạc sự kiện cho Windows: bảng 32 kênh kiểu cart player + trang Playlist.
Viết bằng Python + PySide6 (Qt 6), giải mã âm thanh bằng FFmpeg có sẵn trong Qt.

## Chạy
- Cài thư viện: `python -m pip install PySide6 mutagen av pillow`
- Chạy: nháy đúp `run.bat` hoặc `python main.py`
- Đóng gói .exe: nháy đúp `build.bat` → `release\StarkidEventPlayer\StarkidEventPlayer.exe` và file zip
  (chép nguyên thư mục `release\StarkidEventPlayer` hoặc file zip sang máy khác là chạy, không cần Python)

## Tính năng
**Trang Audio 1-16 / Audio 17-32** — 32 kênh, mỗi kênh có:
- Fader âm lượng (%, dB) + đồng hồ VU stereo có giữ đỉnh
- Thời gian đã phát / còn lại, thanh tua
- Nút lớn hiện số kênh + tên bài, phím tắt riêng (1–8, 9, 0, Q–Y, U–P, A–L, Z–C)
- ‖ tạm dừng, Dừng, 🔁 lặp, ◢ fade in khi phát, ◣ fade out rồi dừng
- Menu •••: đổi tên, đổi màu, chọn thiết bị ra riêng, nghe thử ra tai nghe, xóa
- Kéo thả file từ Explorer vào kênh

**Cột phải**: nút **GO** (phát lần lượt các kênh có nhạc, Space) và **Master** (fader + VU tổng).

**Thanh công cụ**: Dự án mới / Mở / Lưu (`.evp`), Tùy chọn, Phím tắt, Hướng dẫn,
**Phát đơn** (phát kênh mới thì kênh khác tự fade out), **Long View** (màn hình lớn đếm ngược),
**Dừng hết** (Esc; bấm 2 lần = dừng ngay), **Khóa cài đặt** (chống đổi nhầm khi đang diễn).

**Trang Playlist**: nhiều danh sách dạng tab, 4 chế độ (dừng sau mỗi bài / liên tục / lặp bài /
lặp danh sách), crossfade, đặt bài kế tiếp, "dừng sau bài này", cảnh báo sắp hết bài, nhập/xuất M3U.

Chương trình tự nhớ toàn bộ trạng thái khi tắt và mở lại y như cũ.

## Cấu trúc mã
| File | Nội dung |
|---|---|
| `main.py` | Cửa sổ chính, thanh công cụ, GO, Master, Long View, dự án, tùy chọn |
| `channel.py` | Một kênh phát (channel strip) |
| `playlist_page.py` | Trang Playlist |
| `playlist.py` | Danh sách bài, đọc tag (mutagen), kéo thả |
| `widgets.py` | Đồng hồ VU, fader, nút cart, biểu tượng |
| `audio.py` | `Deck`: trình phát có fade, đo mức, chọn thiết bị ra |
