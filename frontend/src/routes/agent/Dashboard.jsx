import { AlertTriangle, Inbox } from "lucide-react";
import { Link } from "react-router-dom";

import { PortCallItem } from "../../components/domain";
import { Card, EmptyState, Kpi, Loader, Money, PageHeader } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { formatDate } from "../../lib/format";

const COLUMNS = [
  ["requested", "Requested"],
  ["pda_sent", "PDA"],
  ["advance_received", "Advance"],
  ["in_port", "In port"],
  ["fda_issued", "FDA issued"],
  ["disputed", "Disputed"],
  ["settled", "Settled"],
];

/** Agent dashboard: many concurrent port calls across owners as a status pipeline (flow 13). */
export default function AgentDashboard() {
  const { me } = useAuth();
  const dash = useResource("/dashboard", { pollMs: 60000 });
  return (
    <div className="stack">
      <PageHeader title="Pipeline" sub={`${me.organization?.trade_name || me.organization?.legal_name} · every port call across your owners`} />
      <Loader resource={dash}>
        {(d) => (
          <>
            <div className="grid grid-kpi">
              <Kpi label="Active port calls" value={d.kpis.active_calls} />
              <Kpi label="New requests" value={d.kpis.pending_requests} />
              <Kpi label="Open disputes" value={d.kpis.open_disputes} />
              <Kpi label="Invoices to review" value={d.kpis.invoices_awaiting_review} hint={`${d.kpis.payments_to_confirm} payment(s) to confirm`} />
            </div>
            <div className="grid grid-2">
              <Kpi label="Balances owed by owners" value={<Money value={d.kpis.outstanding_balance_due} />} />
              <Kpi label="Refunds you owe owners" value={<Money value={d.kpis.outstanding_refund_due} />} />
            </div>
            {d.attention.length > 0 && (
              <Card title={<span className="row"><AlertTriangle size={18} color="var(--color-cta)" aria-hidden /> Needs attention</span>}>
                <div className="stack-sm">
                  {d.attention.map((a, i) => (
                    <Link key={i} to={`/port-calls/${a.port_call.id}`} className="row-between small">
                      <span>{a.message}</span><span className="mono xs">{a.port_call.reference}</span>
                    </Link>
                  ))}
                </div>
              </Card>
            )}
            <div className="pipeline" aria-label="Port call pipeline">
              {COLUMNS.map(([key, label]) => {
                const items = d.pipeline[key] || [];
                return (
                  <section key={key} className="col" aria-label={label}>
                    <div className="col-head"><span>{label}</span><span className="badge badge-primary">{items.length}</span></div>
                    <div className="col-body">
                      {key === "requested"
                        ? items.map((r) => (
                            <Link key={r.id} to={`/requests/${r.id}`} className="item">
                              <div className="small strong">{r.vessel?.name || r.subject}</div>
                              <div className="xs muted">{r.from_organization.legal_name}</div>
                              <div className="xs muted">{r.port?.name} · ETA {formatDate(r.eta)}</div>
                            </Link>
                          ))
                        : items.map((pc) => <PortCallItem key={pc.id} pc={pc} compact />)}
                      {!items.length && <p className="xs muted" style={{ textAlign: "center", padding: 12 }}>Empty</p>}
                    </div>
                  </section>
                );
              })}
            </div>
            {!Object.values(d.pipeline).some((v) => v.length) && <EmptyState icon={Inbox} title="No port calls yet">Requests from owners appear in the first column.</EmptyState>}
          </>
        )}
      </Loader>
    </div>
  );
}
