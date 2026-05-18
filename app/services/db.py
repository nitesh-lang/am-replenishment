import os
from contextlib import contextmanager

import psycopg2


@contextmanager
def get_conn():
    """Yield a psycopg2 connection and guarantee close() on exit.

    Usage:
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
            conn.commit()   # only for writes
    """
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    try:
        yield conn
    finally:
        conn.close()
