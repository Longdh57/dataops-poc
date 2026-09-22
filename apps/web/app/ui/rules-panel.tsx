"use client";

// Nut "Xem bo luat" + hop hien bo luat QC.
//
// Man hinh nay tra loi dung mot cau: "luat nay la gi". Nguoi doc bao cao
// thay rule_id tren bang vi pham nhung khong mo repo duoc, nen bo luat
// phai den duoc tu trong ung dung.
//
// Hai cach doc, va giu ca hai co chu dich: DANH SACH de tra cuu nhanh
// tung luat, YAML GOC de doi chieu nguyen van — khi nghi ngo API dien
// giai sai thi thu nguoi ta can nhin la chinh cai file.

import { useState } from "react";

import { useI18n } from "@/app/i18n/context";
import { useRules } from "@/app/lib/queries";
import type { QcRule } from "@/app/lib/types";

import { ErrBox, Loading, Modal, Severity } from "./bits";

export default function RulesButton({ counts }: {
  /** {rule_id: so vi pham o lan nap hien tai} — co thi hien kem moi luat. */
  counts?: Record<string, number>;
}) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);

  return (
    <>
      <button type="button" className="btn btn-sm" onClick={() => setOpen(true)}>
        {t("rules.button")}
      </button>
      {open ? <RulesModal counts={counts} onClose={() => setOpen(false)} /> : null}
    </>
  );
}

function RulesModal({
  counts, onClose,
}: {
  counts?: Record<string, number>;
  onClose: () => void;
}) {
  const { t } = useI18n();
  const [raw, setRaw] = useState(false);
  // Hop chi duoc dung len khi nguoi dung bam nut, nen API cung chi bi goi
  // luc do — bo luat khong nam trong duong tai cua moi trang.
  const { data, isPending, error } = useRules();

  return (
    <Modal wide title={t("rules.title")} onClose={onClose}>
      {error ? <ErrBox error={error} /> : null}
      {isPending && !error ? <Loading what={t("rules.loading")} /> : null}

      {data ? (
        <>
          <p className="sub" style={{ marginBottom: 10 }}>
            {t("rules.sub", {
              n: data.rules.length,
              v: data.version ?? "—",
              file: data.source,
            })}
            {/* So vi pham di kem la so TRONG PHAM VI va bo loc dang bat,
                khong phai so toan cuc — noi ro de khong bi doc nham. */}
            {counts ? ` · ${t("rules.countsNote")}` : null}
          </p>

          {/* Version trong file khac version QC da chay = danh sach vi pham
              tren man hinh duoc sinh ra duoi mot bo luat KHAC cai dang doc.
              Im lang o day thi nguoi doc doi chieu nham. */}
          {!data.in_sync ? (
            <div className="banner banner-warn" style={{ marginBottom: 12 }}>
              <div className="banner-body">
                {t("rules.outOfSync", {
                  file: data.version ?? "—",
                  applied: data.applied_version ?? "—",
                })}
              </div>
            </div>
          ) : null}

          <div className="langswitch" style={{ marginBottom: 12 }}>
            <button type="button" className="langswitch-btn" data-on={raw ? "0" : "1"}
                    onClick={() => setRaw(false)}>
              {t("rules.tab.list")}
            </button>
            <button type="button" className="langswitch-btn" data-on={raw ? "1" : "0"}
                    onClick={() => setRaw(true)}>
              {t("rules.tab.raw")}
            </button>
          </div>

          {raw ? (
            <pre className="code-block">{data.raw}</pre>
          ) : (
            <div className="rule-list">
              {/* Luat khong co trong bang dem la luat khong bat duoc o nao
                  — QC chay HET moi luat, nen vang mat nghia la 0, khong
                  phai khong biet. */}
              {data.rules.map((r) => (
                <RuleItem key={r.id} rule={r} n={counts ? (counts[r.id] ?? 0) : undefined} />
              ))}
            </div>
          )}
        </>
      ) : null}

      <div style={{ display: "flex", justifyContent: "flex-end", marginTop: 14 }}>
        <button type="button" className="btn" onClick={onClose}>{t("common.close")}</button>
      </div>
    </Modal>
  );
}

function RuleItem({ rule, n }: { rule: QcRule; n?: number }) {
  const { t } = useI18n();
  return (
    <div className="rule">
      <div className="rule-head">
        <span className="mono rule-id">{rule.id}</span>
        <Severity value={rule.severity} />
        <span className="pill">
          {rule.scope ? t("rules.scope", { states: rule.scope.join(", ") }) : t("rules.scopeAll")}
        </span>
        {/* Khong co so = khong biet, khac han voi biet la 0. Chi hien khi
            nguoi goi truyen bang dem xuong. */}
        {n !== undefined ? (
          <span className={`pill ${n ? "pill-warn" : "pill-good"}`}>
            {n ? t("rules.hits", { n, count: n }) : t("rules.noHits")}
          </span>
        ) : null}
      </div>
      <p className="rule-msg">{rule.message}</p>
      <details>
        <summary>{t("rules.showSql")}</summary>
        <pre className="code-block">{rule.sql}</pre>
      </details>
    </div>
  );
}
