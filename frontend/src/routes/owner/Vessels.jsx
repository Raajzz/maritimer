import { Plus, Ship } from "lucide-react";
import { useState } from "react";

import { Button, Card, DataTable, EmptyState, ErrorAlert, Input, Loader, Modal, PageHeader, Select } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api } from "../../lib/api";
import { humanize } from "../../lib/format";

const TYPES = ["BULK_CARRIER", "CONTAINER", "TANKER", "GENERAL_CARGO", "RORO", "LNG_LPG", "PASSENGER", "OFFSHORE", "OTHER"];
const BLANK = { name: "", imo_number: "", call_sign: "", flag_country_code: "", vessel_type: "BULK_CARRIER", dwt: "", grt: "", nrt: "", loa_m: "", beam_m: "", max_draft_m: "" };

function VesselModal({ vessel, onClose, onSaved }) {
  const countries = useResource("/countries");
  const [form, setForm] = useState(vessel ? Object.fromEntries(Object.keys(BLANK).map((k) => [k, vessel[k] ?? ""])) : BLANK);
  const bind = (n) => ({ name: n, value: form[n], onChange: (e) => setForm({ ...form, [n]: e.target.value }) });
  const save = useAction(async () => {
    const body = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" ? null : v]));
    body.name = form.name;
    body.call_sign = form.call_sign || "";
    if (vessel) await api.patch(`/vessels/${vessel.id}`, body);
    else await api.post("/vessels", body);
    onSaved();
  });
  return (
    <Modal title={vessel ? `Edit ${vessel.name}` : "Add vessel"} wide onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>Cancel</Button><Button busy={save.busy} disabled={!form.name} onClick={() => save.run()}>Save</Button></>}>
      <div className="grid grid-3">
        <Input label="Name *" {...bind("name")} />
        <Input label="IMO number" inputMode="numeric" maxLength={7} {...bind("imo_number")} hint="7 digits" />
        <Input label="Call sign" {...bind("call_sign")} />
        <Select label="Type" options={TYPES.map((t) => ({ value: t, label: humanize(t) }))} {...bind("vessel_type")} />
        <Select label="Flag" placeholder="—" options={(countries.data || []).map((c) => ({ value: c.code, label: c.name }))} {...bind("flag_country_code")} />
        <Input label="DWT" inputMode="decimal" {...bind("dwt")} />
        <Input label="GRT" inputMode="decimal" {...bind("grt")} />
        <Input label="NRT" inputMode="decimal" {...bind("nrt")} />
        <Input label="LOA (m)" inputMode="decimal" {...bind("loa_m")} />
        <Input label="Beam (m)" inputMode="decimal" {...bind("beam_m")} />
        <Input label="Max draft (m)" inputMode="decimal" {...bind("max_draft_m")} />
      </div>
      <ErrorAlert error={save.error} />
    </Modal>
  );
}

export default function Vessels() {
  const vessels = useResource("/vessels?page_size=100");
  const [editing, setEditing] = useState(null);
  const remove = useAction(async (v) => {
    await api.del(`/vessels/${v.id}`);
    vessels.refetch();
  });
  return (
    <div className="stack">
      <PageHeader title="Vessels" sub="Your fleet. Vessels with an active port call cannot be removed."
        actions={<Button variant="cta" icon={Plus} onClick={() => setEditing("new")}>Add vessel</Button>} />
      <ErrorAlert error={remove.error} />
      <Card>
        <Loader resource={vessels}>
          {(page) => (
            <DataTable rows={page.results} empty={<EmptyState icon={Ship} title="No vessels yet" />}
              columns={[
                { key: "name", label: "Name", render: (v) => <span className="strong">{v.name}</span> },
                { key: "imo", label: "IMO", render: (v) => v.imo_number || "—" },
                { key: "type", label: "Type", render: (v) => humanize(v.vessel_type) },
                { key: "flag", label: "Flag", render: (v) => v.flag_country_code || "—" },
                { key: "dwt", label: "DWT", num: true, render: (v) => v.dwt || "—" },
                { key: "act", label: "", render: (v) => (
                  <div className="row">
                    <Button size="sm" variant="secondary" onClick={() => setEditing(v)}>Edit</Button>
                    <Button size="sm" variant="ghost" onClick={() => remove.run(v)}>Remove</Button>
                  </div>
                ) },
              ]} />
          )}
        </Loader>
      </Card>
      {editing && <VesselModal vessel={editing === "new" ? null : editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); vessels.refetch(); }} />}
    </div>
  );
}
