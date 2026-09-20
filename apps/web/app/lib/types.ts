export type Me = {
  email: string;
  display_name: string | null;
  roles: string[];
  scope_states: string[] | "tat ca";
  require_iap: boolean;
};

export type VersionInfo = {
  run_id: string | null;
  last_synced_at: string | null;
  age_seconds: number | null;
  stale: boolean;
  row_count: number | null;
  source_row_count: number | null;
  status: string;
  error: string | null;
};

export type SignedVersion = {
  id: number;
  run_id: string;
  /** Cac lan nap du lieu duoc dong bang trong ban ky nay. */
  source_run_ids?: string[] | null;
  label: string;
  row_count: number;
  signed_by: string;
  signed_at: string;
  /** Van tay DU LIEU — phat hien nguon bi sua tai cho duoi cung run_id. */
  checksum?: string | null;
  /** {rule_id: so o vi pham} luc ky. */
  violations?: Record<string, number> | null;
  violations_fingerprint?: string | null;
  rules_version?: number | null;
  open_tickets?: number[] | null;
  /** Phieu duyet: vi sao van ky du con no. */
  approval_note?: string | null;
  sent?: SentRecord[];
};

export type SentRecord = {
  customer: string;
  sent_by: string;
  sent_at: string;
  file_path: string | null;
};

/** Cong phat hanh. Vi pham luat KHONG khoa — chi ticket chan va QC cu. */
export type Gate = {
  locked: boolean;
  blocking_tickets: { id: number; title: string; khoa: string; status: string }[];
  open_tickets: number;
  violations: {
    total: number;
    by_severity: Record<string, number>;
    by_rule: { rule_id: string; severity: string; n: number }[];
    fingerprint: string | null;
  };
  /** Con no thi van ky duoc, nhung phai kem phieu duyet. */
  needs_approval: boolean;
  /** QC chua kiem lan nap hien tai -> danh sach vi pham la cua lan truoc. */
  qc_stale: boolean;
  run_id: string | null;
  qc_run_id: string | null;
  rules_version: number | null;
  last_signed: SignedVersion | null;
};

export type Ticket = {
  id: number;
  year: number;
  state: string;
  gender: string;
  name: string;
  field: string;
  title: string;
  expected_value: string;
  observed_at_open: string | null;
  last_observed: string | null;
  evidence: string | null;
  blocking: boolean;
  from_rule_id: string | null;
  status: "open" | "awaiting_verify" | "closed" | "cancelled" | string;
  created_by: string;
  created_at: string;
  marked_fixed_by: string | null;
  marked_fixed_at: string | null;
  last_checked_run_id: string | null;
  last_checked_at: string | null;
  closed_run_id: string | null;
  closed_at: string | null;
};

export type Fact = {
  year: number;
  state: string;
  gender: string;
  name: string;
  run_id: string;
  number: number;
  market_share: number | null;
  prev_number: number | null;
  prev_year: number | null;
  /** O nay dang co ticket cho nguon sua — so VAN la so cua nguon. */
  ticket_id: number | null;
  ticket_status: string | null;
  ticket_expected: string | null;
  ticket_blocking: boolean | null;
};

export type FactsPage = {
  rows: Fact[];
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
  scope: string[] | "tat ca";
};

/** Mot vi pham luat, thuoc ve dung mot lan nap. Khong co trang thai. */
export type QcException = {
  id: number;
  run_id: string;
  rule_id: string;
  severity: "critical" | "warning" | string;
  year: number | null;
  state: string | null;
  gender: string | null;
  name: string | null;
  message: string;
  observed: Record<string, unknown> | null;
  created_at: string;
};

export type ExceptionDetail = {
  exception: QcException;
  fact: {
    year: number;
    state: string;
    gender: string;
    name: string;
    run_id: string;
    number: number;
    market_share: number | null;
    prev_number: number | null;
    prev_year: number | null;
  } | null;
  /** Ticket dang song tren dung o nay, neu co. */
  ticket: Ticket | null;
  can_open_ticket: boolean;
  last_signed: SignedVersion | null;
  history: {
    actor: string;
    action: string;
    before: Record<string, unknown> | null;
    after: Record<string, unknown> | null;
    created_at: string;
  }[];
};

export type Summary = {
  scope: string[] | "tat ca";
  facts: { rows: number; year_min: number | null; year_max: number | null; total_number: number | null };
  exceptions: {
    open: number;
    by_severity: Record<string, number>;
    by_rule: { rule_id: string; severity: string; n: number }[];
    by_state: { state: string; n: number }[];
    flagged_rows: number;
    run_id: string | null;
  };
  tickets: { open: number; awaiting_verify: number; blocking: number };
  gate: { locked: boolean; blocking: number; qc_stale: boolean; needs_approval: boolean };
  last_signed: SignedVersion | null;
  delta: {
    run_changed: boolean;
    rows_signed: number | null;
    rows_now: number | null;
    rows_delta: number | null;
    tickets_since: number;
    /** Van tay doi = TAP vi pham da khac, du tong so co the y het. */
    violations_changed: boolean;
    violations_signed: Record<string, number> | null;
    violations_now: Record<string, number>;
  };
  sync: { last_run_id: string | null; last_synced_at: string | null; last_row_count: number | null; status: string } | null;
};

export type ExportJob = {
  id: number;
  run_id: string;
  status: "pending" | "running" | "done" | "error" | string;
  format: string;
  scope_states: string[] | null;
  row_count: number | null;
  /** Canh bao khong lam job that bai — vi du vuot gioi han dong cua Excel. */
  warning: string | null;
  signed_version_id: number | null;
  signed_label: string | null;
  requested_by: string;
  created_at: string;
  finished_at: string | null;
  gcs_path: string | null;
  /** File dau ban ky di kem: ky kem vi pham gi, ticket nao chua dong. */
  stamp_path?: string | null;
  error: string | null;
};

export type ExportCreated = {
  job_id: number;
  status: string;
  signed_version: { id: number; label: string };
  format: string;
  scope: string[] | null;
  /** false = job chua duoc kich hoat tu dong, yeu cau nam trong hang doi. */
  triggered: boolean;
  note: string;
};

export type Options = {
  states: string[];
  years: number[];
  genders: string[];
  sortable: string[];
};
