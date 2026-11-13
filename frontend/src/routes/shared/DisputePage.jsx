import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Alert, Button, Card, DefinitionList, ErrorAlert, Input, Loader, Modal, Money, PageHeader, Select, StatusBadge, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { api } from "../../lib/api";
import { formatDateTime, formatMoney, humanize } from "../../lib/format";

function ResolveModal({ dispute, onClose, onDone }) {
  const invoiceBacked = Boolean(dispute.line_item.vendor_invoice_id);
  const [form, setForm] = useState({ resolution_type: "EXPLAINED", note: "", adjusted_local_amount: dispute.line_item.local_amount, mode: invoiceBacked ? "CREDIT_LINE" : "EDIT_LINE" });
  const bind = (n) => ({ name: n, value: form[n], onChange: (e) => setForm({ ...form, [n]: e.target.value }) });
  const save = useAction(async () => {
    const body = { resolution_type: form.resolution_type, note: form.note };
    if (form.resolution_type === "ADJUSTED") Object.assign(body, { adjusted_local_amount: form.adjusted_local_amount, mode: form.mode });
    await api.post(`/disputes/${dispute.id}/resolve`, body);
    onDone();
  });
  return (
    <Modal title="Resolve dispute" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="cta" busy={save.busy} disabled={!form.note.trim()} onClick={() => save.run()}>Resolve</Button></>}>
      <Select label="Resolution" options={[{ value: "EXPLAINED", label: "Explained — no change to the amount" }, { value: "ADJUSTED", label: "Adjusted — change the amount" }]} {...bind("resolution_type")} />
      {form.resolution_type === "ADJUSTED" && (
        <>
          <Input label={`Correct amount (${dispute.line_item.local_currency_code})`} inputMode="decimal" {...bind("adjusted_local_amount")}
            hint={`Currently ${formatMoney(dispute.line_item.local_amount, dispute.line_item.local_currency_code)}. Converted at the line's FX rate.`} />
          <Select label="How" options={[
            ...(invoiceBacked ? [] : [{ value: "EDIT_LINE", label: "Edit the line" }]),
            { value: "CREDIT_LINE", label: "Add a credit / adjustment line" },
          ]} {...bind("mode")} />
          <Alert tone="info">A new FDA version is drafted with the change. Re-issue it to the owner afterwards.</Alert>
        </>
      )}
      <Textarea label="Explanation for the owner" {...bind("note")} />
      <ErrorAlert error={save.error} />
    </Modal>
  );
}

export default function DisputePage() {
  const { id } = useParams();
  const { me } = useAuth();
  const resource = useResource(`/disputes/${id}`);
  const [comment, setComment] = useState("");
  const [modal, setModal] = useState(null);
  const [note, setNote] = useState("");
  const act = useAction(async (path, body) => {
    await api.post(path, body);
    setComment("");
    setNote("");
    setModal(null);
    resource.refetch();
  });
  const role = me.user.role;
  return (
    <Loader resource={resource}>
      {(d) => {
        const live = d.status === "OPEN" || d.status === "UNDER_REVIEW";
        const cur = d.line_item.local_currency_code;
        return (
          <div className="stack">
            <PageHeader
              back={<Link to={`/port-calls/${d.port_call_id}?tab=disputes`} className="row small"><ArrowLeft size={16} aria-hidden /> {d.port_call_reference}</Link>}
              title={<span className="row">Dispute {d.reference} <StatusBadge status={d.status} /></span>}
              sub={d.line_description}
            />
            <div className="grid grid-main-side">
              <div className="stack">
                <Card title="History">
                  <ul className="timeline">
                    {d.events.map((e) => (
                      <li key={e.id}>
                        <div className="small strong">{humanize(e.event_type)}{e.to_status ? ` · ${humanize(e.to_status)}` : ""}</div>
                        <div className="xs muted">{e.actor.display_name || e.actor.email} · {formatDateTime(e.created_at)}</div>
                        {e.body && <p className="small" style={{ marginTop: 4, whiteSpace: "pre-wrap" }}>{e.body}</p>}
                      </li>
                    ))}
                  </ul>
                  {live && (
                    <div className="stack-sm" style={{ marginTop: 8 }}>
                      <Textarea label="Add a comment" value={comment} onChange={(e) => setComment(e.target.value)} />
                      <div><Button variant="secondary" disabled={!comment.trim()} busy={act.busy} onClick={() => act.run(`/disputes/${d.id}/comment`, { body: comment })}>Post comment</Button></div>
                    </div>
                  )}
                </Card>
              </div>
              <div className="stack">
                <Card title="Disputed line">
                  <DefinitionList items={[
                    ["FDA", `${d.line_item.account_reference}`],
                    ["Category", d.line_item.service_category],
                    ["Local amount", formatMoney(d.line_item.local_amount, cur)],
                    ["Amount", <Money key="a" value={d.line_amount} />],
                    ["Owner proposes", d.disputed_amount ? <Money key="p" value={d.disputed_amount} /> : "—"],
                    ["Resolution", d.resolution_type ? humanize(d.resolution_type) : "—"],
                    d.fda && ["Adjusted in", <Link key="f" to={`/accounts/${d.fda.id}`}>{d.fda.reference} ({humanize(d.fda.status)})</Link>],
                  ]} />
                  {d.resolution_note && <Alert tone="info">{d.resolution_note}</Alert>}
                </Card>
                <Card title="Actions">
                  <div className="stack-sm">
                    {role === "AGENT" && d.status === "OPEN" && <Button variant="secondary" busy={act.busy} onClick={() => act.run(`/disputes/${d.id}/acknowledge`)}>Acknowledge (under review)</Button>}
                    {role === "AGENT" && live && <Button variant="cta" onClick={() => setModal("resolve")}>Resolve</Button>}
                    {role === "AGENT" && live && <Button variant="danger" onClick={() => setModal("reject")}>Reject dispute</Button>}
                    {role === "OWNER" && live && <Button variant="secondary" busy={act.busy} onClick={() => act.run(`/disputes/${d.id}/withdraw`)}>Withdraw dispute</Button>}
                    {role === "OWNER" && d.status === "REJECTED" && d.reopen_count < 1 && <Button variant="cta" onClick={() => setModal("reopen")}>Reopen (once)</Button>}
                    {!live && !(role === "OWNER" && d.status === "REJECTED" && d.reopen_count < 1) && <p className="small muted">This dispute is closed.</p>}
                    <ErrorAlert error={act.error} />
                  </div>
                </Card>
              </div>
            </div>
            {modal === "resolve" && <ResolveModal dispute={d} onClose={() => setModal(null)} onDone={() => { setModal(null); resource.refetch(); }} />}
            {(modal === "reject" || modal === "reopen") && (
              <Modal title={modal === "reject" ? "Reject dispute" : "Reopen dispute"} onClose={() => setModal(null)}
                footer={<><Button variant="secondary" onClick={() => setModal(null)}>Cancel</Button>
                  <Button variant={modal === "reject" ? "danger" : "cta"} busy={act.busy} disabled={modal === "reject" && !note.trim()}
                    onClick={() => act.run(`/disputes/${d.id}/${modal}`, modal === "reject" ? { note } : { body: note })}>{modal === "reject" ? "Reject" : "Reopen"}</Button></>}>
                <Textarea label={modal === "reject" ? "Why is the charge correct?" : "Why are you reopening it?"} value={note} onChange={(e) => setNote(e.target.value)} />
                <ErrorAlert error={act.error} />
              </Modal>
            )}
          </div>
        );
      }}
    </Loader>
  );
}
