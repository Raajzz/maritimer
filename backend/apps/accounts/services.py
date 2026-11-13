"""Onboarding, verification and account administration (STATE_MACHINES.md §1)."""
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.audit import audit, diff
from apps.core.enums import OrgType, ReviewStatus, Role, UserStatus, VerificationStatus
from apps.core.exceptions import Conflict, Forbidden, InvalidTransition, ValidationFailed
from apps.core.services import lock, require, transition
from apps.masterdata.models import Country, Location, Port, ServiceCategory

from .models import (
    AgentProfile,
    MerchantProfile,
    Organization,
    OrganizationLocation,
    OrganizationMember,
    OrganizationPort,
    OrganizationService,
    OwnerProfile,
    User,
    VerificationDocument,
)
from .transitions import ORGANIZATION_MACHINE, USER_MACHINE

DEFAULT_COUNTRY_CODE = getattr(settings, "DEFAULT_COUNTRY_CODE", "IN")
ORG_FIELDS = [
    "legal_name",
    "trade_name",
    "registration_number",
    "tax_id",
    "email",
    "phone",
    "website",
    "address_line1",
    "address_line2",
    "city",
    "postal_code",
]
PROFILE_FIELDS = {
    OrgType.OWNER: ["operator_kind", "fleet_size", "preferred_currency_id", "notes"],
    OrgType.AGENT: ["description", "emergency_phone", "default_agency_fee_amount", "default_agency_fee_currency_id"],
    OrgType.MERCHANT: ["description", "catalog_notes", "default_currency_id"],
}
PROFILE_MODELS = {OrgType.OWNER: OwnerProfile, OrgType.AGENT: AgentProfile, OrgType.MERCHANT: MerchantProfile}


def profile_for(org):
    return PROFILE_MODELS[org.type].objects.filter(organization=org).first()


def _create_profile(org, data=None):
    model = PROFILE_MODELS[org.type]
    fields = {k: v for k, v in (data or {}).items() if k in PROFILE_FIELDS[org.type]}
    return model.objects.create(organization=org, **fields)


def _placeholder_name(user):
    return f"{user.email} (draft)"


# ---- Self-service onboarding --------------------------------------------


@transaction.atomic
def choose_role(*, user, role, legal_name=None, country_code=None):
    user = lock(user)
    if role not in (Role.OWNER, Role.AGENT, Role.MERCHANT):
        raise ValidationFailed("Role must be OWNER, AGENT or MERCHANT.", {"role": ["Invalid choice."]})
    country_code = (country_code or DEFAULT_COUNTRY_CODE).upper()
    if not Country.objects.filter(code=country_code).exists():
        raise ValidationFailed("Unknown country.", {"country_code": ["Not found."]})
    user.role = role
    transition(machine=USER_MACHINE, instance=user, event="choose_role", actor=user, action="user.role_chosen",
               metadata={"role": role, "user_id": user.pk}, extra_updates={"role": role})
    org = Organization.objects.create(
        type=role,
        legal_name=(legal_name or "").strip() or _placeholder_name(user),
        country_id=country_code,
        email=user.email,
        created_by_user=user,
    )
    _create_profile(org)
    OrganizationMember.objects.create(organization=org, user=user, is_primary_contact=True)
    user.refresh_membership()
    audit(actor=user, action="organization.created", entity=org, metadata={"type": role, "via": "onboarding"})
    return user


def _editable_onboarding(user):
    """Onboarding edits are allowed in ONBOARDING; a REJECTED user's first edit performs `resubmit`."""
    if user.status == UserStatus.REJECTED:
        transition(machine=USER_MACHINE, instance=user, event="resubmit", actor=user, action="user.resubmitted")
        org = user.organization
        if org and org.verification_status == VerificationStatus.REJECTED:
            transition(field="verification_status", machine=ORGANIZATION_MACHINE, instance=org, event="resubmit", actor=user, action="organization.resubmitted")
    if user.status != UserStatus.ONBOARDING:
        raise InvalidTransition("Onboarding can only be edited before it is submitted.", {"status": user.status})
    org = user.organization
    if org is None:
        raise InvalidTransition("Choose a role first.")
    return org


@transaction.atomic
def update_organization(*, user, data):
    user = lock(user)
    org = _editable_onboarding(user)
    values = {k: data[k] for k in ORG_FIELDS if k in data}
    if "legal_name" in values:
        values["legal_name"] = (values["legal_name"] or "").strip()
        require(values["legal_name"], "Legal name is required.", {"legal_name": ["Required."]})
    if "country_code" in data:
        require(Country.objects.filter(code=data["country_code"]).exists(), "Unknown country.", {"country_code": ["Not found."]})
        values["country_id"] = data["country_code"]
    changes = diff(org, values)
    org.save()
    audit(actor=user, action="organization.updated", entity=org, changes=changes)
    return org


@transaction.atomic
def update_profile(*, user, data):
    user = lock(user)
    org = _editable_onboarding(user)
    return _apply_profile(actor=user, org=org, data=data)


def _apply_profile(*, actor, org, data):
    profile = profile_for(org) or _create_profile(org)
    values = {}
    if org.type == OrgType.OWNER:
        for key in ("operator_kind", "fleet_size", "notes"):
            if key in data:
                values[key] = data[key]
        if "preferred_currency_code" in data:
            values["preferred_currency_id"] = data["preferred_currency_code"]
    elif org.type == OrgType.AGENT:
        for key in ("description", "emergency_phone"):
            if key in data:
                values[key] = data[key]
        if "default_agency_fee" in data:
            fee = data["default_agency_fee"]
            values["default_agency_fee_amount"] = fee["amount"] if fee else None
            values["default_agency_fee_currency_id"] = fee["currency_code"] if fee else None
    else:
        for key in ("description", "catalog_notes"):
            if key in data:
                values[key] = data[key]
        if "default_currency_code" in data:
            values["default_currency_id"] = data["default_currency_code"]
    changes = diff(profile, values)
    profile.save()
    audit(actor=actor, action="organization.profile_updated", entity=org, changes=changes)
    return profile


@transaction.atomic
def update_coverage(*, user, location_ids=None, port_ids=None, service_category_ids=None):
    user = lock(user)
    org = _editable_onboarding(user)
    return _apply_coverage(actor=user, org=org, location_ids=location_ids, port_ids=port_ids, service_category_ids=service_category_ids)


def _apply_coverage(*, actor, org, location_ids=None, port_ids=None, service_category_ids=None):
    if port_ids is not None:
        ports = list(Port.objects.filter(pk__in=port_ids, is_active=True))
        require(len(ports) == len(set(port_ids)), "Unknown or inactive port.", {"port_ids": ["Invalid id."]})
        OrganizationPort.objects.filter(organization=org).exclude(port_id__in=port_ids).delete()
        for port in ports:
            OrganizationPort.objects.get_or_create(organization=org, port=port)
        # A port implies its location (keeps discovery by location consistent).
        port_locations = {p.location_id for p in ports}
        if location_ids is None:
            existing = set(OrganizationLocation.objects.filter(organization=org).values_list("location_id", flat=True))
            location_ids = sorted(existing | port_locations)
        else:
            location_ids = sorted(set(location_ids) | port_locations)
    if location_ids is not None:
        locations = list(Location.objects.filter(pk__in=location_ids, is_active=True))
        require(len(locations) == len(set(location_ids)), "Unknown or inactive location.", {"location_ids": ["Invalid id."]})
        OrganizationLocation.objects.filter(organization=org).exclude(location_id__in=location_ids).delete()
        for location in locations:
            OrganizationLocation.objects.get_or_create(organization=org, location=location)
    if service_category_ids is not None:
        if org.type == OrgType.OWNER and service_category_ids:
            raise ValidationFailed("Owners do not offer services.", {"service_category_ids": ["Not allowed for owners."]})
        services = list(ServiceCategory.objects.filter(pk__in=service_category_ids, is_active=True))
        require(len(services) == len(set(service_category_ids)), "Unknown or inactive service.", {"service_category_ids": ["Invalid id."]})
        OrganizationService.objects.filter(organization=org).exclude(service_category_id__in=service_category_ids).delete()
        for service in services:
            OrganizationService.objects.get_or_create(organization=org, service_category=service)
    audit(
        actor=actor,
        action="organization.coverage_updated",
        entity=org,
        metadata={"location_ids": location_ids, "port_ids": port_ids, "service_category_ids": service_category_ids},
    )
    return org


@transaction.atomic
def add_verification_document(*, user, document_type, title, file):
    user = lock(user)
    org = _editable_onboarding(user)
    doc = VerificationDocument.objects.create(
        organization=org, uploaded_by_user=user, document_type=document_type, title=title or "", file=file
    )
    audit(actor=user, action="verification_document.uploaded", entity=doc, metadata={"document_type": document_type})
    return doc


@transaction.atomic
def delete_verification_document(*, user, document):
    user = lock(user)
    org = _editable_onboarding(user)
    if document.organization_id != org.pk:
        raise Forbidden()
    if document.status != ReviewStatus.PENDING:
        raise InvalidTransition("Only pending documents can be removed.")
    audit(actor=user, action="verification_document.deleted", entity=document)
    document.delete()


def completeness(org, user=None) -> list[str]:
    missing = []
    if not org.legal_name or org.legal_name.endswith("(draft)"):
        missing.append("organization.legal_name")
    if not org.country_id:
        missing.append("organization.country_code")
    if not org.port_links.exists():
        missing.append("coverage.ports")
    if org.type in (OrgType.AGENT, OrgType.MERCHANT) and not org.service_links.exists():
        missing.append("coverage.services")
    if not org.verification_documents.exists():
        missing.append("documents")
    return missing


@transaction.atomic
def submit_onboarding(*, user):
    user = lock(user)
    org = _editable_onboarding(user)
    missing = completeness(org, user)
    if missing:
        raise ValidationFailed("Onboarding is incomplete.", {"missing": missing})
    transition(machine=USER_MACHINE, instance=user, event="submit_onboarding", actor=user, action="user.onboarding_submitted")
    org = lock(org)
    if org.verification_status == VerificationStatus.DRAFT:
        transition(
            field="verification_status", machine=ORGANIZATION_MACHINE, instance=org, event="submit", actor=user, action="organization.submitted",
            extra_updates={"submitted_at": timezone.now()},
        )
    return user


# ---- Admin -----------------------------------------------------------------


def _status_meta(user, actor, reason):
    return {"status_changed_at": timezone.now(), "status_changed_by_user": actor, "status_reason": reason}


@transaction.atomic
def approve_user(*, actor, user, note=None):
    user = lock(user)
    transition(machine=USER_MACHINE, instance=user, event="approve", actor=actor, action="user.approved",
               metadata={"note": note, "user_id": user.pk}, extra_updates=_status_meta(user, actor, None))
    org = user.organization
    if org is not None and org.verification_status == VerificationStatus.PENDING_REVIEW:
        approve_organization(actor=actor, organization=org, note=note)
    return user


@transaction.atomic
def reject_user(*, actor, user, reason):
    require(reason, "A reason is required.", {"reason": ["Required."]})
    user = lock(user)
    transition(machine=USER_MACHINE, instance=user, event="reject", actor=actor, action="user.rejected",
               metadata={"reason": reason, "user_id": user.pk}, extra_updates=_status_meta(user, actor, reason))
    org = user.organization
    if org is not None and org.verification_status == VerificationStatus.PENDING_REVIEW:
        reject_organization(actor=actor, organization=org, reason=reason)
    return user


@transaction.atomic
def suspend_user(*, actor, user, reason=None):
    user = lock(user)
    if user.pk == actor.pk:
        raise Forbidden("You cannot suspend yourself.")
    return transition(machine=USER_MACHINE, instance=user, event="suspend", actor=actor, action="user.suspended",
                      metadata={"reason": reason, "user_id": user.pk}, extra_updates=_status_meta(user, actor, reason))


@transaction.atomic
def reinstate_user(*, actor, user, reason=None):
    user = lock(user)
    return transition(machine=USER_MACHINE, instance=user, event="reinstate", actor=actor, action="user.reinstated",
                      metadata={"reason": reason, "user_id": user.pk}, extra_updates=_status_meta(user, actor, None))


@transaction.atomic
def approve_organization(*, actor, organization, note=None):
    org = lock(organization)
    return transition(field="verification_status", machine=ORGANIZATION_MACHINE, instance=org, event="approve", actor=actor, action="organization.approved",
                      metadata={"note": note},
                      extra_updates={"verified_at": timezone.now(), "verified_by_user": actor, "verification_note": note})


@transaction.atomic
def reject_organization(*, actor, organization, reason):
    require(reason, "A reason is required.", {"reason": ["Required."]})
    org = lock(organization)
    return transition(field="verification_status", machine=ORGANIZATION_MACHINE, instance=org, event="reject", actor=actor, action="organization.rejected",
                      metadata={"reason": reason}, extra_updates={"verification_note": reason})


@transaction.atomic
def suspend_organization(*, actor, organization, reason=None):
    org = lock(organization)
    return transition(field="verification_status", machine=ORGANIZATION_MACHINE, instance=org, event="suspend", actor=actor, action="organization.suspended",
                      metadata={"reason": reason}, extra_updates={"verification_note": reason})


@transaction.atomic
def reinstate_organization(*, actor, organization, reason=None):
    org = lock(organization)
    return transition(field="verification_status", machine=ORGANIZATION_MACHINE, instance=org, event="reinstate", actor=actor, action="organization.reinstated",
                      metadata={"reason": reason})


@transaction.atomic
def review_document(*, actor, document, approve, note=None):
    doc = lock(document)
    if doc.status != ReviewStatus.PENDING:
        raise InvalidTransition("Document already reviewed.", {"status": doc.status})
    if not approve:
        require(note, "A note is required when rejecting.", {"note": ["Required."]})
    previous = doc.status
    doc.status = ReviewStatus.APPROVED if approve else ReviewStatus.REJECTED
    doc.review_note = note
    doc.reviewed_by_user = actor
    doc.reviewed_at = timezone.now()
    doc.save()
    audit(actor=actor, action="verification_document.approved" if approve else "verification_document.rejected",
          entity=doc, from_state=previous, to_state=doc.status, metadata={"note": note})
    return doc


@transaction.atomic
def admin_create_organization(*, actor, type, organization, profile=None, coverage=None):
    require(type in OrgType.values, "Invalid organization type.", {"type": ["Invalid choice."]})
    values = {k: organization[k] for k in ORG_FIELDS if k in organization}
    require(values.get("legal_name"), "Legal name is required.", {"organization.legal_name": ["Required."]})
    country = organization.get("country_code")
    require(country and Country.objects.filter(code=country).exists(), "Valid country required.", {"organization.country_code": ["Required."]})
    if Organization.objects.filter(type=type, legal_name__iexact=values["legal_name"], deleted_at__isnull=True).exists():
        raise Conflict("An organization of this type with that legal name already exists.")
    org = Organization.objects.create(
        type=type,
        country_id=country,
        verification_status=VerificationStatus.APPROVED,
        verified_at=timezone.now(),
        verified_by_user=actor,
        created_by_user=actor,
        **values,
    )
    _create_profile(org)
    if profile:
        _apply_profile(actor=actor, org=org, data=profile)
    if coverage:
        _apply_coverage(actor=actor, org=org, **{k: coverage.get(k) for k in ("location_ids", "port_ids", "service_category_ids")})
    audit(actor=actor, action="organization.created", entity=org, to_state=org.verification_status, metadata={"type": type, "via": "admin"})
    return org


@transaction.atomic
def admin_update_organization(*, actor, organization, organization_data=None, profile=None, coverage=None):
    org = lock(organization)
    if organization_data:
        values = {k: organization_data[k] for k in ORG_FIELDS if k in organization_data}
        if "country_code" in organization_data:
            values["country_id"] = organization_data["country_code"]
        changes = diff(org, values)
        org.save()
        audit(actor=actor, action="organization.updated", entity=org, changes=changes)
    if profile:
        _apply_profile(actor=actor, org=org, data=profile)
    if coverage:
        _apply_coverage(actor=actor, org=org, **{k: coverage.get(k) for k in ("location_ids", "port_ids", "service_category_ids")})
    return org


@transaction.atomic
def admin_create_org_user(*, actor, organization, email, display_name=""):
    email = (email or "").strip().lower()
    require("@" in email, "A valid email is required.", {"email": ["Invalid."]})
    if User.objects.filter(email__iexact=email).exists():
        raise Conflict("A user with this email already exists.")
    has_primary = OrganizationMember.objects.filter(organization=organization, is_primary_contact=True).exists()
    user = User.objects.create(
        email=email,
        display_name=display_name or "",
        role=organization.type,
        status=UserStatus.APPROVED,
        status_changed_at=timezone.now(),
        status_changed_by_user=actor,
    )
    OrganizationMember.objects.create(organization=organization, user=user, is_primary_contact=not has_primary)
    audit(actor=actor, action="user.provisioned", entity=user, to_state=user.status,
          metadata={"organization_id": organization.pk, "email": email})
    return user


@transaction.atomic
def bootstrap_admin(*, email, display_name=""):
    email = email.strip().lower()
    user = User.objects.filter(email__iexact=email).first()
    if user is None:
        user = User.objects.create(email=email, display_name=display_name, role=Role.ADMIN, status=UserStatus.APPROVED,
                                   status_changed_at=timezone.now())
        created = True
    else:
        if user.organization is not None:
            raise Conflict("This email already belongs to an organization member; use a different email for the admin.")
        user.role = Role.ADMIN
        user.status = UserStatus.APPROVED
        user.status_changed_at = timezone.now()
        user.save()
        created = False
    audit(actor=None, action="user.admin_bootstrapped", entity=user, to_state=user.status, metadata={"email": email, "created": created})
    return user, created
