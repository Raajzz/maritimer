import { Link } from "react-router-dom";

import { Timeline } from "../../components/domain";
import { Card, Kpi, Loader, PageHeader, StatusBadge } from "../../components/ui";
import { useResource } from "../../hooks/useResource";
import { humanize } from "../../lib/format";

export default function AdminDashboard() {
  const dash = useResource("/admin/dashboard", { pollMs: 60000 });
  return (
    <div className="stack">
      <PageHeader title="Administration" sub="Approvals, master data and platform activity." />
      <Loader resource={dash}>
        {(d) => (
          <>
            <div className="grid grid-kpi">
              <Link to="/admin/approvals" className="card-link"><Kpi label="Users awaiting review" value={d.pending_users} /></Link>
              <Kpi label="Organizations awaiting review" value={d.pending_organizations} />
              <Kpi label="Documents to check" value={d.pending_documents} />
            </div>
            <div className="grid grid-main-side">
              <Card title="Recent activity" actions={<Link to="/admin/audit" className="small">Audit log</Link>}><Timeline entries={d.recent_audit} /></Card>
              <div className="stack">
                <Card title="Users by role">
                  {Object.entries(d.users_by_role).map(([role, n]) => (
                    <div key={role} className="row-between small"><span>{role === "None" ? "Not chosen yet" : humanize(role)}</span><span className="strong">{n}</span></div>
                  ))}
                </Card>
                <Card title="Port calls by status">
                  {Object.entries(d.port_calls_by_status).map(([s, n]) => (
                    <div key={s} className="row-between small"><StatusBadge status={s} /><span className="strong">{n}</span></div>
                  ))}
                </Card>
              </div>
            </div>
          </>
        )}
      </Loader>
    </div>
  );
}
