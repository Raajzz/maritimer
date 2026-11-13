import { ArrowLeft } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { Alert, Button, Card, ErrorAlert, Input, Loader, PageHeader, Select, Textarea } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api } from "../../lib/api";

function addDecimals(a, b) {
  // Two-decimal string addition without floats.
  const toCents = (s) => {
    const [i, f = ""] = String(s || "0").split(".");
    return BigInt(i || "0") * 100n + BigInt((f + "00").slice(0, 2)) * (String(s).trim().startsWith("-") ? -1n : 1n);
  };
  const cents = toCents(a) + toCents(b);
  const sign = cents < 0n ? "-" : "";
  const abs = cents < 0n ? -cents : cents;
  return `${sign}${abs / 100n}.${String(abs % 100n).padStart(2, "0")}`;
}

/** Merchant flow 6: issue an invoice (usually INR) against an accepted service request. */
export default function NewInvoice() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const requests = useResource("/requests?direction=incoming&status=ACCEPTED&request_type=VENDOR_SERVICE&page_size=100");
  const services = useResource("/service-categories?vendor_only=true");
  const currencies = useResource("/currencies");
  const [requestId, setRequestId] = useState(params.get("request") || "");
  const [form, setForm] = useState({ invoice_number: "", issue_date: new Date().toISOString().slice(0, 10), due_date: "", currency_code: "INR", subtotal_amount: "", tax_amount: "0.00", service_category_id: "", notes: "" });
  const [file, setFile] = useState(null);
  const bind = (n) => ({ name: n, value: form[n], onChange: (e) => setForm({ ...form, [n]: e.target.value }) });
  const selected = requests.data?.results.find((r) => String(r.id) === String(requestId));
  const validAmounts = /^\d+(\.\d{1,2})?$/.test(form.subtotal_amount) && /^\d+(\.\d{1,2})?$/.test(form.tax_amount || "0");
  const total = validAmounts ? addDecimals(form.subtotal_amount, form.tax_amount || "0") : "";

  const save = useAction(async (issue) => {
    const uploaded = file ? await api.upload("/files", { file, purpose: "INVOICE" }) : null;
    const invoice = await api.post("/vendor-invoices", {
      ...form, due_date: form.due_date || null, port_call_id: selected.port_call.id, vendor_request_id: selected.id,
      service_category_id: Number(form.service_category_id), total_amount: total, file_id: uploaded?.id ?? null,
    });
    if (issue) await api.post(`/vendor-invoices/${invoice.id}/issue`);
    navigate(`/invoices/${invoice.id}`);
  });
  const ready = selected && form.invoice_number && form.service_category_id && validAmounts;
  return (
    <div className="stack" style={{ maxWidth: 820 }}>
      <PageHeader back={<Link to="/invoices" className="row small"><ArrowLeft size={16} aria-hidden /> Invoices</Link>} title="New invoice" />
      <Card>
        <Loader resource={requests}>
          {(page) => page.results.length ? (
            <div className="stack">
              <Select label="Service request *" placeholder="Choose the job you are invoicing…" value={requestId} onChange={(e) => setRequestId(e.target.value)}
                options={page.results.map((r) => ({ value: r.id, label: `${r.reference} · ${r.subject || "Service"} · ${r.port_call?.reference} (${r.from_organization.legal_name})` }))} />
              <div className="grid grid-3">
                <Input label="Your invoice number *" {...bind("invoice_number")} />
                <Input label="Issue date" type="date" {...bind("issue_date")} />
                <Input label="Due date" type="date" {...bind("due_date")} />
                <Select label="Service *" placeholder="Choose…" options={(services.data || []).map((s) => ({ value: s.id, label: s.name }))} {...bind("service_category_id")} />
                <Select label="Currency" options={(currencies.data || [{ code: "INR" }]).map((c) => ({ value: c.code, label: c.code }))} {...bind("currency_code")} />
                <Input label="Subtotal *" inputMode="decimal" placeholder="95000.00" {...bind("subtotal_amount")} />
                <Input label="Tax (GST)" inputMode="decimal" {...bind("tax_amount")} />
                <Input label="Total" value={total} readOnly hint="Subtotal + tax" />
                <Input label="Invoice file (PDF or image)" type="file" accept="application/pdf,image/png,image/jpeg,image/webp" onChange={(e) => setFile(e.target.files[0] || null)} />
              </div>
              <Textarea label="Notes" {...bind("notes")} />
              {!file && <Alert tone="warn">Attach the invoice file to issue it; you can save a draft without one.</Alert>}
              <ErrorAlert error={save.error} />
              <div className="row">
                <Button variant="cta" busy={save.busy} disabled={!ready || !file} onClick={() => save.run(true)}>Issue to agent</Button>
                <Button variant="secondary" busy={save.busy} disabled={!ready} onClick={() => save.run(false)}>Save draft</Button>
              </div>
            </div>
          ) : <Alert tone="info">You can invoice once you have accepted a service request from an agent.</Alert>}
        </Loader>
      </Card>
    </div>
  );
}
