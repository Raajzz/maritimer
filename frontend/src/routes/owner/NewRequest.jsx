import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Alert, Button, Card, CheckGroup, ErrorAlert, Input, Loader, PageHeader, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api } from "../../lib/api";
import { fromLocalInput } from "../../lib/format";

/** Owner flow 2: send a port-call request to an agent (vessel, port, ETA/ETD, cargo, services, notes). */
export default function NewRequest() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const agentId = params.get("agent");
  const agent = useResource(agentId ? `/agents/${agentId}` : null);
  const vessels = useResource("/vessels?page_size=100");
  const cargo = useResource("/cargo-types");
  const services = useResource("/service-categories?vendor_only=true");
  const [form, setForm] = useState({
    vessel_id: "", port_id: params.get("port") || "", eta: "", etd: "", cargo_type_id: "", cargo_description: "", cargo_quantity: "", cargo_unit: "MT", message: "",
  });
  const [serviceIds, setServiceIds] = useState([]);
  const bind = (n) => ({ name: n, value: form[n], onChange: (e) => setForm({ ...form, [n]: e.target.value }) });
  const send = useAction(async () => {
    const vessel = vessels.data.results.find((v) => String(v.id) === String(form.vessel_id));
    const port = agent.data.ports.find((p) => String(p.id) === String(form.port_id));
    const created = await api.post("/requests", {
      request_type: "PORT_CALL",
      to_organization_id: Number(agentId),
      subject: `${vessel?.name || "Vessel"} – ${port?.name || "port call"}`,
      message: form.message,
      details: {
        vessel_id: Number(form.vessel_id), port_id: Number(form.port_id), eta: fromLocalInput(form.eta), etd: fromLocalInput(form.etd),
        cargo_type_id: Number(form.cargo_type_id), cargo_description: form.cargo_description, cargo_quantity: form.cargo_quantity || null, cargo_unit: form.cargo_unit,
      },
      services: serviceIds.map((id) => ({ service_category_id: id })),
    });
    navigate(`/requests/${created.id}`);
  });
  if (!agentId) return <Alert tone="info">Choose an agent first. <Link to="/agents">Find a port agent</Link></Alert>;
  const ready = form.vessel_id && form.port_id && form.eta && form.etd && form.cargo_type_id;
  return (
    <div className="stack" style={{ maxWidth: 860 }}>
      <PageHeader back={<Link to="/agents" className="row small"><ArrowLeft size={16} aria-hidden /> Agents</Link>} title="New port-call request"
        sub={agent.data ? `To ${agent.data.legal_name}` : ""} />
      <Loader resource={agent}>
        {(a) => (
          <Card>
            <form className="stack" onSubmit={(e) => { e.preventDefault(); send.run(); }}>
              <div className="grid grid-2">
                <Loader resource={vessels}>
                  {(page) => page.results.length ? (
                    <Select label="Vessel *" placeholder="Choose a vessel…" options={page.results.map((v) => ({ value: v.id, label: `${v.name}${v.imo_number ? ` · IMO ${v.imo_number}` : ""}` }))} {...bind("vessel_id")} />
                  ) : <Alert tone="warn">Add a vessel first. <Link to="/vessels">Manage vessels</Link></Alert>}
                </Loader>
                <Select label="Port *" placeholder="Choose a port…" options={a.ports.map((p) => ({ value: p.id, label: p.name }))} {...bind("port_id")} />
                <Input label="ETA *" type="datetime-local" required {...bind("eta")} />
                <Input label="ETD *" type="datetime-local" required {...bind("etd")} />
                <Loader resource={cargo}>{(list) => <Select label="Cargo type *" placeholder="Choose…" options={list.map((c) => ({ value: c.id, label: c.name }))} {...bind("cargo_type_id")} />}</Loader>
                <Input label="Cargo description" {...bind("cargo_description")} placeholder="Steel coils" />
                <Input label="Quantity" inputMode="decimal" {...bind("cargo_quantity")} />
                <Select label="Unit" options={["MT", "TEU", "m3", "units"].map((u) => ({ value: u, label: u }))} {...bind("cargo_unit")} />
              </div>
              <div className="field">
                <label>Services required</label>
                <Loader resource={services}>{(list) => <CheckGroup options={list.map((s) => ({ value: s.id, label: s.name }))} value={serviceIds} onChange={setServiceIds} />}</Loader>
              </div>
              <Textarea label="Notes and special requirements" {...bind("message")} placeholder="Crew change of 2, fresh water 300 MT, cash to master USD 5,000…" />
              <ErrorAlert error={send.error} />
              <div className="row">
                <Button type="submit" variant="cta" busy={send.busy} disabled={!ready}>Send request</Button>
                <Button variant="ghost" onClick={() => navigate(-1)}>Cancel</Button>
              </div>
            </form>
          </Card>
        )}
      </Loader>
    </div>
  );
}
