import { useState } from "react";

import { Alert, Button, Card, DataTable, ErrorAlert, Input, Loader, PageHeader, Pager, Select } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { api, qs } from "../../lib/api";
import { formatDateTime, formatRate, fromLocalInput, humanize, toLocalInput } from "../../lib/format";

const SOURCE_LABEL = { ECB: "Market (ECB)", CURRENCY_API: "Market (currency-api)", MANUAL: "Manual" };

/** FX rates are append-only: corrections are new rows (SCHEMA.md D9). */
export default function FxRates() {
  const currencies = useResource("/currencies");
  const [filter, setFilter] = useState({ base: "INR", quote: "USD" });
  const [page, setPage] = useState(1);
  const rates = useResource(`/fx-rates${qs({ ...filter, page })}`);
  const [form, setForm] = useState({ base_currency_code: "INR", quote_currency_code: "USD", rate: "", as_of: toLocalInput(new Date().toISOString()), source_reference: "" });
  const bind = (n) => ({ name: n, value: form[n], onChange: (e) => setForm({ ...form, [n]: e.target.value }) });
  const add = useAction(async () => {
    await api.post("/fx-rates", { ...form, as_of: fromLocalInput(form.as_of), source: "MANUAL" });
    setForm({ ...form, rate: "", source_reference: "" });
    rates.refetch();
  });
  const [fetched, setFetched] = useState(null);
  const fetchMarket = useAction(async () => {
    setFetched(null);
    const fx = await api.post("/fx-rates/fetch", { base_currency_code: form.base_currency_code, quote_currency_code: form.quote_currency_code, as_of: fromLocalInput(form.as_of) });
    setFilter({ base: fx.base_currency_code, quote: fx.quote_currency_code });
    setPage(1);
    rates.refetch();
    setFetched(fx);
  });
  const opts = (currencies.data || []).map((c) => ({ value: c.code, label: `${c.code} · ${c.name}` }));
  return (
    <div className="stack">
      <PageHeader title="FX rates" sub="Rates used to convert vendor invoices into the owner's settlement currency." />
      <Card title="Record a rate">
        <form className="stack" onSubmit={(e) => { e.preventDefault(); add.run(); }}>
          <Alert tone="info">
            Rate = units of the quote currency per 1 unit of the base currency (1 INR = 0.0106 USD). Rates are fetched automatically at the time of each transaction:
            vendor invoices use the rate of their issue date, payments their payment date, other FDA lines the vessel's departure. Market rates come from the
            European Central Bank (via frankfurter.dev), or currency-api for currencies the ECB doesn't publish. A rate you record here is used instead when
            it is the latest one on or before the transaction.
          </Alert>
          <div className="grid grid-4">
            <Select label="Base" options={opts} {...bind("base_currency_code")} />
            <Select label="Quote" options={opts} {...bind("quote_currency_code")} />
            <Input label="Rate" inputMode="decimal" placeholder="0.0120000000" {...bind("rate")} />
            <Input label="Valid as of" type="datetime-local" {...bind("as_of")} />
          </div>
          <Input label="Source / reference" placeholder="RBI reference rate 13-Nov" {...bind("source_reference")} />
          <ErrorAlert error={add.error} />
          <ErrorAlert error={fetchMarket.error} />
          {fetched && (
            <Alert tone="success">
              Recorded 1 {fetched.base_currency_code} = {formatRate(fetched.rate)} {fetched.quote_currency_code} · {fetched.source_reference}
            </Alert>
          )}
          <div className="row">
            <Button type="submit" busy={add.busy} disabled={!form.rate}>Record rate</Button>
            <Button type="button" variant="secondary" busy={fetchMarket.busy} disabled={form.base_currency_code === form.quote_currency_code} onClick={() => fetchMarket.run()}>
              Fetch market rate for this date
            </Button>
          </div>
        </form>
      </Card>
      <Card title="History">
        <div className="grid grid-2" style={{ marginBottom: 12, maxWidth: 420 }}>
          <Select label="Base" options={opts} placeholder="Any" value={filter.base} onChange={(e) => { setFilter({ ...filter, base: e.target.value }); setPage(1); }} />
          <Select label="Quote" options={opts} placeholder="Any" value={filter.quote} onChange={(e) => { setFilter({ ...filter, quote: e.target.value }); setPage(1); }} />
        </div>
        <Loader resource={rates}>
          {(data) => (
            <>
              <DataTable rows={data.results} columns={[
                { key: "id", label: "ID", render: (r) => <span className="mono">#{r.id}</span> },
                { key: "pair", label: "Pair", render: (r) => `${r.base_currency_code} → ${r.quote_currency_code}` },
                { key: "rate", label: "Rate", num: true, render: (r) => formatRate(r.rate) },
                { key: "as_of", label: "Valid as of", render: (r) => formatDateTime(r.as_of) },
                { key: "source", label: "Source", render: (r) => `${SOURCE_LABEL[r.source] || humanize(r.source)}${r.source_reference ? ` · ${r.source_reference}` : ""}` },
              ]} />
              <Pager data={data} page={page} onPage={setPage} />
            </>
          )}
        </Loader>
      </Card>
    </div>
  );
}
