// Tu dien tieng Viet — ban goc. Khoa khai bao o day la khoa duy nhat cua
// ca ung dung: en.ts phai phu kin dung tap khoa nay, thieu mot cai la
// TypeScript bao loi ngay luc build chu khong doi tui nguoi dung phat hien.
//
// Quy uoc trong chuoi:
//   {ten}     — cho thay the, dien bang t() hoac tn()
//   mot||nhieu — chon theo so luong, doc tu vals.count (hoac vals.n neu no
//                la so). Tieng Viet khong chia so nhieu nen hau het khong
//                dung; tieng Anh thi co.

export const vi = {
  // ------------------------------------------------------------- chung
  "common.all": "tất cả",
  "common.data": "dữ liệu",
  "common.loading": "Đang tải {what}…",
  "common.loadingShort": "Đang tải…",
  "common.cancel": "Thôi",
  "common.confirm": "Xác nhận",
  "common.sending": "Đang gửi…",
  "common.none": "—",
  "common.close": "Đóng",

  "meta.title": "Data Operations WebApp",
  "meta.description": "Nơi xem số, sửa sổ và chặn số sai đi ra ngoài",

  "ago.seconds": "{n} giây",
  "ago.minutes": "{n} phút",
  "ago.hours": "{n} giờ",
  "ago.days": "{n} ngày",

  "lang.label": "Ngôn ngữ",
  "lang.switchTo": "Chuyển sang {name}",

  // ---------------------------------------------------------- thanh tab
  "nav.dashboard": "Dashboard",
  "nav.data": "Dữ liệu",
  "nav.exceptions": "Vi phạm",
  "nav.tickets": "Ticket",
  "nav.versions": "Phiên bản",
  "nav.requests": "Yêu cầu dữ liệu",
  "nav.agent": "AI Agent",
  "shell.brand": "Data Operations",
  "shell.badgeBlocking": "{n} ticket đang chặn phát hành",
  "shell.badgeGateLocked": "cổng phát hành đang khoá",

  // ----------------------------------------------------------- thanh loc
  "filter.year": "Kỳ",
  "filter.allYears": "tất cả năm",
  "filter.state": "Khu vực",
  "filter.myScope": "trong phạm vi của tôi",
  "filter.institution": "Tổ chức",
  "filter.institutionPlaceholder": "bắt đầu bằng…",
  "filter.clear": "Xoá {n} bộ lọc",

  // ------------------------------------------------------------ danh tinh
  "identity.fromIap": "Danh tính đến từ IAP",
  "identity.switchDev": "Đổi danh tính (chế độ dev)",
  "identity.signInAs": "Đăng nhập với tư cách",
  "identity.user.admin": "Admin — toàn quyền",
  "identity.user.lead": "Team Lead — ký phát hành",
  "identity.user.analystTx": "Analyst — chỉ Texas",
  "identity.user.analystCa": "Analyst — chỉ California",
  "identity.user.sale": "Sale — CA + TX",

  // ---------------------------------------------------------- do tuoi du lieu
  "strip.run": "Lần nạp",
  "strip.rows": "{n} dòng",
  "strip.syncedAgo": "đồng bộ cách đây {age}",
  "strip.tooOld": " — quá cũ",
  "strip.refresh": "Làm mới bảng",
  "strip.refreshTitle": "Đọc lại bản sao Postgres — tức thì, không chạm BigQuery",
  "strip.rebuild": "Nạp lại từ nguồn",
  "strip.rebuildTitle": "Chạy lại Sync Job: đọc lại toàn bộ từ BigQuery",
  "strip.newRunTitle": "Có lần nạp mới trên BigQuery",
  "strip.newRunBody":
    "Bản sao vừa đổi sang {runId}. Màn hình vẫn giữ số của {baseline} cho tới khi bạn bấm tải lại.",
  "strip.reload": "Tải lại",
  "strip.confirmTitle": "Nạp lại từ nguồn?",
  "strip.confirmBody":
    "Việc này {notLike} Làm mới bảng. Nó chạy lại Sync Job: đọc toàn bộ bảng fact từ BigQuery, ghi ra parquet, nạp vào bảng staging rồi đổi tên. Mất khoảng 30–60 giây và chỉ cần làm khi nghi bản sao lệch so với nguồn.",
  "strip.confirmNotLike": "không giống",
  "strip.calling": "Đang gọi…",
  "strip.runSyncJob": "Chạy Sync Job",
  "strip.triggeredTitle": "Sync Job đã được kích hoạt",
  "strip.triggeredBody": "Khi job xong, banner độ tươi ở trên sẽ báo có lần nạp mới.",

  // ----------------------------------------------------------- nhan trang thai
  "severity.critical": "nghiêm trọng",
  "severity.warning": "cảnh báo",
  "status.open": "đang mở",
  "status.awaiting_verify": "chờ QC xác minh",
  "status.closed": "đã đóng",
  "status.cancelled": "huỷ",
  "status.pending": "chờ chạy",
  "status.running": "đang chạy",
  "status.done": "xong",
  "status.error": "lỗi",

  // -------------------------------------------------------------- dashboard
  "dash.loading": "dashboard",
  "dash.gate.stale": "QC chưa kiểm lần nạp hiện tại",
  "dash.gate.locked": "Cổng phát hành đang KHOÁ",
  "dash.gate.debt": "Ký được, nhưng bản này còn nợ",
  "dash.gate.ready": "Cổng phát hành sẵn sàng",
  "dash.gateBody.stale":
    "Danh sách vi phạm đang hiển thị là của lần nạp trước. Ký lúc này bị máy chủ từ chối — QC chạy mỗi 5 phút.",
  "dash.gateBody.locked":
    "Còn {n} ticket đang chặn — lỗi đã xác nhận bằng bằng chứng, phải sửa ở nguồn chứ không duyệt cho qua được.",
  "dash.gateBody.debt":
    "{v} vi phạm luật và {t} ticket chưa đóng. Ký được, nhưng phải kèm phiếu duyệt có tên người.",
  "dash.gateBody.ready":
    "Không còn vi phạm luật, không còn ticket. Team Lead có thể ký phát hành.",
  "dash.viewBlocking": "Xem ticket đang chặn",
  "dash.goSign": "Sang trang ký",
  "dash.stat.rows": "Dòng trong phạm vi",
  "dash.stat.critical": "Vi phạm nghiêm trọng",
  "dash.stat.criticalNote": "nghi ngờ — không tự khoá cổng",
  "dash.stat.warning": "Cảnh báo",
  "dash.stat.warningNote": "trong phạm vi của bạn",
  "dash.stat.flagged": "Dòng bị gắn cờ",
  "dash.stat.flaggedNote": "ở lần nạp {runId}",
  "dash.stat.blocking": "Ticket đang chặn",
  "dash.stat.blockingNote": "{n} đang chờ QC xác minh",
  "dash.stat.deposit": "Tổng deposit",
  "dash.stat.depositNote": "số của nguồn",
  "dash.byRule.title": "Vi phạm theo luật",
  "dash.byRule.sub": "Luật khai báo trong {file}",
  "dash.byRule.empty": "Không còn ngoại lệ nào đang mở.",
  "dash.chart.exceptions": "ngoại lệ",
  "dash.delta.title": "Chênh lệch so với bản đã ký",
  "dash.delta.signedVersion": "bản ký",
  "dash.delta.signedBy": "người ký",
  "dash.delta.thisRun": "lần nạp này",
  "dash.delta.rowsAtSign": "Số dòng khi ký",
  "dash.delta.rowsNow": "Số dòng bây giờ",
  "dash.delta.rowsUnit": "{n} dòng",
  "dash.delta.runChanged":
    "Đã có lần nạp mới sau khi ký — số trên màn hình không còn là số đã ký.",
  "dash.delta.runSame": "Vẫn đang ở đúng lần nạp đã ký.",
  "dash.delta.ticketsSince": "{n} ticket mở thêm kể từ đó.",
  "dash.delta.noTicketsSince": "Không có ticket nào mở thêm kể từ đó.",
  "dash.delta.violationsChanged": "Tập vi phạm đã khác so với lúc ký.",
  "dash.delta.empty":
    "Chưa có bản nào được ký. Sang {link} để ký bản đầu tiên — còn nợ vẫn ký được, miễn là kèm phiếu duyệt.",
  "dash.delta.emptyLink": "trang phiên bản",
  // ------------------------------------------------------------- bộ luật
  "rules.button": "Xem bộ luật",
  "rules.title": "Bộ luật QC",
  "rules.sub": "{n} luật · version {v} · khai báo trong {file}",
  "rules.loading": "bộ luật",
  "rules.tab.list": "DANH SÁCH",
  "rules.tab.raw": "YAML GỐC",
  "rules.outOfSync":
    "File luật đang là version {file}, nhưng lần QC gần nhất chạy version {applied} — " +
    "danh sách vi phạm trên màn hình được sinh ra dưới bộ luật cũ. Chạy lại QC để hai bên khớp nhau.",
  "rules.scope": "chỉ {states}",
  "rules.scopeAll": "mọi bảng",
  "rules.showSql": "SQL của luật",
  "rules.countsNote": "Số vi phạm đếm trên lần nạp hiện tại, trong phạm vi và bộ lọc của bạn.",
  "rules.hits": "{n} vi phạm",
  "rules.noHits": "không vi phạm",

  "dash.byState.title": "Vi phạm theo khu vực",
  "dash.byState.lastSigned": "Bản ký gần nhất: {label}",
  "dash.byState.noneSigned": "Chưa ký bản nào",

  // ------------------------------------------------------------- man du lieu
  "data.title": "Dữ liệu trong phạm vi",
  "data.sub":
    "Phạm vi áp ở tầng server — đổi tham số trên URL không lấy được dữ liệu ngoài phạm vi được gán. Đã tải {n} dòng{more}.",
  "data.subMore": ", cuộn xuống để nạp tiếp",
  "data.subEnd": " — hết dữ liệu",
  "data.sortAll": "Sắp xếp toàn bộ",
  "data.sort.deposit": "deposit",
  "data.sort.share": "thị phần",
  "data.sort.year": "năm",
  "data.sort.institution": "tổ chức",
  "data.desc": "giảm dần ↓",
  "data.asc": "tăng dần ↑",
  "data.loading": "500 dòng đầu",
  "data.col.state": "Bang",
  "data.col.year": "Năm",
  "data.col.institution": "Tổ chức",
  "data.col.deposit": "Deposit",
  "data.col.share": "Thị phần",
  "data.col.prev": "Năm trước",
  "data.col.ticketExpected": "Ticket yêu cầu",
  "data.ticketPill": "ticket",
  "data.ticketTitle": "ticket #{id} — nguồn phải sửa thành {expected}",
  "data.loadMore": "Tải thêm {n} dòng",
  "data.loadingMore": "Đang nạp…",
  "data.allLoaded": "Đã tải hết",
  "data.sortNote":
    "Bấm tiêu đề cột chỉ sắp xếp trong {n} dòng đã tải. Muốn sắp xếp toàn bộ thì đổi ô {field} ở trên — lần đó chạy ở server.",

  // ------------------------------------------------------------- man vi pham
  "exc.title": "Vi phạm luật",
  "exc.sub":
    "{total} vi phạm trong phạm vi của bạn, ở lần nạp {runId}{rules}. Đây là nghi ngờ của máy, không phải kết luận — bấm một dòng để điều tra.",
  "exc.rulesVersion": " · bộ luật version {v}",
  "exc.severity": "Mức",
  "exc.col.rule": "Luật",
  "exc.col.key": "Khoá",
  "exc.col.message": "Vấn đề",
  "exc.col.observed": "Số liệu quan sát",
  "exc.staleTitle": "QC chưa kiểm lần nạp mới nhất",
  "exc.staleBody":
    "Danh sách dưới đây là của lần nạp {runId}, không phải lần nạp đang có trong bản sao. Ký lúc này bị máy chủ từ chối — chờ QC chạy xong (mỗi 5 phút).",
  "exc.loading": "vi phạm",
  "exc.panel.title": "Panel điều tra",
  "exc.panel.empty":
    "Chọn một vi phạm ở bảng bên trái. Panel sẽ đặt bản đã ký gần nhất cạnh lần nạp này để bạn thấy rõ số nào đổi, rồi cho mở ticket nếu số thật sự sai.",
  "exc.panel.loading": "chi tiết",
  "exc.lastSigned": "Bản đã ký gần nhất",
  "exc.noneSigned": "chưa ký bản nào",
  "exc.otherRun": " · lần nạp khác",
  "exc.thisRun": "Lần nạp này",
  "exc.prevYear": "{year}: {value}",
  "exc.noPrevYear": "không có số năm trước",
  "exc.notPerCell":
    "Vi phạm này gắn với cả một nhóm chứ không gắn vào một ô cụ thể, nên không mở ticket theo ô được. Sửa ở nguồn rồi để QC kiểm lại ở lần nạp sau.",
  "exc.readOnly": "Vai trò của bạn chỉ xem được. Nhờ analyst hoặc team lead mở ticket.",
  "exc.openTitle": "Mở ticket cho team Data",
  "exc.openSub":
    "Số đúng ở dưới là {acceptance}: QC sẽ đọc số thật ở lần nạp sau và đối chiếu với nó. Chỉ QC mới đóng được ticket này — không ai bấm đóng bằng tay.",
  "exc.openSubAcceptance": "điều kiện nghiệm thu",
  "exc.expectedLabel": "Số đúng phải là",
  "exc.sourceNow": "nguồn đang là {n}",
  "exc.titlePlaceholder": "Lỗi là gì — câu người khác đọc",
  "exc.evidencePlaceholder": "Bằng chứng — link, số đối chiếu, ai xác nhận",
  "exc.blockingLabel":
    "Chặn phát hành cho tới khi nguồn sửa xong — bỏ tick nếu lỗi không ảnh hưởng bản đang bán.",
  "exc.opening": "Đang mở…",
  "exc.open": "Mở ticket",
  "exc.trail": "Dấu vết",
  "exc.box.title": "Ô này đã có ticket #{id}",
  "exc.box.blocking": "chặn phát hành",
  "exc.box.meta": "cần = {expected} · lúc mở đọc được {observed}",
  "exc.box.qcChecked": " · QC kiểm ở {runId}: {observed}",
  "exc.box.qcNever": " · QC chưa kiểm lần nào",
  "exc.box.noRow": "không còn dòng",
  "exc.box.awaiting":
    "{who} báo đã sửa. Ticket đóng khi lần nạp sau đọc được đúng {expected} — không đóng bằng tay.",
  "exc.reasonPlaceholder": "Lý do — bắt buộc, vào audit log",
  "exc.markFixed": "Nguồn đã sửa — nhờ QC xác minh",
  "exc.cancelTicket": "Báo nhầm — huỷ ticket",

  // -------------------------------------------------------------- man ticket
  "tk.title": "Ticket gửi team Data",
  "tk.sub":
    "Mỗi ticket mang một {acceptance} kiểm được bằng máy. QC đọc số thật ở lần nạp kế tiếp và đối chiếu — chỉ nó mới đóng được ticket.",
  "tk.subAcceptance": "điều kiện nghiệm thu",
  "tk.statusLabel": "Trạng thái",
  "tk.filter.live": "chưa đóng",
  "tk.filter.open": "đang mở",
  "tk.filter.awaiting": "chờ QC xác minh",
  "tk.filter.closed": "đã đóng",
  "tk.filter.cancelled": "đã huỷ",
  "tk.blockingTitle": "{n} ticket đang chặn phát hành",
  "tk.blockingBody":
    "Không ký và không xuất file được cho tới khi nguồn sửa xong và QC xác minh. Nếu một lỗi trong số này không ảnh hưởng bản đang bán, team lead gỡ chặn từng cái — đó là một quyết định có tên người, không phải bộ lọc.",
  "tk.loading": "ticket",
  "tk.col.id": "#",
  "tk.col.cell": "Ô",
  "tk.col.issue": "Lỗi",
  "tk.col.expected": "Cần",
  "tk.col.sourceNow": "Nguồn đang là",
  "tk.col.status": "Trạng thái",
  "tk.col.openedBy": "Người mở",
  "tk.col.lastQc": "QC kiểm gần nhất",
  "tk.fromRule": "từ {rule}",
  "tk.selfFound": "người tự phát hiện",
  "tk.blockPill": "chặn",
  "tk.closedAt": "đóng ở {runId}",
  "tk.notChecked": "chưa kiểm",
  "tk.markFixed": "Đã sửa nguồn",
  "tk.unblock": "Gỡ chặn",
  "tk.setBlock": "Đặt chặn",
  "tk.cancel": "Huỷ",
  "tk.empty": "Không có ticket nào ở trạng thái này.",
  "tk.modal.mark_fixed": "Báo đã sửa ở nguồn",
  "tk.modal.set_blocking": "Đổi mức chặn phát hành",
  "tk.modal.cancel": "Huỷ ticket — báo nhầm",
  "tk.modal.title": "{action} — #{id}",
  "tk.modal.markFixedBody":
    "Ticket chuyển sang {awaiting}. Nó chỉ đóng khi lần nạp kế tiếp đọc được đúng {expected} ở ô {cell}. Lệch thì ticket tự bật lại kèm số đọc được.",
  "tk.modal.markFixedAwaiting": "chờ QC xác minh",
  "tk.modal.unblockBody":
    "Gỡ chặn nghĩa là {still} dù lỗi này chưa sửa. Lý do bạn ghi sẽ nằm trong audit log và ticket vẫn mở cho tới khi nguồn sửa.",
  "tk.modal.unblockStill": "vẫn phát hành được",
  "tk.modal.blockBody":
    "Đặt chặn nghĩa là không ai ký và không ai xuất file được cho tới khi nguồn sửa xong.",
  "tk.modal.cancelBody":
    "Huỷ dùng khi ticket mở nhầm — dữ liệu thật ra vẫn đúng. Nó không sửa gì ở nguồn và không xoá dấu vết.",

  // ------------------------------------------------------------ man phien ban
  "ver.title": "Phiên bản đã ký",
  "ver.sub":
    "Ký là đóng băng một lần nạp làm bản phát hành. File gửi khách chỉ xuất từ bản đã ký, và mang theo đúng món nợ ghi ở đây.",
  "ver.signNew": "Ký bản mới",
  "ver.pill.stale": "QC chưa kiểm lần nạp này",
  "ver.pill.blocking": "{n} ticket đang chặn",
  "ver.pill.debt": "ký được, nhưng còn nợ",
  "ver.pill.clean": "sạch",
  "ver.blockedStaleTitle": "Danh sách vi phạm đang hiển thị là của lần nạp trước",
  "ver.blockedTicketTitle": "Bị chặn bởi ticket",
  "ver.blockedStaleBody":
    "Lần nạp hiện tại là {runId} nhưng QC mới kiểm tới {qcRunId}. Ký lúc này là ký một thứ chưa ai nhìn thấy, nên máy chủ từ chối. QC chạy mỗi 5 phút.",
  "ver.blockedTicketBody":
    "Đây là lỗi đã xác nhận bằng bằng chứng, không phải nghi ngờ của máy — nên không duyệt cho qua được. Sửa ở nguồn rồi chờ QC xác minh, hoặc gỡ chặn từng ticket ở trang Ticket.",
  "ver.labelPlaceholder": "Tên bản, ví dụ: Báo cáo Q3 2026",
  "ver.approvalLabel": "Phiếu duyệt — bắt buộc",
  "ver.approvalPlaceholder":
    "Vì sao vẫn ký dù còn nợ. Ví dụ: 3 ô dưới ngưỡng là số thật của bang nhỏ, đã đối chiếu SSA. Ticket #123 không ảnh hưởng bang đang bán.",
  "ver.approvalHint":
    "Câu này đi theo bản ký vĩnh viễn và in vào file gửi khách. Tên bạn nằm cạnh nó.",
  "ver.signing": "Đang ký…",
  "ver.signWithApproval": "Ký kèm phiếu duyệt",
  "ver.sign": "Ký phát hành",
  "ver.col.version": "Bản",
  "ver.col.run": "Lần nạp",
  "ver.col.rows": "Số dòng",
  "ver.col.debt": "Nợ lúc ký",
  "ver.col.signedBy": "Người ký",
  "ver.col.at": "Lúc",
  "ver.col.sentTo": "Đã gửi cho",
  "ver.fingerprint": "vân tay {hash}",
  "ver.noFingerprint": "không có vân tay — ký trước P6",
  "ver.sourceRuns": "{n} lần nạp dữ liệu",
  "ver.noSourceRuns": "không ghi lại lần nạp — không xuất file được",
  "ver.rulesVersion": " · luật v{v}",
  "ver.notSent": "chưa gửi ai",
  "ver.recordSent": "Ghi nhận đã gửi",
  "ver.empty": "Chưa có bản nào được ký.",
  "ver.loading": "phiên bản",
  "ver.debt.violations": "Vi phạm luật ở lần nạp này",
  "ver.debt.critical": "{n} nghiêm trọng · ",
  "ver.debt.warning": "{n} cảnh báo",
  "ver.debt.noWarning": "không có cảnh báo",
  "ver.debt.openTickets": "Ticket chưa đóng",
  "ver.debt.someBlocking": "{n} trong số đó đang chặn",
  "ver.debt.noneBlocking": "không cái nào chặn phát hành",
  "ver.debt.compare": "So với bản ký gần nhất ({label}): ",
  "ver.debt.same": "đúng cùng một tập vi phạm, không có gì mới.",
  "ver.debt.different": "tập vi phạm đã khác — có cái mới hoặc cái cũ đã hết.",
  "ver.debt.noFingerprint": "bản trước không ghi vân tay nên không so được.",
  "ver.no.violations": "{n} vi phạm",
  "ver.no.tickets": "ticket {list}",
  "ver.send.title": "Ghi nhận đã gửi — {label}",
  "ver.send.body":
    "Ghi lại đã gửi bản nào cho khách nào ngày nào. Dòng này không xoá được.",
  "ver.send.customer": "Tên khách hàng",
  "ver.send.submit": "Ghi nhận",

  // ------------------------------------------------------------- man yeu cau
  "req.title": "Yêu cầu dữ liệu",
  "req.sub":
    "File gửi khách xuất thẳng từ BigQuery — nguồn sự thật — nhưng chỉ lấy những lần nạp nằm trong bản đã ký, và chỉ những bang trong phạm vi của bạn. Các ô sửa tay được áp lên trên, thị phần tính lại cho nhóm bị sửa.",
  "req.askTitle": "Xin một bản file",
  "req.gateLocked": "cổng đang khoá",
  "req.gateReady": "cổng sẵn sàng",
  "req.format": "Định dạng",
  "req.submit": "Gửi yêu cầu",
  "req.lockedNote":
    "Cổng phát hành đang khoá nên không xin file được. Máy chủ trả 409 kể cả khi bạn gọi thẳng API.",
  "req.created.triggered": "Đã nhận yêu cầu #{id} và kích hoạt Export Job",
  "req.created.queued": "Đã xếp hàng yêu cầu #{id}",
  "req.created.body": "Xuất từ bản ký {label}{scope}{note}",
  "req.created.scope": " · phạm vi {states}",
  "req.created.scopeAll": " · toàn bộ phạm vi",
  "req.created.note": " — {note}",
  "req.col.status": "Trạng thái",
  "req.col.signed": "Bản ký",
  "req.col.format": "Định dạng",
  "req.col.scope": "Phạm vi",
  "req.col.rows": "Số dòng",
  "req.col.requestedBy": "Người yêu cầu",
  "req.col.at": "Lúc gửi",
  "req.empty": "Chưa có yêu cầu nào.",
  "req.loading": "yêu cầu",
  "req.waiting": "đang chờ job chạy",
  "req.download": "Tải file",
  "req.downloadSigning": "Đang ký link…",
  "req.downloadTitle": "Link ký sẵn, hết hạn sau 15 phút",
  "req.downloadTitleLocked": "Cổng phát hành đang khoá",

  // --------------------------------------------------------------- man agent
  "agent.title": "AI Agent — hỏi về vi phạm & ticket",
  "agent.sub":
    "Agent chỉ đọc dữ liệu QC đang có trong phạm vi của bạn và trả lời có căn cứ — nó không đóng ticket, không ký bản, không sửa số. Quyết định cuối luôn là của con người.",
  "agent.try": "Thử hỏi:",
  "agent.suggest1": "Tình hình QC hôm nay sao rồi?",
  "agent.suggest2": "Tôi nên xử lý cái gì trước?",
  "agent.suggest3": "Có ticket nào đang chặn phát hành không?",
  "agent.thinking": "Agent đang đọc dữ liệu…",
  "agent.placeholder": "Hỏi về vi phạm, ticket, ưu tiên xử lý…",
  "agent.send": "Gửi",

  // ---------------------------------------------------------------- AG Grid
  "grid.noRows": "Không có dòng nào",
  "grid.loading": "Đang tải…",
} as const;

export type MessageKey = keyof typeof vi;
