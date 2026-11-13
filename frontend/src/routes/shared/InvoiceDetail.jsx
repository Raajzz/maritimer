import { ArrowLeft, FileDown } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Alert, Button, Card, DataTable, DefinitionList, ErrorAlert, Input, Loader, Modal, Money, PageHeader, StatusBadge, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { api, openFile } from "../../lib/api";
import { formatDate, formatDateTime, formatMoney } from "../../lib/format";

export default function InvoiceDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const resource = useResource(`/vendor-invoices/${id}`);
  const [modal, setModal] = useState(null);
  const [note, setNote] = useState("");
  const [bankRef, setBankRef] = useState("");
  const act = useAction(async (path, body) => {
    await api.post(path, body);
    setModal(null);
    resource.refetch();
  });
  const role = me.user.role;
  return (
    <Loader resource={resource}>
      {(inv) => (
        <div className="stack">
          <PageHeader
            back={<Link to={`/port-calls/${inv.port_call.id}?tab=invoices`} className="row small"><ArrowLeft size={16} aria-hidden /> {inv.port_call.reference}</Link>}
            title={<span className="row">Invoice {inv.invoice_number} <StatusBadge status={inv.status} /></span>}
            sub={`${inv.vendor.legal_name} → ${inv.agent.legal_name}`}
            actions={inv.file && <Button variant="secondary" icon={FileDown} onClick={() => openFile(inv.file)}>Open file</Button>}
          />
          <div className="grid grid-main-side">
            <Card title="Details">
              <DefinitionList items={[
                ["Service", inv.service_category.name],
                ["Issue date", formatDate(inv.issue_date)],
                ["Due date", formatDate(inv.due_date)],
                ["Subtotal", formatMoney(inv.subtotal_amount, inv.currency_code)],
                ["Tax", formatMoney(inv.tax_amount, inv.currency_code)],
                ["Total", <strong key="t"><Money value={inv.total} /></strong>],
                ["On FDA", inv.fda_line ? <Link key="f" to={`/accounts/${inv.fda_line.account_id}`}>FDA version {inv.fda_line.version}</Link> : "Not yet"],
                ["Paid", inv.payment ? `${formatMoney(inv.payment.amount.amount, inv.payment.amount.currency_code)} on ${formatDateTime(inv.payment.paid_at)}` : "—"],
              ]} />
              {inv.notes && <p className="small" style={{ marginTop: 12 }}>{inv.notes}</p>}
              {inv.review_note && <Alert tone={inv.status === "REJECTED" ? "error" : "info"}>Agent: {inv.review_note}</Alert>}
              {inv.lines.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <DataTable rowKey="line_no" rows={inv.lines} columns={[
                    { key: "description", label: "Description" },
                    { key: "quantity", label: "Qty", num: true },
                    { key: "unit_amount", label: "Unit", num: true, render: (l) => formatMoney(l.unit_amount, inv.currency_code) },
                    { key: "amount", label: "Amount", num: true, render: (l) => formatMoney(l.amount, inv.currency_code) },
                  ]} />
                </div>
              )}
            </Card>
            <Card title="Actions">
              <div className="stack-sm">
                {role === "MERCHANT" && inv.status === "DRAFT" && (
                  <>
                    {!inv.file && <Alert tone="warn">Attach the invoice file before issuing (edit from the port call's Invoices tab).</Alert>}
                    <Button variant="cta" busy={act.busy} disabled={!inv.file} onClick={() => act.run(`/vendor-invoices/${inv.id}/issue`)}>Issue to agent</Button>
                  </>
                )}
                {role === "MERCHANT" && inv.status === "REJECTED" && <Button variant="secondary" busy={act.busy} onClick={() => act.run(`/vendor-invoices/${inv.id}/reopen`)}>Reopen as draft</Button>}
                {role === "MERCHANT" && ["DRAFT", "ISSUED"].includes(inv.status) && <Button variant="ghost" busy={act.busy} onClick={() => act.run(`/vendor-invoices/${inv.id}/void`)}>Void</Button>}
                {role === "AGENT" && inv.status === "ISSUED" && (
                  <>
                    <Button variant="cta" busy={act.busy} onClick={() => act.run(`/vendor-invoices/${inv.id}/accept`, { note: "" })}>Accept</Button>
                    <Button variant="danger" onClick={() => setModal("reject")}>Reject</Button>
                  </>
                )}
                {role === "AGENT" && inv.status === "ACCEPTED" && <Button variant="primary" onClick={() => setModal("pay")}>Mark as paid</Button>}
                {!["DRAFT", "ISSUED", "REJECTED", "ACCEPTED"].includes(inv.status) && <p className="small muted">No actions.</p>}
                <ErrorAlert error={act.error} />
              </div>
            </Card>
          </div>
          {modal === "reject" && (
            <Modal title="Reject invoice" onClose={() => setModal(null)}
              footer={<><Button variant="secondary" onClick={() => setModal(null)}>Cancel</Button><Button variant="danger" disabled={!note.trim()} busy={act.busy} onClick={() => act.run(`/vendor-invoices/${inv.id}/reject`, { note })}>Reject</Button></>}>
              <Textarea label="What needs fixing?" value={note} onChange={(e) => setNote(e.target.value)} />
              <ErrorAlert error={act.error} />
            </Modal>
          )}
          {modal === "pay" && (
            <Modal title="Record payment to vendor" onClose={() => setModal(null)}
              footer={<><Button variant="secondary" onClick={() => setModal(null)}>Cancel</Button><Button busy={act.busy} onClick={() => act.run(`/vendor-invoices/${inv.id}/mark-paid`, { bank_reference: bankRef })}>Mark paid</Button></>}>
              <p className="small">Records a confirmed payment of {formatMoney(inv.total_amount, inv.currency_code)} to {inv.vendor.legal_name}.</p>
              <Input label="Bank reference" value={bankRef} onChange={(e) => setBankRef(e.target.value)} placeholder="NEFT / RTGS UTR" />
              <ErrorAlert error={act.error} />
            </Modal>
          )}
        </div>
      )}
    </Loader>
  );
}
