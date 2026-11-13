import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Button, Card, DataTable, DefinitionList, ErrorAlert, Input, Loader, PageHeader, StatusBadge, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api, openFile } from "../../lib/api";
import { humanize } from "../../lib/format";

export default function AdminOrganizationDetail() {
  const { id } = useParams();
  const org = useResource(`/admin/organizations/${id}`);
  const [reason, setReason] = useState("");
  const [user, setUser] = useState({ email: "", display_name: "" });
  const act = useAction(async (path, body) => {
    await api.post(path, body);
    setReason("");
    setUser({ email: "", display_name: "" });
    org.refetch();
  });
  return (
    <Loader resource={org}>
      {(o) => (
        <div className="stack">
          <PageHeader back={<Link to="/admin/organizations" className="row small"><ArrowLeft size={16} aria-hidden /> Organizations</Link>}
            title={<span className="row">{o.legal_name} <StatusBadge status={o.verification_status} /></span>} sub={humanize(o.type)} />
          <div className="grid grid-main-side">
            <div className="stack">
              <Card title="Details">
                <DefinitionList items={[
                  ["Trading name", o.trade_name], ["Registration", o.registration_number], ["Tax ID", o.tax_id],
                  ["Address", [o.address_line1, o.address_line2, o.city, o.postal_code, o.country_code].filter(Boolean).join(", ")],
                  ["Email", o.email], ["Phone", o.phone], ["Website", o.website],
                  ["Ports", o.ports.map((p) => p.name).join(", ")], ["Services", o.services.map((s) => s.name).join(", ") || "—"],
                ]} />
              </Card>
              <Card title="Members">
                <DataTable rows={o.members} columns={[
                  { key: "email", label: "User", render: (m) => <Link to={`/admin/users/${m.id}`}>{m.display_name || m.email}</Link> },
                  { key: "status", label: "Status", render: (m) => <StatusBadge status={m.status} /> },
                  { key: "primary", label: "Primary", render: (m) => (m.is_primary_contact ? "Yes" : "") },
                ]} />
                <div className="grid grid-2" style={{ marginTop: 12 }}>
                  <Input label="Add user (Google email)" type="email" value={user.email} onChange={(e) => setUser({ ...user, email: e.target.value })} />
                  <Input label="Name" value={user.display_name} onChange={(e) => setUser({ ...user, display_name: e.target.value })} />
                </div>
                <div style={{ marginTop: 8 }}><Button variant="secondary" disabled={!user.email} busy={act.busy} onClick={() => act.run(`/admin/organizations/${o.id}/users`, user)}>Add pre-approved user</Button></div>
              </Card>
              <Card title="Documents">
                {o.documents.length ? o.documents.map((d) => (
                  <div key={d.id} className="row-between small" style={{ padding: "6px 0" }}>
                    <Button variant="ghost" size="sm" onClick={() => openFile(d.file)}>{humanize(d.document_type)}</Button>
                    <StatusBadge status={d.status} />
                  </div>
                )) : <p className="small muted">No documents.</p>}
              </Card>
            </div>
            <Card title="Verification">
              <div className="stack-sm">
                <Textarea label="Note / reason" value={reason} onChange={(e) => setReason(e.target.value)} />
                {o.verification_status === "PENDING_REVIEW" && (
                  <>
                    <Button variant="cta" busy={act.busy} onClick={() => act.run(`/admin/organizations/${o.id}/approve`, { note: reason })}>Approve</Button>
                    <Button variant="danger" disabled={!reason.trim()} busy={act.busy} onClick={() => act.run(`/admin/organizations/${o.id}/reject`, { reason })}>Reject</Button>
                  </>
                )}
                {o.verification_status === "APPROVED" && <Button variant="danger" busy={act.busy} onClick={() => act.run(`/admin/organizations/${o.id}/suspend`, { reason })}>Suspend organization</Button>}
                {o.verification_status === "SUSPENDED" && <Button busy={act.busy} onClick={() => act.run(`/admin/organizations/${o.id}/reinstate`, { reason })}>Reinstate</Button>}
                <ErrorAlert error={act.error} />
              </div>
            </Card>
          </div>
        </div>
      )}
    </Loader>
  );
}
