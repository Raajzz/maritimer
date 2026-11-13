import { ArrowLeft, FileDown } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { LineItemsTable, VarianceTable } from "../../components/domain";
import { Button, Card, ErrorAlert, Loader, PageHeader, StatusBadge } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useResource } from "../../hooks/useResource";
import { openDocument } from "../../lib/api";

/** Read-only view of any PDA/FDA version (history links, dispute adjustments). Editing happens on the port call. */
export default function AccountPage() {
  const { id } = useParams();
  const resource = useResource(`/disbursement-accounts/${id}`);
  const pdf = useAction(() => openDocument(`/disbursement-accounts/${id}/pdf`));
  return (
    <Loader resource={resource}>
      {(acc) => (
        <div className="stack">
          <PageHeader
            back={<Link to={`/port-calls/${acc.port_call_id}?tab=${acc.kind.toLowerCase()}`} className="row small"><ArrowLeft size={16} aria-hidden /> Back to port call</Link>}
            title={<span className="row">{acc.reference} <StatusBadge status={acc.status} /></span>}
            sub={`${acc.kind} version ${acc.version}${acc.is_current ? " (current)" : ""}`}
            actions={<Button variant="secondary" icon={FileDown} onClick={() => pdf.run()}>PDF</Button>}
          />
          <ErrorAlert error={pdf.error} />
          <Card title="Line items"><LineItemsTable account={acc} /></Card>
          {acc.variance && <Card title="Variance against the PDA"><VarianceTable variance={acc.variance} /></Card>}
        </div>
      )}
    </Loader>
  );
}
