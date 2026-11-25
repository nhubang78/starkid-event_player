"""Cửa sổ Hướng dẫn sử dụng: mục lục bên trái, nội dung bên phải, có ô tìm kiếm."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                               QPushButton, QTextBrowser, QVBoxLayout)

from theme import T


def K(*keys):
    """Hiển thị phím bấm dạng nút."""
    return "&nbsp;+&nbsp;".join(f"<span class='kbd'>&nbsp;{k}&nbsp;</span>" for k in keys)


def table(rows, head=("Thao tác", "Phím")):
    h = "".join(f"<th>{x}</th>" for x in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table cellspacing='0' cellpadding='7' width='100%'><tr>{h}</tr>{body}</table>"


def tip(text, kind="tip"):
    label = {"tip": "Mẹo", "warn": "Lưu ý", "pro": "Khi diễn"}[kind]
    return f"<table class='{kind}' width='100%' cellpadding='10'><tr><td><b>{label}:</b> {text}</td></tr></table>"


SECTIONS = [
    ("Bắt đầu nhanh", "Chuẩn bị một chương trình trong 1 phút", f"""
<p>Starkid Event Player là phần mềm phát nhạc cho sự kiện, sân khấu, lễ hội: <b>32 kênh phát nhanh</b>
(mỗi kênh một bài, bấm là phát) và một <b>trang Playlist</b> để phát danh sách dài.</p>
<ol>
<li><b>Chọn loa:</b> bấm <b>Tùy chọn</b>, chọn sound card cho các kênh, cho Playlist và tai nghe nghe thử.</li>
<li><b>Nạp nhạc:</b> kéo file nhạc từ Explorer thả vào một kênh (hoặc bấm vào nút lớn của kênh trống).</li>
<li><b>Đặt tên, màu:</b> bấm <b>•••</b> trên kênh &rarr; <i>Cài đặt kênh</i>, đặt tên dễ nhận ra và màu theo phần chương trình.</li>
<li><b>Chỉnh âm lượng:</b> kéo fader của từng kênh cho các bài đều nhau; âm lượng tổng chỉnh bằng fader <b>Master</b>.</li>
<li><b>Lưu dự án:</b> {K('Ctrl', 'S')} để lưu toàn bộ thành file <code>.evp</code>.</li>
<li><b>Khi diễn:</b> bấm {K('Space')} (GO) để phát lần lượt từng kênh, {K('Esc')} để dừng tất cả.
Bật <b>Khóa cài đặt</b> để không ai bấm nhầm.</li>
</ol>
{tip("Mở <b>Long View</b> ({0}) trên màn hình thứ hai để thấy rõ bài đang phát và thời gian còn lại.".format(K('F2')))}
"""),
    ("Màn hình chính", "Các vùng trên cửa sổ", f"""
<h3>Thanh công cụ</h3>
<ul>
<li><b>Audio 1-16 / Audio 17-32 / Playlist / Âm thanh</b>: chuyển trang ({K('Ctrl', '1')} … {K('Ctrl', '4')}).
Trang Âm thanh dùng để đo tần số, chỉnh micro và chống hú.</li>
<li><b>Dự án mới, Mở, Lưu</b>: quản lý file dự án <code>.evp</code>.</li>
<li><b>Tùy chọn, Phím tắt, Hướng dẫn</b>: cài đặt chung, bảng phím tắt và trang này ({K('F1')}).</li>
<li><b>Sáng / Tối</b>: đổi giao diện.</li>
<li><b>Phát đơn</b>: khi bật, phát một kênh thì các kênh khác tự nhỏ dần rồi dừng.</li>
<li><b>Long View</b>: màn hình lớn cho người điều khiển.</li>
<li><b>Dừng hết</b>: dừng mọi nguồn đang phát.</li>
<li><b>Khóa cài đặt</b>: khóa bàn phím và chuột để tránh bấm nhầm khi diễn.</li>
</ul>
<h3>Vùng kênh</h3>
<p>Mỗi trang có 16 kênh xếp 2 hàng. Từ trên xuống, mỗi kênh gồm: nút chọn file &#9834; và nút <b>•••</b>,
fader âm lượng, đèn mức (VU), mức âm lượng (% và dB), thời gian đã phát, thời gian còn lại,
<b>nút lớn</b> để phát, nút tạm dừng / dừng, thanh tua, và hàng biểu tượng nhỏ.</p>
<h3>Cột bên phải</h3>
<p>Nút <b>GO</b> (phát kênh kế tiếp theo thứ tự) và <b>Master</b> (âm lượng chính của sound card + đèn mức tổng).</p>
<h3>Thanh trạng thái</h3>
<p>Dưới cùng: thông báo, phiên bản và đồng hồ. Ngay dưới thanh công cụ là đường dẫn dự án đang mở
(có dấu <b>*</b> nếu còn thay đổi chưa lưu).</p>
"""),
    ("Nạp nhạc vào kênh", "Kéo thả, chọn file, định dạng hỗ trợ", f"""
<ul>
<li><b>Kéo thả:</b> kéo file từ Explorer thả lên bất kỳ chỗ nào của kênh.</li>
<li><b>Chọn file:</b> bấm nút lớn của kênh trống, nút &#9834;, hoặc <b>•••</b> &rarr; <i>Chọn file...</i></li>
<li><b>Thay bài:</b> nạp file khác vào kênh đã có nhạc; tên kênh đổi theo tên file.</li>
<li><b>Bỏ bài:</b> <b>•••</b> &rarr; <i>Bỏ file khỏi kênh</i>.</li>
</ul>
<p>Định dạng hỗ trợ: MP3, WAV, FLAC, M4A, AAC, OGG, OPUS, WMA, AIFF, MP2, AC3.</p>
{tip("Khi nạp nhạc vào kênh trống, kênh tự nhận <i>chế độ bấm</i> và <i>fade</i> mặc định "
     "(đặt bằng nút <b>*Đặt làm mặc định</b> trong Cài đặt kênh).")}
{tip("Dự án chỉ lưu <b>đường dẫn</b> tới file nhạc, không chép nhạc vào dự án. Đừng đổi tên, di chuyển "
     "hay xóa file nhạc sau khi đã nạp.", "warn")}
"""),
    ("Phát, tạm dừng, dừng", "Nút lớn, chế độ bấm, dừng có fade", f"""
<h3>Nút lớn của kênh</h3>
<p>Hiện số kênh, tên bài và phím tắt (góc trên trái). Màu nút cho biết trạng thái:</p>
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Màu</th><th>Ý nghĩa</th></tr>
<tr><td><span style='color:#16a34a'>&#9632;</span> <b>Xanh lá</b></td><td>Đang phát; thanh mảnh bên trong nút là tiến trình bài.</td></tr>
<tr><td><span style='color:#f59e0b'>&#9632;</span> <b>Vàng</b></td><td>Đang dừng lại: tạm dừng, hoặc đang nhỏ dần (fade out) để dừng.</td></tr>
<tr><td><b>Màu kênh</b></td><td>Đã có nhạc, đang chờ phát.</td></tr>
<tr><td><b>Viền nét đứt</b></td><td>Kênh trống.</td></tr>
</table>
<h3>Chế độ bấm (Cài đặt kênh)</h3>
<ul>
<li><b>Play / Stop</b> (mặc định): bấm lần 1 phát, lần 2 dừng (có fade out nếu đã đặt). Bấm thêm lần nữa khi
đang fade out = dừng ngay.</li>
<li><b>Play / Pause</b>: bấm để phát, bấm lại để tạm dừng, bấm nữa để phát tiếp.</li>
<li><b>Retrigger</b>: mỗi lần bấm phát lại từ đầu (hợp cho hiệu ứng, tiếng vỗ tay, chuông).</li>
</ul>
<h3>Các nút khác</h3>
<ul>
<li><b>‖</b>: tạm dừng / phát tiếp (có fade ngắn, chỉnh trong Tùy chọn).</li>
<li><b>Dừng</b>: dừng kênh, có fade out nếu kênh đã đặt.</li>
<li><b>Thanh tua</b>: bấm hoặc kéo để nhảy tới vị trí trong bài.</li>
<li><b>•••</b> &rarr; <i>Dừng ngay (bỏ fade)</i>: cắt tiếng lập tức.</li>
</ul>
"""),
    ("Âm lượng và đèn mức", "Fader kênh, Master, đọc đèn VU", f"""
<h3>Fader kênh</h3>
<p>Chỉnh to / nhỏ <b>riêng kênh đó</b>. Dưới fader hiện mức theo % và dB (80% &asymp; -3,2 dB).
Nháy đúp vào fader để đưa về 80%. Menu <i>Sửa &rarr; Đưa tất cả fader về 80%</i> để đặt lại tất cả.</p>
<h3>Master = âm lượng sound card</h3>
<p>Fader <b>Master</b> chính là thanh âm lượng của Windows cho sound card mà các kênh đang phát ra.
Kéo Master thì âm lượng Windows đổi theo, và ngược lại: chỉnh bằng phím âm lượng hay thanh âm lượng
của Windows thì fader Master tự chạy theo. Nếu Windows đang tắt tiếng, dưới Master hiện chữ <i>tắt tiếng</i>.</p>
<h3>Đèn mức (VU)</h3>
<ul>
<li><span style='color:#2fc25b'><b>Xanh</b></span>: mức bình thường (dưới -18 dB).</li>
<li><span style='color:#f5b81c'><b>Vàng</b></span>: mức to (-18 tới -6 dB).</li>
<li><span style='color:#ef4444'><b>Đỏ</b></span>: sát mức tối đa (trên -6 dB) &mdash; dễ méo tiếng.</li>
</ul>
<p>Vạch sáng đứng yên phía trên là <b>đỉnh</b> vừa đạt được, giữ lại một lúc cho dễ đọc.
Đèn kênh đo mức sau fader kênh; đèn Master đo tổng mọi nguồn đang phát.</p>
{tip("Giữ đèn Master phần lớn thời gian ở vùng xanh / vàng. Nếu thường xuyên chạm đỏ, hạ fader kênh "
     "thay vì hạ Master, để các bài vẫn cân nhau.")}
"""),
    ("Fade và lặp", "Nhỏ dần, to dần, lặp bài", f"""
<ul>
<li><b>Fade in</b> (biểu tượng &#9698;): bài to dần khi bắt đầu phát.</li>
<li><b>Fade out</b> (biểu tượng &#9699;): bài nhỏ dần khi bấm dừng, và tự nhỏ dần trước khi hết đoạn phát.</li>
<li>Bấm biểu tượng ở hàng dưới kênh: mỗi lần <b>+0,5 giây</b>, quá 3 giây thì về tắt.
Cần dài hơn (tới 60 giây) thì đặt trong <i>Cài đặt kênh</i>.</li>
<li><b>Lặp</b> (&#8635;): phát hết bài thì phát lại từ đầu đoạn phát, cho tới khi bấm dừng.</li>
</ul>
<p>Biểu tượng chuyển <b>màu xanh</b> khi tính năng đang bật; rê chuột lên biểu tượng để xem số giây.</p>
"""),
    ("Cài đặt kênh", "Tên, màu, ngõ ra, đoạn phát, phím riêng", f"""
<p>Mở bằng <b>•••</b> trên kênh hoặc chuột phải vào nút lớn &rarr; <i>Cài đặt kênh...</i></p>
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Mục</th><th>Công dụng</th></tr>
<tr><td><b>Tên</b></td><td>Tên hiện trên nút lớn và trên Long View.</td></tr>
<tr><td><b>Màu</b></td><td>Tô màu nút để phân nhóm (ví dụ: vàng = nhạc nền, đỏ = hiệu ứng).</td></tr>
<tr><td><b>Ngõ ra âm thanh</b></td><td>Cho kênh này phát ra sound card riêng; để mặc định thì theo Tùy chọn.</td></tr>
<tr><td><b>Chế độ bấm</b></td><td>Play / Stop, Play / Pause hoặc Retrigger.</td></tr>
<tr><td><b>Lặp, Fade-In, Fade-Out</b></td><td>Như mục <i>Fade và lặp</i>, đặt được tới 60 giây.</td></tr>
<tr><td><b>Đoạn phát</b></td><td>Chỉ phát một đoạn của bài (bỏ đoạn đầu dạo, cắt đuôi). Bấm <b>Sửa...</b> để chọn trên dạng sóng.</td></tr>
<tr><td><b>Phím phát</b></td><td>Gán phím riêng cho kênh, bấm được ở mọi trang. <i>Dùng phím ô</i> = theo phím của vị trí; Backspace = không phím.</td></tr>
</table>
<h3>Chọn đoạn phát trên dạng sóng</h3>
<ul>
<li>Bấm hoặc kéo trên sóng để dời mốc (bắt đầu / kết thúc) gần nhất.</li>
<li>Cuộn chuột để phóng to / thu nhỏ; Shift + cuộn để kéo ngang. <i>Soi điểm đầu / cuối</i> để xem kỹ chỗ cắt.</li>
<li>Gõ thời gian chính xác vào ô, hoặc dùng các nút tinh chỉnh &plusmn;10 ms, &plusmn;100 ms, &plusmn;1 s.</li>
<li><i>Nghe từ điểm đầu</i>, <i>Nghe 5 giây cuối</i>: nghe thử ra tai nghe trước khi lưu.</li>
</ul>
<h3>Các mục có dấu *</h3>
<p><b>*Đặt làm mặc định</b>: chế độ bấm và fade này được áp dụng mỗi khi nạp nhạc vào kênh trống.<br>
<b>*Áp dụng cho tất cả</b>: áp dụng ngay cho mọi kênh đã có nhạc và đang dừng.</p>
"""),
    ("Hàng biểu tượng dưới kênh", "Ý nghĩa từng biểu tượng", f"""
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Biểu tượng</th><th>Công dụng</th></tr>
<tr><td>&#9654;</td><td>Phát từ đầu đoạn phát (kể cả khi đang phát).</td></tr>
<tr><td>&#9632; / ‖</td><td>Trạng thái: dừng hoặc tạm dừng. Bấm để dừng kênh.</td></tr>
<tr><td>&#8635;</td><td>Bật / tắt lặp.</td></tr>
<tr><td>&#9698;</td><td>Fade in: mỗi lần bấm +0,5 giây, quá 3 giây về tắt.</td></tr>
<tr><td>&#9699;</td><td>Fade out: mỗi lần bấm +0,5 giây, quá 3 giây về tắt.</td></tr>
</table>
<p>Biểu tượng <b>xanh</b> = đang bật / đang hoạt động; <b>mờ</b> = tắt hoặc kênh chưa có nhạc.</p>
"""),
    ("GO và con trỏ GO", "Phát lần lượt theo kịch bản", f"""
<p>Nút <b>GO</b> phát lần lượt các kênh <b>có nhạc</b> theo số thứ tự, bỏ qua kênh trống. Chữ trên nút
(ví dụ <b>GO 3</b>) cho biết kênh sẽ phát ở lần bấm tới.</p>
<ul>
<li>Bấm <b>GO</b> hoặc {K('Space')}: phát kênh kế tiếp rồi con trỏ tự nhảy sang kênh sau.</li>
<li>{K('↑')} / {K('↓')}: lùi / tiến con trỏ GO mà không phát.</li>
<li>Chuột phải vào GO: chọn thẳng kênh sẽ phát tiếp theo.</li>
<li>Hết danh sách thì con trỏ quay về kênh đầu tiên.</li>
</ul>
{tip("Sắp xếp các bài vào kênh theo đúng trình tự chương trình (kênh 1, 2, 3...). Khi diễn chỉ cần "
     "nhìn Long View và bấm Space.", "pro")}
"""),
    ("Phát đơn", "Chỉ một nguồn phát tại một thời điểm", f"""
<p>Khi bật <b>Phát đơn</b>, phát một kênh (hoặc Playlist) thì mọi nguồn khác đang phát sẽ tự fade out rồi dừng.
Hợp với chương trình chuyển bài liên tục, không muốn hai bài chồng lên nhau.</p>
<ul>
<li>Thời gian fade khi chuyển chỉnh ở <i>Tùy chọn &rarr; Phát đơn — fade kênh cũ</i> (0 = dừng ngay).</li>
<li>Tắt Phát đơn để phát chồng: ví dụ nhạc nền chạy liên tục, thêm tiếng vỗ tay hay hiệu ứng lên trên.</li>
</ul>
"""),
    ("Playlist", "Phát danh sách dài, crossfade", f"""
<p>Trang Playlist dùng cho nhạc nền, nhạc đón khách, giờ nghỉ: phát danh sách dài theo thứ tự.</p>
<h3>Tạo danh sách</h3>
<ul>
<li><b>+ File</b>, <b>+ Thư mục</b>, hoặc kéo file / thư mục từ Explorer thả vào bảng.</li>
<li>Kéo bài lên xuống để đổi thứ tự; {K('Delete')} để xóa bài đã chọn.</li>
<li>Nhiều danh sách dạng tab: nút <b>+</b> để tạo, nháy đúp tên tab để đổi tên.</li>
<li><b>Nhập... / Xuất...</b>: mở / lưu danh sách (<code>.evpl</code> hoặc M3U).</li>
<li>Từ một kênh: <b>•••</b> &rarr; <i>Thêm vào playlist</i>.</li>
</ul>
<h3>Phát</h3>
<ul>
<li><b>PHÁT</b> (hoặc {K('Space')} khi đang ở trang Playlist): phát / tạm dừng. Nháy đúp một bài để phát ngay.</li>
<li><b>DỪNG</b>: dừng có fade out; bấm 2 lần = dừng ngay.</li>
<li>{K('Ctrl', '→')} / {K('Ctrl', '←')}: bài tiếp / bài trước.</li>
<li>{K('Ctrl', 'E')}: đặt bài đang chọn làm <b>bài kế tiếp</b>. {K('Ctrl', 'L')}: nghe thử bài đang chọn ra tai nghe.</li>
<li>Chuột phải vào bài: <i>Dừng sau bài này</i>, đánh dấu đã phát / chưa phát, mở thư mục chứa file.</li>
</ul>
<h3>Chế độ phát</h3>
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Chế độ</th><th>Hoạt động</th></tr>
<tr><td><b>Dừng sau mỗi bài</b></td><td>Hết bài thì dừng, chờ bấm phát bài tiếp (chế độ sự kiện).</td></tr>
<tr><td><b>Phát liên tục</b></td><td>Tự phát bài tiếp cho tới hết danh sách.</td></tr>
<tr><td><b>Lặp lại 1 bài</b></td><td>Phát đi phát lại bài hiện tại.</td></tr>
<tr><td><b>Lặp lại cả danh sách</b></td><td>Hết danh sách thì quay lại bài đầu.</td></tr>
</table>
<p><b>Crossfade</b>: số giây bài cũ nhỏ dần trong khi bài mới to dần (dùng cho Phát liên tục / Lặp danh sách).
Khi sắp hết bài, thời gian còn lại nhấp nháy đỏ (số giây cảnh báo chỉnh trong Tùy chọn).</p>
<p>Ký hiệu trong bảng: <span style='color:{T["ok"]}'>&#9654; đang phát</span>,
<span style='color:{T["warn"]}'>&#9197; kế tiếp đã chọn</span>, &#8250; bài tiếp theo, &#9209; dừng sau bài này,
<span style='color:{T["played"]}'>chữ mờ = đã phát</span>, <span style='color:{T["danger"]}'>chữ đỏ = mất file</span>.</p>
"""),
    ("Long View", "Màn hình lớn cho người điều khiển", f"""
<p>Bấm <b>Long View</b> hoặc {K('F2')} để mở cửa sổ chữ lớn, nên kéo sang màn hình thứ hai hoặc TV.
Nhấn {K('F11')} để bật / tắt toàn màn hình.</p>
<ul>
<li><b>ĐANG PHÁT</b>: bài vừa phát gần nhất, thời gian còn lại cỡ lớn và thanh tiến trình. Các nguồn khác
đang phát cùng lúc liệt kê bên dưới.</li>
<li><b>TIẾP THEO</b>: kênh mà nút GO sẽ phát, và bài kế tiếp của Playlist.</li>
<li>Thời gian còn lại <span style='color:{T["danger"]}'><b>nhấp nháy đỏ</b></span> khi sắp hết bài.</li>
<li>Hàng nút dưới cùng: <b>◀ Trước</b>, <b>GO</b>, <b>Sau ▶</b>, <b>Dừng hết</b> &mdash; điều khiển ngay trên Long View.
Phím {K('Space')}, {K('Esc')}, {K('↑')} {K('↓')} cũng dùng được khi đang ở cửa sổ này.</li>
<li><b>Lời nhắn</b>: gõ nội dung rồi Enter để hiện chữ thật to trên Long View (ví dụ "MC chuẩn bị lên",
"Còn 2 phút"). Bấm <b>Xóa</b> để tắt lời nhắn.</li>
</ul>
"""),
    ("Bảng chỉnh bài", "Dạng sóng, BPM, CUE, cắt IN / OUT, LOOP, nghe trước", f"""
<p>Bảng phía trên lưới kênh (trang Audio 1-16 / 17-32) hiện <b>kênh đang chọn</b> &mdash; kênh có viền xanh.
Bấm vào một kênh để chọn; kênh vừa phát cũng tự được chọn. Bấm <b>▾</b> ở góc trái để thu gọn bảng khi cần
nhiều chỗ cho các kênh.</p>
<h3>Dạng sóng</h3>
<ul>
<li>Phần đã phát tô màu (màu kênh, hoặc cam), phần chưa phát màu xám; vạch trắng là đầu phát.</li>
<li><b>Lăn chuột</b>: phóng to / thu nhỏ quanh con trỏ · <b>Shift + lăn</b>: kéo ngang · <b>Bấm</b>: tua tới đó
(khi đang dừng: đặt điểm sẽ phát) · <b>Kéo</b>: chọn một đoạn.</li>
<li>Rê chuột tới chỗ cần rồi bấm phím {K('I')} / {K('O')} để đặt IN / OUT; kéo tay cầm <b>IN</b> (xanh) /
<b>OUT</b> (đỏ) để tinh chỉnh. Chuột phải: menu nhanh (phát từ đây, nghe trước, đặt IN/OUT, CUE, A/B).</li>
<li><b>1 sóng / 2 sóng</b>: thêm dải tổng quan cả bài phía trên; bấm / kéo trên dải này để dời khung xem.</li>
</ul>
<h3>Thời gian và BPM</h3>
<p><b>ĐÃ CHẠY / CÒN LẠI / TỔNG</b> tính theo cả file. <b>BPM</b> được tự dò từ bài; kéo thanh trượt để chỉnh tay,
bấm <i>Dùng tự động</i> để quay lại BPM tự dò.</p>
<h3>Soi nhịp</h3>
<p>Nút <b>Soi nhịp</b> (góc phải trên sóng) mở cửa sổ phân tích chi tiết bài của kênh đang chọn:</p>
<ul>
<li><b>Nhạc cụ</b>: Kick, Snare, Clap, Hi-hat, Bass, Giọng hát &mdash; mỗi loại một dải màu bên dưới sóng, kèm số lần xuất hiện.
Bấm các nút màu để ẩn / hiện từng loại.</li>
<li><b>Phách, Ô nhịp</b> (đánh số 1, 2, 3...), <b>Đoạn</b> (INTRO / BUILD / DROP / BREAK / OUTRO) và
<b>◆ Điểm Drop</b> (tam giác đỏ).</li>
<li>Bấm sóng = tua · chuột phải kéo = chọn vùng (rồi <i>Loop vùng chọn</i>) · lăn chuột = phóng to ·
<b>bấm tam giác Drop = đặt IN ngay tại điểm Drop</b> · bấm một điểm nhạc cụ = tua tới đó và phát ·
bấm <b>Hot Cue</b> = nhảy tới và phát.</li>
<li>Các nút CUE / CẮT / LOOP giống bảng chỉnh bài; mọi thay đổi đồng bộ hai bên.</li>
</ul>
<p>Lần đầu soi một bài mất vài giây để phân tích; kết quả được lưu lại nên lần sau mở ngay.
Nhận diện dựa trên dải tần và nhịp gõ (không tách nhạc bằng AI): Kick, Snare, Hi-hat, phách, ô nhịp, điểm Drop
khá tin cậy với nhạc có trống; <b>Clap và Giọng hát chỉ là ước lượng</b>.</p>
<h3>Các nút</h3>
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Nhóm</th><th>Công dụng</th></tr>
<tr><td><b>⏮ ▶ ■</b></td><td>Về điểm IN · phát / tạm dừng (phát từ điểm đã bấm trên sóng) · dừng.</td></tr>
<tr><td><b>CUE</b></td><td><i>+ Cue</i> lưu vị trí hiện tại (tối đa 9). Bấm điểm CUE để nhảy tới; chuột phải để xóa.</td></tr>
<tr><td><b>CẮT</b></td><td><i>IN / OUT</i> đặt điểm bắt đầu / kết thúc phát tại vị trí hiện tại; <i>✕</i> bỏ cắt.
Đây chính là <i>Đoạn phát</i> trong Cài đặt kênh.</td></tr>
<tr><td><b>LOOP</b></td><td><i>A / B</i> đặt vùng lặp; <i>⟳</i> bật / tắt lặp; <i>1s 2s 4s 8s</i> lặp ngay từ vị trí hiện tại;
<i>Loop vùng chọn</i> lặp đoạn vừa kéo chọn; <i>✕</i> bỏ lặp. Vùng lặp tô tím trên sóng.</td></tr>
<tr><td><b>ZOOM</b></td><td><i>− / +</i> thu / phóng, <i>Toàn bài</i> xem cả bài. Khi đang phát, khung xem tự chạy theo đầu phát.</td></tr>
<tr><td><b>🎧 Nghe trước</b></td><td>Nghe từ vị trí hiện tại ra <b>tai nghe</b> (chọn trong Tùy chọn) mà không phát ra loa.</td></tr>
</table>
<p>CUE, vùng lặp và BPM chỉnh tay được lưu cùng dự án.</p>
{tip("Dùng loop 4s / 8s để kéo dài đoạn nhạc nền khi MC nói lâu hơn dự kiến; bấm ⟳ để tắt lặp, nhạc chạy tiếp tự nhiên.", "pro")}
"""),
    ("Âm thanh: đo tần số, micro, chống hú", "RTA, mức micro, phát hiện hú, ring-out, đo phòng, tone", f"""
<p>Trang <b>Âm thanh</b> ({K('Ctrl', '4')}) giúp chỉnh hệ thống loa / micro trước và trong sự kiện.
Máy tính <b>nghe</b> qua một nguồn vào để phân tích, rồi chỉ cho bạn cần chỉnh gì trên <b>mixer</b>;
phần mềm không tự lọc tiếng micro sân khấu (vì tiếng micro đi qua mixer, không qua máy tính).</p>
<h3>Nối dây</h3>
<ul>
<li><b>Micro đo</b> (micro đo chuyên dụng hoặc micro thường) cắm vào máy tính, đặt ở vị trí khán giả; hoặc</li>
<li>Cổng <b>line-in</b> của máy tính nhận tín hiệu từ ngõ ra phụ (AUX / REC OUT) của mixer.</li>
<li>Chọn nguồn đó ở ô <i>Nguồn vào</i> rồi bấm <b>▶ Bắt đầu đo</b>.</li>
</ul>
{tip("Tắt các hiệu ứng 'Khử tiếng ồn', 'Tăng âm micro' của Windows / Realtek cho micro đo "
     "(Cài đặt âm thanh &rarr; Thuộc tính thiết bị) để kết quả đo chính xác.", "warn")}
<h3>Biểu đồ tần số (RTA)</h3>
<p>Cột = mức của 31 dải 1/3 octave (20 Hz – 20 kHz, giống EQ 31 băng trên mixer); đường xanh = FFT chi tiết;
vạch ngang = đỉnh giữ lại. <i>Tốc độ</i> Nhanh để xem tức thời, Chậm để xem trung bình. Tam giác cam phía trên
là các tần số dễ hú đã tìm được bằng ring-out.</p>
<h3>Mức micro</h3>
<p>Đồng hồ ngang hiện RMS (thanh màu), đỉnh (vạch) và đỉnh giữ 3 giây. Cho người nói / hát ở <b>mức thật</b>,
rồi chỉnh gain trên mixer theo gợi ý:</p>
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Đỉnh 3 giây</th><th>Đánh giá</th></tr>
<tr><td>từ −1 dBFS trở lên</td><td><span style='color:{T["danger"]}'><b>Vỡ tiếng</b></span> — giảm gain ngay</td></tr>
<tr><td>−6 … −1 dBFS</td><td><span style='color:{T["warn"]}'><b>Hơi to</b></span> — giảm bớt để chừa khoảng an toàn</td></tr>
<tr><td>−24 … −6 dBFS</td><td><span style='color:{T["ok"]}'><b>Tốt</b></span></td></tr>
<tr><td>dưới −24 dBFS</td><td><span style='color:{T["warn"]}'><b>Nhỏ</b></span> — tăng gain</td></tr>
</table>
<h3>Chống hú (phát hiện hú)</h3>
<p>Phần mềm tìm tần số <b>nhọn, nổi hẳn so với xung quanh, đứng yên và kéo dài</b> — dấu hiệu của tiếng hú.
Khi phát hiện: ô báo chuyển đỏ <b>⚠ HÚ 2,51 kHz</b>, vạch đỏ trên biểu đồ, kèm gợi ý
(ví dụ <i>Cắt −9 dB, Q hẹp · EQ 31 băng: 2,5k</i>). Đang ở trang khác thì tab <b>Âm thanh</b> chuyển đỏ và thanh
trạng thái báo tần số.</p>
<ul>
<li><b>Xử lý nhanh khi đang diễn:</b> hạ fader micro 3–6 dB ngay, rồi cắt tần số được báo trên EQ của kênh micro hoặc EQ tổng.</li>
<li><b>Độ nhạy:</b> Cao = báo sớm (dễ báo nhầm khi nhạc có nốt ngân dài); Thấp = chỉ báo khi hú rõ.
Khi đang phát nhạc, nên để Vừa hoặc Thấp.</li>
</ul>
<h3>Ring-out (trước giờ diễn)</h3>
<ol>
<li>Phòng yên lặng, không phát nhạc. Đặt micro sân khấu đúng chỗ người dùng sẽ đứng.</li>
<li>Bấm <b>● Bắt đầu ring-out</b>, tăng từ từ fader micro trên mixer.</li>
<li>Mỗi lần bắt đầu hú, phần mềm kêu "bíp" và ghi tần số vào danh sách &rarr; cắt tần số đó trên EQ, rồi tăng tiếp.</li>
<li>Đạt mức to mong muốn thì hạ fader 3–6 dB để có khoảng an toàn. Danh sách được lưu lại; <i>Sao chép danh sách</i> để dán / in.</li>
</ol>
<h3>Đo phòng bằng pink noise</h3>
<p>Chọn <i>Loa phát thử / đo</i>, đặt micro đo ở chỗ khán giả, bấm <b>▶ Bắt đầu đo phòng</b>. Phần mềm đo tiếng ồn nền
2 giây, phát pink noise và đo trong số giây đã chọn, rồi vẽ độ lệch từng dải: <span style='color:{T["danger"]}'>đỏ = dư
(nên cắt)</span>, <span style='color:{T["accent"]}'>xanh dương = thiếu</span>, xám = quá gần tiếng ồn nên bỏ qua.
Ưu tiên <b>cắt</b> chỗ dư; chỗ thiếu chỉ tăng tối đa +3 dB.</p>
<h3>Phát tone thử loa</h3>
<p>Sóng sin (một tần số, có nút chọn nhanh 63 Hz … 16 kHz), quét tần số từ thấp lên cao (nghe tiếng rè / lạch cạch
của loa, đồ vật cộng hưởng), pink noise hoặc white noise. Luôn bắt đầu ở mức nhỏ; <b>Dừng hết</b> / {K('Esc')}
cũng tắt tone.</p>
{tip("Tone liên tục ở mức lớn, nhất là tần số cao, có thể làm hỏng loa treble (tweeter).", "warn")}
"""),
    ("Khóa cài đặt khi diễn", "Chống bấm nhầm", f"""
<p>Khi bật <b>Khóa cài đặt</b>, mọi bàn phím và chuột trên vùng kênh, Playlist, GO, Master đều bị chặn;
nhạc đang phát <b>vẫn tiếp tục</b>. Các nút trên Long View cũng bị khóa (riêng ô lời nhắn vẫn dùng được).</p>
<ul>
<li>Muốn mở khóa: bấm lại nút <b>Khóa cài đặt</b> (nút màu đỏ khi đang khóa).</li>
<li>Vẫn chuyển trang, mở Long View và đổi giao diện được khi đang khóa.</li>
</ul>
{tip("Khóa ngay sau khi chuẩn bị xong và trước giờ diễn, để không ai vô tình kéo fader hay bấm phím.", "pro")}
"""),
    ("Phím tắt", "Danh sách đầy đủ, cách đổi phím", f"""
<p>Đổi phím ở nút <b>Phím tắt</b>: bấm vào ô rồi bấm phím muốn gán; Backspace để bỏ gán.</p>
<h3>Phím chỉnh được (mặc định)</h3>
{table([("GO — phát kênh kế tiếp (ở trang Playlist: phát / tạm dừng)", K('Space')),
        ("Dừng tất cả (bấm 2 lần = dừng ngay)", K('Esc')),
        ("Lùi / tiến con trỏ GO", K('↑') + " / " + K('↓')),
        ("Bật / tắt Long View", K('F2')),
        ("Phát kênh 1–8 của trang đang xem", K('1') + " … " + K('8')),
        ("Phát kênh 9–16 của trang đang xem", " ".join(K(x) for x in "90QWERTY")),
        ("Dừng các kênh (Playlist vẫn phát)", "chưa gán")])}
<h3>Phím cố định</h3>
{table([("Hướng dẫn", K('F1')),
        ("Chuyển trang Audio 1-16 / 17-32 / Playlist / Âm thanh",
         K('Ctrl', '1') + " " + K('Ctrl', '2') + " " + K('Ctrl', '3') + " " + K('Ctrl', '4')),
        ("Dự án mới / Mở / Lưu / Lưu thành", K('Ctrl', 'N') + " " + K('Ctrl', 'O') + " " + K('Ctrl', 'S') + " " + K('Ctrl', 'Shift', 'S')),
        ("Playlist: bài tiếp / bài trước", K('Ctrl', '→') + " / " + K('Ctrl', '←')),
        ("Playlist: đặt bài kế tiếp / nghe thử", K('Ctrl', 'E') + " / " + K('Ctrl', 'L')),
        ("Dừng khẩn cấp mọi thứ, không fade", K('Ctrl', 'Shift', 'Esc'))])}
<p>Phím riêng của kênh (đặt trong Cài đặt kênh) được ưu tiên hơn phím ô của trang.
Khi đang ở trang Playlist, các phím mũi tên / Enter / Delete dành cho danh sách.</p>
"""),
    ("Dự án và mang sang máy khác", "Lưu, mở, tự lưu", f"""
<ul>
<li>Dự án <code>.evp</code> lưu toàn bộ: 32 kênh (file, tên, màu, âm lượng, fade, đoạn phát, phím),
các danh sách Playlist, chế độ Phát đơn và vị trí GO.</li>
<li>Mặc định lưu trong <i>Documents\\EventPlayer</i>. Tiêu đề cửa sổ có dấu <b>*</b> khi còn thay đổi chưa lưu.</li>
<li>Chương trình <b>tự nhớ</b> trạng thái khi tắt và mở lại y như cũ, kể cả khi chưa lưu dự án.</li>
</ul>
<h3>Mang sang máy khác</h3>
<ol>
<li>Chép thư mục chương trình <code>StarkidEventPlayer</code> (hoặc file zip) sang máy mới. Không cần cài Python.</li>
<li>Chép file dự án và <b>toàn bộ nhạc</b>; nên đặt nhạc ở cùng đường dẫn ổ đĩa như máy cũ.</li>
<li>Mở dự án; bài nào không tìm thấy file sẽ báo lỗi khi phát (trong Playlist hiện chữ đỏ) &mdash; nạp lại bài đó.</li>
</ol>
{tip("Không lưu dự án hay để nhạc bên trong thư mục chương trình: khi cập nhật phần mềm thư mục này "
     "có thể bị thay thế.", "warn")}
"""),
    ("Tùy chọn và giao diện", "Sound card, thời gian fade, Tối / Sáng", f"""
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Mục</th><th>Công dụng</th></tr>
<tr><td><b>Thiết bị ra của các kênh</b></td><td>Sound card cho 32 kênh. Fader Master điều khiển âm lượng sound card này.</td></tr>
<tr><td><b>Thiết bị ra của Playlist</b></td><td>Có thể khác sound card của kênh (ví dụ nhạc nền ra loa sảnh).</td></tr>
<tr><td><b>Tai nghe nghe thử</b></td><td>Thiết bị để nghe thử bài trước khi phát ra loa.</td></tr>
<tr><td><b>Phát đơn — fade kênh cũ</b></td><td>Thời gian nhỏ dần của kênh cũ khi Phát đơn đang bật.</td></tr>
<tr><td><b>Playlist — fade in / fade out</b></td><td>Fade đầu bài và fade khi bấm dừng Playlist.</td></tr>
<tr><td><b>Fade khi tạm dừng</b></td><td>Fade ngắn khi tạm dừng / phát tiếp, tránh tiếng "bụp".</td></tr>
<tr><td><b>Cảnh báo sắp hết bài</b></td><td>Số giây cuối bài mà thời gian còn lại nhấp nháy đỏ.</td></tr>
</table>
<p><b>Giao diện:</b> nút <b>Sáng / Tối</b> trên thanh công cụ, hoặc menu <i>Hiển thị &rarr; Giao diện</i>.
Giao diện tối dịu mắt hơn khi điều khiển trong hội trường tối.</p>
"""),
    ("Xử lý sự cố", "Các lỗi thường gặp", f"""
<table cellspacing='0' cellpadding='7' width='100%'>
<tr><th>Hiện tượng</th><th>Cách xử lý</th></tr>
<tr><td>Bấm kênh không có tiếng</td><td>Kiểm tra fader kênh và Master (Master = âm lượng Windows, có thể đang tắt tiếng);
kiểm tra <i>Tùy chọn</i> đã chọn đúng sound card; xem đèn VU kênh có nhảy không.</td></tr>
<tr><td>Báo "không tìm thấy file"</td><td>File nhạc đã bị đổi tên, di chuyển hoặc ổ USB chưa cắm. Nạp lại file cho kênh.</td></tr>
<tr><td>Phím tắt không ăn</td><td>Đang bật <b>Khóa cài đặt</b>; hoặc đang gõ trong ô nhập; hoặc phím đã gán cho kênh khác (xem bảng Phím tắt).</td></tr>
<tr><td>Fader Master bị mờ</td><td>Không đọc được âm lượng của sound card (thiết bị bị rút ra). Cắm lại hoặc chọn lại thiết bị trong Tùy chọn.</td></tr>
<tr><td>Rút / cắm sound card khi đang chạy</td><td>Chương trình tự nhận lại thiết bị; nếu vẫn im, mở Tùy chọn và bấm OK.</td></tr>
<tr><td>Cần dừng mọi thứ ngay</td><td>{K('Ctrl', 'Shift', 'Esc')} hoặc bấm <b>Dừng hết</b> hai lần.</td></tr>
</table>
"""),
]


def _css():
    return f"""
body {{ color:{T['text']}; font-family:'Segoe UI'; font-size:10.5pt; }}
h1 {{ color:{T['accent_text']}; font-size:19pt; font-weight:700; margin:0 0 2px 0; }}
h3 {{ color:{T['text']}; font-size:11.5pt; font-weight:700; margin:16px 0 4px 0; }}
p.sub {{ color:{T['text_dim']}; font-size:10pt; margin:0 0 14px 0; }}
p {{ margin:6px 0 8px 0; line-height:150%; }}
li {{ margin:3px 0 3px 0; line-height:150%; }}
code {{ font-family:Consolas; color:{T['accent_text']}; }}
.kbd {{ font-family:Consolas; font-size:9.5pt; background-color:{T['surface2']}; color:{T['text']};
        border:1px solid {T['border_strong']}; }}
table {{ border-collapse:collapse; margin:8px 0 10px 0; }}
th {{ background-color:{T['surface2']}; color:{T['text_dim']}; text-align:left; font-weight:600;
      border-bottom:1px solid {T['border_strong']}; }}
td {{ border-bottom:1px solid {T['border']}; vertical-align:top; }}
table.tip td {{ background-color:{T['accent_soft']}; border:none; }}
table.warn td {{ background-color:{T['warn_soft']}; border:none; }}
table.pro td {{ background-color:{T['ok_soft']}; border:none; }}
"""


class GuideDialog(QDialog):
    def __init__(self, parent, app_name, version, start=0):
        super().__init__(parent)
        self.setWindowTitle(f"Hướng dẫn sử dụng — {app_name}")
        self.resize(1080, 720)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 16, 20, 16)
        v.setSpacing(12)
        head = QHBoxLayout()
        t = QLabel("Hướng dẫn sử dụng")
        t.setObjectName("title")
        head.addWidget(t)
        ver = QLabel(f"{app_name} · phiên bản {version}")
        ver.setObjectName("note")
        head.addWidget(ver)
        head.addStretch()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Tìm trong hướng dẫn...")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(260)
        self.search.textChanged.connect(self.filter)
        head.addWidget(self.search)
        v.addLayout(head)

        body = QHBoxLayout()
        body.setSpacing(14)
        self.nav = QListWidget()
        self.nav.setObjectName("guideNav")
        self.nav.setFixedWidth(270)
        for i, (name, _sub, _html) in enumerate(SECTIONS):
            it = QListWidgetItem(f"{i + 1:>2}.  {name}")
            it.setData(Qt.ItemDataRole.UserRole, i)
            self.nav.addItem(it)
        self.nav.currentItemChanged.connect(self.show_item)
        body.addWidget(self.nav)
        self.view = QTextBrowser()
        self.view.setObjectName("guideView")
        self.view.setOpenExternalLinks(True)
        self.view.document().setDocumentMargin(22)
        body.addWidget(self.view, 1)
        v.addLayout(body, 1)

        foot = QHBoxLayout()
        self.lbl_pos = QLabel()
        self.lbl_pos.setObjectName("note")
        foot.addWidget(self.lbl_pos)
        foot.addStretch()
        self.b_prev = QPushButton("◀  Mục trước")
        self.b_next = QPushButton("Mục sau  ▶")
        close = QPushButton("Đóng")
        close.setObjectName("save")
        for b in (self.b_prev, self.b_next, close):
            b.setAutoDefault(False)
            foot.addWidget(b)
        self.b_prev.clicked.connect(lambda: self.step(-1))
        self.b_next.clicked.connect(lambda: self.step(1))
        close.clicked.connect(self.accept)
        v.addLayout(foot)
        self.nav.setCurrentRow(start)

    def show_item(self, item, _prev=None):
        if item is None:
            return
        i = item.data(Qt.ItemDataRole.UserRole)
        name, sub, html = SECTIONS[i]
        self.view.document().setDefaultStyleSheet(_css())
        self.view.setHtml(f"<h1>{name}</h1><p class='sub'>{sub}</p>{html}")
        self.lbl_pos.setText(f"Mục {i + 1} / {len(SECTIONS)}")
        self.b_prev.setEnabled(i > 0)
        self.b_next.setEnabled(i < len(SECTIONS) - 1)
        q = self.search.text().strip()
        if q:
            self.view.find(q)

    def step(self, d):
        rows = [r for r in range(self.nav.count()) if not self.nav.item(r).isHidden()]
        cur = self.nav.currentRow()
        if cur in rows:
            k = rows.index(cur) + d
            if 0 <= k < len(rows):
                self.nav.setCurrentRow(rows[k])

    def filter(self, text):
        q = text.strip().lower()
        first = None
        for r in range(self.nav.count()):
            name, sub, html = SECTIONS[r]
            hit = not q or q in (name + " " + sub + " " + html).lower()
            self.nav.item(r).setHidden(not hit)
            if hit and first is None:
                first = r
        if first is not None and (self.nav.currentItem() is None or self.nav.currentItem().isHidden()):
            self.nav.setCurrentRow(first)
        elif self.nav.currentItem() is not None:
            self.show_item(self.nav.currentItem())
