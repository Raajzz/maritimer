import { ArrowLeft, MessageSquare } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { Alert, Button, Card, DefinitionList, ErrorAlert, Loader, PageHeader, StatusBadge, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { api } from "../../lib/api";
import { formatDateTime, humanize } from "../../lib/format";

export default function RequestDetail() {
  const { id } = useParams();
  const { me } = useAuth();
  const navigate = useNavigate();
  const resource = useResource(`/requests/${id}`);
  const [note, setNote] = useState("");
  const act = useAction(async (verb) => {
    const result = await api.post(`/requests/${id}/${verb}`, { note });
    if (verb === "accept" && result.request_type === "PORT_CALL" && result.port_call) navigate(`/port-calls/${result.port_call.id}`);
    else resource.refetch();
  });
  return (
    <Loader resource={resource}>
      {(r) => {
        const incoming = r.to_organization.id === me.organization?.id;
        const outgoing = r.from_organization.id === me.organization?.id;
        const d = r.details;
        return (
          <div className="stack">
            <PageHeader
              back={<Link to="/requests" className="row small"><ArrowLeft size={16} aria-hidden /> Requests</Link>}
              title={<span className="row">{r.subject || humanize(r.request_type)} <StatusBadge status={r.status} /></span>}
              sub={<span><span className="mono">{r.reference}</span> · {humanize(r.request_type)} · {r.from_organization.legal_name} → {r.to_organization.legal_name}</span>}
            />
            <div className="grid grid-main-side">
              <Card title="Request">
                <div className="stack">
                  {d && (
                    <DefinitionList items={[
                      ["Vessel", `${d.vessel.name}${d.vessel.imo_number ? ` · IMO ${d.vessel.imo_number}` : ""}`],
                      ["Port", d.port.name],
                      ["ETA", formatDateTime(d.eta)],
                      ["ETD", formatDateTime(d.etd)],
                      ["Cargo", `${d.cargo_type.name}${d.cargo_description ? ` · ${d.cargo_description}` : ""}${d.cargo_quantity ? ` · ${d.cargo_quantity} ${d.cargo_unit}` : ""}`],
                    ]} />
                  )}
                  {r.port_call && r.request_type === "VENDOR_SERVICE" && <p className="small">For port call <Link to={`/port-calls/${r.port_call.id}`}>{r.port_call.reference}</Link></p>}
                  <div>
                    <div className="small strong">Services</div>
                    <ul className="small" style={{ margin: "4px 0 0", paddingLeft: 18 }}>
                      {r.services.map((s) => <li key={s.service_category.id}>{s.service_category.name}{s.quantity ? ` · ${s.quantity} ${s.unit}` : ""}{s.notes ? ` · ${s.notes}` : ""}</li>)}
                      {!r.services.length && <li className="muted">None listed</li>}
                    </ul>
                  </div>
                  {r.message && <div><div className="small strong">Notes</div><p className="small" style={{ whiteSpace: "pre-wrap" }}>{r.message}</p></div>}
                  {r.response_note && <Alert tone="info">Response: {r.response_note}</Alert>}
                </div>
              </Card>
              <Card title="Actions">
                <div className="stack-sm">
                  {incoming && r.status === "PENDING" && (
                    <>
                      <Textarea label="Note (optional)" value={note} onChange={(e) => setNote(e.target.value)} />
                      <Button variant="cta" busy={act.busy} onClick={() => act.run("accept")}>Accept</Button>
                      <Button variant="danger" busy={act.busy} onClick={() => act.run("decline")}>Decline</Button>
                    </>
                  )}
                  {outgoing && r.status === "PENDING" && <Button variant="secondary" busy={act.busy} onClick={() => act.run("withdraw")}>Withdraw request</Button>}
                  {r.port_call && r.request_type === "PORT_CALL" && <Button onClick={() => navigate(`/port-calls/${r.port_call.id}`)}>Open port call</Button>}
                  {r.chat_thread_id && me.user.role !== "ADMIN" && <Button variant="secondary" icon={MessageSquare} onClick={() => navigate(`/chat/${r.chat_thread_id}`)}>Open conversation</Button>}
                  {me.user.role === "MERCHANT" && r.status === "ACCEPTED" && <Button variant="secondary" onClick={() => navigate(`/invoices/new?request=${r.id}`)}>Create invoice</Button>}
                  {r.status !== "PENDING" && <p className="xs muted">Responded {formatDateTime(r.responded_at)}</p>}
                  <ErrorAlert error={act.error} />
                </div>
              </Card>
            </div>
          </div>
        );
      }}
    </Loader>
  );
}
