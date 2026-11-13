from django.conf import settings
from django.db import models
from django.db.models import F, Q

from apps.core.enums import PartyRole, RequestStatus, RequestType, check_in
from apps.core.models import TimeStampedModel


class RequestRolePolicy(TimeStampedModel):
    """Which role may send which request type to which role. Opening directionality = a row (SCHEMA.md D5)."""

    request_type = models.CharField(max_length=32, choices=RequestType.choices)
    from_role = models.CharField(max_length=16, choices=PartyRole.choices)
    to_role = models.CharField(max_length=16, choices=PartyRole.choices)
    is_enabled = models.BooleanField(default=True)
    requires_port_call = models.BooleanField()
    creates_chat_thread = models.BooleanField(default=True)

    class Meta:
        db_table = "request_role_policies"
        constraints = [
            models.UniqueConstraint(fields=["request_type", "from_role", "to_role"], name="request_policy_uniq"),
            models.CheckConstraint(condition=check_in("request_type", RequestType), name="request_policy_type_chk"),
            models.CheckConstraint(condition=check_in("from_role", PartyRole), name="request_policy_from_chk"),
            models.CheckConstraint(condition=check_in("to_role", PartyRole), name="request_policy_to_chk"),
        ]


class Request(TimeStampedModel):
    reference = models.CharField(max_length=24, unique=True)
    request_type = models.CharField(max_length=32, choices=RequestType.choices)
    from_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    from_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="outgoing_requests")
    from_role = models.CharField(max_length=16, choices=PartyRole.choices)
    to_organization = models.ForeignKey("accounts.Organization", on_delete=models.PROTECT, related_name="incoming_requests")
    to_role = models.CharField(max_length=16, choices=PartyRole.choices)
    to_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=RequestStatus.choices, default=RequestStatus.PENDING)
    port_call = models.ForeignKey("portcalls.PortCall", null=True, blank=True, on_delete=models.PROTECT, related_name="requests")
    subject = models.CharField(max_length=200, default="", blank=True)
    message = models.TextField(default="", blank=True)
    payload = models.JSONField(default=dict, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    response_note = models.TextField(default="", blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "requests"
        indexes = [
            models.Index(fields=["to_organization", "status"], name="request_to_status_idx"),
            models.Index(fields=["from_organization", "status"], name="request_from_status_idx"),
            models.Index(fields=["port_call"], name="request_port_call_idx"),
            models.Index(fields=["request_type", "status"], name="request_type_status_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=check_in("request_type", RequestType), name="request_type_chk"),
            models.CheckConstraint(condition=check_in("from_role", PartyRole), name="request_from_role_chk"),
            models.CheckConstraint(condition=check_in("to_role", PartyRole), name="request_to_role_chk"),
            models.CheckConstraint(condition=check_in("status", RequestStatus), name="request_status_chk"),
            models.CheckConstraint(condition=~Q(from_organization=F("to_organization")), name="request_distinct_orgs_chk"),
            models.CheckConstraint(
                condition=~Q(request_type=RequestType.VENDOR_SERVICE) | Q(port_call__isnull=False), name="request_vendor_needs_call_chk"
            ),
            models.CheckConstraint(
                condition=Q(status__in=[RequestStatus.ACCEPTED, RequestStatus.DECLINED], responded_at__isnull=False)
                | (~Q(status__in=[RequestStatus.ACCEPTED, RequestStatus.DECLINED]) & Q(responded_at__isnull=True)),
                name="request_responded_at_chk",
            ),
        ]


class PortCallRequestDetail(TimeStampedModel):
    request = models.OneToOneField(Request, primary_key=True, on_delete=models.CASCADE, related_name="port_call_detail")
    vessel = models.ForeignKey("vessels.Vessel", on_delete=models.PROTECT, related_name="+")
    port = models.ForeignKey("masterdata.Port", on_delete=models.PROTECT, related_name="+")
    eta = models.DateTimeField()
    etd = models.DateTimeField()
    cargo_type = models.ForeignKey("masterdata.CargoType", on_delete=models.PROTECT, related_name="+")
    cargo_description = models.CharField(max_length=300, default="", blank=True)
    cargo_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    cargo_unit = models.CharField(max_length=16, default="", blank=True)

    class Meta:
        db_table = "port_call_request_details"
        constraints = [models.CheckConstraint(condition=Q(etd__gt=F("eta")), name="pc_request_etd_after_eta_chk")]


class RequestService(TimeStampedModel):
    request = models.ForeignKey(Request, on_delete=models.CASCADE, related_name="services")
    service_category = models.ForeignKey("masterdata.ServiceCategory", on_delete=models.PROTECT, related_name="+")
    quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    unit = models.CharField(max_length=16, default="", blank=True)
    notes = models.TextField(default="", blank=True)

    class Meta:
        db_table = "request_services"
        constraints = [models.UniqueConstraint(fields=["request", "service_category"], name="request_service_uniq")]
