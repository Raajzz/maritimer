// Pure formatting helpers. Money stays a string end to end; Intl formats decimal strings without float math.

const moneyFormatters = new Map();

export function formatMoney(amount, currency = "USD", { signed = false } = {}) {
  if (amount === null || amount === undefined || amount === "") return "—";
  const key = `${currency}|${signed}`;
  if (!moneyFormatters.has(key)) {
    moneyFormatters.set(
      key,
      new Intl.NumberFormat("en-US", { style: "currency", currency, currencyDisplay: "code", signDisplay: signed ? "exceptZero" : "auto" }),
    );
  }
  return moneyFormatters.get(key).format(String(amount));
}

export function money(m, opts) {
  return m ? formatMoney(m.amount, m.currency_code, opts) : "—";
}

export function decimalSign(value) {
  const s = String(value ?? "0").trim();
  if (/^-/.test(s) && /[1-9]/.test(s)) return -1;
  if (/[1-9]/.test(s)) return 1;
  return 0;
}

export function formatRate(rate) {
  if (!rate) return "—";
  return String(rate).replace(/(\.\d*?[1-9])0+$/, "$1").replace(/\.0+$/, "");
}

const dateFmt = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", year: "numeric" });
const dateTimeFmt = new Intl.DateTimeFormat("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

export function formatDate(value) {
  return value ? dateFmt.format(new Date(value)) : "—";
}

export function formatDateTime(value) {
  return value ? dateTimeFmt.format(new Date(value)) : "—";
}

export function relativeTime(value, now = Date.now()) {
  if (!value) return "";
  const diff = Math.round((new Date(value).getTime() - now) / 60000);
  const abs = Math.abs(diff);
  const unit = abs < 60 ? [diff, "minute"] : abs < 1440 ? [Math.round(diff / 60), "hour"] : [Math.round(diff / 1440), "day"];
  return new Intl.RelativeTimeFormat("en", { numeric: "auto" }).format(unit[0], unit[1]);
}

// <input type="datetime-local"> works in local time; the API speaks ISO UTC.
export function toLocalInput(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(value) {
  return value ? new Date(value).toISOString() : null;
}

const ACRONYMS = new Set(["pda", "fda", "eta", "etd", "ata", "atd", "id", "fx", "imo", "ai"]);

export function humanize(code) {
  if (!code) return "";
  const words = String(code).toLowerCase().split(/[_\s]+/).filter(Boolean);
  return words.map((w, i) => (ACRONYMS.has(w) ? w.toUpperCase() : i === 0 ? w[0].toUpperCase() + w.slice(1) : w)).join(" ");
}

// Status → badge tone (ARCHITECTURE.md §5): neutral draft/pending, accent in progress, cta needs action,
// success done, error declined/rejected/cancelled.
const TONES = {
  success: ["APPROVED", "ACCEPTED", "SETTLED", "CLOSED", "CONFIRMED", "PAID", "FINAL", "RESOLVED"],
  error: ["DECLINED", "REJECTED", "CANCELLED", "VOID", "SUSPENDED", "WITHDRAWN", "EXPIRED"],
  cta: ["PDA_SENT", "DISPUTED", "OPEN", "PENDING_REVIEW", "FDA_ISSUED", "BALANCE_DUE", "REFUND_DUE", "PARTIALLY_PAID"],
  accent: ["ADVANCE_RECEIVED", "IN_PORT", "DEPARTED", "PDA_APPROVED", "ISSUED", "UNDER_REVIEW", "FDA_FINAL", "ONBOARDING"],
};

export function statusTone(status) {
  for (const [tone, list] of Object.entries(TONES)) if (list.includes(status)) return tone;
  return "neutral";
}

export function initials(name) {
  return (name || "?").split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("");
}
