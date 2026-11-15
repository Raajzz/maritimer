import { Inbox, Star, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { formatMoney, humanize, statusTone } from "../../lib/format";

export function Button({ variant = "primary", size, block, icon: Icon, busy, children, className = "", ...props }) {
  const cls = ["btn", `btn-${variant}`, size === "sm" && "btn-sm", block && "btn-block", !children && "icon-btn", className].filter(Boolean).join(" ");
  return (
    <button type="button" className={cls} disabled={busy || props.disabled} {...props}>
      {busy ? <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} /> : Icon && <Icon size={18} aria-hidden />}
      {children}
    </button>
  );
}

export function Card({ title, actions, children, className = "", ...props }) {
  return (
    <section className={`card ${className}`} {...props}>
      {(title || actions) && (
        <div className="card-header">
          {title && <h2>{title}</h2>}
          {actions && <div className="row">{actions}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

export function Badge({ tone = "neutral", children }) {
  return <span className={`badge badge-${tone}`}>{children}</span>;
}

export function StatusBadge({ status, label }) {
  if (!status) return null;
  return <Badge tone={statusTone(status)}>{label || humanize(status)}</Badge>;
}

export function Money({ value, currency, signed, className = "" }) {
  const amount = value && typeof value === "object" ? value.amount : value;
  const code = value && typeof value === "object" ? value.currency_code : currency;
  return <span className={`num ${className}`}>{formatMoney(amount, code || "USD", { signed })}</span>;
}

export function PageHeader({ title, sub, actions, back }) {
  return (
    <header className="page-header">
      <div className="stack-sm" style={{ gap: 4 }}>
        {back}
        <h1>{title}</h1>
        {sub && <div className="sub">{sub}</div>}
      </div>
      {actions && <div className="row">{actions}</div>}
    </header>
  );
}

export function Field({ label, hint, error, children, htmlFor }) {
  return (
    <div className="field">
      {label && <label htmlFor={htmlFor}>{label}</label>}
      {children}
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="error">{error}</span>}
    </div>
  );
}

// Every field gets a unique id so its <label> is associated (screen readers, getByLabel).
export function Input({ label, hint, error, id, ...props }) {
  const auto = useId();
  const fieldId = id || auto;
  return (
    <Field label={label} hint={hint} error={error} htmlFor={fieldId}>
      <input id={fieldId} className="input" {...props} />
    </Field>
  );
}

export function Select({ label, hint, error, id, options, placeholder, ...props }) {
  const auto = useId();
  const fieldId = id || auto;
  return (
    <Field label={label} hint={hint} error={error} htmlFor={fieldId}>
      <select id={fieldId} className="select" {...props}>
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </Field>
  );
}

export function Textarea({ label, hint, error, id, ...props }) {
  const auto = useId();
  const fieldId = id || auto;
  return (
    <Field label={label} hint={hint} error={error} htmlFor={fieldId}>
      <textarea id={fieldId} className="textarea" {...props} />
    </Field>
  );
}

export function CheckGroup({ options, value, onChange }) {
  const selected = new Set(value);
  return (
    <div className="checks">
      {options.map((o) => (
        <label key={o.value} className={`check ${selected.has(o.value) ? "on" : ""}`}>
          <input
            type="checkbox"
            checked={selected.has(o.value)}
            onChange={(e) => onChange(e.target.checked ? [...value, o.value] : value.filter((v) => v !== o.value))}
          />
          {o.label}
        </label>
      ))}
    </div>
  );
}

export function ErrorAlert({ error }) {
  if (!error) return null;
  const lines = error.fieldMessages || [];
  return (
    <div className="alert alert-error" role="alert">
      <strong>{error.message || String(error)}</strong>
      {lines.length > 0 && (
        <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>
          {lines.slice(0, 6).map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Alert({ tone = "info", children }) {
  return <div className={`alert alert-${tone}`}>{children}</div>;
}

export function Spinner({ label = "Loading" }) {
  return (
    <div className="row" style={{ justifyContent: "center", padding: 32 }} role="status">
      <span className="spinner" />
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function EmptyState({ icon: Icon = Inbox, title, children }) {
  return (
    <div className="empty">
      <Icon size={32} aria-hidden />
      <div className="strong" style={{ color: "var(--color-text)" }}>{title}</div>
      {children && <div className="small" style={{ marginTop: 4 }}>{children}</div>}
    </div>
  );
}

/** Wraps a useResource result: spinner while loading, error banner on failure, children(data) otherwise. */
export function Loader({ resource, children }) {
  if (resource.loading && !resource.data) return <Spinner />;
  if (resource.error && !resource.data) return <ErrorAlert error={resource.error} />;
  if (!resource.data) return null;
  return children(resource.data);
}

export function Modal({ title, onClose, children, wide, footer }) {
  useEffect(() => {
    const onKey = (e) => e.key === "Escape" && onClose();
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`sheet ${wide ? "wide" : ""}`} role="dialog" aria-modal="true" aria-label={title}>
        <div className="sheet-head">
          <h2>{title}</h2>
          <Button variant="ghost" icon={X} aria-label="Close" onClick={onClose} />
        </div>
        <div className="stack">{children}</div>
        {footer && <div className="row" style={{ justifyContent: "flex-end", marginTop: 20 }}>{footer}</div>}
      </div>
    </div>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={active === t.id} className={active === t.id ? "active" : ""} onClick={() => onChange(t.id)}>
          {t.label}
          {t.count ? <span className="count">{t.count}</span> : null}
        </button>
      ))}
    </div>
  );
}

export function Kpi({ label, value, hint }) {
  return (
    <div className="card kpi">
      <span className="label">{label}</span>
      <span className="value">{value}</span>
      {hint && <span className="xs muted">{hint}</span>}
    </div>
  );
}

export function Stars({ value }) {
  const n = Math.round(Number(value || 0));
  return (
    <span className="stars" aria-label={`${value} out of 5`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} size={14} fill={i <= n ? "currentColor" : "none"} aria-hidden />
      ))}
    </span>
  );
}

/** Responsive table: columns [{key, label, render, num}] — stacks into cards below 640px. */
/** `pageSize` pages a plain array on the client; server-paginated lists use <Pager> instead. */
export function DataTable({ columns, rows, onRowClick, rowKey = "id", empty, footer, pageSize }) {
  const [visible, pager] = usePaged(rows || [], pageSize);
  if (!rows?.length) return empty || <EmptyState title="Nothing here yet" />;
  return (
    <>
    <div className="table-wrap">
      <table className="table responsive">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={c.num ? "num" : ""}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {visible.map((row) => (
            <tr key={row[rowKey]} className={onRowClick ? "clickable" : ""} onClick={onRowClick ? () => onRowClick(row) : undefined}>
              {columns.map((c) => (
                <td key={c.key} data-label={c.label} className={c.num ? "num" : ""}>
                  {c.render ? c.render(row) : row[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
        {footer && <tfoot>{footer}</tfoot>}
      </table>
    </div>
    {pager}
    </>
  );
}

function PagerBar({ page, pages, total, hasPrev, hasNext, onPage, compact }) {
  return (
    <div className="pager" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: 8, marginTop: compact ? 8 : 12 }}>
      <Button variant="secondary" size="sm" disabled={!hasPrev} onClick={() => onPage(page - 1)} aria-label="Previous page">
        {compact ? "‹" : "Previous"}
      </Button>
      <span className="small muted" style={{ fontVariantNumeric: "tabular-nums" }}>
        {compact ? `${page} / ${pages}` : `Page ${page} of ${pages}`}{!compact && total != null ? ` · ${total} total` : ""}
      </span>
      <Button variant="secondary" size="sm" disabled={!hasNext} onClick={() => onPage(page + 1)} aria-label="Next page">
        {compact ? "›" : "Next"}
      </Button>
    </div>
  );
}

/** Pager for server-paginated responses ({count, next, previous, results}); 25 per page by default. */
export function Pager({ data, page, onPage, pageSize = 25, compact = false }) {
  if (!data || (!data.next && !data.previous)) return null;
  const pages = Math.max(1, Math.ceil((data.count ?? 0) / pageSize));
  return <PagerBar page={page} pages={pages} total={data.count} hasPrev={Boolean(data.previous)} hasNext={Boolean(data.next)} onPage={onPage} compact={compact} />;
}

/** Client-side paging for a plain array. Returns [visible items, pager element or null]. */
export function usePaged(items, pageSize, { compact = false } = {}) {
  const [page, setPage] = useState(1);
  const list = items || [];
  const pages = pageSize ? Math.max(1, Math.ceil(list.length / pageSize)) : 1;
  const current = Math.min(page, pages);
  useEffect(() => {
    if (page !== current) setPage(current);
  }, [page, current]);
  if (!pageSize || list.length <= pageSize) return [list, null];
  const visible = list.slice((current - 1) * pageSize, current * pageSize);
  const bar = <PagerBar page={current} pages={pages} total={list.length} hasPrev={current > 1} hasNext={current < pages} onPage={setPage} compact={compact} />;
  return [visible, bar];
}

/** Render-prop form of usePaged, for lists drawn inside callbacks: <Paged items={xs} pageSize={5}>{(page) => …}</Paged>. */
export function Paged({ items, pageSize, compact = true, children }) {
  const [visible, pager] = usePaged(items, pageSize, { compact });
  return <>{children(visible)}{pager}</>;
}

export function DefinitionList({ items }) {
  return (
    <dl className="dl">
      {items.filter(Boolean).map(([k, v]) => (
        <div key={k} style={{ display: "contents" }}>
          <dt>{k}</dt>
          <dd>{v ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}
