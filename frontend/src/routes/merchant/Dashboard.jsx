import { Inbox, MessageSquare } from "lucide-react";
import { Link } from "react-router-dom";

import { Card, EmptyState, Kpi, Loader, Money, PageHeader, StatusBadge } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { formatDate, formatMoney, humanize } from "../../lib/format";

export default function MerchantDashboard() {
  const { me } = useAuth();
  const dash = useResource("/dashboard", { pollMs: 60000 });
  return (
    <div className="stack">
      <PageHeader title={me.organization?.trade_name || me.organization?.legal_name} sub="Service requests from port agents and your invoices." />
      <Loader resource={dash}>
        {(d) => (
          <>
            <div className="grid grid-kpi">
              <Kpi label="New requests" value={d.incoming_requests.length} />
              <Kpi label="Active jobs" value={d.active_jobs.length} />
              <Kpi label="Invoices awaiting agent" value={d.invoices_by_status.ISSUED || 0} />
              <Kpi label="Unpaid" value={d.unpaid_total.length ? d.unpaid_total.map((u) => formatMoney(u.amount, u.currency_code)).join(" · ") : "—"} />
            </div>
            <div className="grid grid-2">
              <Card title="New requests" actions={<Link to="/requests" className="small">All</Link>}>
                {d.incoming_requests.length ? (
                  <div className="stack-sm">
                    {d.incoming_requests.map((r) => (
                      <Link key={r.id} to={`/requests/${r.id}`} className="card card-link" style={{ padding: 12 }}>
                        <div className="row-between"><span className="strong small">{r.subject}</span><StatusBadge status={r.status} /></div>
                        <div className="xs muted">{r.from_organization.legal_name} · {r.port_call?.reference} · {formatDate(r.created_at)}</div>
                      </Link>
                    ))}
                  </div>
                ) : <EmptyState icon={Inbox} title="No new requests" />}
              </Card>
              <Card title="Active jobs">
                {d.active_jobs.length ? (
                  <div className="stack-sm">
                    {d.active_jobs.map((j) => (
                      <div key={j.request.id} className="card" style={{ padding: 12 }}>
                        <div className="row-between">
                          <Link to={`/requests/${j.request.id}`} className="strong small">{j.request.subject || j.request.reference}</Link>
                          <StatusBadge status={j.port_call.status} />
                        </div>
                        <div className="xs muted">{j.port_call.vessel.name} · {j.port_call.port.name} · ETA {formatDate(j.port_call.eta)}</div>
                        <div className="row" style={{ marginTop: 8 }}>
                          {j.chat_thread_id && <Link className="btn btn-secondary btn-sm" to={`/chat/${j.chat_thread_id}`}><MessageSquare size={14} aria-hidden /> Chat</Link>}
                          <Link className="btn btn-cta btn-sm" to={`/invoices/new?request=${j.request.id}`}>Invoice</Link>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : <EmptyState title="No active jobs" />}
              </Card>
            </div>
            <Card title="Invoices by status" actions={<Link to="/invoices" className="small">All invoices</Link>}>
              <div className="row" style={{ gap: 16 }}>
                {Object.entries(d.invoices_by_status).map(([s, n]) => <span key={s} className="row small"><StatusBadge status={s} /> {n}</span>)}
                {!Object.keys(d.invoices_by_status).length && <span className="muted small">No invoices yet.</span>}
              </div>
            </Card>
            <Card title="Recent payments">
              {d.recent_payments.length ? (
                <div className="stack-sm">
                  {d.recent_payments.map((p) => (
                    <div key={p.id} className="row-between small">
                      <span>{p.payer.legal_name} · {formatDate(p.paid_at)} · {humanize(p.method)}</span>
                      <Money value={p.amount} />
                    </div>
                  ))}
                </div>
              ) : <EmptyState title="No payments yet" />}
            </Card>
          </>
        )}
      </Loader>
    </div>
  );
}
