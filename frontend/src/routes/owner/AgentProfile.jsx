import { ArrowLeft, Phone } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { Badge, Card, DefinitionList, EmptyState, Loader, PageHeader, Stars } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { formatDate, formatMoney } from "../../lib/format";

export default function AgentProfile() {
  const { id } = useParams();
  const { me } = useAuth();
  const agent = useResource(`/agents/${id}`);
  return (
    <Loader resource={agent}>
      {(a) => {
        const total = Object.values(a.rating_distribution).reduce((n, c) => n + c, 0);
        return (
          <div className="stack">
            <PageHeader
              back={<Link to="/agents" className="row small"><ArrowLeft size={16} aria-hidden /> Agents</Link>}
              title={a.trade_name || a.legal_name}
              sub={<span className="row"><Stars value={a.profile.rating_avg} /> {a.profile.rating_avg} · {a.profile.rating_count} reviews · {a.profile.completed_port_calls} completed calls</span>}
              actions={me.user.role === "OWNER" && <Link className="btn btn-cta" to={`/requests/new?agent=${a.id}&port=${a.ports[0]?.id || ""}`}>Send request</Link>}
            />
            <div className="grid grid-main-side">
              <div className="stack">
                <Card title="About">
                  <p className="small" style={{ whiteSpace: "pre-wrap", marginBottom: 12 }}>{a.profile.description || "No description yet."}</p>
                  <DefinitionList items={[
                    ["Legal name", a.legal_name],
                    ["Location", [a.city, a.country_code].filter(Boolean).join(", ")],
                    ["Email", a.email],
                    ["Phone", a.phone],
                    ["Emergency", a.profile.emergency_phone ? <span key="e" className="row"><Phone size={14} aria-hidden /> {a.profile.emergency_phone}</span> : "—"],
                    ["Standard fee", a.profile.default_agency_fee ? formatMoney(a.profile.default_agency_fee.amount, a.profile.default_agency_fee.currency_code) : "On request"],
                  ]} />
                </Card>
                <Card title="Reviews">
                  {a.recent_ratings.length ? (
                    <div className="stack">
                      {a.recent_ratings.map((r, i) => (
                        <div key={i} className="stack-sm" style={{ gap: 2 }}>
                          <div className="row"><Stars value={r.score} /><span className="xs muted">{formatDate(r.created_at)} · {r.port_call_reference}</span></div>
                          {r.comment && <p className="small">{r.comment}</p>}
                        </div>
                      ))}
                    </div>
                  ) : <EmptyState title="No reviews yet" />}
                </Card>
              </div>
              <div className="stack">
                <Card title="Rating breakdown">
                  {[5, 4, 3, 2, 1].map((s) => {
                    const n = a.rating_distribution[String(s)];
                    return (
                      <div key={s} className="row small" style={{ gap: 8 }}>
                        <span style={{ width: 16 }}>{s}★</span>
                        <div style={{ flex: 1, height: 8, borderRadius: 4, background: "var(--color-border)" }} aria-hidden>
                          <div style={{ width: total ? `${(n / total) * 100}%` : 0, height: "100%", borderRadius: 4, background: "var(--color-cta)" }} />
                        </div>
                        <span className="muted" style={{ width: 20, textAlign: "right" }}>{n}</span>
                      </div>
                    );
                  })}
                </Card>
                <Card title="Ports">{a.ports.map((p) => <div key={p.id} className="small">{p.name}{p.unlocode ? ` (${p.unlocode})` : ""}</div>)}</Card>
                <Card title="Services"><div className="row" style={{ gap: 4 }}>{a.services.map((s) => <Badge key={s.id} tone="accent">{s.name}</Badge>)}</div></Card>
              </div>
            </div>
          </div>
        );
      }}
    </Loader>
  );
}
