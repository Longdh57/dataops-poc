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
  label: string;
  row_count: number;
  signed_by: string;
  signed_at: string;
  sent?: SentRecord[];
};

export type SentRecord = {
  customer: string;
  sent_by: string;
  sent_at: string;
  file_path: string | null;
};

export type Gate = {
  locked: boolean;
  blocking: number;
  open_by_severity: Record<string, number>;
  last_signed: SignedVersion | null;
};

export type Fact = {
  year: number;
  state: string;
  gender: string;
  name: string;
  run_id: string;
  number: number;
  number_raw: number;
  market_share: number | null;
  prev_number: number | null;
  prev_year: number | null;
  overridden: boolean;
  override_reason: string | null;
  override_by: string | null;
  override_version: number;
};

export type FactsPage = {
  rows: Fact[];
  limit: number;
  has_more: boolean;
  next_cursor: string | null;
  scope: string[] | "tat ca";
};

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
  status: string;
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
  override: {
    old_value: string | null;
    new_value: string;
    reason: string;
    version: number;
    created_by: string;
    created_at: string;
  } | null;
  expected_version: number;
  last_signed: SignedVersion | null;
  history: {
    actor: string;
    action: string;
    before: Record<string, unknown> | null;
    after: Record<string, unknown> | null;
    created_at: string;
  }[];
};

/** Than cua loi 409 khoa lac quan — API tra ve day du de hien diff. */
export type ConflictDetail = {
  loi: string;
  expected_version: number;
  current_version: number;
  gia_tri_goc: number | null;
  gia_tri_hien_tai: number | null;
  gia_tri_ban_muon_ghi: number | null;
};

export type Summary = {
  scope: string[] | "tat ca";
  facts: { rows: number; year_min: number | null; year_max: number | null; total_number: number | null };
  exceptions: {
    open: number;
    by_severity: Record<string, number>;
    by_rule: { rule_id: string; severity: string; n: number }[];
    by_state: { state: string; n: number }[];
    resolved: number;
    flagged_rows: number;
  };
  overrides: number;
  gate: { locked: boolean; blocking: number };
  last_signed: SignedVersion | null;
  delta: {
    run_changed: boolean;
    rows_signed: number | null;
    rows_now: number | null;
    rows_delta: number | null;
    overrides_since: number;
  };
  sync: { last_run_id: string | null; last_synced_at: string | null; last_row_count: number | null; status: string } | null;
};

export type ExportJob = {
  id: number;
  run_id: string;
  status: "pending" | "running" | "done" | "error" | string;
  requested_by: string;
  created_at: string;
  finished_at: string | null;
  gcs_path: string | null;
  error: string | null;
};

export type Options = {
  states: string[];
  years: number[];
  genders: string[];
  sortable: string[];
};
