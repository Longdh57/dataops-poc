# Kịch bản trình bày 5 phút

Mục tiêu của buổi demo không phải khoe màn hình, mà chứng minh **một con số
sai không ra khỏi được hệ thống**. Mọi thứ khác chỉ là bối cảnh cho điều đó.

Chuẩn bị trước: mở sẵn hai tab — ứng dụng và một cửa sổ terminal.

---

## 0:00 — Vấn đề (30 giây)

> "Dữ liệu thị trường gom từ nhiều nguồn, luôn có chỗ sai. Hiện tại việc
> soát và sửa làm bằng bảng tính và email: không biết ai sửa gì, và không
> có gì chặn một bản còn lỗi bị gửi cho khách."

Mở dashboard. Chỉ vào dải đỏ trên cùng.

> "Đây là cùng một vòng đời đó, nhưng ở một nơi. Cổng phát hành **đang
> khoá** vì còn 20 ngoại lệ nghiêm trọng. Chừng nào nó còn đỏ thì không ai
> ký được và không ai tải file được — kể cả khi gọi thẳng vào API."

---

## 0:30 — Dữ liệu thật, không phải dữ liệu mẫu (45 giây)

Sang tab *Dữ liệu*. Cuộn nhanh vài lần.

> "1,2 triệu dòng thật — tên khai sinh ở Mỹ do Cục An sinh Xã hội công bố.
> Lưới tải 500 dòng một lượt và tự nối tiếp khi cuộn, nên không có nút sang
> trang nào cả."

Chỉ vào banner độ tươi.

> "Dòng này nói bản sao được cập nhật cách đây bao lâu. Team Data ghi vào
> BigQuery theo lịch riêng của họ, không báo ai. Hệ thống tự phát hiện bằng
> metadata — truy vấn đó quét 0 byte nên chạy mỗi 60 giây cả ngày vẫn không
> tốn đồng nào."

---

## 1:15 — Một con số sai (90 giây)

Sang tab *Ngoại lệ*. Chọn một dòng `tang_dot_bien`.

> "Luật QC khai báo trong một file YAML, thêm luật mới không cần sửa code.
> Luật này bắt được những chỗ tăng hơn 10 lần so với năm trước."

Panel mở bên phải.

> "Bên trái là bản đã ký gần nhất, bên phải là lần nạp này. Người xử lý thấy
> ngay số nào đổi, không phải mở file khác để đối chiếu."

Gõ số mới và lý do. **Trước khi bấm Áp dụng**, chạy ở terminal:

```bash
docker exec dashboard-bigquery-db-1 psql -U dataops -d dataops -c \
  "UPDATE fact_override SET new_value='777', version=version+1 WHERE name='<tên>'"
```

> "Giả sử đúng lúc này, một đồng nghiệp vừa sửa cùng dòng đó."

Bấm *Áp dụng số mới*. Màn hình đỏ lên với ba con số.

> "Số của tôi **không** được ghi. Hệ thống đưa ra ba con số — số gốc, số
> trên máy chủ, số tôi định ghi — rồi để tôi quyết định. Đây là chỗ bảng
> tính luôn thua: hai người sửa cùng lúc thì một người mất việc mà không ai
> biết."

Bấm *Ghi đè có chủ đích*.

> "Ghi đè là một quyết định có chủ ý, và nó vào audit log kèm lý do."

---

## 2:45 — Mở cổng và ký (60 giây)

Xử lý nốt các ngoại lệ còn lại (chuẩn bị trước cho nhanh). Quay về dashboard.

> "Hết ngoại lệ nghiêm trọng, cổng chuyển xanh."

Sang tab *Phiên bản*, ký với nhãn có ý nghĩa.

> "Ký là đóng băng: bản này ghi lại đúng những lần nạp dữ liệu nào nằm trong
> nó. Dữ liệu team Data đẩy lên sau thời điểm này sẽ không lọt vào file gửi
> khách — cho tới khi có người ký bản mới."

---

## 3:45 — Sale lấy file (60 giây)

Đổi danh tính sang **Sale**.

> "Tài khoản này phạm vi California và Texas."

Sang tab *Yêu cầu dữ liệu*, chọn Excel, gửi yêu cầu.

> "Yêu cầu trả về ngay, file sinh ở một job chạy nền — không ai ngồi chờ
> một triệu dòng trong trình duyệt."

Khi xong, chỉ vào dòng trong bảng.

> "170 nghìn dòng, chỉ CA và TX. Không phải giao diện lọc hộ — máy chủ lọc,
> nên sửa tham số trên URL cũng không lấy thêm được bang nào. File xuất
> thẳng từ BigQuery rồi áp các ô đã sửa tay lên trên, và thị phần được tính
> lại cho nhóm bị sửa để khách cộng lại vẫn tròn 100%."

---

## 4:45 — Chốt (15 giây)

> "Toàn bộ hạ tầng là Terraform, dựng lại cho một dataset khác mất khoảng 15
> phút. Chi phí chạy khoảng 12–17 đô một tháng. Và điều quan trọng nhất vẫn
> là dải đỏ lúc đầu: số sai không đi ra ngoài được."

---

## Chuẩn bị trước buổi demo

```bash
# 1. Dữ liệu và người dùng
gcloud run jobs execute dataops-seed --region=asia-southeast1

# 2. Sinh lại ngoại lệ để cổng đang khoá lúc bắt đầu
gcloud run jobs execute dataops-qc --region=asia-southeast1 \
  --update-env-vars=FORCE_QC=1

# 3. Kiểm tra cổng đang khoá
curl -s https://dataops-dev.3ddesigns.xyz/api/gw/gate | python3 -m json.tool
```

Nếu cổng đang mở mà muốn khoá lại cho demo: mở lại vài ngoại lệ nghiêm trọng.

```sql
UPDATE qc_exception SET status='open', resolved_at=NULL, resolved_by=NULL
WHERE severity='critical' AND status <> 'open';
```

Hai chỗ dễ vấp khi demo:

- **Ký xong mới xin file.** Xin file khi chưa ký bản nào thì API trả 409 —
  đúng thiết kế, nhưng sẽ làm hỏng mạch kể chuyện.
- **Bản ký cũ không xuất được.** Bản ký từ trước khi hệ thống biết ghi lại
  danh sách lần nạp sẽ bị Export Job từ chối. Ký một bản mới trước buổi demo.
