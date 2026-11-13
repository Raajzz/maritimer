import { Anchor, Ship, Store } from "lucide-react";
import { useState } from "react";

import { Button, ErrorAlert } from "../../components/ui";
import { useAction } from "../../hooks/useAction";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../lib/api";

const ROLES = [
  { role: "OWNER", icon: Ship, title: "Shipowner / operator", text: "Find port agents, approve estimates, track advances, review final accounts." },
  { role: "AGENT", icon: Anchor, title: "Port agent", text: "Handle port calls for many owners: PDAs, vendors, FDAs and settlement." },
  { role: "MERCHANT", icon: Store, title: "Merchant / vendor", text: "Pilotage, tugs, water, provisions and more: accept jobs and invoice agents." },
];

export default function ChooseRole() {
  const { me, refreshMe, signOut } = useAuth();
  const [role, setRole] = useState(null);
  const action = useAction(async () => {
    await api.post("/auth/choose-role", { role });
    await refreshMe();
  });
  return (
    <div className="center-page">
      <div className="card stack" style={{ maxWidth: 720, width: "100%" }}>
        <div>
          <h1>Welcome{me.user.display_name ? `, ${me.user.display_name.split(" ")[0]}` : ""}</h1>
          <p className="muted">How will you use Maritimer? Your role decides what you can see and do. An administrator verifies every account.</p>
        </div>
        <div className="grid grid-3">
          {ROLES.map(({ role: r, icon: Icon, title, text }) => (
            <button
              key={r}
              type="button"
              className="card"
              onClick={() => setRole(r)}
              aria-pressed={role === r}
              style={{ textAlign: "left", cursor: "pointer", borderColor: role === r ? "var(--color-accent)" : undefined, boxShadow: role === r ? "var(--focus-ring)" : undefined }}
            >
              <Icon size={28} color="var(--color-accent)" aria-hidden />
              <h3 style={{ margin: "8px 0 4px" }}>{title}</h3>
              <p className="small muted">{text}</p>
            </button>
          ))}
        </div>
        <ErrorAlert error={action.error} />
        <div className="row-between">
          <Button variant="ghost" onClick={signOut}>Sign out</Button>
          <Button variant="cta" disabled={!role} busy={action.busy} onClick={() => action.run()}>
            Continue
          </Button>
        </div>
      </div>
    </div>
  );
}
