from src.database.url import normalize_database_url


def test_neon_libpq_url_becomes_asyncpg_with_ssl_and_no_unsupported_options():
    url = "postgresql://neondb_owner:s3cret@ep-x.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    out = normalize_database_url(url)
    assert out.startswith("postgresql+asyncpg://neondb_owner:s3cret@ep-x.us-east-2.aws.neon.tech/neondb")
    assert "sslmode" not in out
    assert "channel_binding" not in out
    assert "ssl=require" in out


def test_postgres_scheme_is_accepted_and_password_is_kept():
    out = normalize_database_url("postgres://u:p%40ss@host/db")
    assert out == "postgresql+asyncpg://u:p%40ss@host/db"


def test_already_asyncpg_url_is_unchanged_apart_from_query_cleanup():
    url = "postgresql+asyncpg://u:p@host/db?ssl=require"
    assert normalize_database_url(url) == url


def test_sqlite_urls_are_left_unchanged():
    url = "sqlite+aiosqlite:///./ipo_system.db"
    assert normalize_database_url(url) == url


def test_engine_connect_args_for_neon_url_have_no_sslmode():
    from sqlalchemy.dialects.postgresql.asyncpg import PGDialect_asyncpg
    from sqlalchemy.engine import make_url

    url = normalize_database_url(
        "postgresql://u:p@ep-x.us-east-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
    )
    _, kwargs = PGDialect_asyncpg().create_connect_args(make_url(url))
    assert "sslmode" not in kwargs and "channel_binding" not in kwargs
    assert kwargs.get("ssl") == "require"
