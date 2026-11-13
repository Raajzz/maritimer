from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.enums import FilePurpose, GeneratedDocumentType, check_in
from apps.core.models import TimeStampedModel


class StoredFile(TimeStampedModel):
    storage_key = models.CharField(max_length=512, unique=True)
    bucket = models.CharField(max_length=100)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size_bytes = models.BigIntegerField()
    sha256 = models.CharField(max_length=64)
    uploaded_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    purpose = models.CharField(max_length=32, choices=FilePurpose.choices)

    class Meta:
        db_table = "stored_files"
        constraints = [
            models.CheckConstraint(condition=Q(size_bytes__gt=0), name="file_size_positive_chk"),
            models.CheckConstraint(condition=check_in("purpose", FilePurpose), name="file_purpose_chk"),
        ]

    def __str__(self):
        return self.original_filename


class GeneratedDocument(TimeStampedModel):
    port_call = models.ForeignKey("portcalls.PortCall", on_delete=models.PROTECT, related_name="generated_documents")
    document_type = models.CharField(max_length=32, choices=GeneratedDocumentType.choices)
    disbursement_account = models.ForeignKey(
        "disbursements.DisbursementAccount", null=True, blank=True, on_delete=models.PROTECT, related_name="generated_documents"
    )
    settlement = models.ForeignKey("payments.Settlement", null=True, blank=True, on_delete=models.PROTECT, related_name="generated_documents")
    entity_status = models.CharField(max_length=16)
    file = models.ForeignKey(StoredFile, on_delete=models.PROTECT, related_name="+")
    generated_by_user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "generated_documents"
        constraints = [
            models.CheckConstraint(condition=check_in("document_type", GeneratedDocumentType), name="gendoc_type_chk"),
            models.CheckConstraint(
                condition=Q(document_type__in=["PDA", "FDA"], disbursement_account__isnull=False)
                | (~Q(document_type__in=["PDA", "FDA"]) & Q(disbursement_account__isnull=True)),
                name="gendoc_account_link_chk",
            ),
            models.CheckConstraint(
                condition=Q(document_type="SETTLEMENT_STATEMENT", settlement__isnull=False)
                | (~Q(document_type="SETTLEMENT_STATEMENT") & Q(settlement__isnull=True)),
                name="gendoc_settlement_link_chk",
            ),
            models.UniqueConstraint(
                fields=["disbursement_account", "entity_status"],
                condition=Q(disbursement_account__isnull=False),
                name="gendoc_account_status_uniq",
            ),
            models.UniqueConstraint(
                fields=["settlement", "entity_status"], condition=Q(settlement__isnull=False), name="gendoc_settlement_status_uniq"
            ),
        ]
