"""Firebase ID token authentication (ARCHITECTURE.md §3.3).

Header: `Authorization: Bearer <Firebase ID token>`.
Dev-only: when settings.AUTH_DEV_TOKENS is true, `Bearer dev:<email>` signs in as that email
(used by local seed/demo and tests). prod settings force AUTH_DEV_TOKENS = False.
"""
import base64
import json
import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import authentication, exceptions

logger = logging.getLogger(__name__)
_firebase_lock = threading.Lock()
_firebase_app = None


def get_firebase_app():
    global _firebase_app
    if _firebase_app is not None:
        return _firebase_app
    with _firebase_lock:
        if _firebase_app is not None:
            return _firebase_app
        import firebase_admin
        from firebase_admin import credentials

        options = {"projectId": settings.FIREBASE_PROJECT_ID} if settings.FIREBASE_PROJECT_ID else {}
        if settings.FIREBASE_SERVICE_ACCOUNT_JSON_BASE64:
            info = json.loads(base64.b64decode(settings.FIREBASE_SERVICE_ACCOUNT_JSON_BASE64))
            cred = credentials.Certificate(info)
            _firebase_app = firebase_admin.initialize_app(cred, options)
        else:
            # Token verification only needs the project id (public signing keys are fetched by the SDK).
            _firebase_app = firebase_admin.initialize_app(options=options)
        return _firebase_app


def verify_firebase_token(token: str) -> dict:
    from firebase_admin import auth

    app = get_firebase_app()
    return auth.verify_id_token(token, app=app, check_revoked=settings.FIREBASE_CHECK_REVOKED)


def _dev_claims(token: str) -> dict:
    email = token[4:].strip().lower()
    if "@" not in email:
        raise exceptions.AuthenticationFailed("Invalid dev token.")
    return {"uid": f"dev-{email}", "email": email, "email_verified": True, "name": email.split("@")[0]}


def resolve_user(claims: dict):
    """Map verified token claims to the local User (create on first sign-in)."""
    from apps.accounts.models import User

    uid = claims.get("uid") or claims.get("sub")
    email = (claims.get("email") or "").strip().lower()
    if not uid or not email:
        raise exceptions.AuthenticationFailed("Token has no uid/email.")

    user = User.objects.filter(firebase_uid=uid).first()
    if user is None:
        existing = User.objects.filter(email__iexact=email).first()
        if existing is not None:
            if existing.firebase_uid is None and claims.get("email_verified"):
                existing.firebase_uid = uid  # admin pre-provisioned account: link on first sign-in
                existing.save(update_fields=["firebase_uid", "updated_at"])
                user = existing
            else:
                raise exceptions.AuthenticationFailed("This email is linked to another sign-in.")
        else:
            try:
                with transaction.atomic():
                    user = User.objects.create(
                        firebase_uid=uid,
                        email=email,
                        email_verified=bool(claims.get("email_verified")),
                        display_name=claims.get("name") or "",
                        photo_url=claims.get("picture"),
                    )
            except IntegrityError:
                user = User.objects.get(firebase_uid=uid)

    if user.deleted_at is not None:
        raise exceptions.AuthenticationFailed("Account deleted.")

    updates = {}
    now = timezone.now()
    if not user.display_name and claims.get("name"):
        updates["display_name"] = claims["name"]
    if claims.get("picture") and user.photo_url != claims.get("picture"):
        updates["photo_url"] = claims["picture"]
    if bool(claims.get("email_verified")) and not user.email_verified:
        updates["email_verified"] = True
    if user.last_login_at is None or now - user.last_login_at > timedelta(minutes=5):
        updates["last_login_at"] = now
    if updates:
        for key, value in updates.items():
            setattr(user, key, value)
        User.objects.filter(pk=user.pk).update(**updates, updated_at=now)
    return user


class FirebaseAuthentication(authentication.BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None
        parts = header.split(" ", 1)
        if len(parts) != 2 or parts[0] != self.keyword or not parts[1].strip():
            raise exceptions.AuthenticationFailed("Malformed Authorization header.")
        token = parts[1].strip()
        if token.startswith("dev:"):
            if not settings.AUTH_DEV_TOKENS:
                raise exceptions.AuthenticationFailed("Dev tokens are disabled.")
            claims = _dev_claims(token)
        else:
            try:
                claims = verify_firebase_token(token)
            except Exception as exc:  # firebase raises several types; never leak details
                logger.info("Firebase token rejected: %s", exc.__class__.__name__)
                raise exceptions.AuthenticationFailed("Invalid or expired token.") from exc
        return resolve_user(claims), claims

    def authenticate_header(self, request):
        return self.keyword
