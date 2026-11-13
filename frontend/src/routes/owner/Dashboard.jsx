import { Compass, Ship } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { PortCallItem, Timeline } from "../../components/domain";
import { Badge, Button, Card, EmptyState, Kpi, Loader, PageHeader, StatusBadge } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { formatDate } from "../../lib/format";

const ACTION_LABELS = {
  APPROVE_PDA: ["Approve PDA", "pda"],
  RECORD_ADVANCE: ["Send & record advance", "payments"],
  REVIEW_FDA: ["Review FDA", "fda"],
  PAY_BALANCE: ["Pay balance", "payments"],
  CONFIRM_REFUND: ["Confirm refund", "payments"],
  RATE_AGENT: ["Rate agent", "overview"],
};

export default function OwnerDashboard() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const dash = useResource("/dashboard", { pollMs: 60000 });
  return (
    <div className="stack">
      <PageHeader title={me.organization?.trade_name || me.organization?.legal_name} sub="Your vessels, port calls and what needs your attention."
        actions={<Button variant="cta" icon={Compass} onClick={() => navigate("/agents")}>Find a port agent</Button>} />
      <Loader resource={dash}>
        {(d) => {
          const active = Object.entries(d.calls_by_status).filter(([s]) => !["CLOSED", "CANCELLED"].includes(s)).reduce((n, [, c]) => n + c, 0);
          return (
            <>
              <div className="grid grid-kpi">
                <Kpi label="Active port calls" value={active} />
                <Kpi label="Needs your action" value={d.pending_actions.length} />
                <Kpi label="Vessels" value={d.vessels.length} />
                <Kpi label="Requests pending" value={d.outgoing_requests.filter((r) => r.status === "PENDING").length} />
              </div>
              <div className="grid grid-main-side">
                <div className="stack">
                  <Card title="Needs your action">
                    {d.pending_actions.length ? (
                      <div className="stack-sm">
                        {d.pending_actions.map((a, i) => {
                          const [label, tab] = ACTION_LABELS[a.type] || [a.type, "overview"];
                          return (
                            <Link key={`${a.type}-${a.port_call.id}-${i}`} to={`/port-calls/${a.port_call.id}?tab=${tab}`} className="card card-link row-between" style={{ padding: 12 }}>
                              <span className="small"><span className="strong">{a.port_call.vessel.name}</span> · {a.port_call.port.name} <span className="mono xs muted">{a.port_call.reference}</span></span>
                              <Badge tone="cta">{label}</Badge>
                            </Link>
                          );
                        })}
                      </div>
                    ) : <EmptyState title="You're all caught up" />}
                  </Card>
                  <Card title="Fleet" actions={<Link to="/vessels" className="small">Manage vessels</Link>}>
                    {d.vessels.length ? (
                      <div className="grid grid-2">
                        {d.vessels.map(({ vessel, active_call }) => active_call ? <PortCallItem key={vessel.id} pc={active_call} /> : (
                          <div key={vessel.id} className="card" style={{ padding: 12 }}>
                            <div className="row"><Ship size={16} aria-hidden color="var(--color-muted)" /><span className="strong">{vessel.name}</span></div>
                            <div className="small muted">No active port call</div>
                          </div>
                        ))}
                      </div>
                    ) : <EmptyState icon={Ship} title="No vessels yet"><Link to="/vessels">Add your first vessel</Link></EmptyState>}
                  </Card>
                </div>
                <div className="stack">
                  <Card title="Recent requests" actions={<Link to="/requests" className="small">All</Link>}>
                    {d.outgoing_requests.length ? (
                      <div className="stack-sm">
                        {d.outgoing_requests.slice(0, 6).map((r) => (
                          <Link key={r.id} to={`/requests/${r.id}`} className="row-between small">
                            <span className="truncate" style={{ maxWidth: "65%" }}>{r.subject || r.reference}<span className="xs muted"> · {formatDate(r.created_at)}</span></span>
                            <StatusBadge status={r.status} />
                          </Link>
                        ))}
                      </div>
                    ) : <EmptyState title="No requests yet" />}
                  </Card>
                  <Card title="Recent activity"><Timeline entries={d.recent_activity.slice(0, 8)} /></Card>
                </div>
              </div>
            </>
          );
        }}
      </Loader>
    </div>
  );
}
