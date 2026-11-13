import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, DataTable, EmptyState, Loader, PageHeader, Pager, Select, StatusBadge, Tabs } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { qs } from "../../lib/api";
import { formatDate, humanize } from "../../lib/format";

export default function RequestList() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const role = me.user.role;
  const [direction, setDirection] = useState(role === "OWNER" ? "outgoing" : "incoming");
  const [status, setStatus] = useState("");
  const [page, setPage] = useState(1);
  const resource = useResource(`/requests${qs({ direction, status, page })}`);
  const tabs = role === "AGENT"
    ? [{ id: "incoming", label: "From owners" }, { id: "outgoing", label: "To merchants" }]
    : role === "OWNER" ? [{ id: "outgoing", label: "Sent" }] : [{ id: "incoming", label: "From agents" }];
  return (
    <div className="stack">
      <PageHeader title="Requests" sub={role === "OWNER" ? "Port-call requests you sent to agents." : "Requests to and from your organization."}
        actions={role === "OWNER" && <Button variant="cta" icon={Plus} onClick={() => navigate("/agents")}>New request</Button>} />
      <Card>
        {tabs.length > 1 && <Tabs tabs={tabs} active={direction} onChange={(d) => { setDirection(d); setPage(1); }} />}
        <div style={{ maxWidth: 260, marginBottom: 12 }}>
          <Select label="Status" value={status} placeholder="All" onChange={(e) => { setStatus(e.target.value); setPage(1); }}
            options={["PENDING", "ACCEPTED", "DECLINED", "WITHDRAWN", "EXPIRED"].map((s) => ({ value: s, label: humanize(s) }))} />
        </div>
        <Loader resource={resource}>
          {(data) => (
            <>
              <DataTable rows={data.results} onRowClick={(r) => navigate(`/requests/${r.id}`)} empty={<EmptyState title="No requests" />}
                columns={[
                  { key: "reference", label: "Ref", render: (r) => <span className="mono">{r.reference}</span> },
                  { key: "subject", label: "Subject", render: (r) => r.subject || humanize(r.request_type) },
                  { key: "party", label: direction === "incoming" ? "From" : "To", render: (r) => (direction === "incoming" ? r.from_organization : r.to_organization).legal_name },
                  { key: "vessel", label: "Vessel / call", render: (r) => r.vessel?.name || r.port_call?.reference || "—" },
                  { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
                  { key: "date", label: "Sent", render: (r) => formatDate(r.created_at) },
                ]} />
              <Pager data={data} page={page} onPage={setPage} />
            </>
          )}
        </Loader>
      </Card>
    </div>
  );
}
