from django.conf import settings
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.core.permissions import IsAdminRole

urlpatterns = [
    path("api/v1/", include("config.api_urls")),
    path("api/schema", SpectacularAPIView.as_view(permission_classes=[IsAdminRole] if not settings.DEBUG else []), name="schema"),
    path("api/docs", SpectacularSwaggerView.as_view(url_name="schema", permission_classes=[IsAdminRole] if not settings.DEBUG else []), name="docs"),
]
