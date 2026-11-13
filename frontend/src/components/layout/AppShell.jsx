import {
  Anchor,
  ClipboardCheck,
  Compass,
  Database,
  FileText,
  Inbox,
  LayoutDashboard,
  LogOut,
  MessageSquare,
  Ship,
  ScrollText,
  Building2,
  ArrowLeftRight,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../../hooks/useAuth";
import { initials } from "../../lib/format";
import ThemeToggle from "../ThemeToggle";
import { Button } from "../ui";

// Primary destinations per role; the first four also appear in the mobile tab bar.
const NAV = {
  OWNER: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/port-calls", label: "Port calls", icon: Anchor },
    { to: "/agents", label: "Find agents", icon: Compass },
    { to: "/chat", label: "Messages", icon: MessageSquare },
    { to: "/vessels", label: "Vessels", icon: Ship },
    { to: "/requests", label: "Requests", icon: Inbox },
  ],
  AGENT: [
    { to: "/", label: "Pipeline", icon: LayoutDashboard, end: true },
    { to: "/port-calls", label: "Port calls", icon: Anchor },
    { to: "/requests", label: "Requests", icon: Inbox },
    { to: "/chat", label: "Messages", icon: MessageSquare },
    { to: "/invoices", label: "Invoices", icon: FileText },
    { to: "/fx-rates", label: "FX rates", icon: ArrowLeftRight },
  ],
  MERCHANT: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/requests", label: "Requests", icon: Inbox },
    { to: "/invoices", label: "Invoices", icon: FileText },
    { to: "/chat", label: "Messages", icon: MessageSquare },
    { to: "/port-calls", label: "Jobs", icon: Anchor },
  ],
  ADMIN: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
    { to: "/admin/approvals", label: "Approvals", icon: ClipboardCheck },
    { to: "/admin/organizations", label: "Organizations", icon: Building2 },
    { to: "/admin/master-data", label: "Master data", icon: Database },
    { to: "/port-calls", label: "Port calls", icon: Anchor },
    { to: "/admin/audit", label: "Audit log", icon: ScrollText },
  ],
};

function Logo({ light }) {
  return (
    <span className="brand">
      <Anchor size={22} color={light ? "#fff" : "var(--color-accent)"} aria-hidden />
      Maritimer
    </span>
  );
}

export function AppShell() {
  const { me, signOut } = useAuth();
  const items = NAV[me.user.role] || [];
  const mobile = items.slice(0, 4);
  return (
    <div className="shell">
      <aside className="sidebar" aria-label="Main navigation">
        <Logo light />
        <nav>
          {items.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon size={18} aria-hidden /> {label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <div className="strong" style={{ color: "#fff" }}>{me.organization?.trade_name || me.organization?.legal_name || "Administrator"}</div>
          <div className="xs">{me.user.email}</div>
        </div>
      </aside>
      <div>
        <header className="topbar">
          <Logo />
          <span className="spacer" />
          <span className="small muted truncate" style={{ maxWidth: 180 }}>{me.user.role.toLowerCase()}</span>
          <ThemeToggle />
          <span className="avatar" title={me.user.display_name || me.user.email}>
            {me.user.photo_url ? <img src={me.user.photo_url} alt="" referrerPolicy="no-referrer" /> : initials(me.user.display_name || me.user.email)}
          </span>
          <Button variant="ghost" icon={LogOut} aria-label="Sign out" onClick={signOut} />
        </header>
        <main className="main">
          <Outlet />
        </main>
        <nav className="tabbar" aria-label="Main navigation">
          {mobile.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end}>
              <Icon size={20} aria-hidden />
              {label}
            </NavLink>
          ))}
          {items.length > 4 && (
            <NavLink to="/more">
              <LayoutDashboard size={20} aria-hidden />
              More
            </NavLink>
          )}
        </nav>
      </div>
    </div>
  );
}

export function MorePage() {
  const { me, signOut } = useAuth();
  const items = (NAV[me.user.role] || []).slice(4);
  return (
    <div className="stack">
      <h1>More</h1>
      <div className="card stack-sm">
        {items.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className="row" style={{ minHeight: 44 }}>
            <Icon size={18} aria-hidden /> {label}
          </NavLink>
        ))}
        <div className="divider" />
        <Button variant="secondary" icon={LogOut} onClick={signOut}>
          Sign out
        </Button>
      </div>
    </div>
  );
}
