from .base import *  # noqa: F401,F403
from .base import env, env_bool

DEBUG = False
AUTH_DEV_TOKENS = False  # never accept dev tokens in production

if SECRET_KEY.startswith("dev-insecure"):  # noqa: F405
    raise RuntimeError("DJANGO_SECRET_KEY must be set in production")
if not FIREBASE_PROJECT_ID:  # noqa: F405
    raise RuntimeError("FIREBASE_PROJECT_ID must be set in production")

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = int(env("SECURE_HSTS_SECONDS", "31536000"))
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)
SECURE_REDIRECT_EXEMPT = [r"^api/v1/health$"]

# Render injects its public hostname; allow it automatically.
_render_host = env("RENDER_EXTERNAL_HOSTNAME", "")
if _render_host and _render_host not in ALLOWED_HOSTS:  # noqa: F405
    ALLOWED_HOSTS.append(_render_host)  # noqa: F405
