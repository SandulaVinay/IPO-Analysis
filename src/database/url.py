"""Normalize database URLs so the async driver accepts them.

Neon and most hosted Postgres providers give libpq-style URLs such as
`postgresql://...?sslmode=require&channel_binding=require`. asyncpg does not
accept `sslmode` or `channel_binding`, so SQLAlchemy would pass them through and
the connection would fail. This converts them to the asyncpg form.
"""

from sqlalchemy.engine import make_url

# Options asyncpg does not take; `ssl` covers what sslmode was asking for.
_UNSUPPORTED_QUERY_KEYS = ("channel_binding", "sslmode")


def normalize_database_url(url: str) -> str:
    parsed = make_url(url)
    if parsed.drivername not in ("postgres", "postgresql"):
        return url  # SQLite and others are left unchanged.

    query = dict(parsed.query)
    sslmode = query.get("sslmode")
    for key in _UNSUPPORTED_QUERY_KEYS:
        query.pop(key, None)
    if sslmode is not None and "ssl" not in query:
        query["ssl"] = sslmode  # asyncpg accepts the same level names as sslmode.

    parsed = parsed.set(drivername="postgresql+asyncpg")
    return parsed.set(query=query).render_as_string(hide_password=False)
