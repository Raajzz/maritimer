import { Navigate, Route, Routes, useLocation } from "react-router-dom";

import { AppShell, MorePage } from "./components/layout/AppShell";
import { ErrorAlert, Spinner } from "./components/ui";
import { useAuth } from "./hooks/useAuth";
import AdminAudit from "./routes/admin/Audit";
import AdminDashboard from "./routes/admin/Dashboard";
import AdminApprovals from "./routes/admin/Approvals";
import AdminMasterData from "./routes/admin/MasterData";
import AdminOrganizationDetail from "./routes/admin/OrganizationDetail";
import AdminOrganizations from "./routes/admin/Organizations";
import AdminUserDetail from "./routes/admin/UserDetail";
import AgentDashboard from "./routes/agent/Dashboard";
import FxRates from "./routes/agent/FxRates";
import ChooseRole from "./routes/auth/ChooseRole";
import Onboarding from "./routes/auth/Onboarding";
import PendingReview from "./routes/auth/PendingReview";
import SignIn from "./routes/auth/SignIn";
import MerchantDashboard from "./routes/merchant/Dashboard";
import NewInvoice from "./routes/merchant/NewInvoice";
import AgentProfile from "./routes/owner/AgentProfile";
import Discovery from "./routes/owner/Discovery";
import NewRequest from "./routes/owner/NewRequest";
import OwnerDashboard from "./routes/owner/Dashboard";
import Vessels from "./routes/owner/Vessels";
import AccountPage from "./routes/shared/AccountPage";
import ChatPage from "./routes/shared/ChatPage";
import DisputePage from "./routes/shared/DisputePage";
import InvoiceDetail from "./routes/shared/InvoiceDetail";
import InvoiceList from "./routes/shared/InvoiceList";
import NotFound from "./routes/shared/NotFound";
import PortCallList from "./routes/shared/PortCallList";
import PortCallPage from "./routes/shared/PortCallPage";
import RequestDetail from "./routes/shared/RequestDetail";
import RequestList from "./routes/shared/RequestList";

const HOME = { OWNER: OwnerDashboard, AGENT: AgentDashboard, MERCHANT: MerchantDashboard, ADMIN: AdminDashboard };

function RequireRole({ roles, children }) {
  const { me } = useAuth();
  return roles.includes(me.user.role) ? children : <NotFound />;
}

/** Routes by /auth/me `next_step`. The backend enforces the same rules on every endpoint. */
export default function App() {
  const { me, loading, signedIn, error } = useAuth();
  const location = useLocation();

  if (loading) return <div className="center-page"><Spinner /></div>;
  if (!signedIn || !me) {
    return (
      <Routes>
        <Route path="/signin" element={<SignIn error={signedIn ? error : null} />} />
        <Route path="*" element={<Navigate to="/signin" replace state={{ from: location.pathname }} />} />
      </Routes>
    );
  }

  const step = me.next_step;
  if (step === "CHOOSE_ROLE") return <Routes><Route path="*" element={<ChooseRole />} /></Routes>;
  if (step === "ONBOARDING" || step === "REJECTED") return <Routes><Route path="*" element={<Onboarding />} /></Routes>;
  if (step === "PENDING_REVIEW" || step === "SUSPENDED") return <Routes><Route path="*" element={<PendingReview />} /></Routes>;
  if (step !== "APP") return <div className="center-page"><ErrorAlert error={{ message: `Unknown account state ${step}` }} /></div>;

  const Home = HOME[me.user.role];
  const owner = ["OWNER"];
  const agent = ["AGENT"];
  const admin = ["ADMIN"];
  return (
    <Routes>
      <Route path="/signin" element={<Navigate to={location.state?.from || "/"} replace />} />
      <Route element={<AppShell />}>
        <Route index element={<Home />} />
        <Route path="more" element={<MorePage />} />
        <Route path="port-calls" element={<PortCallList />} />
        <Route path="port-calls/:id" element={<PortCallPage />} />
        <Route path="accounts/:id" element={<RequireRole roles={["OWNER", "AGENT", "ADMIN"]}><AccountPage /></RequireRole>} />
        <Route path="disputes/:id" element={<RequireRole roles={["OWNER", "AGENT", "ADMIN"]}><DisputePage /></RequireRole>} />
        <Route path="requests" element={<RequireRole roles={["OWNER", "AGENT", "MERCHANT"]}><RequestList /></RequireRole>} />
        <Route path="requests/:id" element={<RequestDetail />} />
        <Route path="invoices" element={<RequireRole roles={["AGENT", "MERCHANT", "OWNER"]}><InvoiceList /></RequireRole>} />
        <Route path="invoices/new" element={<RequireRole roles={["MERCHANT"]}><NewInvoice /></RequireRole>} />
        <Route path="invoices/:id" element={<InvoiceDetail />} />
        <Route path="chat" element={<RequireRole roles={["OWNER", "AGENT", "MERCHANT"]}><ChatPage /></RequireRole>} />
        <Route path="chat/:id" element={<RequireRole roles={["OWNER", "AGENT", "MERCHANT"]}><ChatPage /></RequireRole>} />
        <Route path="agents" element={<RequireRole roles={owner}><Discovery /></RequireRole>} />
        <Route path="agents/:id" element={<RequireRole roles={["OWNER", "ADMIN"]}><AgentProfile /></RequireRole>} />
        <Route path="vessels" element={<RequireRole roles={owner}><Vessels /></RequireRole>} />
        <Route path="requests/new" element={<RequireRole roles={owner}><NewRequest /></RequireRole>} />
        <Route path="fx-rates" element={<RequireRole roles={["AGENT", "ADMIN"]}><FxRates /></RequireRole>} />
        <Route path="admin/approvals" element={<RequireRole roles={admin}><AdminApprovals /></RequireRole>} />
        <Route path="admin/users/:id" element={<RequireRole roles={admin}><AdminUserDetail /></RequireRole>} />
        <Route path="admin/organizations" element={<RequireRole roles={admin}><AdminOrganizations /></RequireRole>} />
        <Route path="admin/organizations/:id" element={<RequireRole roles={admin}><AdminOrganizationDetail /></RequireRole>} />
        <Route path="admin/master-data" element={<RequireRole roles={admin}><AdminMasterData /></RequireRole>} />
        <Route path="admin/audit" element={<RequireRole roles={admin}><AdminAudit /></RequireRole>} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
