import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { PortCallTable } from "../../components/domain";
import { Card, Input, Loader, PageHeader, Pager, Select } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";
import { useResource } from "../../hooks/useResource";
import { qs } from "../../lib/api";

const GROUPS = [
  ["", "All stages"], ["pda_sent", "PDA stage"], ["advance_received", "Advance / approved"], ["in_port", "In port / departed"],
  ["fda_issued", "FDA issued"], ["disputed", "Disputed"], ["settled", "Final / settled / closed"],
];

export default function PortCallList() {
  const { me } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [group, setGroup] = useState("");
  const [sort, setSort] = useState("-status_changed_at");
  const [page, setPage] = useState(1);
  const resource = useResource(`/port-calls${qs({ q, status_group: group, sort, page })}`);
  return (
    <div className="stack">
      <PageHeader title={me.user.role === "MERCHANT" ? "Jobs" : "Port calls"} sub="Every port call you are part of." />
      <Card>
        <div className="grid grid-3" style={{ marginBottom: 16 }}>
          <Input label="Search" placeholder="Reference, vessel or port" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          <Select label="Stage" value={group} onChange={(e) => { setGroup(e.target.value); setPage(1); }} options={GROUPS.map(([value, label]) => ({ value, label }))} />
          <Select label="Sort" value={sort} onChange={(e) => setSort(e.target.value)} options={[
            { value: "-status_changed_at", label: "Recently updated" }, { value: "eta", label: "ETA (soonest)" }, { value: "-eta", label: "ETA (latest)" }, { value: "-reference", label: "Reference" },
          ]} />
        </div>
        <Loader resource={resource}>
          {(data) => (
            <>
              <PortCallTable rows={data.results} onOpen={(r) => navigate(`/port-calls/${r.id}`)} />
              <Pager data={data} page={page} onPage={setPage} />
            </>
          )}
        </Loader>
      </Card>
    </div>
  );
}
