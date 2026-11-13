from contextvars import ContextVar

_current_ip: ContextVar[str | None] = ContextVar("current_ip", default=None)


def current_ip():
    return _current_ip.get()


class RequestContextMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
        token = _current_ip.set(ip or None)
        try:
            return self.get_response(request)
        finally:
            _current_ip.reset(token)
