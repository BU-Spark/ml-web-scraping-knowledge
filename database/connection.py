"""Open a Postgres connection from DATABASE_URL.

Shared by data_pipeline (loading) and mcp_server (retrieval). Reads only the environment; the URL is
never logged. Locally, put DATABASE_URL in .env (gitignored); on Heroku it is a config var.
"""
import os


def database_url(env_var="DATABASE_URL"):
    url = os.environ.get(env_var)
    if not url:
        try:
            from dotenv import load_dotenv
            load_dotenv()
            url = os.environ.get(env_var)
        except ImportError:
            pass
    if not url:
        raise RuntimeError(f"{env_var} is not set. Copy .env.example to .env and fill it in.")
    return url


def connect(url=None, autocommit=False):
    """Return a psycopg (v3) connection. Use as a context manager to commit/rollback automatically."""
    import psycopg

    return psycopg.connect(url or database_url(), autocommit=autocommit)
