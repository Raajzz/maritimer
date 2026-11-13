import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Card, DataTable, EmptyState, Input, Loader, PageHeader, Pager, Select, StatusBadge } from "../../components/ui";
import { useResource } from "../../hooks/useResource";
import { qs } from "../../lib/api";
import { formatDate, humanize } from "../../lib/format";

export default function AdminApprovals() {
  const navigate = useNavigate();
  const [status, setStatus] = useState("PENDING_REVIEW");
  const [role, setRole] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const users = useResource(`/admin/users${qs({ status, role, q, page })}`);
  return (
    <div className="stack">
      <PageHeader title="Users & approvals" sub="Review documents and approve or reject accounts. Only approved users can use the app." />
      <Card>
        <div className="grid grid-3" style={{ marginBottom: 12 }}>
          <Select label="Status" value={status} placeholder="All" onChange={(e) => { setStatus(e.target.value); setPage(1); }}
            options={["PENDING_REVIEW", "ONBOARDING", "NEW", "APPROVED", "REJECTED", "SUSPENDED"].map((s) => ({ value: s, label: humanize(s) }))} />
          <Select label="Role" value={role} placeholder="All" onChange={(e) => { setRole(e.target.value); setPage(1); }}
            options={["OWNER", "AGENT", "MERCHANT", "ADMIN"].map((r) => ({ value: r, label: humanize(r) }))} />
          <Input label="Search" placeholder="Email, name or company" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <Loader resource={users}>
          {(data) => (
            <>
              <DataTable rows={data.results} onRowClick={(u) => navigate(`/admin/users/${u.id}`)} empty={<EmptyState title="Nobody here" />}
                columns={[
                  { key: "email", label: "User", render: (u) => <div className="stack-sm" style={{ gap: 0 }}><span className="strong">{u.display_name || u.email}</span><span className="xs muted">{u.email}</span></div> },
                  { key: "role", label: "Role", render: (u) => humanize(u.role || "—") },
                  { key: "org", label: "Organization", render: (u) => u.organization?.legal_name || "—" },
                  { key: "status", label: "User", render: (u) => <StatusBadge status={u.status} /> },
                  { key: "org_status", label: "Org", render: (u) => <StatusBadge status={u.organization_status} /> },
                  { key: "created", label: "Joined", render: (u) => formatDate(u.created_at) },
                ]} />
              <Pager data={data} page={page} onPage={setPage} />
            </>
          )}
        </Loader>
      </Card>
    </div>
  );
}
