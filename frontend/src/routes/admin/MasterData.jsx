import { Plus } from "lucide-react";
import { useState } from "react";

import { Badge, Button, Card, DataTable, ErrorAlert, Input, Loader, Modal, PageHeader, Tabs } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api } from "../../lib/api";
import { humanize } from "../../lib/format";
import FxRates from "../agent/FxRates";

// Each entity: list endpoint, admin write endpoint, editable fields, table columns.
const ENTITIES = {
  locations: {
    label: "Locations", list: "/locations?include_inactive=true", write: "/admin/locations",
    fields: [["country_code", "Country code"], ["name", "Name"], ["region", "Region / state"]],
    columns: [["name", "Name"], ["country_code", "Country"], ["region", "Region"]],
  },
  ports: {
    label: "Ports", list: "/ports?include_inactive=true", write: "/admin/ports",
    fields: [["location_id", "Location ID"], ["name", "Name"], ["unlocode", "UN/LOCODE"], ["timezone", "Timezone (IANA)"]],
    columns: [["name", "Name"], ["unlocode", "UN/LOCODE"], ["location", "Location", (p) => p.location.name], ["timezone", "Timezone"]],
  },
  services: {
    label: "Service categories", list: "/service-categories?include_inactive=true", write: "/admin/service-categories",
    fields: [["code", "Code (UPPER_SNAKE)"], ["name", "Name"], ["description", "Description"], ["sort_order", "Sort order"]],
    columns: [["name", "Name"], ["code", "Code"], ["vendor", "Vendor service", (s) => (s.is_vendor_service ? "Yes" : "No")]],
  },
  cargo: {
    label: "Cargo types", list: "/cargo-types?include_inactive=true", write: "/admin/cargo-types",
    fields: [["code", "Code"], ["name", "Name"]],
    columns: [["name", "Name"], ["code", "Code"]],
  },
  currencies: {
    label: "Currencies", list: "/currencies?include_inactive=true", write: "/admin/currencies", key: "code", noCreate: true,
    fields: [],
    columns: [["code", "Code"], ["name", "Name"], ["minor_units", "Decimals"]],
  },
};

function EntityTab({ entity }) {
  const cfg = ENTITIES[entity];
  const list = useResource(cfg.list);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({});
  const act = useAction(async (fn) => {
    await fn();
    list.refetch();
  });
  const keyOf = (row) => row[cfg.key || "id"];
  return (
    <Card title={cfg.label} actions={!cfg.noCreate && <Button icon={Plus} onClick={() => { setForm({}); setCreating(true); }}>Add</Button>}>
      <ErrorAlert error={act.error} />
      <Loader resource={list}>
        {(rows) => (
          <DataTable rowKey={cfg.key || "id"} rows={rows} columns={[
            ...cfg.columns.map(([key, label, render]) => ({ key, label, render })),
            { key: "active", label: "Active", render: (r) => <Badge tone={r.is_active ? "success" : "neutral"}>{r.is_active ? "Active" : "Inactive"}</Badge> },
            { key: "toggle", label: "", render: (r) => (
              <Button size="sm" variant="secondary" onClick={() => act.run(() => api.patch(`${cfg.write}/${keyOf(r)}`, { is_active: !r.is_active }))}>
                {r.is_active ? "Deactivate" : "Activate"}
              </Button>
            ) },
          ]} />
        )}
      </Loader>
      {creating && (
        <Modal title={`Add ${cfg.label.toLowerCase().replace(/s$/, "")}`} onClose={() => setCreating(false)}
          footer={<><Button variant="secondary" onClick={() => setCreating(false)}>Cancel</Button>
            <Button busy={act.busy} onClick={() => act.run(async () => { await api.post(cfg.write, form); setCreating(false); })}>Save</Button></>}>
          {cfg.fields.map(([name, label]) => (
            <Input key={name} label={label} value={form[name] || ""} onChange={(e) => setForm({ ...form, [name]: e.target.value })} />
          ))}
          <ErrorAlert error={act.error} />
        </Modal>
      )}
    </Card>
  );
}

function PoliciesTab() {
  const list = useResource("/admin/request-policies");
  const act = useAction(async (p) => {
    await api.patch(`/admin/request-policies/${p.id}`, { is_enabled: !p.is_enabled });
    list.refetch();
  });
  return (
    <Card title="Request directions">
      <p className="small muted" style={{ marginBottom: 12 }}>Which role may send which request to which role. Enabling a row opens that direction without a code change.</p>
      <ErrorAlert error={act.error} />
      <Loader resource={list}>
        {(rows) => (
          <DataTable rows={rows} columns={[
            { key: "type", label: "Request", render: (p) => humanize(p.request_type) },
            { key: "dir", label: "Direction", render: (p) => `${humanize(p.from_role)} → ${humanize(p.to_role)}` },
            { key: "on", label: "Status", render: (p) => <Badge tone={p.is_enabled ? "success" : "neutral"}>{p.is_enabled ? "Enabled" : "Disabled"}</Badge> },
            { key: "act", label: "", render: (p) => <Button size="sm" variant="secondary" busy={act.busy} onClick={() => act.run(p)}>{p.is_enabled ? "Disable" : "Enable"}</Button> },
          ]} />
        )}
      </Loader>
    </Card>
  );
}

export default function AdminMasterData() {
  const [tab, setTab] = useState("locations");
  return (
    <div className="stack">
      <PageHeader title="Master data" sub="Reference data is never deleted; deactivate it instead." />
      <Tabs active={tab} onChange={setTab} tabs={[
        ...Object.entries(ENTITIES).map(([id, cfg]) => ({ id, label: cfg.label })),
        { id: "fx", label: "FX rates" }, { id: "policies", label: "Request policies" },
      ]} />
      {ENTITIES[tab] && <EntityTab key={tab} entity={tab} />}
      {tab === "fx" && <FxRates />}
      {tab === "policies" && <PoliciesTab />}
    </div>
  );
}
