"""All routes under /api/v1 (API.md)."""
from django.urls import path

from apps.accounts import views as accounts
from apps.adminpanel import views as admin
from apps.chat import views as chat
from apps.core import views as core
from apps.dashboards import views as dashboards
from apps.disbursements import views as accounts_da
from apps.disputes import views as disputes
from apps.documents import views as documents
from apps.invoices import views as invoices
from apps.masterdata import views as master
from apps.payments import views as payments
from apps.portcalls import views as portcalls
from apps.ratings import views as ratings
from apps.requests import views as requests_
from apps.vessels import views as vessels

urlpatterns = [
    # §1 Auth
    path("health", core.HealthView.as_view()),
    path("auth/me", accounts.MeView.as_view()),
    path("auth/choose-role", accounts.ChooseRoleView.as_view()),
    path("auth/logout", accounts.LogoutView.as_view()),
    # §2 Onboarding
    path("onboarding", accounts.OnboardingView.as_view()),
    path("onboarding/organization", accounts.OnboardingOrganizationView.as_view()),
    path("onboarding/profile", accounts.OnboardingProfileView.as_view()),
    path("onboarding/coverage", accounts.OnboardingCoverageView.as_view()),
    path("onboarding/documents", accounts.OnboardingDocumentsView.as_view()),
    path("onboarding/documents/<int:pk>", accounts.OnboardingDocumentDetailView.as_view()),
    path("onboarding/submit", accounts.OnboardingSubmitView.as_view()),
    # §3 Master data
    path("meta/enums", core.EnumsView.as_view()),
    path("countries", master.CountryListView.as_view()),
    path("locations", master.LocationListView.as_view()),
    path("ports", master.PortListView.as_view()),
    path("service-categories", master.ServiceCategoryListView.as_view()),
    path("cargo-types", master.CargoTypeListView.as_view()),
    path("currencies", master.CurrencyListView.as_view()),
    path("fx-rates", master.FxRateListView.as_view()),
    path("fx-rates/latest", master.FxRateLatestView.as_view()),
    path("admin/locations", admin.AdminLocationCreateView.as_view()),
    path("admin/locations/<int:pk>", admin.AdminLocationDetailView.as_view()),
    path("admin/ports", admin.AdminPortCreateView.as_view()),
    path("admin/ports/<int:pk>", admin.AdminPortDetailView.as_view()),
    path("admin/service-categories", admin.AdminServiceCreateView.as_view()),
    path("admin/service-categories/<int:pk>", admin.AdminServiceDetailView.as_view()),
    path("admin/cargo-types", admin.AdminCargoCreateView.as_view()),
    path("admin/cargo-types/<int:pk>", admin.AdminCargoDetailView.as_view()),
    path("admin/currencies/<str:pk>", admin.AdminCurrencyDetailView.as_view()),
    path("admin/request-policies", admin.AdminPolicyListView.as_view()),
    path("admin/request-policies/<int:pk>", admin.AdminPolicyDetailView.as_view()),
    # §4 Admin
    path("admin/dashboard", admin.AdminDashboardView.as_view()),
    path("admin/users", admin.AdminUserListView.as_view()),
    path("admin/users/<int:pk>", admin.AdminUserDetailView.as_view()),
    path("admin/users/<int:pk>/approve", admin.AdminUserApproveView.as_view()),
    path("admin/users/<int:pk>/reject", admin.AdminUserRejectView.as_view()),
    path("admin/users/<int:pk>/suspend", admin.AdminUserSuspendView.as_view()),
    path("admin/users/<int:pk>/reinstate", admin.AdminUserReinstateView.as_view()),
    path("admin/organizations", admin.AdminOrganizationListView.as_view()),
    path("admin/organizations/<int:pk>", admin.AdminOrganizationDetailView.as_view()),
    path("admin/organizations/<int:pk>/approve", admin.AdminOrganizationApproveView.as_view()),
    path("admin/organizations/<int:pk>/reject", admin.AdminOrganizationRejectView.as_view()),
    path("admin/organizations/<int:pk>/suspend", admin.AdminOrganizationSuspendView.as_view()),
    path("admin/organizations/<int:pk>/reinstate", admin.AdminOrganizationReinstateView.as_view()),
    path("admin/organizations/<int:pk>/users", admin.AdminOrganizationUsersView.as_view()),
    path("admin/documents/<int:pk>/approve", admin.AdminDocumentApproveView.as_view()),
    path("admin/documents/<int:pk>/reject", admin.AdminDocumentRejectView.as_view()),
    path("admin/audit-log", admin.AdminAuditLogView.as_view()),
    path("admin/payments/<int:pk>/confirm", payments.PaymentConfirmView.as_view()),
    path("admin/payments/<int:pk>/cancel", payments.PaymentCancelView.as_view()),
    # §5 Discovery
    path("agents", accounts.AgentListView.as_view()),
    path("agents/<int:pk>", accounts.AgentDetailView.as_view()),
    path("merchants", accounts.MerchantListView.as_view()),  # PROGRESS.md C11
    # §6 Vessels
    path("vessels", vessels.VesselListView.as_view()),
    path("vessels/<int:pk>", vessels.VesselDetailView.as_view()),
    # §7 Requests
    path("requests", requests_.RequestListView.as_view()),
    path("requests/<int:pk>", requests_.RequestDetailView.as_view()),
    path("requests/<int:pk>/accept", requests_.RequestAcceptView.as_view()),
    path("requests/<int:pk>/decline", requests_.RequestDeclineView.as_view()),
    path("requests/<int:pk>/withdraw", requests_.RequestWithdrawView.as_view()),
    # §8 Port calls
    path("port-calls", portcalls.PortCallListView.as_view()),
    path("port-calls/<int:pk>", portcalls.PortCallDetailView.as_view()),
    path("port-calls/<int:pk>/arrive", portcalls.PortCallArriveView.as_view()),
    path("port-calls/<int:pk>/depart", portcalls.PortCallDepartView.as_view()),
    path("port-calls/<int:pk>/cancel", portcalls.PortCallCancelView.as_view()),
    path("port-calls/<int:pk>/close", portcalls.PortCallCloseView.as_view()),
    path("port-calls/<int:pk>/timeline", portcalls.PortCallTimelineView.as_view()),
    path("port-calls/<int:pk>/vendor-requests", portcalls.PortCallVendorRequestsView.as_view()),
    path("port-calls/<int:pk>/documents", portcalls.PortCallDocumentsView.as_view()),
    # §9 PDA / FDA
    path("port-calls/<int:pk>/pda", accounts_da.CurrentPdaView.as_view()),
    path("port-calls/<int:pk>/pda/versions", accounts_da.PdaVersionsView.as_view()),
    path("port-calls/<int:pk>/fda", accounts_da.CurrentFdaView.as_view()),
    path("port-calls/<int:pk>/fda/versions", accounts_da.FdaVersionsView.as_view()),
    path("port-calls/<int:pk>/fda/generate", accounts_da.GenerateFdaView.as_view()),
    path("disbursement-accounts/<int:pk>", accounts_da.AccountDetailView.as_view()),
    path("disbursement-accounts/<int:pk>/line-items", accounts_da.AccountLinesView.as_view()),
    path("disbursement-accounts/<int:pk>/issue", accounts_da.AccountIssueView.as_view()),
    path("disbursement-accounts/<int:pk>/approve", accounts_da.AccountApproveView.as_view()),
    path("disbursement-accounts/<int:pk>/reject", accounts_da.AccountRejectView.as_view()),
    path("disbursement-accounts/<int:pk>/accept", accounts_da.AccountAcceptView.as_view()),
    path("disbursement-accounts/<int:pk>/revise", accounts_da.AccountReviseView.as_view()),
    path("disbursement-accounts/<int:pk>/finalize", accounts_da.AccountFinalizeView.as_view()),
    path("disbursement-accounts/<int:pk>/discard", accounts_da.AccountDiscardView.as_view()),
    path("disbursement-accounts/<int:pk>/pdf", accounts_da.AccountPdfView.as_view()),
    # §10 Vendor invoices
    path("vendor-invoices", invoices.InvoiceListView.as_view()),
    path("vendor-invoices/<int:pk>", invoices.InvoiceDetailView.as_view()),
    path("vendor-invoices/<int:pk>/issue", invoices.InvoiceIssueView.as_view()),
    path("vendor-invoices/<int:pk>/accept", invoices.InvoiceAcceptView.as_view()),
    path("vendor-invoices/<int:pk>/reject", invoices.InvoiceRejectView.as_view()),
    path("vendor-invoices/<int:pk>/reopen", invoices.InvoiceReopenView.as_view()),
    path("vendor-invoices/<int:pk>/void", invoices.InvoiceVoidView.as_view()),
    path("vendor-invoices/<int:pk>/mark-paid", invoices.InvoiceMarkPaidView.as_view()),
    path("vendor-invoices/<int:pk>/file", invoices.InvoiceFileView.as_view()),
    # §11 Payments & settlement
    path("port-calls/<int:pk>/payments", payments.PortCallPaymentsView.as_view()),
    path("payments/<int:pk>", payments.PaymentDetailView.as_view()),
    path("payments/<int:pk>/confirm", payments.PaymentConfirmView.as_view()),
    path("payments/<int:pk>/cancel", payments.PaymentCancelView.as_view()),
    path("port-calls/<int:pk>/settlement", payments.PortCallSettlementView.as_view()),
    path("settlements/<int:pk>/force-close", payments.SettlementForceCloseView.as_view()),
    path("settlements/<int:pk>/pdf", payments.SettlementPdfView.as_view()),
    # §12 Disputes
    path("disputes", disputes.DisputeListView.as_view()),
    path("disputes/<int:pk>", disputes.DisputeDetailView.as_view()),
    path("disputes/<int:pk>/comment", disputes.DisputeCommentView.as_view()),
    path("disputes/<int:pk>/acknowledge", disputes.DisputeAcknowledgeView.as_view()),
    path("disputes/<int:pk>/resolve", disputes.DisputeResolveView.as_view()),
    path("disputes/<int:pk>/reject", disputes.DisputeRejectView.as_view()),
    path("disputes/<int:pk>/withdraw", disputes.DisputeWithdrawView.as_view()),
    path("disputes/<int:pk>/reopen", disputes.DisputeReopenView.as_view()),
    # §13 Files
    path("files", documents.FileUploadView.as_view()),
    path("files/<int:pk>", documents.FileDetailView.as_view()),
    path("files/download/<str:token>", documents.FileDownloadView.as_view(), name="file-download"),
    # §14 Chat
    path("chat/threads", chat.ThreadListView.as_view()),
    path("chat/threads/<int:pk>", chat.ThreadDetailView.as_view()),
    path("chat/threads/<int:pk>/messages", chat.ThreadMessagesView.as_view()),
    path("chat/threads/<int:pk>/read", chat.ThreadReadView.as_view()),
    # §15 Ratings
    path("port-calls/<int:pk>/ratings", ratings.PortCallRatingsView.as_view()),
    path("organizations/<int:pk>/ratings", ratings.OrganizationRatingsView.as_view()),
    # §16 Dashboards
    path("dashboard", dashboards.DashboardView.as_view()),
]
