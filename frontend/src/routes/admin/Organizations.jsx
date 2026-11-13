import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, CheckGroup, DataTable, EmptyState, ErrorAlert, Input, Loader, Modal, PageHeader, Pager, Select, StatusBadge } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api, qs } from "../../lib/api";
import { formatDate, humanize } from "../../lib/format";

/** Admin creates/onboards owners, agents and merchants directly (approved on creation). */
function CreateOrgModal({ onClose, onCreated }) {
  const countries = useResource("/countries");
  const ports = useResource("/ports");
  const services = useResource("/service-categories?vendor_only=true");
  const [type, setType] = useState("AGENT");
  const [org, setOrg] = useState({ legal_name: "", trade_name: "", country_code: "IN", city: "", email: "", phone: "", tax_id: "" });
  const [portIds, setPortIds] = useState([]);
  const [serviceIds, setServiceIds] = useState([]);
  const [user, setUser] = useState({ email: "", display_name: "" });
  const bind = (n) => ({ name: n, value: org[n], onChange: (e) => setOrg({ ...org, [n]: e.target.value }) });
  const save = useAction(async () => {
    const created = await api.post("/admin/organizations", {
      type, organization: org, coverage: { port_ids: portIds, service_category_ids: type === "OWNER" ? [] : serviceIds },
    });
    if (user.email) await api.post(`/admin/organizations/${created.id}/users`, user);
    onCreated(created);
  });
  return (
    <Modal title="Create organization" wide onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button variant="cta" busy={save.busy} disabled={!org.legal_name} onClick={() => save.run()}>Create</Button></>}>
      <div className="grid grid-3">
        <Select label="Type" value={type} onChange={(e) => setType(e.target.value)} options={["OWNER", "AGENT", "MERCHANT"].map((t) => ({ value: t, label: humanize(t) }))} />
        <Input label="Legal name *" {...bind("legal_name")} />
        <Input label="Trading name" {...bind("trade_name")} />
        <Select label="Country" options={(countries.data || []).map((c) => ({ value: c.code, label: c.name }))} {...bind("country_code")} />
        <Input label="City" {...bind("city")} />
        <Input label="Tax ID" {...bind("tax_id")} />
        <Input label="Email" type="email" {...bind("email")} />
        <Input label="Phone" {...bind("phone")} />
      </div>
      <div className="field"><label>Ports</label><CheckGroup options={(ports.data || []).map((p) => ({ value: p.id, label: p.name }))} value={portIds} onChange={setPortIds} /></div>
      {type !== "OWNER" && <div className="field"><label>Services</label><CheckGroup options={(services.data || []).map((s) => ({ value: s.id, label: s.name }))} value={serviceIds} onChange={setServiceIds} /></div>}
      <div className="grid grid-2">
        <Input label="First user's Google email" type="email" value={user.email} onChange={(e) => setUser({ ...user, email: e.target.value })} hint="Pre-approved; linked on their first Google sign-in." />
        <Input label="Their name" value={user.display_name} onChange={(e) => setUser({ ...user, display_name: e.target.value })} />
      </div>
      <ErrorAlert error={save.error} />
    </Modal>
  );
}

export default function AdminOrganizations() {
  const navigate = useNavigate();
  const [type, setType] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const orgs = useResource(`/admin/organizations${qs({ type, q, page })}`);
  return (
    <div className="stack">
      <PageHeader title="Organizations" sub="Owners, port agents and merchants." actions={<Button variant="cta" icon={Plus} onClick={() => setCreating(true)}>Create organization</Button>} />
      <Card>
        <div className="grid grid-2" style={{ marginBottom: 12 }}>
          <Select label="Type" value={type} placeholder="All" onChange={(e) => { setType(e.target.value); setPage(1); }} options={["OWNER", "AGENT", "MERCHANT"].map((t) => ({ value: t, label: humanize(t) }))} />
          <Input label="Search" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        </div>
        <Loader resource={orgs}>
          {(data) => (
            <>
              <DataTable rows={data.results} onRowClick={(o) => navigate(`/admin/organizations/${o.id}`)} empty={<EmptyState title="No organizations" />}
                columns={[
                  { key: "legal_name", label: "Name", render: (o) => <span className="strong">{o.legal_name}</span> },
                  { key: "type", label: "Type", render: (o) => humanize(o.type) },
                  { key: "loc", label: "Location", render: (o) => [o.city, o.country_code].filter(Boolean).join(", ") },
                  { key: "status", label: "Verification", render: (o) => <StatusBadge status={o.verification_status} /> },
                  { key: "created", label: "Created", render: (o) => formatDate(o.created_at) },
                ]} />
              <Pager data={data} page={page} onPage={setPage} />
            </>
          )}
        </Loader>
      </Card>
      {creating && <CreateOrgModal onClose={() => setCreating(false)} onCreated={(o) => navigate(`/admin/organizations/${o.id}`)} />}
    </div>
  );
}
