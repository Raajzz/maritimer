from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .enums import ALL_ENUMS


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"status": "ok"})


class EnumsView(APIView):
    def get(self, request):
        return Response({name: [{"value": c.value, "label": c.label} for c in enum] for name, enum in ALL_ENUMS.items()})
