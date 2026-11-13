// Domain components shared across roles.
import { AlertTriangle, Calendar, MapPin, Send, Ship } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import { useAuth } from "../hooks/useAuth";
import { useResource } from "../hooks/useResource";
import { api } from "../lib/api";
import { decimalSign, formatDate, formatDateTime, formatMoney, formatRate, humanize, relativeTime } from "../lib/format";
import { Badge, Button, DataTable, EmptyState, ErrorAlert, Loader, Money, StatusBadge } from "./ui";

export function PortCallItem({ pc, compact }) {
  return (
    <Link to={`/port-calls/${pc.id}`} className={compact ? "item" : "card card-link"}>
      <div className="row-between">
        <span className="strong small mono">{pc.reference}</span>
        <StatusBadge status={pc.status} />
      </div>
      <div className="row" style={{ marginTop: 6, gap: 6 }}>
        <Ship size={14} aria-hidden color="var(--color-muted)" />
        <span className="strong">{pc.vessel.name}</span>
      </div>
      <div className="row small muted" style={{ gap: 6 }}>
        <span className="row" style={{ gap: 4 }}><MapPin size={14} aria-hidden /> {pc.port.name}</span>
        <span className="row" style={{ gap: 4 }}><Calendar size={14} aria-hidden /> {pc.ata ? "Arrived" : "ETA"} {formatDate(pc.ata || pc.eta)}</span>
      </div>
      {pc.owner && <div className="xs muted" style={{ marginTop: 4 }}>{pc.owner.trade_name || pc.owner.legal_name} → {pc.agent.trade_name || pc.agent.legal_name}</div>}
      {(pc.pda_total || pc.fda_total) && (
        <div className="row small" style={{ marginTop: 6, gap: 12 }}>
          {pc.pda_total && <span>PDA <Money value={pc.pda_total} /></span>}
          {pc.fda_total && <span>FDA <Money value={pc.fda_total} /></span>}
        </div>
      )}
      {pc.open_disputes > 0 && (
        <div className="row xs" style={{ marginTop: 6, color: "var(--color-cta-text)" }}>
          <AlertTriangle size={14} aria-hidden /> {pc.open_disputes} open dispute{pc.open_disputes > 1 ? "s" : ""}
        </div>
      )}
    </Link>
  );
}

export function PortCallTable({ rows, onOpen }) {
  return (
    <DataTable
      rows={rows}
      onRowClick={onOpen}
      columns={[
        { key: "reference", label: "Ref", render: (r) => <span className="mono strong">{r.reference}</span> },
        { key: "vessel", label: "Vessel", render: (r) => r.vessel.name },
        { key: "port", label: "Port", render: (r) => r.port.name },
        { key: "eta", label: "ETA", render: (r) => formatDate(r.eta) },
        { key: "party", label: "Owner / agent", render: (r) => (r.owner ? `${r.owner.legal_name} / ${r.agent.legal_name}` : r.agent.legal_name) },
        { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
        { key: "pda", label: "PDA", num: true, render: (r) => (r.pda_total ? <Money value={r.pda_total} /> : "—") },
        { key: "fda", label: "FDA", num: true, render: (r) => (r.fda_total ? <Money value={r.fda_total} /> : "—") },
      ]}
      empty={<EmptyState icon={Ship} title="No port calls yet" />}
    />
  );
}

/** Read-only line items for a PDA or FDA, with per-line dispute action for owners. */
export function LineItemsTable({ account, onDispute, disputedLineIds = new Set() }) {
  const cur = account.currency_code;
  return (
    <DataTable
      rows={account.line_items}
      columns={[
        { key: "line_no", label: "#" },
        { key: "cat", label: "Category", render: (l) => l.service_category.name },
        {
          key: "desc", label: "Description",
          render: (l) => (
            <div className="stack-sm" style={{ gap: 2, textAlign: "left" }}>
              <span>{l.description}</span>
              {l.vendor_name && <span className="xs muted">{l.vendor_name}{l.vendor_invoice_number ? ` · inv. ${l.vendor_invoice_number}` : ""}</span>}
              {account.kind === "FDA" && !l.vendor_invoice_id && !l.is_adjustment && <span className="xs muted">Agent-paid</span>}
              {l.is_adjustment && <Badge tone="cta">Dispute adjustment</Badge>}
            </div>
          ),
        },
        { key: "local", label: "Local amount", num: true, render: (l) => formatMoney(l.local_amount, l.local_currency_code) },
        { key: "rate", label: "FX rate", num: true, render: (l) => (l.fx_rate_id ? formatRate(l.fx_rate_applied) : "—") },
        { key: "amount", label: `Amount (${cur})`, num: true, render: (l) => <Money value={l.amount} currency={cur} /> },
        ...(onDispute
          ? [{
              key: "dispute", label: "",
              render: (l) => (disputedLineIds.has(l.id)
                ? <Badge tone="cta">Disputed</Badge>
                : <Button size="sm" variant="secondary" onClick={(e) => { e.stopPropagation(); onDispute(l); }}>Dispute</Button>),
            }]
          : []),
      ]}
      footer={
        <tr>
          <td colSpan={5} data-label="">Total</td>
          <td className="num" data-label="Total" colSpan={onDispute ? 2 : 1}><Money value={account.total} /></td>
        </tr>
      }
    />
  );
}

export function VarianceTable({ variance }) {
  const cur = variance.currency_code;
  const tone = (v) => (decimalSign(v) > 0 ? "pos" : decimalSign(v) < 0 ? "neg" : "");
  return (
    <DataTable
      rowKey="key"
      rows={variance.lines.map((r, i) => ({ ...r, key: `${r.pda_line_item_id}-${i}` }))}
      columns={[
        { key: "category", label: "Category" },
        { key: "description", label: "Description" },
        { key: "pda", label: "PDA", num: true, render: (r) => formatMoney(r.pda_amount, cur) },
        { key: "fda", label: "FDA", num: true, render: (r) => formatMoney(r.fda_amount, cur) },
        { key: "var", label: "Variance", num: true, render: (r) => <span className={tone(r.variance)}>{formatMoney(r.variance, cur, { signed: true })}</span> },
      ]}
      footer={
        <tr>
          <td colSpan={2} data-label="">Total vs {variance.pda_reference || "PDA"}</td>
          <td className="num" data-label="PDA">{formatMoney(variance.pda_total, cur)}</td>
          <td className="num" data-label="FDA">{formatMoney(variance.fda_total, cur)}</td>
          <td className={`num ${tone(variance.total_variance)}`} data-label="Variance">{formatMoney(variance.total_variance, cur, { signed: true })}</td>
        </tr>
      }
    />
  );
}

/**
 * Editable line set for a DRAFT PDA/FDA. The server computes `amount` from local amount × FX rate,
 * so the editor only sends inputs and shows the saved result (SCHEMA.md D9).
 */
export function LineEditor({ account, pdaLines, onSaved }) {
  const categories = useResource("/service-categories");
  const currencies = useResource("/currencies");
  const [lines, setLines] = useState(() =>
    account.line_items.map((l) => ({
      id: l.id, service_category_id: l.service_category_id, description: l.description, local_amount: l.local_amount,
      local_currency_code: l.local_currency_code, quantity: l.quantity, unit: l.unit, pda_line_item_id: l.pda_line_item_id,
      vendor_invoice_id: l.vendor_invoice_id, vendor_invoice_number: l.vendor_invoice_number, is_adjustment: l.is_adjustment, notes: l.notes,
    })),
  );
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const isFda = account.kind === "FDA";

  function update(i, patch) {
    setLines(lines.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const payload = lines.map((l) => {
        const out = { id: l.id || undefined, service_category_id: Number(l.service_category_id) || null, description: l.description, notes: l.notes || "" };
        if (!l.vendor_invoice_id && !l.is_adjustment) {
          out.local_amount = l.local_amount;
          out.local_currency_code = l.local_currency_code;
        }
        if (isFda) out.pda_line_item_id = l.pda_line_item_id ? Number(l.pda_line_item_id) : null;
        if (l.vendor_invoice_id) out.vendor_invoice_id = l.vendor_invoice_id;
        return out;
      });
      onSaved(await api.put(`/disbursement-accounts/${account.id}/line-items`, { line_items: payload }));
    } catch (err) {
      setError(err);
    } finally {
      setBusy(false);
    }
  }

  if (!categories.data || !currencies.data) return <Loader resource={categories.data ? currencies : categories}>{() => null}</Loader>;
  const catOptions = categories.data.map((c) => ({ value: c.id, label: c.name }));
  const curOptions = currencies.data.map((c) => ({ value: c.code, label: c.code }));
  return (
    <div className="stack">
      {lines.map((l, i) => {
        const locked = Boolean(l.vendor_invoice_id || l.is_adjustment);
        return (
          <div key={l.id || `new-${i}`} className="card" style={{ padding: 12, background: "var(--color-bg)" }}>
            <div className="row-between" style={{ marginBottom: 8 }}>
              <span className="small strong">Line {i + 1}{l.vendor_invoice_number ? ` · invoice ${l.vendor_invoice_number}` : ""}{l.is_adjustment ? " · dispute adjustment" : ""}</span>
              {!l.is_adjustment && <Button size="sm" variant="ghost" onClick={() => setLines(lines.filter((_, idx) => idx !== i))}>Remove</Button>}
            </div>
            <div className="grid grid-4">
              <label className="field"><span className="small strong">Category</span>
                <select className="select" value={l.service_category_id || ""} onChange={(e) => update(i, { service_category_id: e.target.value })} disabled={locked}>
                  <option value="">Choose…</option>
                  {catOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              <label className="field"><span className="small strong">Description</span>
                <input className="input" value={l.description} onChange={(e) => update(i, { description: e.target.value })} />
              </label>
              <label className="field"><span className="small strong">Local amount</span>
                <input className="input" inputMode="decimal" value={l.local_amount} disabled={locked} onChange={(e) => update(i, { local_amount: e.target.value })} />
              </label>
              <label className="field"><span className="small strong">Currency</span>
                <select className="select" value={l.local_currency_code} disabled={locked} onChange={(e) => update(i, { local_currency_code: e.target.value })}>
                  {curOptions.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
              </label>
              {isFda && pdaLines?.length > 0 && (
                <label className="field"><span className="small strong">Compare with PDA line</span>
                  <select className="select" value={l.pda_line_item_id || ""} onChange={(e) => update(i, { pda_line_item_id: e.target.value })}>
                    <option value="">None (new cost)</option>
                    {pdaLines.map((p) => <option key={p.id} value={p.id}>{p.line_no}. {p.description}</option>)}
                  </select>
                </label>
              )}
            </div>
          </div>
        );
      })}
      <div className="row">
        <Button variant="secondary" onClick={() => setLines([...lines, { service_category_id: "", description: "", local_amount: "", local_currency_code: "INR", notes: "" }])}>
          Add line
        </Button>
        <Button busy={busy} onClick={save}>Save lines</Button>
      </div>
      <p className="xs muted">Amounts in other currencies are converted with the latest recorded FX rate {isFda ? "on or before departure" : "today"}; the exact rate is stored on each line.</p>
      <ErrorAlert error={error} />
    </div>
  );
}

/** Polling chat (ARCHITECTURE.md: every 5 s while open). */
export function ChatPanel({ threadId }) {
  const { me } = useAuth();
  const thread = useResource(threadId ? `/chat/threads/${threadId}` : null);
  const messages = useResource(threadId ? `/chat/threads/${threadId}/messages?limit=100` : null, { pollMs: 5000 });
  const [body, setBody] = useState("");
  const [error, setError] = useState(null);
  const logRef = useRef(null);
  const list = messages.data?.results || [];
  const lastId = list.length ? list[list.length - 1].id : null;

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    if (lastId) api.post(`/chat/threads/${threadId}/read`, { last_read_message_id: lastId }).catch(() => {});
  }, [lastId, threadId]);

  async function send(e) {
    e.preventDefault();
    if (!body.trim()) return;
    try {
      await api.post(`/chat/threads/${threadId}/messages`, { body });
      setBody("");
      setError(null);
      messages.refetch();
    } catch (err) {
      setError(err);
    }
  }

  if (!threadId) return <EmptyState title="No conversation yet" />;
  const closed = messages.data?.is_closed;
  return (
    <div className="chat">
      {thread.data && (
        <div className="small muted" style={{ paddingBottom: 8, borderBottom: "1px solid var(--color-border)" }}>
          <span className="strong" style={{ color: "var(--color-text)" }}>{thread.data.subject}</span>
          <div className="xs">With {thread.data.participants.filter((p) => p.id !== me.organization?.id).map((p) => p.legal_name).join(", ")}</div>
        </div>
      )}
      <div className="chat-log" ref={logRef} aria-live="polite">
        {messages.loading && !messages.data && <span className="spinner" />}
        {list.length === 0 && messages.data && <p className="muted small" style={{ textAlign: "center", padding: 24 }}>No messages yet. Use this thread for special requirements and negotiation.</p>}
        {list.map((m) => {
          const mine = m.sender_organization.id === me.organization?.id;
          return (
            <div key={m.id} className={`msg ${mine ? "mine" : ""}`}>
              <div className="meta">{mine ? "You" : m.sender_organization.legal_name} · {formatDateTime(m.created_at)}</div>
              {m.body}
            </div>
          );
        })}
      </div>
      <ErrorAlert error={error} />
      {closed ? (
        <p className="small muted" style={{ textAlign: "center", paddingTop: 8 }}>This conversation is closed.</p>
      ) : (
        <form className="chat-input" onSubmit={send}>
          <input className="input" aria-label="Message" placeholder="Write a message…" value={body} onChange={(e) => setBody(e.target.value)} maxLength={5000} />
          <Button type="submit" icon={Send} aria-label="Send" />
        </form>
      )}
    </div>
  );
}

export function Timeline({ entries }) {
  if (!entries?.length) return <EmptyState title="No activity yet" />;
  return (
    <ul className="timeline">
      {entries.map((e) => (
        <li key={e.id}>
          <div className="small strong">{humanize(e.action.replace(/\./g, " · "))}</div>
          <div className="xs muted">
            {e.actor ? e.actor.display_name || e.actor.email : "System"} · {formatDateTime(e.created_at)} ({relativeTime(e.created_at)})
            {e.from_state && e.to_state ? ` · ${humanize(e.from_state)} → ${humanize(e.to_state)}` : ""}
          </div>
        </li>
      ))}
    </ul>
  );
}
