from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.functional import cached_property

from apps.core.enums import (
    DocumentType,
    OperatorKind,
    OrgType,
    ReviewSource,
    ReviewStatus,
    Role,
    UserStatus,
    VerificationStatus,
    check_in,
)
from apps.core.models import CITextField, TimeStampedModel


class UserManager(BaseUserManager):
    def create_user(self, email, **extra):
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("role", Role.ADMIN)
        extra.setdefault("status", UserStatus.APPROVED)
        return self.create_user(email, **extra)


class User(AbstractBaseUser, TimeStampedModel):
    """Identity + role + approval status. Passwords are never used (Firebase Google sign-in only)."""

    firebase_uid = models.CharField(max_length=128, null=True, blank=True)
    email = CITextField(unique=True)
    email_verified = models.BooleanField(default=False)
    display_name = models.CharField(max_length=200, default="", blank=True)
    photo_url = models.TextField(null=True, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, null=True, blank=True)
    status = models.CharField(max_length=16, choices=UserStatus.choices, default=UserStatus.NEW)
    status_reason = models.TextField(null=True, blank=True)
    status_changed_at = models.DateTimeField(null=True, blank=True)
    status_changed_by_user = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    last_login_at = models.DateTimeField(null=True, blank=True)
    deleted_at = models.DateTimeField(null=True, blank=True)

    # Google sign-in only: drop AbstractBaseUser's password/last_login columns (SCHEMA.md has neither).
    password = None
    last_login = None

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    objects = UserManager()

    class Meta:
        db_table = "users"
        indexes = [models.Index(fields=["status", "role"], name="users_status_role_idx")]
        constraints = [
            models.UniqueConstraint(fields=["firebase_uid"], condition=Q(firebase_uid__isnull=False), name="users_firebase_uid_uniq"),
            models.CheckConstraint(condition=Q(role__isnull=True) | check_in("role", Role), name="users_role_chk"),
            models.CheckConstraint(condition=check_in("status", UserStatus), name="users_status_chk"),
            models.CheckConstraint(condition=Q(role__isnull=False) | Q(status=UserStatus.NEW), name="users_role_required_chk"),
            models.CheckConstraint(
                condition=~Q(role=Role.ADMIN) | Q(status__in=[UserStatus.APPROVED, UserStatus.SUSPENDED]),
                name="users_admin_status_chk",
            ),
        ]

    def __str__(self):
        return self.email

    # Django admin-site compatibility (role ADMIN == staff/superuser)
    @property
    def is_active(self):
        return self.deleted_at is None and self.status != UserStatus.SUSPENDED

    @property
    def is_staff(self):
        return self.role == Role.ADMIN and self.status == UserStatus.APPROVED

    @property
    def is_superuser(self):
        return self.is_staff

    def has_perm(self, perm, obj=None):
        return self.is_staff

    def has_perms(self, perm_list, obj=None):
        return self.is_staff

    def has_module_perms(self, app_label):
        return self.is_staff

    @cached_property
    def membership(self):
        return self.memberships.select_related("organization").first()

    @property
    def organization(self):
        membership = self.membership
        return membership.organization if membership else None

    @property
    def organization_id(self):
        membership = self.membership
        return membership.organization_id if membership else None

    def refresh_membership(self):
        self.__dict__.pop("membership", None)

    def refresh_from_db(self, *args, **kwargs):
        self.refresh_membership()
        return super().refresh_from_db(*args, **kwargs)


class Organization(TimeStampedModel):
    type = models.CharField(max_length=16, choices=OrgType.choices)
    legal_name = models.CharField(max_length=200)
    trade_name = models.CharField(max_length=200, default="", blank=True)
    registration_number = models.CharField(max_length=100, default="", blank=True)
    tax_id = models.CharField(max_length=100, default="", blank=True)
    email = CITextField(default="", blank=True)
    phone = models.CharField(max_length=40, default="", blank=True)
    website = models.CharField(max_length=255, default="", blank=True)
    address_line1 = models.CharField(max_length=200, default="", blank=True)
    address_line2 = models.CharField(max_length=200, default="", blank=True)
    city = models.CharField(max_length=100, default="", blank=True)
    postal_code = models.CharField(max_length=20, default="", blank=True)
    country = models.ForeignKey("masterdata.Country", on_delete=models.PROTECT, db_column="country_code", related_name="+")
    verification_status = models.CharField(max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.DRAFT)
    verification_note = models.TextField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    submitted_at = models.DateTimeField(null=True, blank=True)
    created_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    deleted_at = models.DateTimeField(null=True, blank=True)

    locations = models.ManyToManyField("masterdata.Location", through="OrganizationLocation", related_name="organizations")
    ports = models.ManyToManyField("masterdata.Port", through="OrganizationPort", related_name="organizations")
    services = models.ManyToManyField("masterdata.ServiceCategory", through="OrganizationService", related_name="organizations")

    class Meta:
        db_table = "organizations"
        indexes = [
            models.Index(fields=["type", "verification_status"], name="org_type_status_idx"),
            models.Index(fields=["legal_name"], name="org_legal_name_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=check_in("type", OrgType), name="org_type_chk"),
            models.CheckConstraint(condition=check_in("verification_status", VerificationStatus), name="org_verification_status_chk"),
            models.UniqueConstraint("type", Lower("legal_name"), condition=Q(deleted_at__isnull=True), name="org_type_legal_name_uniq"),
        ]

    def __str__(self):
        return self.legal_name

    @property
    def display_name(self):
        return self.trade_name or self.legal_name

    @property
    def is_approved(self):
        return self.verification_status == VerificationStatus.APPROVED and self.deleted_at is None


class OrganizationMember(models.Model):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="members")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="memberships")
    is_primary_contact = models.BooleanField(default=True)
    joined_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "organization_members"
        constraints = [
            models.UniqueConstraint(fields=["organization", "user"], name="org_member_uniq"),
            # v1: one organization per user. Drop this constraint to allow multi-org users (SCHEMA.md D2).
            models.UniqueConstraint(fields=["user"], name="org_member_one_org_per_user"),
            models.UniqueConstraint(fields=["organization"], condition=Q(is_primary_contact=True), name="org_member_one_primary"),
        ]


class OwnerProfile(TimeStampedModel):
    organization = models.OneToOneField(Organization, primary_key=True, on_delete=models.CASCADE, related_name="owner_profile")
    operator_kind = models.CharField(max_length=16, choices=OperatorKind.choices, default=OperatorKind.OWNER)
    fleet_size = models.IntegerField(null=True, blank=True)
    preferred_currency = models.ForeignKey(
        "masterdata.Currency", on_delete=models.PROTECT, db_column="preferred_currency_code", default="USD", related_name="+"
    )
    notes = models.TextField(default="", blank=True)

    class Meta:
        db_table = "owner_profiles"
        constraints = [
            models.CheckConstraint(condition=check_in("operator_kind", OperatorKind), name="owner_operator_kind_chk"),
            models.CheckConstraint(condition=Q(fleet_size__isnull=True) | Q(fleet_size__gte=0), name="owner_fleet_size_chk"),
        ]


class AgentProfile(TimeStampedModel):
    organization = models.OneToOneField(Organization, primary_key=True, on_delete=models.CASCADE, related_name="agent_profile")
    description = models.TextField(default="", blank=True)
    emergency_phone = models.CharField(max_length=40, default="", blank=True)
    default_agency_fee_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    default_agency_fee_currency = models.ForeignKey(
        "masterdata.Currency", null=True, blank=True, on_delete=models.PROTECT, db_column="default_agency_fee_currency_code", related_name="+"
    )
    # Denormalized (SCHEMA.md D16)
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.IntegerField(default=0)
    completed_port_calls = models.IntegerField(default=0)

    class Meta:
        db_table = "agent_profiles"
        constraints = [
            models.CheckConstraint(
                condition=Q(default_agency_fee_amount__isnull=True, default_agency_fee_currency__isnull=True)
                | Q(default_agency_fee_amount__isnull=False, default_agency_fee_currency__isnull=False),
                name="agent_fee_currency_pair_chk",
            ),
            models.CheckConstraint(condition=Q(rating_avg__gte=0, rating_avg__lte=5), name="agent_rating_avg_chk"),
        ]


class MerchantProfile(TimeStampedModel):
    organization = models.OneToOneField(Organization, primary_key=True, on_delete=models.CASCADE, related_name="merchant_profile")
    description = models.TextField(default="", blank=True)
    catalog_notes = models.TextField(default="", blank=True)
    default_currency = models.ForeignKey(
        "masterdata.Currency", on_delete=models.PROTECT, db_column="default_currency_code", default="INR", related_name="+"
    )
    rating_avg = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    rating_count = models.IntegerField(default=0)

    class Meta:
        db_table = "merchant_profiles"
        constraints = [
            models.CheckConstraint(condition=Q(rating_avg__gte=0, rating_avg__lte=5), name="merchant_rating_avg_chk"),
        ]


class OrganizationLocation(TimeStampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="location_links")
    location = models.ForeignKey("masterdata.Location", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "organization_locations"
        constraints = [models.UniqueConstraint(fields=["organization", "location"], name="org_location_uniq")]


class OrganizationPort(TimeStampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="port_links")
    port = models.ForeignKey("masterdata.Port", on_delete=models.PROTECT, related_name="+")

    class Meta:
        db_table = "organization_ports"
        constraints = [models.UniqueConstraint(fields=["organization", "port"], name="org_port_uniq")]
        indexes = [models.Index(fields=["port"], name="org_port_port_idx")]


class OrganizationService(TimeStampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="service_links")
    service_category = models.ForeignKey("masterdata.ServiceCategory", on_delete=models.PROTECT, related_name="+")
    notes = models.TextField(default="", blank=True)

    class Meta:
        db_table = "organization_services"
        constraints = [models.UniqueConstraint(fields=["organization", "service_category"], name="org_service_uniq")]
        indexes = [models.Index(fields=["service_category"], name="org_service_cat_idx")]


class VerificationDocument(TimeStampedModel):
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="verification_documents")
    uploaded_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    title = models.CharField(max_length=200, default="", blank=True)
    file = models.ForeignKey("documents.StoredFile", on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=16, choices=ReviewStatus.choices, default=ReviewStatus.PENDING)
    review_note = models.TextField(null=True, blank=True)
    reviewed_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_source = models.CharField(max_length=16, choices=ReviewSource.choices, default=ReviewSource.HUMAN)
    review_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "verification_documents"
        indexes = [models.Index(fields=["organization", "status"], name="verif_doc_org_status_idx")]
        constraints = [
            models.CheckConstraint(condition=check_in("document_type", DocumentType), name="verif_doc_type_chk"),
            models.CheckConstraint(condition=check_in("status", ReviewStatus), name="verif_doc_status_chk"),
            models.CheckConstraint(condition=check_in("review_source", ReviewSource), name="verif_doc_review_source_chk"),
        ]
