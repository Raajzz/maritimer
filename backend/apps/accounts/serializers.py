from rest_framework import serializers

from apps.core.enums import DocumentType, OperatorKind, OrgType
from apps.core.serializers import MoneyInputSerializer, dec, dt, file_ref, org_summary, user_summary

from .services import completeness, profile_for


class ChooseRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=["OWNER", "AGENT", "MERCHANT"])
    legal_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    country_code = serializers.CharField(required=False, max_length=2)


class OrganizationInputSerializer(serializers.Serializer):
    legal_name = serializers.CharField(max_length=200, required=False)
    trade_name = serializers.CharField(max_length=200, required=False, allow_blank=True)
    registration_number = serializers.CharField(max_length=100, required=False, allow_blank=True)
    tax_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    website = serializers.CharField(max_length=255, required=False, allow_blank=True)
    address_line1 = serializers.CharField(max_length=200, required=False, allow_blank=True)
    address_line2 = serializers.CharField(max_length=200, required=False, allow_blank=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    postal_code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    country_code = serializers.CharField(max_length=2, required=False)


class ProfileInputSerializer(serializers.Serializer):
    # OWNER
    operator_kind = serializers.ChoiceField(choices=OperatorKind.choices, required=False)
    fleet_size = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    preferred_currency_code = serializers.CharField(max_length=3, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    # AGENT
    description = serializers.CharField(required=False, allow_blank=True)
    emergency_phone = serializers.CharField(max_length=40, required=False, allow_blank=True)
    default_agency_fee = MoneyInputSerializer(required=False, allow_null=True)
    # MERCHANT
    catalog_notes = serializers.CharField(required=False, allow_blank=True)
    default_currency_code = serializers.CharField(max_length=3, required=False)


class CoverageInputSerializer(serializers.Serializer):
    location_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    port_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    service_category_ids = serializers.ListField(child=serializers.IntegerField(), required=False)


class DocumentUploadSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=DocumentType.choices)
    title = serializers.CharField(required=False, allow_blank=True, max_length=200)
    file = serializers.FileField()


def profile_data(org):
    profile = profile_for(org)
    if profile is None:
        return None
    if org.type == OrgType.OWNER:
        return {"operator_kind": profile.operator_kind, "fleet_size": profile.fleet_size,
                "preferred_currency_code": profile.preferred_currency_id, "notes": profile.notes}
    if org.type == OrgType.AGENT:
        fee = None
        if profile.default_agency_fee_amount is not None:
            fee = {"amount": dec(profile.default_agency_fee_amount), "currency_code": profile.default_agency_fee_currency_id}
        return {"description": profile.description, "emergency_phone": profile.emergency_phone, "default_agency_fee": fee,
                "rating_avg": dec(profile.rating_avg), "rating_count": profile.rating_count, "completed_port_calls": profile.completed_port_calls}
    return {"description": profile.description, "catalog_notes": profile.catalog_notes, "default_currency_code": profile.default_currency_id,
            "rating_avg": dec(profile.rating_avg), "rating_count": profile.rating_count}


def organization_data(org):
    return {
        **org_summary(org),
        "registration_number": org.registration_number,
        "tax_id": org.tax_id,
        "email": org.email,
        "phone": org.phone,
        "website": org.website,
        "address_line1": org.address_line1,
        "address_line2": org.address_line2,
        "postal_code": org.postal_code,
        "verification_status": org.verification_status,
        "verification_note": org.verification_note,
        "submitted_at": dt(org.submitted_at),
        "verified_at": dt(org.verified_at),
        "created_at": dt(org.created_at),
    }


def coverage_data(org):
    return {
        "locations": [{"id": l.location_id, "name": l.location.name, "country_code": l.location.country_id}
                      for l in org.location_links.select_related("location").order_by("location__name")],
        "ports": [{"id": p.port_id, "name": p.port.name, "unlocode": p.port.unlocode, "location_id": p.port.location_id}
                  for p in org.port_links.select_related("port").order_by("port__name")],
        "services": [{"id": s.service_category_id, "code": s.service_category.code, "name": s.service_category.name}
                     for s in org.service_links.select_related("service_category").order_by("service_category__sort_order")],
    }


def document_data(doc, request=None):
    return {
        "id": doc.pk,
        "document_type": doc.document_type,
        "title": doc.title,
        "status": doc.status,
        "review_note": doc.review_note,
        "review_source": doc.review_source,
        "reviewed_at": dt(doc.reviewed_at),
        "file": file_ref(doc.file, request),
        "uploaded_by": user_summary(doc.uploaded_by_user),
        "created_at": dt(doc.created_at),
    }


def onboarding_data(user, request=None):
    org = user.organization
    if org is None:
        return {"organization": None, "profile": None, "locations": [], "ports": [], "services": [], "documents": [],
                "completeness": {"missing": ["role"]}}
    coverage = coverage_data(org)
    return {
        "organization": organization_data(org),
        "profile": profile_data(org),
        **coverage,
        "documents": [document_data(d, request) for d in org.verification_documents.select_related("file", "uploaded_by_user").order_by("created_at")],
        "completeness": {"missing": completeness(org, user)},
    }


def me_data(user):
    from apps.core.permissions import next_step

    org = user.organization
    return {
        "user": {
            "id": user.pk,
            "email": user.email,
            "display_name": user.display_name,
            "photo_url": user.photo_url,
            "role": user.role,
            "status": user.status,
            "status_reason": user.status_reason,
        },
        "organization": org_summary(org),
        "organization_status": org.verification_status if org else None,
        "next_step": next_step(user),
    }


def agent_row(org):
    profile = getattr(org, "agent_profile", None)
    return {
        **org_summary(org),
        "rating_avg": dec(profile.rating_avg) if profile else "0.00",
        "rating_count": profile.rating_count if profile else 0,
        "completed_port_calls": profile.completed_port_calls if profile else 0,
        "services": [{"id": s.service_category_id, "code": s.service_category.code, "name": s.service_category.name} for s in org.service_links.all()],
        "ports": [{"id": p.port_id, "name": p.port.name, "unlocode": p.port.unlocode} for p in org.port_links.all()],
    }


def user_admin_row(user):
    org = user.organization
    return {
        **user_summary(user),
        "status": user.status,
        "status_reason": user.status_reason,
        "organization": org_summary(org),
        "organization_status": org.verification_status if org else None,
        "created_at": dt(user.created_at),
        "last_login_at": dt(user.last_login_at),
        "linked": user.firebase_uid is not None,
    }
