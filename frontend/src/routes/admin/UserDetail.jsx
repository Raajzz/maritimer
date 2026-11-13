import { ArrowLeft, FileText } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { Timeline } from "../../components/domain";
import { Alert, Button, Card, DefinitionList, ErrorAlert, Loader, PageHeader, StatusBadge, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api, openFile } from "../../lib/api";
import { humanize } from "../../lib/format";

export default function AdminUserDetail() {
  const { id } = useParams();
  const user = useResource(`/admin/users/${id}`);
  const [note, setNote] = useState("");
  const act = useAction(async (path, body) => {
    await api.post(path, body);
    setNote("");
    user.refetch();
  });
  return (
    <Loader resource={user}>
      {(u) => {
        const org = u.organization_detail;
        return (
          <div className="stack">
            <PageHeader back={<Link to="/admin/approvals" className="row small"><ArrowLeft size={16} aria-hidden /> Users</Link>}
              title={<span className="row">{u.display_name || u.email} <StatusBadge status={u.status} /></span>}
              sub={`${u.email} · ${humanize(u.role || "no role")}${u.linked ? "" : " · not signed in yet"}`} />
            <div className="grid grid-main-side">
              <div className="stack">
                {org ? (
                  <Card title={<span className="row">{org.legal_name} <StatusBadge status={org.verification_status} /></span>}
                    actions={<Link to={`/admin/organizations/${org.id}`} className="small">Organization</Link>}>
                    <DefinitionList items={[
                      ["Type", humanize(org.type)], ["Trading name", org.trade_name], ["Registration", org.registration_number], ["Tax ID", org.tax_id],
                      ["Address", [org.address_line1, org.city, org.postal_code, org.country_code].filter(Boolean).join(", ")],
                      ["Email / phone", [org.email, org.phone].filter(Boolean).join(" · ")],
                      ["Ports", u.coverage?.ports.map((p) => p.name).join(", ") || "—"],
                      ["Services", u.coverage?.services.map((s) => s.name).join(", ") || "—"],
                    ]} />
                    {u.profile?.description && <p className="small" style={{ marginTop: 12 }}>{u.profile.description}</p>}
                  </Card>
                ) : <Alert tone="info">This user has not created an organization yet.</Alert>}
                <Card title="Verification documents">
                  <div className="stack-sm">
                    {u.documents.map((d) => (
                      <div key={d.id} className="card" style={{ padding: 12 }}>
                        <div className="row-between">
                          <Button variant="ghost" size="sm" icon={FileText} onClick={() => openFile(d.file)}>{humanize(d.document_type)}{d.title ? ` · ${d.title}` : ""}</Button>
                          <StatusBadge status={d.status} />
                        </div>
                        {d.review_note && <div className="xs muted">Note: {d.review_note}</div>}
                        {d.status === "PENDING" && (
                          <div className="row" style={{ marginTop: 8 }}>
                            <Button size="sm" busy={act.busy} onClick={() => act.run(`/admin/documents/${d.id}/approve`, { note })}>Approve document</Button>
                            <Button size="sm" variant="danger" busy={act.busy} disabled={!note.trim()} onClick={() => act.run(`/admin/documents/${d.id}/reject`, { note })}>Reject document</Button>
                          </div>
                        )}
                      </div>
                    ))}
                    {!u.documents.length && <p className="small muted">No documents uploaded.</p>}
                    <p className="xs muted">Future: automated (AI) document checks will appear here as a second reviewer.</p>
                  </div>
                </Card>
              </div>
              <div className="stack">
                <Card title="Decision">
                  <div className="stack-sm">
                    <Textarea label="Note / reason" value={note} onChange={(e) => setNote(e.target.value)} hint="Required to reject. Shown to the user." />
                    {u.status === "PENDING_REVIEW" && (
                      <>
                        <Button variant="cta" busy={act.busy} onClick={() => act.run(`/admin/users/${u.id}/approve`, { note })}>Approve user & organization</Button>
                        <Button variant="danger" busy={act.busy} disabled={!note.trim()} onClick={() => act.run(`/admin/users/${u.id}/reject`, { reason: note })}>Reject</Button>
                      </>
                    )}
                    {u.status === "APPROVED" && <Button variant="danger" busy={act.busy} onClick={() => act.run(`/admin/users/${u.id}/suspend`, { reason: note })}>Suspend user</Button>}
                    {u.status === "SUSPENDED" && <Button busy={act.busy} onClick={() => act.run(`/admin/users/${u.id}/reinstate`, { reason: note })}>Reinstate user</Button>}
                    {["NEW", "ONBOARDING", "REJECTED"].includes(u.status) && <p className="small muted">Waiting for the user to submit onboarding.</p>}
                    <ErrorAlert error={act.error} />
                  </div>
                </Card>
                <Card title="Activity"><Timeline entries={u.audit} /></Card>
              </div>
            </div>
          </div>
        );
      }}
    </Loader>
  );
}
