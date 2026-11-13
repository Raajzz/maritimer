"""File storage (ARCHITECTURE.md §3.6) and file access checks."""
import hashlib
import uuid

from django.conf import settings
from django.core import signing
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from apps.core.enums import FilePurpose, Role
from apps.core.exceptions import ValidationFailed

from .models import StoredFile

_SIGNER_SALT = "maritimer.file-download"


def _detect_content_type(head: bytes, declared: str) -> str | None:
    if head.startswith(b"%PDF"):
        return "application/pdf"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    return None


def store_bytes(*, data: bytes, filename: str, content_type: str, purpose: str, user=None) -> StoredFile:
    extension = settings.FILE_ALLOWED_CONTENT_TYPES.get(content_type, "")
    now = timezone.now()
    key = f"{purpose.lower()}/{now:%Y/%m}/{uuid.uuid4().hex}{extension}"
    saved_key = default_storage.save(key, ContentFile(data))
    return StoredFile.objects.create(
        storage_key=saved_key,
        bucket=getattr(settings, "STORAGE_BUCKET_LABEL", "local"),
        original_filename=(filename or "file")[:255],
        content_type=content_type,
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        uploaded_by_user=user,
        purpose=purpose,
    )


def store_upload(*, upload, purpose, user) -> StoredFile:
    if purpose not in FilePurpose.values or purpose == FilePurpose.GENERATED_PDF:
        raise ValidationFailed("Invalid file purpose.", {"purpose": ["Invalid choice."]})
    if upload.size <= 0:
        raise ValidationFailed("The file is empty.", {"file": ["Empty."]})
    if upload.size > settings.FILE_UPLOAD_MAX_BYTES:
        raise ValidationFailed("The file is too large.", {"file": [f"Max {settings.FILE_UPLOAD_MAX_BYTES // (1024 * 1024)} MB."]})
    data = upload.read()
    detected = _detect_content_type(data[:16], upload.content_type)
    if detected is None or detected not in settings.FILE_ALLOWED_CONTENT_TYPES:
        raise ValidationFailed("Only PDF, PNG, JPEG or WEBP files are allowed.", {"file": ["Unsupported type."]})
    return store_bytes(data=data, filename=upload.name, content_type=detected, purpose=purpose, user=user)


def read_bytes(stored: StoredFile) -> bytes:
    with default_storage.open(stored.storage_key, "rb") as handle:
        return handle.read()


def download_url(stored: StoredFile, request=None) -> str:
    """Short-lived URL. S3/R2: presigned URL. Local storage: signed token served by Django."""
    if settings.STORAGE_BACKEND == "s3":
        return default_storage.url(stored.storage_key, parameters={
            "ResponseContentDisposition": f'inline; filename="{stored.original_filename}"',
        })
    token = signing.dumps({"id": stored.pk}, salt=_SIGNER_SALT)
    path = reverse("file-download", kwargs={"token": token})
    return request.build_absolute_uri(path) if request is not None else path


def resolve_download_token(token: str) -> StoredFile | None:
    try:
        data = signing.loads(token, salt=_SIGNER_SALT, max_age=settings.FILE_DOWNLOAD_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    return StoredFile.objects.filter(pk=data.get("id")).first()


def can_access(user, stored: StoredFile) -> bool:
    """Resolve access through the row(s) that reference the file (API.md §13)."""
    from apps.accounts.models import VerificationDocument
    from apps.chat.models import ChatMessage
    from apps.disputes.models import DisputeEvent
    from apps.invoices.models import VendorInvoice
    from apps.portcalls.selectors import port_calls_for

    if user.role == Role.ADMIN:
        return True
    if stored.uploaded_by_user_id == user.pk:
        return True
    org_id = user.organization_id
    if org_id is None:
        return False
    if VerificationDocument.objects.filter(file=stored, organization_id=org_id).exists():
        return True
    if ChatMessage.objects.filter(file=stored, thread__participants__organization_id=org_id).exists():
        return True
    visible_calls = port_calls_for(user).values("pk")
    invoice_q = Q(file=stored) & (Q(vendor_organization_id=org_id) | Q(agent_organization_id=org_id) | Q(port_call__owner_organization_id=org_id))
    if VendorInvoice.objects.filter(invoice_q).exists():
        return True
    if DisputeEvent.objects.filter(file=stored, dispute__port_call__in=visible_calls).exists():
        if user.role in (Role.OWNER, Role.AGENT):
            return True
    if stored.purpose == FilePurpose.GENERATED_PDF:
        from .models import GeneratedDocument

        return GeneratedDocument.objects.filter(file=stored, port_call__in=visible_calls).exists() and user.role in (Role.OWNER, Role.AGENT)
    return False
