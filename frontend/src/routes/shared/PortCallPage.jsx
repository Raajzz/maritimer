import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ChatPanel, Timeline } from "../../components/domain";
import { Alert, Button, Card, DefinitionList, ErrorAlert, Input, Loader, Modal, Money, PageHeader, StatusBadge, Tabs, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { api } from "../../lib/api";
import { formatDateTime, fromLocalInput, humanize, toLocalInput } from "../../lib/format";
import AccountTab from "./tabs/AccountTab";
import { DisputesTab, DocumentsTab, InvoicesTab, PaymentsTab, RateModal, VendorsTab } from "./tabs/OtherTabs";

const STEPS = ["PDA_PENDING", "PDA_SENT", "PDA_APPROVED", "ADVANCE_RECEIVED", "IN_PORT", "DEPARTED", "FDA_ISSUED", "FDA_FINAL", "SETTLED", "CLOSED"];

function Progress({ status }) {
  const idx = STEPS.indexOf(status === "DISPUTED" ? "FDA_ISSUED" : status);
  if (status === "CANCELLED") return <Alert tone="error">This port call was cancelled.</Alert>;
  return (
    <div aria-label="Progress" style={{ display: "grid", gridTemplateColumns: `repeat(${STEPS.length}, 1fr)`, gap: 4 }}>
      {STEPS.map((s, i) => (
        <div key={s} title={humanize(s)} style={{ height: 6, borderRadius: 3, background: i <= idx ? (status === "DISPUTED" && i === idx ? "var(--color-cta)" : "var(--color-accent)") : "var(--color-border)" }} />
      ))}
    </div>
  );
}

function TimeModal({ title, field, onClose, onSubmit }) {
  const [value, setValue] = useState(toLocalInput(new Date().toISOString()));
  const act = useAction(async () => { await onSubmit({ [field]: fromLocalInput(value) }); onClose(); });
  return (
    <Modal title={title} onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="cta" busy={act.busy} onClick={() => act.run()}>Save</Button></>}>
      <Input label={field === "ata" ? "Actual time of arrival" : "Actual time of departure"} type="datetime-local" value={value} onChange={(e) => setValue(e.target.value)} />
      <ErrorAlert error={act.error} />
    </Modal>
  );
}

function EditModal({ pc, onClose, onSubmit }) {
  const [form, setForm] = useState({ eta: toLocalInput(pc.eta), etd: toLocalInput(pc.etd), berth: pc.berth || "", notes: pc.notes || "" });
  const act = useAction(async () => { await onSubmit({ ...form, eta: fromLocalInput(form.eta), etd: fromLocalInput(form.etd) }); onClose(); });
  const bind = (n) => ({ name: n, value: form[n], onChange: (e) => setForm({ ...form, [n]: e.target.value }) });
  return (
    <Modal title="Update port call" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button busy={act.busy} onClick={() => act.run()}>Save</Button></>}>
      <div className="grid grid-2">
        <Input label="ETA" type="datetime-local" {...bind("eta")} />
        <Input label="ETD" type="datetime-local" {...bind("etd")} />
      </div>
      <Input label="Berth" {...bind("berth")} />
      <Textarea label="Notes" {...bind("notes")} />
      <ErrorAlert error={act.error} />
    </Modal>
  );
}

function CancelModal({ onClose, onSubmit }) {
  const [reason, setReason] = useState("");
  const act = useAction(async () => { await onSubmit({ reason }); onClose(); });
  return (
    <Modal title="Cancel port call" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Keep it</Button><Button variant="danger" busy={act.busy} disabled={!reason.trim()} onClick={() => act.run()}>Cancel port call</Button></>}>
      <p className="small">The current PDA is voided, pending vendor requests are withdrawn and chats close. Any confirmed advance must be refunded separately.</p>
      <Textarea label="Reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      <ErrorAlert error={act.error} />
    </Modal>
  );
}

function Overview({ pc, onAction }) {
  const [modal, setModal] = useState(null);
  const can = (a) => pc.allowed_actions.includes(a);
  const act = useAction(async (path, body) => { await api.post(path, body); onAction(); });
  const patch = async (body) => { await api.patch(`/port-calls/${pc.id}`, body); onAction(); };
  const restricted = pc.my_role === "MERCHANT";
  return (
    <div className="grid grid-main-side">
      <div className="stack">
        <Card title="Voyage">
          <DefinitionList items={[
            ["Vessel", `${pc.vessel.name}${pc.vessel.imo_number ? ` · IMO ${pc.vessel.imo_number}` : ""}`],
            ["Type", humanize(pc.vessel.vessel_type)],
            ["Port", `${pc.port.name}${pc.port.unlocode ? ` (${pc.port.unlocode})` : ""}`],
            ["Cargo", pc.cargo_type?.name],
            ["ETA / ETD", `${formatDateTime(pc.eta)} → ${formatDateTime(pc.etd)}`],
            ["Arrived", formatDateTime(pc.ata)],
            ["Departed", formatDateTime(pc.atd)],
            ["Berth", pc.berth || "—"],
            !restricted && ["Owner", pc.owner?.legal_name],
            ["Agent", pc.agent.legal_name],
          ]} />
          {pc.notes && <p className="small" style={{ marginTop: 12, whiteSpace: "pre-wrap" }}>{pc.notes}</p>}
          {pc.cancelled_reason && <Alert tone="error">Cancelled: {pc.cancelled_reason}</Alert>}
        </Card>
        {!restricted && (
          <Card title="Money">
            <DefinitionList items={[
              ["PDA", pc.pda ? <span><Money value={pc.pda.total} /> · <StatusBadge status={pc.pda.status} /></span> : "—"],
              ["Advance received", <Money key="adv" value={pc.advance_total} />],
              ["FDA", pc.fda ? <span><Money value={pc.fda.total} /> · <StatusBadge status={pc.fda.status} /></span> : "—"],
              ["Settlement", pc.settlement ? <span><StatusBadge status={pc.settlement.direction} /> outstanding <Money value={pc.settlement.outstanding} /></span> : "—"],
              ["Open disputes", pc.open_disputes],
            ]} />
          </Card>
        )}
      </div>
      <Card title="Actions">
        <div className="stack-sm">
          {can("arrive") && <Button variant="cta" onClick={() => setModal("arrive")}>Record arrival</Button>}
          {can("depart") && <Button variant="cta" onClick={() => setModal("depart")}>Record departure</Button>}
          {can("close") && <Button variant="primary" busy={act.busy} onClick={() => act.run(`/port-calls/${pc.id}/close`)}>Close port call</Button>}
          {can("rate") && <Button variant="cta" onClick={() => setModal("rate")}>Rate the agent</Button>}
          {can("edit") && <Button variant="secondary" onClick={() => setModal("edit")}>Update ETA / berth</Button>}
          {can("cancel") && <Button variant="danger" onClick={() => setModal("cancel")}>Cancel port call</Button>}
          {!pc.allowed_actions.length && <p className="small muted">Nothing needs your action right now.</p>}
          {pc.allowed_actions.some((a) => a.startsWith("pda.")) && <p className="small muted">PDA actions are on the PDA tab.</p>}
          {pc.allowed_actions.some((a) => a.startsWith("fda.") || a.startsWith("dispute.")) && <p className="small muted">FDA and dispute actions are on the FDA tab.</p>}
          {pc.allowed_actions.some((a) => a.startsWith("advance.") || a.startsWith("settlement.") || a === "payment.confirm") && <p className="small muted">Payments are on the Payments tab.</p>}
          <ErrorAlert error={act.error} />
        </div>
      </Card>
      {modal === "arrive" && <TimeModal title="Record arrival" field="ata" onClose={() => setModal(null)} onSubmit={(b) => api.post(`/port-calls/${pc.id}/arrive`, b).then(onAction)} />}
      {modal === "depart" && <TimeModal title="Record departure" field="atd" onClose={() => setModal(null)} onSubmit={(b) => api.post(`/port-calls/${pc.id}/depart`, b).then(onAction)} />}
      {modal === "edit" && <EditModal pc={pc} onClose={() => setModal(null)} onSubmit={patch} />}
      {modal === "cancel" && <CancelModal onClose={() => setModal(null)} onSubmit={(b) => api.post(`/port-calls/${pc.id}/cancel`, b).then(onAction)} />}
      {modal === "rate" && <RateModal pc={pc} onClose={() => setModal(null)} onDone={() => { setModal(null); onAction(); }} />}
    </div>
  );
}

function TimelineTab({ pc }) {
  const timeline = useResource(`/port-calls/${pc.id}/timeline?page_size=100`);
  return <Card title="Timeline"><Loader resource={timeline}>{(page) => <Timeline entries={page.results} />}</Loader></Card>;
}

export default function PortCallPage() {
  const { id } = useParams();
  const { me } = useAuth();
  const [params, setParams] = useSearchParams();
  const resource = useResource(`/port-calls/${id}`, { pollMs: 60000 });
  const tab = params.get("tab") || "overview";
  const setTab = (t) => setParams({ tab: t }, { replace: true });

  return (
    <Loader resource={resource}>
      {(data) => {
        const pc = { ...data, my_org_id: me.organization?.id };
        const role = pc.my_role;
        const money = role === "OWNER" || role === "AGENT" || role === "ADMIN";
        const tabs = [
          { id: "overview", label: "Overview" },
          money && { id: "pda", label: "PDA", count: pc.allowed_actions.some((a) => a.startsWith("pda.")) ? 1 : 0 },
          (role === "AGENT" || role === "MERCHANT" || role === "ADMIN") && { id: "vendors", label: "Vendors" },
          { id: "invoices", label: "Invoices" },
          money && { id: "fda", label: "FDA", count: pc.allowed_actions.some((a) => a.startsWith("fda.") || a.startsWith("dispute.")) ? 1 : 0 },
          money && { id: "payments", label: "Payments", count: pc.counts?.pending_payments || 0 },
          money && { id: "disputes", label: "Disputes", count: pc.open_disputes || 0 },
          role !== "ADMIN" && { id: "chat", label: role === "MERCHANT" ? "Chat with agent" : role === "OWNER" ? "Chat with agent" : "Chat with owner" },
          money && { id: "documents", label: "Documents" },
          money && { id: "timeline", label: "Timeline" },
        ].filter(Boolean);
        const refresh = () => resource.refetch();
        return (
          <div className="stack">
            <PageHeader
              back={<Link to="/port-calls" className="row small"><ArrowLeft size={16} aria-hidden /> Port calls</Link>}
              title={<span className="row" style={{ gap: 10 }}>{pc.vessel.name} <StatusBadge status={pc.status} /></span>}
              sub={<span className="mono">{pc.reference}</span>}
            />
            <Progress status={pc.status} />
            <Tabs tabs={tabs} active={tab} onChange={setTab} />
            {tab === "overview" && <Overview pc={pc} onAction={refresh} />}
            {tab === "pda" && <AccountTab key="pda" pc={pc} kind="PDA" onChanged={refresh} />}
            {tab === "fda" && <AccountTab key="fda" pc={pc} kind="FDA" onChanged={refresh} />}
            {tab === "vendors" && <VendorsTab pc={pc} />}
            {tab === "invoices" && <InvoicesTab pc={pc} />}
            {tab === "payments" && <PaymentsTab pc={pc} onChanged={refresh} />}
            {tab === "disputes" && <DisputesTab pc={pc} />}
            {tab === "chat" && (
              <Card>
                {role === "MERCHANT" ? (
                  pc.chat_thread_ids?.length ? <ChatPanel threadId={pc.chat_thread_ids[0]} /> : <p className="muted">No conversation yet.</p>
                ) : (
                  <ChatPanel threadId={pc.chat_thread_id} />
                )}
              </Card>
            )}
            {tab === "documents" && <DocumentsTab pc={pc} />}
            {tab === "timeline" && <TimelineTab pc={pc} />}
          </div>
        );
      }}
    </Loader>
  );
}
