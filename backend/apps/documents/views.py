from django.http import FileResponse, Http404
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.enums import FilePurpose, UserStatus
from apps.core.exceptions import NotFound, NotApproved
from apps.core.permissions import is_fully_approved, next_step
from apps.core.serializers import dt, file_ref, validated

from .models import StoredFile
from .services import can_access, resolve_download_token, store_upload


class UploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    purpose = serializers.ChoiceField(choices=[c for c in FilePurpose.choices if c[0] != FilePurpose.GENERATED_PDF])


class FileUploadView(APIView):
    """Approved users upload any purpose; onboarding users may upload VERIFICATION files only."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "upload"

    def post(self, request):
        data = validated(UploadSerializer, request.data)
        user = request.user
        if not is_fully_approved(user):
            if not (data["purpose"] == FilePurpose.VERIFICATION and user.status in (UserStatus.ONBOARDING, UserStatus.REJECTED)):
                raise NotApproved(user.status, next_step(user))
        stored = store_upload(upload=data["file"], purpose=data["purpose"], user=user)
        return Response({**file_ref(stored, request), "purpose": stored.purpose, "created_at": dt(stored.created_at)},
                        status=status.HTTP_201_CREATED)


class FileDetailView(APIView):
    def get(self, request, pk):
        stored = StoredFile.objects.filter(pk=pk).first()
        if stored is None or not can_access(request.user, stored):
            raise NotFound()
        return Response({**file_ref(stored, request), "purpose": stored.purpose, "sha256": stored.sha256, "created_at": dt(stored.created_at)})


class FileDownloadView(APIView):
    """Local-storage downloads via a short-lived signed token (S3/R2 uses presigned URLs instead)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, token):
        from django.core.files.storage import default_storage

        stored = resolve_download_token(token)
        if stored is None:
            raise Http404()
        response = FileResponse(default_storage.open(stored.storage_key, "rb"), content_type=stored.content_type)
        response["Content-Disposition"] = f'inline; filename="{stored.original_filename}"'
        response["Cache-Control"] = "private, max-age=60"
        return response
