# Kịch bản trình bày 5 phút

Mục tiêu của buổi demo không phải khoe màn hình, mà chứng minh **một con số
sai không ra khỏi được hệ thống**. Mọi thứ khác chỉ là bối cảnh cho điều đó.

Chuẩn bị trước: mở sẵn hai tab — ứng dụng và một cửa sổ terminal.

---

## 0:00 — Vấn đề (30 giây)

> "Dữ liệu thị trường gom từ nhiều nguồn, luôn có chỗ sai. Hiện tại việc
> soát và sửa làm bằng bảng tính và email: không biết ai sửa gì, và không
> có gì chặn một bản còn lỗi bị gửi cho khách."

Mở dashboard. Chỉ vào dải trạng thái trên cùng.

> "Đây là cùng một vòng đời đó, nhưng ở một nơi. Dải này nói bản hiện tại
> **còn nợ những gì**: bao nhiêu chỗ máy nghi ngờ, bao nhiêu lỗi đã xác
> nhận đang chờ nguồn sửa. Và có một loại nợ mà không ai duyệt cho qua được
> — kể cả khi gọi thẳng vào API."

---

## 0:30 — Dữ liệu thật, không phải dữ liệu mẫu (45 giây)

Sang tab *Dữ liệu*. Cuộn nhanh vài lần.

> "Hơn 31 nghìn dòng thật — deposit của từng ngân hàng theo bang, 5 năm gần
> nhất, do FDIC công bố (Summary of Deposits). Lưới tải 500 dòng một lượt
> và tự nối tiếp khi cuộn, nên không có nút sang trang nào cả."

Chỉ vào banner độ tươi.

> "Dòng này nói bản sao được cập nhật cách đây bao lâu. Team Data ghi vào
> BigQuery theo lịch riêng của họ, không báo ai. Hệ thống tự phát hiện bằng
> metadata — truy vấn đó quét 0 byte nên chạy mỗi 60 giây cả ngày vẫn không
> tốn đồng nào."

---

## 1:15 — Một con số sai (90 giây)

Sang tab *Vi phạm*. Chọn một dòng `deposit_spike`.

> "Luật QC khai báo trong một file YAML, thêm luật mới không cần sửa code.
> Luật này bắt được những chỗ deposit tăng hơn 15 lần so với năm trước."

Panel mở bên phải.

> "Bên trái là bản đã ký gần nhất, bên phải là lần nạp này. Người xử lý thấy
> ngay số nào đổi, không phải mở file khác để đối chiếu."

Chỉ vào chỗ **không có** ô nhập số.

> "Đây là quyết định quan trọng nhất của cả hệ thống: ứng dụng này **không
> sửa số**. Sửa ở đây thì file bán ra và BigQuery lệch nhau, và không ai
> phát hiện. Số sai thì nguồn phải đổi."

Điền *Số đúng phải là*, tiêu đề, rồi bấm *Mở ticket*.

> "Con số vừa gõ không phải để hiển thị — nó là **điều kiện nghiệm thu**.
> QC sẽ đọc số thật ở lần nạp kế tiếp và đối chiếu với đúng con số này."

Sang tab *Ticket*. Chỉ vào ticket vừa tạo, đang chặn.

> "Không có nút Đóng ở đây. Team Data sửa xong thì bấm *Đã sửa nguồn* —
> ticket chuyển sang **chờ QC xác minh**, chứ không đóng. Đóng là việc của
> máy: lần nạp sau đọc đúng số thì nó tự đóng, lệch thì nó bật lại kèm số
> đọc được."

Bấm *Đã sửa nguồn* với một lý do. Chạy ở terminal:

```bash
gcloud run jobs execute dataops-qc --region=asia-southeast1 \
  --update-env-vars=FORCE_QC=1
```

Tải lại trang.

> "Nguồn chưa sửa thật, nên QC bật ticket về lại — và ghi rõ nó đọc được số
> bao nhiêu. Đây là chỗ mọi quy trình bằng email thua: 'đã sửa rồi' là lời
> hứa, còn cái này là bằng chứng."

---

## 2:45 — Ký kèm phiếu duyệt (60 giây)

Sang tab *Ticket*, gỡ chặn ticket vừa rồi với lý do. Sang tab *Phiên bản*.

> "Còn hàng trăm chỗ vi phạm luật, và cổng vẫn cho ký. Vì vi phạm chỉ là
> **nghi ngờ của máy** — phần lớn là deposit thật của tổ chức nhỏ. Máy
> không có quyền phủ quyết người chịu trách nhiệm."

Chỉ vào ô phiếu duyệt.

> "Đổi lại, muốn ký thì phải viết ra vì sao. Câu này đi theo bản ký vĩnh
> viễn và in luôn vào file gửi khách."

Ký với nhãn có ý nghĩa. Chỉ vào cột *Nợ lúc ký* của dòng vừa xuất hiện.

> "Bản ký ghi lại bốn thứ: những lần nạp nào nằm trong nó, còn vi phạm gì và
> bao nhiêu ô, ticket nào chưa đóng, và một vân tay của dữ liệu. Vân tay là
> để bắt trường hợp team Data sửa số **tại chỗ** dưới cùng một nhãn — lúc đó
> nhãn vẫn thế mà số đã khác."

---

## 3:45 — Sale lấy file (60 giây)

Đổi danh tính sang **Sale**.

> "Tài khoản này phạm vi California và Texas."

Sang tab *Yêu cầu dữ liệu*, chọn Excel, gửi yêu cầu.

> "Yêu cầu trả về ngay, file sinh ở một job chạy nền — không ai ngồi chờ
> một triệu dòng trong trình duyệt."

Khi xong, chỉ vào dòng trong bảng.

> "Chỉ CA và TX. Không phải giao diện lọc hộ — máy chủ lọc, nên sửa tham số
> trên URL cũng không lấy thêm được bang nào. Số trong file là số của
> BigQuery, không qua tay ai."

Mở file `.ban-ky.txt` đi kèm.

> "Và file không đi một mình. Đây là dấu bản ký: ký lúc nào, ai ký, còn vi
> phạm gì, ticket nào chưa đóng, kèm nguyên văn phiếu duyệt. Sale biết mình
> đang cầm bản sạch hay bản có nợ — trước đây hai thứ đó trông y hệt nhau."

---

## 4:45 — Chốt (15 giây)

> "Toàn bộ hạ tầng là Terraform, dựng lại cho một dataset khác mất khoảng 15
> phút. Chi phí chạy khoảng 12–17 đô một tháng. Và điều quan trọng nhất vẫn
> là chỗ không có ô nhập số: hệ thống không giấu lỗi đi bằng cách sửa đè lên
> nó. Lỗi hoặc được sửa ở nguồn, hoặc được ghi ra kèm tên người cho qua."

---

## Chuẩn bị trước buổi demo

```bash
# 1. Dữ liệu và người dùng
gcloud run jobs execute dataops-seed --region=asia-southeast1

# 2. Sinh lại vi phạm cho lần nạp hiện tại
gcloud run jobs execute dataops-qc --region=asia-southeast1 \
  --update-env-vars=FORCE_QC=1

# 3. Xem hệ thống đang nợ gì
curl -s https://dataops-dev.3ddesigns.xyz/api/gw/gate | python3 -m json.tool
```

Dọn ticket của buổi demo trước:

```sql
DELETE FROM ticket WHERE created_by LIKE '%dataops.test';
```

Ba chỗ dễ vấp khi demo:

- **QC phải chạy sau lần nạp cuối.** `qc_stale` bật là không ký được — đúng
  thiết kế, nhưng sẽ làm hỏng mạch kể chuyện. Bước 2 ở trên lo việc đó.
- **Ký xong mới xin file.** Xin file khi chưa ký bản nào thì API trả 409.
- **Bản ký cũ không xuất được.** Bản ký từ trước khi hệ thống biết ghi lại
  danh sách lần nạp sẽ bị Export Job từ chối. Ký một bản mới trước buổi demo.
