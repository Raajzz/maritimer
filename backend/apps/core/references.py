"""Human-readable references (SCHEMA.md D1): PREFIX-YYYY-NNNNNN from per-year Postgres sequences."""
import re

from django.db import connection
from django.utils import timezone

_PREFIX_RE = re.compile(r"^[A-Z]{2,4}$")


def next_reference(prefix: str) -> str:
    if not _PREFIX_RE.match(prefix):
        raise ValueError("Invalid reference prefix")
    year = timezone.now().year
    sequence = f"ref_{prefix.lower()}_{year}"
    with connection.cursor() as cursor:
        cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {sequence}")
        cursor.execute("SELECT nextval(%s)", [sequence])
        number = cursor.fetchone()[0]
    return f"{prefix}-{year}-{number:06d}"
