import { useState } from "react";
import { Link } from "react-router-dom";

import { Card, DataTable, Input, Loader, PageHeader, Pager } from "../../components/ui";
import { useResource } from "../../hooks/useResource";
import { qs } from "../../lib/api";
import { formatDateTime, humanize } from "../../lib/format";

export default function AdminAudit() {
  const [action, setAction] = useState("");
  const [portCallId, setPortCallId] = useState("");
  const [page, setPage] = useState(1);
  const log = useResource(`/admin/audit-log${qs({ action, port_call_id: portCallId, page })}`);
  return (
    <div className="stack">
      <PageHeader title="Audit log" sub="Every state transition, append-only." />
      <Card>
        <div className="grid grid-2" style={{ marginBottom: 12 }}>
          <Input label="Action starts with" placeholder="dispute. / pda. / user." value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }} />
          <Input label="Port call ID" inputMode="numeric" value={portCallId} onChange={(e) => { setPortCallId(e.target.value); setPage(1); }} />
        </div>
        <Loader resource={log}>
          {(data) => (
            <>
              <DataTable rows={data.results} columns={[
                { key: "when", label: "When", render: (e) => formatDateTime(e.created_at) },
                { key: "action", label: "Action", render: (e) => <span className="mono xs">{e.action}</span> },
                { key: "actor", label: "Actor", render: (e) => (e.actor ? `${e.actor.email} (${humanize(e.actor_role || "")})` : "System") },
                { key: "entity", label: "Entity", render: (e) => `${e.entity_type} #${e.entity_id}` },
                { key: "states", label: "Transition", render: (e) => (e.from_state || e.to_state ? `${e.from_state || "∅"} → ${e.to_state || "∅"}` : "—") },
                { key: "pc", label: "Port call", render: (e) => (e.port_call_id ? <Link to={`/port-calls/${e.port_call_id}`}>#{e.port_call_id}</Link> : "—") },
              ]} />
              <Pager data={data} page={page} onPage={setPage} />
            </>
          )}
        </Loader>
      </Card>
    </div>
  );
}
