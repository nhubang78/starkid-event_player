# Starkid Event Player

Phần mềm phát nhạc sự kiện cho Windows: bảng 32 kênh kiểu cart player + trang Playlist.
Viết bằng Python + PySide6 (Qt 6), giải mã âm thanh bằng FFmpeg có sẵn trong Qt.

## Chạy
- Cài thư viện: `python -m pip install PySide6 mutagen av pillow numpy`
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
Fader mỗi kênh chỉnh to/nhỏ riêng kênh đó; fader **Master** là âm lượng chính của sound card
(chính là thanh âm lượng Windows — chỉnh bên nào bên kia tự chạy theo).

**Giao diện Tối / Sáng**: nút Sáng/Tối trên thanh công cụ hoặc menu Hiển thị.

**Bảng chỉnh bài** (trên lưới kênh): dạng sóng của kênh đang chọn (zoom, tua, chọn đoạn, 1/2 sóng),
BPM tự dò + lưới nhịp, điểm CUE, cắt IN / OUT, LOOP A-B / 1-2-4-8 giây / vùng chọn, nghe trước ra tai nghe.
Nút **Soi nhịp** mở cửa sổ phân tích: Kick / Snare / Clap / Hi-hat / Bass / Giọng hát, phách, ô nhịp, đoạn
(INTRO / BUILD / DROP / BREAK / OUTRO), điểm Drop (bấm để đặt IN), Hot Cue.

**Trang Âm thanh** (Ctrl+4): máy tính nghe qua micro đo / line-in để
- vẽ biểu đồ tần số (RTA 31 dải 1/3 octave + FFT), đo mức micro và gợi ý chỉnh gain,
- phát hiện hú (báo tần số + gợi ý cắt EQ trên mixer), ring-out tìm sẵn tần số dễ hú,
- đo phòng bằng pink noise (gợi ý EQ), phát tone / quét tần số / noise để thử loa.

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
| `sysvolume.py` | Âm lượng chính của sound card (Windows Core Audio) cho fader Master |
| `theme.py` | Bảng màu + stylesheet giao diện Tối / Sáng |
| `deck_editor.py` | Bảng chỉnh bài: dạng sóng, BPM, CUE, IN / OUT, LOOP, nghe trước |
| `beatscope.py` | Soi nhịp: phân tích nhạc cụ / phách / ô nhịp / đoạn / Drop + cửa sổ hiển thị |
| `soundcheck.py` | Trang Âm thanh: RTA, mức micro, phát hiện hú, ring-out, đo phòng, tone |
| `guide.py` / `longview.py` | Cửa sổ Hướng dẫn / màn hình Long View |
