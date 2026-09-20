# Quy trình chất lượng dữ liệu

Tài liệu thiết kế, không phải mô tả code hiện tại: nó nói dữ liệu đi từ team
Data tới tay khách qua những cửa nào và ai ký tên vào đâu. Phần code còn lệch
nằm ở mục cuối, [Khoảng cách với code hiện tại](#khoảng-cách-với-code-hiện-tại).

Mục tiêu, nhắc lại cho rõ: **sale bán được dữ liệu, dữ liệu đó chính xác, và
mỗi bản gửi đi đều có đúng một người đứng tên.**

---

## Ba nguyên tắc

**1. Chỉ nguồn được sửa.** Dashboard không sửa số, dù chỉ một ô. Số sai thì
BigQuery phải đổi. Sửa ở dashboard tạo ra nguồn sự thật thứ hai, và bản sao
`fact_current` bị thay nguyên khối mỗi lần sync nên bản sửa đó không có chỗ bám.

**2. QC là máy dò, không phải người gác cổng.** Nó chỉ biết những gì đã được
viết thành luật trong `rules/rules.yaml`. Nó bỏ sót được — 10 trẻ nhập thành 20
thì không luật nào bắt — và nó báo nhầm được — số thật nhưng trông lạ. Vì vậy
quyết định cuối cùng thuộc về team lead, không thuộc về QC.

**3. Không có bản sạch và bản bẩn, chỉ có bản ghi rõ mình nợ gì.** Chờ dữ liệu
hoàn hảo rồi mới bán là không bán được. Ký kèm nợ thì được, miễn là món nợ được
ghi ra và có người đứng tên.

## Bốn vai

| Vai | Làm gì | Không được làm |
|---|---|---|
| Team Data | sửa số trên BigQuery, nạp lần nạp mới | — |
| QC Runner | quét luật sau mỗi lần nạp, kiểm lại ticket đang mở | quyết định cho qua hay không |
| Team Lead | đọc danh sách vi phạm, duyệt, ký tên | sửa số |
| Sale | xuất file theo bản đã ký, gửi khách | ký, sửa số |

---

## Luồng chính

```
Team Data sửa/nạp trên BigQuery
        │
        ▼
Sync Job ──── nguồn không đổi ────▶ dừng, không tốn gì
        │ nguồn đổi → lần nạp mới
        ▼
QC Runner ─── quét toàn bộ luật + kiểm lại ticket đang mở
        │
        ▼
Bảng vi phạm   (rule A: 3 ô · rule B: 405 ô · ticket #123, #140 chưa đóng)
        │
        ▼
Team Lead đọc → duyệt → PHIẾU DUYỆT (ghi tên, ghi nợ)
        │
        ▼
Ký bản   (signed_version + phiếu duyệt + vân tay vi phạm + version luật)
        │
        ▼
Sale export theo bản ký → file mang dấu "ký kèm nợ A, B / ticket #123, #140"
```

Mỗi lần nguồn đổi là một vòng mới, **độc lập hoàn toàn với vòng trước**: QC quét
lại từ đầu, team lead duyệt lại từ đầu. Không trạng thái nào của lần duyệt trước
được mang sang. Đổi lại, phiếu duyệt cũ nằm nguyên trong bản ký cũ.

---

## Hai đường vào của lỗi

QC không phải nguồn duy nhất phát hiện lỗi, và đây là chỗ quy trình cũ hụt.

| | Lỗi do QC bắt | Lỗi do người phát hiện |
|---|---|---|
| Ví dụ | tổng thị phần lệch 100%, tăng hơn 10 lần | nhập 10 trẻ thành 20 — số hợp lệ, không luật nào bắt |
| Ai tạo | QC Runner, tự động mỗi lần nạp | analyst, team lead, hoặc chính khách phản hồi |
| Sống ở đâu | bảng vi phạm của lần nạp hiện tại | **ticket**, sống xuyên qua nhiều lần nạp |
| Khi nào hết | lần nạp sau không còn sinh ra | ticket được xác minh là đã sửa |

Hai đường gặp nhau ở đúng một chỗ: **bảng tổng hợp team lead đọc trước khi ký**.
Cả vi phạm luật lẫn ticket chưa đóng đều nằm trên đó.

---

## Ticket

Ticket là đơn vị chịu trách nhiệm giữa hai đội, và là thứ QC không tự sinh ra được.

**Mỗi ticket bắt buộc có điều kiện nghiệm thu kiểm được bằng máy** — không phải
mô tả bằng lời, mà là mệnh đề QC chạy được:

```
ticket #123
  khóa       : (2024, TX, F, Emma)
  hiện tại   : number = 20
  kỳ vọng    : number = 10
  bằng chứng : <link / ảnh / ghi chú>
  chặn ký    : có
```

Không có mệnh đề này thì "team Data sửa xong rồi" chỉ là lời hứa, và "QC kiểm
lại ở lần chạy kế tiếp" không thực hiện được.

**Ai đóng ticket: máy, không phải người.** Team Data sửa xong thì đánh dấu *đã
sửa* → ticket chuyển `chờ xác minh` → QC ở lần nạp kế tiếp so số thực tế với kỳ
vọng → khớp thì ticket tự đóng, lệch thì bật lại kèm số thực tế đọc được.

**Chặn ký hay không phải quyết ngay lúc tạo ticket.** Không phân loại thì hoặc
là bán ra dữ liệu có lỗi đã biết, hoặc là tắc vĩnh viễn vì một ticket nhỏ.

**Mỗi ticket loại "QC không bắt được" nên đẻ ra một luật mới** trong
`rules/rules.yaml`. Nó là bằng chứng bộ luật có vùng mù; không vá thì dataset
sau dính lại đúng chỗ đó.

---

## Phiếu duyệt

Thay cho `apply` / `park` / `send_back` hiện tại. Team lead không xử lý từng
ngoại lệ một; team lead **duyệt cả lần nạp, một lần, có ghi chép**:

> Bản *"SSA 2024 — đợt 3"*, ký bởi `lead@cty.com` lúc 21/09/2026 14:30.
> Duyệt cho qua dù còn vi phạm: `duoi_nguong_kiem_duyet` (3 ô),
> `bien_dong_bat_thuong` (405 ô).
> Ticket chưa đóng: #123, #140.
> Lý do: "3 ô dưới ngưỡng là số thật của bang nhỏ, đã đối chiếu SSA.
> #123 không ảnh hưởng bang đang bán."

Phiếu duyệt gắn vào **bản ký**, không gắn vào từng ô. Nhờ vậy các bản ký độc lập
với nhau: không có trạng thái "đã bỏ qua" nào âm thầm mang sang lần sau rồi nuốt
mất một lỗi mới xuất hiện ở đúng ô đó.

**Team lead duyệt được mọi thứ, kể cả `critical`.** QC không có quyền phủ quyết
người chịu trách nhiệm. Cái giá là tên của họ nằm trên phiếu.

---

## Bản ký ghi gì

Tên luật thôi thì rỗng: hôm nay `duoi_nguong_kiem_duyet` là 3 ô, tháng sau là
3.000 ô, vẫn cùng một chữ. Bản ký phải ghi đủ bốn thứ:

| Ghi gì | Vì sao |
|---|---|
| Số lượng vi phạm theo từng luật | phân biệt 3 ô với 3.000 ô |
| Vân tay tập vi phạm (hash các khóa tự nhiên) | phát hiện nguồn bị sửa tại chỗ dưới cùng một `run_id` |
| Version của `rules.yaml` | tái hiện được team lead đã duyệt dưới bộ luật nào |
| Danh sách ticket chưa đóng | biết bản này nợ gì |

Dòng thứ hai quan trọng hơn vẻ ngoài. `run_id` do team Data đặt, và họ sửa số
tại chỗ dưới cùng một `run_id` được — khi đó bản đã bán cho khách và dữ liệu
hiện tại khác nhau nhưng mang cùng một nhãn. Chỉ vân tay mới phát hiện được.

Và để team lead không bấm duyệt mù trên danh sách 5.000 dòng, màn hình duyệt
phải nói rõ **cái gì mới so với bản ký trước**. Đây không phải trạng thái lưu
qua các lần nạp — nó là phép so hai bản ký, tính lúc hiển thị.

---

## File gửi khách

File export mang theo dấu của bản ký: ký kèm vi phạm gì, ticket nào chưa đóng.
Hai bản ký cùng định dạng mà chất lượng khác hẳn thì sale phải biết mình đang
cầm bản sạch hay bản có nợ.

Chuỗi truy trách nhiệm, từ file ngược về người:

```
versions_sent            ai nhận, ngày nào
  └─ signed_version      nhãn, người ký, phiếu duyệt, vân tay, version luật
       └─ source_run_ids lần nạp nào của team Data
            └─ vi phạm & ticket tại thời điểm ký
                 └─ audit_log  ai duyệt, lý do gì
```

---

## Những gì bị bỏ đi

**`apply` và bảng `fact_override` biến mất.** Đây là hệ quả của nguyên tắc 1, và
nó xoá luôn một lớp vấn đề:

- số trong file bán ra không còn khác số trong BigQuery;
- không còn override sống vĩnh viễn, âm thầm đè lên số mà team Data đã sửa đúng
  ở lần nạp sau;
- luật QC không cần biết tới override;
- cột `da_sua` trong file export không còn lý do tồn tại.

**`park` và `send_back` cũng biến mất**, thay bằng phiếu duyệt (cho qua) và
ticket (trả về nguồn). Cả hai trạng thái cũ có chung một khuyết điểm: chúng đóng
ngoại lệ và mở cổng phát hành trong khi dữ liệu vẫn sai.

---

## Khoảng cách với code hiện tại

Code **chưa** đổi theo tài liệu này. Bảng dưới là phần lệch, xếp theo mức nguy hiểm.

| # | Hiện tại | Mục tiêu | Ở đâu |
|---|---|---|---|
| 1 | `fact_override` không gắn `run_id` và không hết hạn — team Data sửa đúng ở nguồn thì override cũ vẫn đè lên, file bán ra sai mà không ai biết | bỏ hẳn override | [models.py:56](../apps/api/app/models.py:56), [export/main.py:112](../jobs/export/main.py:112) |
| 2 | `signed_version.checksum` có cột nhưng **chưa bao giờ được ghi** | vân tay + số lượng vi phạm + version luật | [models.py:147](../apps/api/app/models.py:147) |
| 3 | Không có khái niệm ticket; `send_back` chỉ đổi status và ghi audit, **không gửi đi đâu cả** | ticket có điều kiện nghiệm thu, QC kiểm lại mỗi lần nạp | [main.py:361](../apps/api/app/main.py:361) |
| 4 | `park` / `send_back` làm giảm bộ đếm cổng → mở cổng dù dữ liệu vẫn sai | phiếu duyệt có tên người | [main.py:384](../apps/api/app/main.py:384) |
| 5 | Ký bị chặn cứng 409 khi còn `critical` | cho ký, bắt buộc kèm phiếu duyệt | [main.py:384](../apps/api/app/main.py:384) |
| 6 | `/api/exceptions` lọc theo `status`, không theo `run_id` → hộp thư trộn lẫn nhiều lần nạp | bảng vi phạm của đúng lần nạp hiện tại | [main.py:249](../apps/api/app/main.py:249) |
| 7 | Luật QC query thẳng `fact_current`, không biết tới override → lỗi đã "sửa" lặp lại mỗi lần nạp | hết vấn đề sau khi bỏ override | [rules.yaml](../rules/rules.yaml) |

Thứ tự đề xuất: **1 → 2 → 3 → 4, 5 → 6 → 7**. Mục 1 là mục duy nhất có thể khiến
sale bán ra số sai mà không ai phát hiện được.
