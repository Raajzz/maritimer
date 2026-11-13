import { Clock, ShieldAlert } from "lucide-react";

import { Button } from "../../components/ui";
import { useAuth } from "../../hooks/useAuth";

export default function PendingReview() {
  const { me, refreshMe, signOut } = useAuth();
  const suspended = me.next_step === "SUSPENDED";
  const Icon = suspended ? ShieldAlert : Clock;
  return (
    <div className="center-page">
      <div className="card auth-card stack" style={{ textAlign: "center", alignItems: "center" }}>
        <Icon size={40} color={suspended ? "var(--color-error)" : "var(--color-accent)"} aria-hidden />
        <h1>{suspended ? "Account suspended" : "Under review"}</h1>
        <p className="muted">
          {suspended
            ? me.user.status_reason || "An administrator has suspended this account. Contact support for help."
            : "Thanks for submitting your details. An administrator is checking your documents; you'll get full access once approved."}
        </p>
        {me.organization && <p className="small strong">{me.organization.legal_name}</p>}
        <div className="row">
          <Button variant="secondary" onClick={refreshMe}>Check again</Button>
          <Button variant="ghost" onClick={signOut}>Sign out</Button>
        </div>
      </div>
    </div>
  );
}
