import { Plus } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Button, Card, DataTable, EmptyState, Input, Loader, Money, PageHeader, Pager, Select, StatusBadge } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { qs } from "../../lib/api";
import { formatDate } from "../../lib/format";

export default function InvoiceList() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const [status, setStatus] = useState(me.user.role === "AGENT" ? "ISSUED" : "");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const resource = useResource(`/vendor-invoices${qs({ status, q, page })}`);
  const merchant = me.user.role === "MERCHANT";
  return (
    <div className="stack">
      <PageHeader title="Invoices" sub={merchant ? "Invoices you issued to port agents." : "Vendor invoices billed to you, in one place."}
        actions={merchant && <Button variant="cta" icon={Plus} onClick={() => navigate("/invoices/new")}>New invoice</Button>} />
      <Card>
        <div className="grid grid-2" style={{ marginBottom: 16 }}>
          <Input label="Search" placeholder="Invoice number or port call" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select label="Status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} placeholder="All statuses"
            options={["DRAFT", "ISSUED", "ACCEPTED", "REJECTED", "PAID", "VOID"].filter((s) => merchant || s !== "DRAFT").map((s) => ({ value: s, label: s.charAt(0) + s.slice(1).toLowerCase() }))} />
        </div>
        <Loader resource={resource}>
          {(data) => (
            <>
              <DataTable rows={data.results} onRowClick={(r) => navigate(`/invoices/${r.id}`)} empty={<EmptyState title="No invoices" />}
                columns={[
                  { key: "invoice_number", label: "Invoice", render: (r) => <span className="mono strong">{r.invoice_number}</span> },
                  { key: "pc", label: "Port call", render: (r) => r.port_call.reference },
                  { key: "party", label: merchant ? "Billed to" : "Vendor", render: (r) => (merchant ? r.agent.legal_name : r.vendor.legal_name) },
                  { key: "svc", label: "Service", render: (r) => r.service_category.name },
                  { key: "date", label: "Date", render: (r) => formatDate(r.issue_date) },
                  { key: "status", label: "Status", render: (r) => <StatusBadge status={r.status} /> },
                  { key: "total", label: "Total", num: true, render: (r) => <Money value={r.total} /> },
                ]} />
              <Pager data={data} page={page} onPage={setPage} />
            </>
          )}
        </Loader>
      </Card>
    </div>
  );
}
