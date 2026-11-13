import { CheckCircle2, FileUp, Trash2 } from "lucide-react";
import { useState } from "react";

import { Alert, Button, Card, CheckGroup, ErrorAlert, Input, Loader, PageHeader, Select, StatusBadge, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { api, openFile } from "../../lib/api";
import { humanize } from "../../lib/format";

const DOC_TYPES = ["COMPANY_REGISTRATION", "TAX_CERTIFICATE", "TRADE_LICENSE", "ID_PROOF", "BANK_PROOF", "OTHER"];
const MISSING_LABELS = {
  "organization.legal_name": "Company legal name",
  "organization.country_code": "Country",
  "coverage.ports": "At least one port",
  "coverage.services": "At least one service",
  documents: "At least one verification document",
};

function OrganizationForm({ org, countries, onSaved }) {
  const [form, setForm] = useState({
    legal_name: org.legal_name.endsWith("(draft)") ? "" : org.legal_name,
    trade_name: org.trade_name, registration_number: org.registration_number, tax_id: org.tax_id, email: org.email,
    phone: org.phone, website: org.website, address_line1: org.address_line1, address_line2: org.address_line2,
    city: org.city, postal_code: org.postal_code, country_code: org.country_code,
  });
  const save = useAction(async () => onSaved(await api.put("/onboarding/organization", form)));
  const bind = (name) => ({ name, value: form[name] || "", onChange: (e) => setForm({ ...form, [name]: e.target.value }) });
  return (
    <Card title="1 · Company details">
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        <div className="grid grid-2">
          <Input label="Legal name *" required {...bind("legal_name")} />
          <Input label="Trading name" {...bind("trade_name")} />
          <Input label="Registration number" {...bind("registration_number")} />
          <Input label="Tax ID (GST / UEN / VAT)" {...bind("tax_id")} />
          <Input label="Company email" type="email" {...bind("email")} />
          <Input label="Phone" type="tel" {...bind("phone")} />
          <Input label="Address" {...bind("address_line1")} />
          <Input label="Address line 2" {...bind("address_line2")} />
          <Input label="City" {...bind("city")} />
          <Input label="Postal code" {...bind("postal_code")} />
          <Select label="Country *" options={countries.map((c) => ({ value: c.code, label: c.name }))} {...bind("country_code")} />
          <Input label="Website" {...bind("website")} />
        </div>
        <ErrorAlert error={save.error} />
        <div><Button type="submit" busy={save.busy}>Save company details</Button></div>
      </form>
    </Card>
  );
}

function ProfileForm({ role, profile, currencies, onSaved }) {
  const [form, setForm] = useState({
    ...profile,
    fee_amount: profile?.default_agency_fee?.amount || "",
    fee_currency: profile?.default_agency_fee?.currency_code || "USD",
  });
  const bind = (name) => ({ name, value: form[name] ?? "", onChange: (e) => setForm({ ...form, [name]: e.target.value }) });
  const currencyOptions = currencies.map((c) => ({ value: c.code, label: `${c.code} — ${c.name}` }));
  const save = useAction(async () => {
    let body;
    if (role === "OWNER") body = { operator_kind: form.operator_kind, fleet_size: form.fleet_size === "" ? null : Number(form.fleet_size), preferred_currency_code: form.preferred_currency_code, notes: form.notes || "" };
    else if (role === "AGENT") body = { description: form.description || "", emergency_phone: form.emergency_phone || "", default_agency_fee: form.fee_amount ? { amount: form.fee_amount, currency_code: form.fee_currency } : null };
    else body = { description: form.description || "", catalog_notes: form.catalog_notes || "", default_currency_code: form.default_currency_code };
    onSaved(await api.put("/onboarding/profile", body));
  });
  return (
    <Card title={`2 · ${role === "OWNER" ? "Owner" : role === "AGENT" ? "Agency" : "Vendor"} profile`}>
      <form className="stack" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
        {role === "OWNER" && (
          <div className="grid grid-2">
            <Select label="You are the vessel's" options={["OWNER", "OPERATOR", "CHARTERER", "MANAGER"].map((v) => ({ value: v, label: humanize(v) }))} {...bind("operator_kind")} />
            <Input label="Fleet size" type="number" min="0" {...bind("fleet_size")} />
            <Select label="Preferred currency" options={currencyOptions} {...bind("preferred_currency_code")} />
            <Textarea label="Other details" {...bind("notes")} />
          </div>
        )}
        {role === "AGENT" && (
          <div className="grid grid-2">
            <Textarea label="About your agency" {...bind("description")} />
            <Input label="24/7 emergency phone" type="tel" {...bind("emergency_phone")} />
            <Input label="Standard agency fee" inputMode="decimal" placeholder="1500.00" {...bind("fee_amount")} hint="Pre-filled on new PDAs; you can change it per call." />
            <Select label="Fee currency" options={currencyOptions} {...bind("fee_currency")} />
          </div>
        )}
        {role === "MERCHANT" && (
          <div className="grid grid-2">
            <Textarea label="About your company" {...bind("description")} />
            <Textarea label="Goods & cargo offered" {...bind("catalog_notes")} />
            <Select label="Invoice currency" options={currencyOptions} {...bind("default_currency_code")} />
          </div>
        )}
        <ErrorAlert error={save.error} />
        <div><Button type="submit" busy={save.busy}>Save profile</Button></div>
      </form>
    </Card>
  );
}

function CoverageForm({ role, data, onSaved }) {
  const ports = useResource("/ports");
  const services = useResource("/service-categories?vendor_only=true");
  const [portIds, setPortIds] = useState(data.ports.map((p) => p.id));
  const [serviceIds, setServiceIds] = useState(data.services.map((s) => s.id));
  const save = useAction(async () => {
    const body = { port_ids: portIds };
    if (role !== "OWNER") body.service_category_ids = serviceIds;
    onSaved(await api.put("/onboarding/coverage", body));
  });
  return (
    <Card title="3 · Ports and services">
      <div className="stack">
        <div className="field">
          <label>Ports you {role === "OWNER" ? "call at" : "serve"}</label>
          <span className="hint">Locations are added automatically from the ports you choose.</span>
          <Loader resource={ports}>
            {(list) => <CheckGroup options={list.map((p) => ({ value: p.id, label: `${p.name} (${p.location.name})` }))} value={portIds} onChange={setPortIds} />}
          </Loader>
        </div>
        {role !== "OWNER" && (
          <div className="field">
            <label>Services you offer</label>
            <Loader resource={services}>
              {(list) => <CheckGroup options={list.map((s) => ({ value: s.id, label: s.name }))} value={serviceIds} onChange={setServiceIds} />}
            </Loader>
          </div>
        )}
        <ErrorAlert error={save.error} />
        <div><Button busy={save.busy} onClick={() => save.run()}>Save coverage</Button></div>
      </div>
    </Card>
  );
}

function DocumentsForm({ documents, onChanged }) {
  const [docType, setDocType] = useState("COMPANY_REGISTRATION");
  const [title, setTitle] = useState("");
  const [file, setFile] = useState(null);
  const upload = useAction(async () => {
    await api.upload("/onboarding/documents", { document_type: docType, title, file });
    setFile(null);
    setTitle("");
    onChanged();
  });
  const remove = useAction(async (id) => {
    await api.del(`/onboarding/documents/${id}`);
    onChanged();
  });
  return (
    <Card title="4 · Verification documents">
      <div className="stack">
        <p className="small muted">Upload your company registration, tax certificate or licence (PDF, PNG, JPEG or WEBP, up to 15 MB). An administrator reviews them before approving your account.</p>
        {documents.map((d) => (
          <div key={d.id} className="row-between card" style={{ padding: 12 }}>
            <div className="stack-sm" style={{ gap: 2 }}>
              <span className="strong small">{humanize(d.document_type)}{d.title ? ` · ${d.title}` : ""}</span>
              <button type="button" className="btn-ghost small" style={{ border: 0, padding: 0, textAlign: "left", cursor: "pointer", color: "var(--color-accent-text)" }} onClick={() => openFile(d.file)}>
                {d.file.original_filename}
              </button>
              {d.review_note && <span className="xs muted">Reviewer: {d.review_note}</span>}
            </div>
            <div className="row">
              <StatusBadge status={d.status} />
              {d.status === "PENDING" && <Button variant="ghost" size="sm" icon={Trash2} aria-label="Remove document" onClick={() => remove.run(d.id)} />}
            </div>
          </div>
        ))}
        <div className="grid grid-3">
          <Select label="Document type" options={DOC_TYPES.map((v) => ({ value: v, label: humanize(v) }))} value={docType} onChange={(e) => setDocType(e.target.value)} />
          <Input label="Title (optional)" value={title} onChange={(e) => setTitle(e.target.value)} />
          <Input label="File" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files[0] || null)} />
        </div>
        <ErrorAlert error={upload.error || remove.error} />
        <div><Button variant="secondary" icon={FileUp} disabled={!file} busy={upload.busy} onClick={() => upload.run()}>Upload document</Button></div>
      </div>
    </Card>
  );
}

export default function Onboarding() {
  const { me, refreshMe, signOut } = useAuth();
  const onboarding = useResource("/onboarding");
  const countries = useResource("/countries");
  const currencies = useResource("/currencies");
  const submit = useAction(async () => {
    await api.post("/onboarding/submit");
    await refreshMe();
  });
  const role = me.user.role;
  const reload = () => onboarding.refetch();
  return (
    <div className="main" style={{ maxWidth: 960 }}>
      <PageHeader
        title="Set up your account"
        sub={`Registering as ${humanize(role)} · ${me.user.email}`}
        actions={<Button variant="ghost" onClick={signOut}>Sign out</Button>}
      />
      {me.next_step === "REJECTED" && (
        <Alert tone="error">
          <strong>Your application was not approved.</strong> {me.user.status_reason || ""} Update the details below and submit again.
        </Alert>
      )}
      <Loader resource={onboarding}>
        {(data) => (
          <div className="stack" style={{ marginTop: 16 }}>
            {countries.data && (
              <OrganizationForm key={`org-${data.organization.id}`} org={data.organization} countries={countries.data} onSaved={reload} />
            )}
            {currencies.data && <ProfileForm role={role} profile={data.profile} currencies={currencies.data} onSaved={reload} />}
            <CoverageForm role={role} data={data} onSaved={reload} />
            <DocumentsForm documents={data.documents} onChanged={reload} />
            <Card>
              <div className="stack">
                {data.completeness.missing.length ? (
                  <Alert tone="warn">
                    Still needed: {data.completeness.missing.map((m) => MISSING_LABELS[m] || m).join(", ")}.
                  </Alert>
                ) : (
                  <Alert tone="success"><CheckCircle2 size={16} aria-hidden /> Everything is filled in. Submit for review.</Alert>
                )}
                <ErrorAlert error={submit.error} />
                <div>
                  <Button variant="cta" disabled={data.completeness.missing.length > 0} busy={submit.busy} onClick={() => submit.run()}>
                    Submit for review
                  </Button>
                </div>
              </div>
            </Card>
          </div>
        )}
      </Loader>
    </div>
  );
}
