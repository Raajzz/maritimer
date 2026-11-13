import { FileDown, History } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { LineEditor, LineItemsTable, VarianceTable } from "../../../components/domain";
import { Alert, Badge, Button, Card, DataTable, EmptyState, ErrorAlert, Input, Modal, Money, Spinner, StatusBadge, Textarea } from "../../../components/ui";
import { useAction } from "../../../hooks/useAction";
import { useResource } from "../../../hooks/useResource";
import { api, openDocument } from "../../../lib/api";
import { formatDate, formatDateTime } from "../../../lib/format";

function DisputeModal({ line, currency, onClose, onDone }) {
  const [reason, setReason] = useState("");
  const [amount, setAmount] = useState("");
  const open = useAction(async () => {
    await api.post("/disputes", { line_item_id: line.id, reason, disputed_amount: amount || null });
    onDone();
  });
  return (
    <Modal
      title={`Dispute line ${line.line_no}`}
      onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="cta" busy={open.busy} disabled={!reason.trim()} onClick={() => open.run()}>Open dispute</Button></>}
    >
      <p className="small">{line.description} · <Money value={line.amount} currency={currency} /></p>
      <Textarea label="What is wrong with this line?" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. GST should be 12%, not 18%" />
      <Input label={`Amount you believe is correct (${currency}, optional)`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} />
      <ErrorAlert error={open.error} />
    </Modal>
  );
}

function NoteModal({ title, label, cta = "Confirm", required = true, onClose, onSubmit }) {
  const [note, setNote] = useState("");
  const act = useAction(async () => {
    await onSubmit(note);
    onClose();
  });
  return (
    <Modal title={title} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button busy={act.busy} disabled={required && !note.trim()} onClick={() => act.run()}>{cta}</Button></>}>
      <Textarea label={label} value={note} onChange={(e) => setNote(e.target.value)} />
      <ErrorAlert error={act.error} />
    </Modal>
  );
}

function Versions({ portCallId, kind }) {
  const versions = useResource(`/port-calls/${portCallId}/${kind.toLowerCase()}/versions`);
  if (!versions.data || versions.data.length < 2) return null;
  return (
    <Card title={<span className="row"><History size={18} aria-hidden /> Version history</span>}>
      <DataTable
        rows={versions.data}
        columns={[
          { key: "reference", label: "Reference", render: (v) => <Link to={`/accounts/${v.id}`} className="mono">{v.reference}</Link> },
          { key: "status", label: "Status", render: (v) => <StatusBadge status={v.status} /> },
          { key: "total", label: "Total", num: true, render: (v) => <Money value={v.total} /> },
          { key: "date", label: "Issued", render: (v) => formatDate(v.issued_at) },
        ]}
      />
    </Card>
  );
}

/** PDA or FDA tab for a port call. Buttons are driven by the server's `allowed_actions`. */
export default function AccountTab({ pc, kind, onChanged }) {
  const path = `/port-calls/${pc.id}/${kind.toLowerCase()}`;
  const account = useResource(path);
  const pda = useResource(kind === "FDA" ? `/port-calls/${pc.id}/pda` : null);
  const [modal, setModal] = useState(null);
  const [warnings, setWarnings] = useState([]);
  const can = (a) => pc.allowed_actions.includes(a);
  const k = kind.toLowerCase();

  const refresh = () => {
    account.refetch();
    onChanged();
  };
  const act = useAction(async (fn) => {
    await fn();
    refresh();
  });
  const post = (url, body) => act.run(() => api.post(url, body));

  const missing = account.error?.code === "not_found";
  if (account.loading && !account.data) return <Spinner />;
  if (account.error && !missing) return <ErrorAlert error={account.error} />;

  const acc = missing ? null : account.data;
  const disputedLineIds = new Set((acc?.disputes || []).filter((d) => d.is_live).map((d) => d.line_item_id));
  const startActions = (
    <div className="stack">
      {kind === "PDA" && can("pda.create") && (
        <Button variant="cta" busy={act.busy} onClick={() => post(path, {})}>{acc ? "Start revised PDA" : "Prepare PDA"}</Button>
      )}
      {kind === "FDA" && can("fda.generate") && (
        <Button variant="cta" busy={act.busy} onClick={() => act.run(async () => setWarnings((await api.post(`${path}/generate`, {})).warnings || []))}>
          {acc ? "Rebuild FDA from invoices" : "Generate FDA from invoices"}
        </Button>
      )}
    </div>
  );

  if (!acc) {
    return (
      <Card>
        <EmptyState title={`No ${kind} yet`}>
          {kind === "PDA" ? "The agent prepares the proforma estimate after accepting the request." : "The agent builds the final account from vendor invoices after departure."}
        </EmptyState>
        {startActions}
        <ErrorAlert error={act.error} />
      </Card>
    );
  }

  const isDraft = acc.status === "DRAFT";
  return (
    <div className="stack">
      <Card
        title={<span className="row">{acc.reference} <StatusBadge status={acc.status} /></span>}
        actions={<Button variant="secondary" size="sm" icon={FileDown} onClick={() => act.run(() => openDocument(`/disbursement-accounts/${acc.id}/pdf`))}>{isDraft ? "Preview PDF" : "PDF"}</Button>}
      >
        <div className="stack">
          <div className="row small muted" style={{ gap: 16 }}>
            <span>Version {acc.version}</span>
            <span>Prepared by {acc.prepared_by?.display_name || acc.prepared_by?.email}</span>
            {acc.issued_at && <span>Issued {formatDateTime(acc.issued_at)}</span>}
            {acc.owner_responded_at && <span>Owner responded {formatDateTime(acc.owner_responded_at)}</span>}
          </div>
          {acc.status === "REJECTED" && <Alert tone="error"><strong>Rejected by owner:</strong> {acc.owner_response_note}</Alert>}
          {acc.owner_response_note && acc.status !== "REJECTED" && <Alert tone="info">Owner note: {acc.owner_response_note}</Alert>}
          {warnings.map((w) => <Alert key={w} tone="warn">{w}</Alert>)}
          {act.error?.code === "fx_rate_missing" && (
            <Alert tone="warn">
              Missing FX rates: {(act.error.details.missing_pairs || []).join(", ")}. <Link to="/fx-rates">Record the rate</Link> dated on or before departure, then try again.
            </Alert>
          )}
          {isDraft && can(`${k}.edit`) ? (
            <LineEditor key={acc.id + acc.line_items.length} account={acc} pdaLines={pda.data?.line_items} onSaved={() => refresh()} />
          ) : (
            <LineItemsTable account={acc} disputedLineIds={disputedLineIds} onDispute={kind === "FDA" && can("dispute.open") ? (line) => setModal({ type: "dispute", line }) : undefined} />
          )}
          {acc.fx_policy_note && <p className="xs muted">FX: {acc.fx_policy_note}</p>}
          {acc.notes && <p className="small">{acc.notes}</p>}
          <ErrorAlert error={act.error?.code === "fx_rate_missing" ? null : act.error} />
          <div className="row">
            {can(`${k}.issue`) && <Button variant="cta" busy={act.busy} onClick={() => post(`/disbursement-accounts/${acc.id}/issue`)}>Issue {kind} to owner</Button>}
            {can("pda.approve") && kind === "PDA" && <Button variant="cta" busy={act.busy} onClick={() => post(`/disbursement-accounts/${acc.id}/approve`, { note: "" })}>Approve PDA</Button>}
            {can("pda.reject") && kind === "PDA" && <Button variant="danger" onClick={() => setModal({ type: "reject" })}>Reject</Button>}
            {can("fda.accept") && kind === "FDA" && <Button variant="secondary" busy={act.busy} onClick={() => post(`/disbursement-accounts/${acc.id}/accept`, { note: "" })}>Accept FDA</Button>}
            {can(`${k}.revise`) && <Button variant="secondary" busy={act.busy} onClick={() => post(`/disbursement-accounts/${acc.id}/revise`)}>Revise</Button>}
            {can("fda.finalize") && kind === "FDA" && <Button variant="primary" busy={act.busy} onClick={() => setModal({ type: "finalize" })}>Finalize FDA</Button>}
            {can("fda.discard") && kind === "FDA" && <Button variant="ghost" busy={act.busy} onClick={() => post(`/disbursement-accounts/${acc.id}/discard`)}>Discard draft</Button>}
            {kind === "PDA" && can("pda.create") && startActions}
            {kind === "FDA" && can("fda.generate") && startActions}
          </div>
          {kind === "FDA" && pc.status === "DISPUTED" && pc.my_role === "AGENT" && (
            <Alert tone="warn">Open disputes block finalization. Resolve them on the Disputes tab.</Alert>
          )}
        </div>
      </Card>

      {acc.variance && (
        <Card title="Variance against the PDA">
          <VarianceTable variance={acc.variance} />
        </Card>
      )}

      {acc.disputes?.length > 0 && (
        <Card title="Disputes on this FDA">
          <div className="stack-sm">
            {acc.disputes.map((d) => (
              <Link key={d.id} to={`/disputes/${d.id}`} className="row-between card card-link" style={{ padding: 12 }}>
                <span className="small"><span className="mono strong">{d.reference}</span> · {d.line_description}</span>
                <StatusBadge status={d.status} />
              </Link>
            ))}
          </div>
        </Card>
      )}

      <Versions portCallId={pc.id} kind={kind} />

      {modal?.type === "dispute" && <DisputeModal line={modal.line} currency={acc.currency_code} onClose={() => setModal(null)} onDone={() => { setModal(null); refresh(); }} />}
      {modal?.type === "reject" && (
        <NoteModal title="Reject PDA" label="Why are you rejecting it? The agent will revise." cta="Reject PDA" onClose={() => setModal(null)}
          onSubmit={async (note) => { await api.post(`/disbursement-accounts/${acc.id}/reject`, { note }); refresh(); }} />
      )}
      {modal?.type === "finalize" && (
        <Modal title="Finalize FDA" onClose={() => setModal(null)}
          footer={<><Button variant="secondary" onClick={() => setModal(null)}>Cancel</Button><Button busy={act.busy} onClick={async () => { await post(`/disbursement-accounts/${acc.id}/finalize`); setModal(null); }}>Finalize</Button></>}>
          <p>Finalizing locks the FDA at <strong><Money value={acc.total} /></strong> and creates the settlement against confirmed advances. This cannot be undone.</p>
          <Badge tone="cta">No open disputes may remain</Badge>
          <ErrorAlert error={act.error} />
        </Modal>
      )}
    </div>
  );
}
