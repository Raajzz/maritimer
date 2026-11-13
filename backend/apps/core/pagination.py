from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100


def apply_sort(queryset, request, allowed: dict[str, str], default: str):
    """`allowed` maps public sort keys to ORM fields; `-key` reverses."""
    raw = request.query_params.get("sort") or default
    desc = raw.startswith("-")
    key = raw[1:] if desc else raw
    field = allowed.get(key)
    if field is None:
        raw = default
        desc = raw.startswith("-")
        field = allowed[raw.lstrip("-")]
    order = f"-{field}" if desc else field
    return queryset.order_by(order, "-id" if desc else "id")
