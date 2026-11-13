import { Compass, MapPin } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge, Card, EmptyState, Input, Loader, PageHeader, Pager, Select, Stars } from "../../components/ui";
import { useResource } from "../../hooks/useResource";
import { qs } from "../../lib/api";

/** Owner flow 1: location → port → agents serving it, sortable and filterable (rating, name, ID). */
export default function Discovery() {
  const locations = useResource("/locations");
  const services = useResource("/service-categories?vendor_only=true");
  const [locationId, setLocationId] = useState("");
  const [portId, setPortId] = useState("");
  const ports = useResource(locationId ? `/ports?location_id=${locationId}` : null);
  const [filters, setFilters] = useState({ sort: "-rating", min_rating: "", service_category_id: "", q: "" });
  const [page, setPage] = useState(1);
  const agents = useResource(locationId ? `/agents${qs({ location_id: locationId, port_id: portId, ...filters, page })}` : null);
  const set = (k) => (e) => { setFilters({ ...filters, [k]: e.target.value }); setPage(1); };

  return (
    <div className="stack">
      <PageHeader title="Find a port agent" sub="Choose where your vessel is calling, then compare agents serving that port." />
      <Card>
        <div className="grid grid-2">
          <Loader resource={locations}>
            {(list) => (
              <Select label="Location" placeholder="Choose a location…" value={locationId}
                onChange={(e) => { setLocationId(e.target.value); setPortId(""); setPage(1); }}
                options={list.map((l) => ({ value: l.id, label: `${l.name}, ${l.country_code}` }))} />
            )}
          </Loader>
          <Select label="Port" placeholder={locationId ? "All ports in this location" : "Choose a location first"} value={portId} disabled={!locationId}
            onChange={(e) => { setPortId(e.target.value); setPage(1); }}
            options={(ports.data || []).map((p) => ({ value: p.id, label: `${p.name}${p.unlocode ? ` (${p.unlocode})` : ""}` }))} />
        </div>
      </Card>
      {!locationId ? (
        <EmptyState icon={MapPin} title="Pick a location to see agents">Mumbai and Singapore have demo agents.</EmptyState>
      ) : (
        <>
          <Card>
            <div className="grid grid-4">
              <Input label="Search" placeholder="Agent name" value={filters.q} onChange={set("q")} />
              <Select label="Sort by" value={filters.sort} onChange={set("sort")} options={[
                { value: "-rating", label: "Rating (high → low)" }, { value: "rating", label: "Rating (low → high)" },
                { value: "name", label: "Name (A → Z)" }, { value: "-name", label: "Name (Z → A)" },
                { value: "id", label: "ID (oldest first)" }, { value: "-id", label: "ID (newest first)" },
              ]} />
              <Select label="Minimum rating" value={filters.min_rating} onChange={set("min_rating")} placeholder="Any"
                options={[4.5, 4, 3, 2].map((n) => ({ value: n, label: `${n}★ and up` }))} />
              <Select label="Offers service" value={filters.service_category_id} onChange={set("service_category_id")} placeholder="Any service"
                options={(services.data || []).map((s) => ({ value: s.id, label: s.name }))} />
            </div>
          </Card>
          <Loader resource={agents}>
            {(data) => data.results.length ? (
              <>
                <div className="grid grid-3">
                  {data.results.map((a) => (
                    <Card key={a.id}>
                      <div className="stack-sm">
                        <div className="row-between">
                          <Link to={`/agents/${a.id}`} className="strong">{a.trade_name || a.legal_name}</Link>
                          <span className="xs muted mono">#{a.id}</span>
                        </div>
                        <div className="row small"><Stars value={a.rating_avg} /> <span className="strong">{a.rating_avg}</span><span className="muted">({a.rating_count} review{a.rating_count === 1 ? "" : "s"})</span></div>
                        <div className="xs muted">{a.completed_port_calls} completed port call{a.completed_port_calls === 1 ? "" : "s"} · {a.city}</div>
                        <div className="row" style={{ gap: 4 }}>{a.services.slice(0, 5).map((s) => <Badge key={s.id} tone="accent">{s.name}</Badge>)}</div>
                        <div className="xs muted">Ports: {a.ports.map((p) => p.name).join(", ")}</div>
                        <div className="row" style={{ marginTop: 8 }}>
                          <Link to={`/agents/${a.id}`} className="btn btn-secondary btn-sm">Profile</Link>
                          <Link to={`/requests/new${qs({ agent: a.id, port: portId || a.ports[0]?.id })}`} className="btn btn-cta btn-sm">Send request</Link>
                        </div>
                      </div>
                    </Card>
                  ))}
                </div>
                <Pager data={data} page={page} onPage={setPage} />
              </>
            ) : <EmptyState icon={Compass} title="No agents match">Try another port or remove filters.</EmptyState>}
          </Loader>
        </>
      )}
    </div>
  );
}
