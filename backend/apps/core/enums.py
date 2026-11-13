"""All CHECK-constraint vocabularies (SCHEMA.md D14). Exposed to the UI via GET /meta/enums."""
from django.db import models


class Role(models.TextChoices):
    ADMIN = "ADMIN"
    OWNER = "OWNER"
    AGENT = "AGENT"
    MERCHANT = "MERCHANT"


class UserStatus(models.TextChoices):
    NEW = "NEW"
    ONBOARDING = "ONBOARDING"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class OrgType(models.TextChoices):
    OWNER = "OWNER"
    AGENT = "AGENT"
    MERCHANT = "MERCHANT"


class VerificationStatus(models.TextChoices):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUSPENDED = "SUSPENDED"


class OperatorKind(models.TextChoices):
    OWNER = "OWNER"
    OPERATOR = "OPERATOR"
    CHARTERER = "CHARTERER"
    MANAGER = "MANAGER"


class DocumentType(models.TextChoices):
    COMPANY_REGISTRATION = "COMPANY_REGISTRATION"
    TAX_CERTIFICATE = "TAX_CERTIFICATE"
    TRADE_LICENSE = "TRADE_LICENSE"
    ID_PROOF = "ID_PROOF"
    BANK_PROOF = "BANK_PROOF"
    OTHER = "OTHER"


class ReviewStatus(models.TextChoices):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ReviewSource(models.TextChoices):
    HUMAN = "HUMAN"
    AUTOMATED = "AUTOMATED"


class FxSource(models.TextChoices):
    MANUAL = "MANUAL"
    OPEN_EXCHANGE_RATES = "OPEN_EXCHANGE_RATES"
    ECB = "ECB"
    RBI = "RBI"
    OTHER = "OTHER"


class VesselType(models.TextChoices):
    BULK_CARRIER = "BULK_CARRIER"
    CONTAINER = "CONTAINER"
    TANKER = "TANKER"
    GENERAL_CARGO = "GENERAL_CARGO"
    RORO = "RORO"
    LNG_LPG = "LNG_LPG"
    PASSENGER = "PASSENGER"
    OFFSHORE = "OFFSHORE"
    OTHER = "OTHER"


class RequestType(models.TextChoices):
    PORT_CALL = "PORT_CALL"
    VENDOR_SERVICE = "VENDOR_SERVICE"


class PartyRole(models.TextChoices):
    OWNER = "OWNER"
    AGENT = "AGENT"
    MERCHANT = "MERCHANT"


class RequestStatus(models.TextChoices):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class PortCallStatus(models.TextChoices):
    PDA_PENDING = "PDA_PENDING"
    PDA_SENT = "PDA_SENT"
    PDA_APPROVED = "PDA_APPROVED"
    ADVANCE_RECEIVED = "ADVANCE_RECEIVED"
    IN_PORT = "IN_PORT"
    DEPARTED = "DEPARTED"
    FDA_ISSUED = "FDA_ISSUED"
    DISPUTED = "DISPUTED"
    FDA_FINAL = "FDA_FINAL"
    SETTLED = "SETTLED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


PORT_CALL_TERMINAL = {PortCallStatus.CLOSED, PortCallStatus.CANCELLED}
PORT_CALL_FROZEN = {
    PortCallStatus.FDA_FINAL,
    PortCallStatus.SETTLED,
    PortCallStatus.CLOSED,
    PortCallStatus.CANCELLED,
}

# Agent dashboard pipeline (STATE_MACHINES.md §3). "requested" holds PENDING requests, not port calls.
PIPELINE_GROUPS = {
    "pda_sent": [PortCallStatus.PDA_PENDING, PortCallStatus.PDA_SENT],
    "advance_received": [PortCallStatus.PDA_APPROVED, PortCallStatus.ADVANCE_RECEIVED],
    "in_port": [PortCallStatus.IN_PORT, PortCallStatus.DEPARTED],
    "fda_issued": [PortCallStatus.FDA_ISSUED],
    "disputed": [PortCallStatus.DISPUTED],
    "settled": [PortCallStatus.FDA_FINAL, PortCallStatus.SETTLED, PortCallStatus.CLOSED],
}


class AccountKind(models.TextChoices):
    PDA = "PDA"
    FDA = "FDA"


class AccountStatus(models.TextChoices):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"
    FINAL = "FINAL"
    VOID = "VOID"


class InvoiceStatus(models.TextChoices):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PAID = "PAID"
    VOID = "VOID"


class PaymentKind(models.TextChoices):
    ADVANCE = "ADVANCE"
    BALANCE = "BALANCE"
    REFUND = "REFUND"
    VENDOR_PAYMENT = "VENDOR_PAYMENT"


class PaymentStatus(models.TextChoices):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class PaymentMethod(models.TextChoices):
    BANK_TRANSFER = "BANK_TRANSFER"
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    CARD = "CARD"
    OTHER = "OTHER"


class SettlementDirection(models.TextChoices):
    BALANCE_DUE = "BALANCE_DUE"
    REFUND_DUE = "REFUND_DUE"
    NIL = "NIL"


class SettlementStatus(models.TextChoices):
    OPEN = "OPEN"
    PARTIALLY_PAID = "PARTIALLY_PAID"
    CLOSED = "CLOSED"


class DisputeStatus(models.TextChoices):
    OPEN = "OPEN"
    UNDER_REVIEW = "UNDER_REVIEW"
    RESOLVED = "RESOLVED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


DISPUTE_LIVE = [DisputeStatus.OPEN, DisputeStatus.UNDER_REVIEW]
DISPUTE_CLOSED = [DisputeStatus.RESOLVED, DisputeStatus.REJECTED, DisputeStatus.WITHDRAWN]


class ResolutionType(models.TextChoices):
    ADJUSTED = "ADJUSTED"
    EXPLAINED = "EXPLAINED"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class DisputeEventType(models.TextChoices):
    OPENED = "OPENED"
    COMMENT = "COMMENT"
    STATUS_CHANGED = "STATUS_CHANGED"
    ADJUSTMENT_PROPOSED = "ADJUSTMENT_PROPOSED"
    REOPENED = "REOPENED"


class FilePurpose(models.TextChoices):
    VERIFICATION = "VERIFICATION"
    INVOICE = "INVOICE"
    CHAT = "CHAT"
    DISPUTE = "DISPUTE"
    GENERATED_PDF = "GENERATED_PDF"
    OTHER = "OTHER"


class GeneratedDocumentType(models.TextChoices):
    PDA = "PDA"
    FDA = "FDA"
    SETTLEMENT_STATEMENT = "SETTLEMENT_STATEMENT"


class ThreadKind(models.TextChoices):
    PORT_CALL = "PORT_CALL"
    VENDOR_SERVICE = "VENDOR_SERVICE"


def check_in(field, choices):
    """Build the Q for a CHECK (field IN (...)) constraint."""
    return models.Q(**{f"{field}__in": [c.value for c in choices]})


ALL_ENUMS = {
    "roles": Role,
    "user_statuses": UserStatus,
    "organization_types": OrgType,
    "verification_statuses": VerificationStatus,
    "operator_kinds": OperatorKind,
    "document_types": DocumentType,
    "review_statuses": ReviewStatus,
    "fx_sources": FxSource,
    "vessel_types": VesselType,
    "request_types": RequestType,
    "request_statuses": RequestStatus,
    "port_call_statuses": PortCallStatus,
    "account_kinds": AccountKind,
    "account_statuses": AccountStatus,
    "invoice_statuses": InvoiceStatus,
    "payment_kinds": PaymentKind,
    "payment_statuses": PaymentStatus,
    "payment_methods": PaymentMethod,
    "settlement_directions": SettlementDirection,
    "settlement_statuses": SettlementStatus,
    "dispute_statuses": DisputeStatus,
    "resolution_types": ResolutionType,
    "file_purposes": FilePurpose,
}
