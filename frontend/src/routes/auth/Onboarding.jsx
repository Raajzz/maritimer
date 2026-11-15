import { CheckCircle2, Trash2 } from "lucide-react";
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

function orgInitial(org) {
  return {
    legal_name: org.legal_name.endsWith("(draft)") ? "" : org.legal_name,
    trade_name: org.trade_name, registration_number: org.registration_number, tax_id: org.tax_id, email: org.email,
    phone: org.phone, website: org.website, address_line1: org.address_line1, address_line2: org.address_line2,
    city: org.city, postal_code: org.postal_code, country_code: org.country_code,
  };
}

function profileBody(role, form) {
  if (role === "OWNER") return { operator_kind: form.operator_kind, fleet_size: form.fleet_size === "" || form.fleet_size == null ? null : Number(form.fleet_size), preferred_currency_code: form.preferred_currency_code, notes: form.notes || "" };
  if (role === "AGENT") return { description: form.description || "", emergency_phone: form.emergency_phone || "", default_agency_fee: form.fee_amount ? { amount: form.fee_amount, currency_code: form.fee_currency } : null };
  return { description: form.description || "", catalog_notes: form.catalog_notes || "", default_currency_code: form.default_currency_code };
}

function OrganizationFields({ form, setForm, countries }) {
  const bind = (name) => ({ name, value: form[name] || "", onChange: (e) => setForm({ ...form, [name]: e.target.value }) });
  return (
    <Card title="1 · Company details">
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
    </Card>
  );
}

function ProfileFields({ role, form, setForm, currencies }) {
  const bind = (name) => ({ name, value: form[name] ?? "", onChange: (e) => setForm({ ...form, [name]: e.target.value }) });
  const currencyOptions = currencies.map((c) => ({ value: c.code, label: `${c.code} — ${c.name}` }));
  return (
    <Card title={`2 · ${role === "OWNER" ? "Owner" : role === "AGENT" ? "Agency" : "Vendor"} profile`}>
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
    </Card>
  );
}

function CoverageFields({ role, portIds, setPortIds, serviceIds, setServiceIds }) {
  const ports = useResource("/ports");
  const services = useResource("/service-categories?vendor_only=true");
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
      </div>
    </Card>
  );
}

function DocumentsFields({ documents, pending, setPending, onRemove, removeError }) {
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
              {d.status === "PENDING" && <Button variant="ghost" size="sm" icon={Trash2} aria-label="Remove document" onClick={() => onRemove(d.id)} />}
            </div>
          </div>
        ))}
        <div className="grid grid-3">
          <Select label="Document type" options={DOC_TYPES.map((v) => ({ value: v, label: humanize(v) }))} value={pending.docType} onChange={(e) => setPending({ ...pending, docType: e.target.value })} />
          <Input label="Title (optional)" value={pending.title} onChange={(e) => setPending({ ...pending, title: e.target.value })} />
          <Input key={pending.inputKey} label="File" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setPending({ ...pending, file: e.target.files[0] || null })}
            hint={pending.file ? "Uploaded when you save or submit." : "To add another document, save first, then choose the next file."} />
        </div>
        <ErrorAlert error={removeError} />
      </div>
    </Card>
  );
}

const EMPTY_PENDING = { docType: "COMPANY_REGISTRATION", title: "", file: null };

function OnboardingForm({ data, role, countries, currencies, onSaved, onSubmitted }) {
  const [org, setOrg] = useState(() => orgInitial(data.organization));
  const [profile, setProfile] = useState(() => ({
    ...data.profile,
    fee_amount: data.profile?.default_agency_fee?.amount || "",
    fee_currency: data.profile?.default_agency_fee?.currency_code || "USD",
  }));
  const [portIds, setPortIds] = useState(data.ports.map((p) => p.id));
  const [serviceIds, setServiceIds] = useState(data.services.map((s) => s.id));
  const [pending, setPending] = useState({ ...EMPTY_PENDING, inputKey: 0 });
  const [saved, setSaved] = useState(false);

  // Mirrors the server's completeness check, so the button reflects unsaved edits too.
  const missing = [];
  if (!org.legal_name?.trim()) missing.push("organization.legal_name");
  if (!org.country_code) missing.push("organization.country_code");
  if (!portIds.length) missing.push("coverage.ports");
  if (role !== "OWNER" && !serviceIds.length) missing.push("coverage.services");
  if (!data.documents.length && !pending.file) missing.push("documents");

  const saveAll = async () => {
    // A blank legal name is rejected by the server; skip company details until it is filled in.
    if (org.legal_name?.trim()) await api.put("/onboarding/organization", org);
    await api.put("/onboarding/profile", profileBody(role, profile));
    const coverage = { port_ids: portIds };
    if (role !== "OWNER") coverage.service_category_ids = serviceIds;
    await api.put("/onboarding/coverage", coverage);
    if (pending.file) {
      await api.upload("/onboarding/documents", { document_type: pending.docType, title: pending.title, file: pending.file });
      setPending({ ...EMPTY_PENDING, inputKey: pending.inputKey + 1 });
    }
  };
  const save = useAction(async () => {
    await saveAll();
    setSaved(true);
    onSaved();
  });
  const submit = useAction(async () => {
    await saveAll();
    await api.post("/onboarding/submit");
    await onSubmitted();
  });
  const remove = useAction(async (id) => {
    await api.del(`/onboarding/documents/${id}`);
    onSaved();
  });
  const touch = (setter) => (value) => { setSaved(false); setter(value); };
  const busy = save.busy || submit.busy;

  return (
    <div className="stack" style={{ marginTop: 16 }}>
      <OrganizationFields form={org} setForm={touch(setOrg)} countries={countries} />
      <ProfileFields role={role} form={profile} setForm={touch(setProfile)} currencies={currencies} />
      <CoverageFields role={role} portIds={portIds} setPortIds={touch(setPortIds)} serviceIds={serviceIds} setServiceIds={touch(setServiceIds)} />
      <DocumentsFields documents={data.documents} pending={pending} setPending={touch(setPending)} onRemove={(id) => remove.run(id)} removeError={remove.error} />
      <Card>
        <div className="stack">
          {missing.length ? (
            <Alert tone="warn">Still needed: {missing.map((m) => MISSING_LABELS[m] || m).join(", ")}.</Alert>
          ) : (
            <Alert tone="success"><CheckCircle2 size={16} aria-hidden /> Everything is filled in. Submit for review.</Alert>
          )}
          <ErrorAlert error={submit.error || save.error} />
          <div className="row">
            <Button variant="cta" disabled={missing.length > 0 || busy} busy={submit.busy} onClick={() => submit.run()}>Submit for review</Button>
            <Button variant="secondary" disabled={busy} busy={save.busy} onClick={() => save.run()}>Save and finish later</Button>
            {saved && <span className="small muted">Saved.</span>}
          </div>
        </div>
      </Card>
    </div>
  );
}

export default function Onboarding() {
  const { me, refreshMe, signOut } = useAuth();
  const onboarding = useResource("/onboarding");
  const countries = useResource("/countries");
  const currencies = useResource("/currencies");
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
        {(data) => countries.data && currencies.data ? (
          <OnboardingForm key={data.organization.id} data={data} role={role} countries={countries.data} currencies={currencies.data}
            onSaved={reload} onSubmitted={refreshMe} />
        ) : null}
      </Loader>
    </div>
  );
}
