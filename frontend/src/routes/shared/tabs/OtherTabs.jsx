import { FileDown, Plus } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { Alert, Button, Card, CheckGroup, DataTable, EmptyState, ErrorAlert, Input, Loader, Modal, Money, Select, Stars, StatusBadge, Textarea } from "../../../components/ui";
import { useAction } from "../../../hooks/useAction";
import { useResource } from "../../../hooks/useResource";
import { api, openDocument, openFile, qs } from "../../../lib/api";
import { formatDate, formatDateTime, formatMoney, fromLocalInput, humanize, toLocalInput } from "../../../lib/format";

// ---- Vendors (agent ↔ merchant service requests) --------------------------------------

function RequestMerchantModal({ pc, onClose, onDone }) {
  const services = useResource("/service-categories?vendor_only=true");
  const [serviceIds, setServiceIds] = useState([]);
  const merchants = useResource(`/merchants${qs({ port_id: pc.port.id, service_category_id: serviceIds[0], page_size: 100 })}`);
  const [merchantId, setMerchantId] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const send = useAction(async () => {
    await api.post("/requests", {
      request_type: "VENDOR_SERVICE", to_organization_id: Number(merchantId), port_call_id: pc.id, subject, message,
      services: serviceIds.map((id) => ({ service_category_id: id })),
    });
    onDone();
  });
  return (
    <Modal title="Request a merchant" wide onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="cta" busy={send.busy} disabled={!merchantId || !serviceIds.length} onClick={() => send.run()}>Send request</Button></>}>
      <div className="field">
        <label>Services needed</label>
        <Loader resource={services}>{(list) => <CheckGroup options={list.map((s) => ({ value: s.id, label: s.name }))} value={serviceIds} onChange={setServiceIds} />}</Loader>
      </div>
      <Loader resource={merchants}>
        {(page) => (
          <Select label={`Merchant serving ${pc.port.name}`} placeholder={page.results.length ? "Choose a merchant…" : "No merchant matches"} value={merchantId}
            onChange={(e) => setMerchantId(e.target.value)}
            options={page.results.map((m) => ({ value: m.id, label: `${m.legal_name} — ${m.services.map((s) => s.name).join(", ")}` }))} />
        )}
      </Loader>
      <Input label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Fresh water 200 MT" />
      <Textarea label="Details" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Berth, timing, quantities, special requirements" />
      <ErrorAlert error={send.error} />
    </Modal>
  );
}

export function VendorsTab({ pc }) {
  const list = useResource(`/port-calls/${pc.id}/vendor-requests`);
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  return (
    <Card title="Vendor requests" actions={pc.allowed_actions.includes("vendor_request.create") && <Button icon={Plus} onClick={() => setOpen(true)}>Request a merchant</Button>}>
      <Loader resource={list}>
        {(rows) => (
          <DataTable rows={rows} onRowClick={(r) => navigate(`/requests/${r.id}`)}
            empty={<EmptyState title="No vendor requests yet">Ask merchants for pilotage, tugs, water, provisions and more.</EmptyState>}
            columns={[
              { key: "reference", label: "Ref", render: (r) => <span className="mono">{r.reference}</span> },
              { key: "subject", label: "Subject" },
              { key: "to", label: "Merchant", render: (r) => r.to_organization.legal_name },
              { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
              { key: "created", label: "Sent", render: (r) => formatDate(r.created_at) },
            ]} />
        )}
      </Loader>
      {open && <RequestMerchantModal pc={pc} onClose={() => setOpen(false)} onDone={() => { setOpen(false); list.refetch(); }} />}
    </Card>
  );
}

// ---- Invoices -----------------------------------------------------------------------------

export function InvoicesTab({ pc }) {
  const list = useResource(`/vendor-invoices?port_call_id=${pc.id}&page_size=100`);
  const navigate = useNavigate();
  return (
    <Card title="Vendor invoices" actions={pc.allowed_actions.includes("invoice.create") && <Button icon={Plus} onClick={() => navigate(`/invoices/new?port_call=${pc.id}`)}>New invoice</Button>}>
      <Loader resource={list}>
        {(page) => (
          <DataTable rows={page.results} onRowClick={(r) => navigate(`/invoices/${r.id}`)}
            empty={<EmptyState title="No invoices yet" />}
            columns={[
              { key: "invoice_number", label: "Invoice", render: (r) => <span className="mono">{r.invoice_number}</span> },
              { key: "vendor", label: "Vendor", render: (r) => r.vendor.legal_name },
              { key: "svc", label: "Service", render: (r) => r.service_category.name },
              { key: "date", label: "Date", render: (r) => formatDate(r.issue_date) },
              { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
              { key: "total", label: "Total", num: true, render: (r) => <Money value={r.total} /> },
            ]} />
        )}
      </Loader>
    </Card>
  );
}

// ---- Payments & settlement ------------------------------------------------------------------

function RecordPaymentModal({ pc, kind, suggested, onClose, onDone }) {
  const currencies = useResource("/currencies");
  const [form, setForm] = useState({ amount: suggested || "", currency_code: "USD", paid_at: toLocalInput(new Date().toISOString()), method: "BANK_TRANSFER", bank_reference: "" });
  const bind = (name) => ({ name, value: form[name], onChange: (e) => setForm({ ...form, [name]: e.target.value }) });
  const save = useAction(async () => {
    await api.post(`/port-calls/${pc.id}/payments`, { ...form, kind, paid_at: fromLocalInput(form.paid_at) });
    onDone();
  });
  const titles = { ADVANCE: "Record advance payment", BALANCE: "Record balance payment", REFUND: "Record refund to owner" };
  return (
    <Modal title={titles[kind]} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="cta" busy={save.busy} disabled={!form.amount} onClick={() => save.run()}>Record payment</Button></>}>
      <Alert tone="info">The receiving party confirms the payment once the funds arrive. Only confirmed payments count.</Alert>
      <div className="grid grid-2">
        <Input label="Amount" inputMode="decimal" {...bind("amount")} />
        <Select label="Currency" options={(currencies.data || [{ code: "USD" }]).map((c) => ({ value: c.code, label: c.code }))} {...bind("currency_code")} />
        <Input label="Value date" type="datetime-local" {...bind("paid_at")} />
        <Select label="Method" options={["BANK_TRANSFER", "CASH", "CHEQUE", "CARD", "OTHER"].map((m) => ({ value: m, label: humanize(m) }))} {...bind("method")} />
      </div>
      <Input label="Bank reference" {...bind("bank_reference")} placeholder="SWIFT / UTR / TT reference" />
      {form.currency_code !== "USD" && <p className="xs muted">Converted to USD at the latest recorded rate on the value date.</p>}
      <ErrorAlert error={save.error} />
    </Modal>
  );
}

export function PaymentsTab({ pc, onChanged }) {
  const payments = useResource(`/port-calls/${pc.id}/payments`);
  const hasSettlement = Boolean(pc.settlement);
  const settlement = useResource(hasSettlement ? `/port-calls/${pc.id}/settlement` : null);
  const [modal, setModal] = useState(null);
  const [forceNote, setForceNote] = useState("");
  const can = (a) => pc.allowed_actions.includes(a);
  const refresh = () => {
    payments.refetch();
    settlement.refetch();
    onChanged();
  };
  const act = useAction(async (fn) => {
    await fn();
    refresh();
  });
  const myOrg = pc.my_org_id;
  return (
    <div className="stack">
      {hasSettlement && (
        <Loader resource={settlement}>
          {(s) => (
            <Card title={<span className="row">Settlement {s.reference} <StatusBadge status={s.status} /></span>}
              actions={<Button variant="secondary" size="sm" icon={FileDown} onClick={() => act.run(() => openDocument(`/settlements/${s.id}/pdf`))}>Statement</Button>}>
              <div className="grid grid-4">
                <div className="kpi"><span className="label">Final FDA</span><span className="value"><Money value={s.fda_total} /></span></div>
                <div className="kpi"><span className="label">Advance received</span><span className="value"><Money value={s.advance_total} /></span></div>
                <div className="kpi">
                  <span className="label">{s.direction === "BALANCE_DUE" ? "Balance due from owner" : s.direction === "REFUND_DUE" ? "Refund due to owner" : "Balance"}</span>
                  <span className="value"><StatusBadge status={s.direction} /> {formatMoney(String(s.balance.amount).replace("-", ""), s.currency_code)}</span>
                </div>
                <div className="kpi"><span className="label">Outstanding</span><span className="value"><Money value={s.outstanding} /></span></div>
              </div>
              <div className="row" style={{ marginTop: 16 }}>
                {can("settlement.pay_balance") && <Button variant="cta" onClick={() => setModal({ kind: "BALANCE", suggested: s.outstanding.amount })}>Record balance payment</Button>}
                {can("settlement.record_refund") && <Button variant="cta" onClick={() => setModal({ kind: "REFUND", suggested: s.outstanding.amount })}>Record refund</Button>}
                {can("settlement.force_close") && s.status !== "CLOSED" && (
                  <div className="row">
                    <input className="input" style={{ width: 220 }} placeholder="Write-off note" value={forceNote} onChange={(e) => setForceNote(e.target.value)} aria-label="Write-off note" />
                    <Button variant="ghost" disabled={!forceNote} onClick={() => act.run(() => api.post(`/settlements/${s.id}/force-close`, { note: forceNote }))}>Close with write-off</Button>
                  </div>
                )}
              </div>
            </Card>
          )}
        </Loader>
      )}
      <Card title="Payments" actions={can("advance.record") && <Button variant="cta" icon={Plus} onClick={() => setModal({ kind: "ADVANCE", suggested: pc.pda?.total?.amount })}>Record advance</Button>}>
        <ErrorAlert error={act.error} />
        <Loader resource={payments}>
          {(rows) => (
            <DataTable rows={rows} empty={<EmptyState title="No payments yet" />}
              columns={[
                { key: "reference", label: "Ref", render: (p) => <span className="mono">{p.reference}</span> },
                { key: "kind", label: "Kind", render: (p) => humanize(p.kind) },
                { key: "date", label: "Value date", render: (p) => formatDate(p.paid_at) },
                { key: "parties", label: "From → to", render: (p) => `${p.payer.legal_name} → ${p.payee.legal_name}` },
                { key: "amount", label: "Amount", num: true, render: (p) => <Money value={p.amount} /> },
                { key: "usd", label: "USD", num: true, render: (p) => <Money value={p.settlement_amount} /> },
                { key: "status", label: "Status", render: (p) => <StatusBadge status={p.status} /> },
                {
                  key: "act", label: "",
                  render: (p) => p.status === "PENDING" && (
                    <div className="row">
                      {p.payee.id === myOrg && <Button size="sm" busy={act.busy} onClick={() => act.run(() => api.post(`/payments/${p.id}/confirm`))}>Confirm received</Button>}
                      {(p.payer.id === myOrg) && <Button size="sm" variant="ghost" onClick={() => act.run(() => api.post(`/payments/${p.id}/cancel`, { reason: "Recorded in error" }))}>Cancel</Button>}
                    </div>
                  ),
                },
              ]} />
          )}
        </Loader>
      </Card>
      {modal && <RecordPaymentModal pc={pc} kind={modal.kind} suggested={modal.suggested} onClose={() => setModal(null)} onDone={() => { setModal(null); refresh(); }} />}
    </div>
  );
}

// ---- Disputes, documents, rating -------------------------------------------------------------

export function DisputesTab({ pc }) {
  const list = useResource(`/disputes?port_call_id=${pc.id}&page_size=100`);
  const navigate = useNavigate();
  return (
    <Card title="Disputes">
      <Loader resource={list}>
        {(page) => (
          <DataTable rows={page.results} onRowClick={(d) => navigate(`/disputes/${d.id}`)}
            empty={<EmptyState title="No disputes">Owners can dispute individual FDA lines from the FDA tab.</EmptyState>}
            columns={[
              { key: "reference", label: "Ref", render: (d) => <span className="mono">{d.reference}</span> },
              { key: "line", label: "Line", render: (d) => d.line_description },
              { key: "amount", label: "Line amount", num: true, render: (d) => <Money value={d.line_amount} /> },
              { key: "status", label: "Status", render: (d) => <StatusBadge status={d.status} /> },
              { key: "created", label: "Opened", render: (d) => formatDateTime(d.created_at) },
            ]} />
        )}
      </Loader>
    </Card>
  );
}

export function DocumentsTab({ pc }) {
  const docs = useResource(`/port-calls/${pc.id}/documents`);
  return (
    <Card title="Documents">
      <p className="small muted" style={{ marginBottom: 12 }}>Issued and final PDAs, FDAs and settlement statements are generated once and kept unchanged. Accepted vendor invoices are listed with them.</p>
      <Loader resource={docs}>
        {(rows) => (
          <DataTable rowKey="key" rows={rows.map((r, i) => ({ ...r, key: i }))} empty={<EmptyState title="No documents yet">Open a PDA or FDA PDF to generate it.</EmptyState>}
            columns={[
              { key: "type", label: "Type", render: (d) => humanize(d.document_type) },
              { key: "reference", label: "Reference", render: (d) => <span className="mono">{d.reference}</span> },
              { key: "status", label: "Status", render: (d) => <StatusBadge status={d.entity_status} /> },
              { key: "date", label: "Date", render: (d) => formatDate(d.generated_at) },
              { key: "open", label: "", render: (d) => <Button size="sm" variant="secondary" icon={FileDown} onClick={() => openFile(d.file)}>Open</Button> },
            ]} />
        )}
      </Loader>
    </Card>
  );
}

export function RateModal({ pc, onClose, onDone }) {
  const [score, setScore] = useState(5);
  const [comment, setComment] = useState("");
  const save = useAction(async () => {
    await api.post(`/port-calls/${pc.id}/ratings`, { ratee_organization_id: pc.agent.id, score, comment });
    onDone();
  });
  return (
    <Modal title={`Rate ${pc.agent.legal_name}`} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="cta" busy={save.busy} onClick={() => save.run()}>Submit rating</Button></>}>
      <div className="row" role="radiogroup" aria-label="Score">
        {[1, 2, 3, 4, 5].map((n) => (
          <Button key={n} variant={n <= score ? "cta" : "secondary"} size="sm" aria-pressed={n === score} onClick={() => setScore(n)}>{n}</Button>
        ))}
        <Stars value={score} />
      </div>
      <Textarea label="Comment (shown on the agent's profile)" value={comment} onChange={(e) => setComment(e.target.value)} />
      <ErrorAlert error={save.error} />
    </Modal>
  );
}

export function MerchantJobLink({ pc }) {
  return pc.chat_thread_ids?.length ? <Link to={`/chat/${pc.chat_thread_ids[0]}`}>Open conversation</Link> : null;
}
