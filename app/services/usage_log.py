import os
import json
import psycopg2
from psycopg2.extras import RealDictCursor


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def ensure_table():
    conn = _conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS app_usage_log (
            id          SERIAL PRIMARY KEY,
            user_email  TEXT,
            event_type  TEXT NOT NULL,
            module      TEXT,
            detail      JSONB,
            created_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_log_user_time ON app_usage_log (user_email, created_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_usage_log_module_time ON app_usage_log (module, created_at DESC);")
    conn.commit()
    cur.close()
    conn.close()


def log_event(user_email: str | None, event_type: str, module: str | None, detail: dict | None):
    if not event_type:
        return
    try:
        ensure_table()
        conn = _conn()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO app_usage_log (user_email, event_type, module, detail)
            VALUES (%s, %s, %s, %s::jsonb);
            """,
            (
                (user_email or "").strip().lower() or None,
                event_type[:64],
                (module or "")[:64] or None,
                json.dumps(detail or {}),
            ),
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        # Logging should never break the app — swallow and print
        print(f"⚠️ usage log failed: {e}")


def summary() -> dict:
    ensure_table()
    conn = _conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Top-line numbers
    cur.execute("""
        SELECT
          COUNT(*)                                                   AS total_events,
          COUNT(DISTINCT user_email)                                 AS unique_users,
          COUNT(*) FILTER (WHERE created_at >= NOW() - interval '1 day')   AS events_24h,
          COUNT(*) FILTER (WHERE created_at >= NOW() - interval '7 days')  AS events_7d,
          COUNT(*) FILTER (WHERE created_at >= NOW() - interval '30 days') AS events_30d,
          COUNT(DISTINCT user_email) FILTER (WHERE created_at >= NOW() - interval '7 days')  AS active_users_7d,
          COUNT(DISTINCT user_email) FILTER (WHERE created_at >= NOW() - interval '30 days') AS active_users_30d
        FROM app_usage_log;
    """)
    overview = dict(cur.fetchone() or {})

    # Per-user breakdown (joined to user table for name + role)
    cur.execute("""
        SELECT
          l.user_email                                                AS email,
          COALESCE(u.name, '')                                        AS name,
          COALESCE(u.role, 'unknown')                                 AS role,
          COUNT(*)                                                    AS total,
          COUNT(*) FILTER (WHERE l.event_type = 'login')              AS logins,
          COUNT(*) FILTER (WHERE l.event_type = 'page_view')          AS page_views,
          COUNT(*) FILTER (WHERE l.event_type = 'save')               AS saves,
          COUNT(*) FILTER (WHERE l.event_type = 'export')             AS exports,
          MAX(l.created_at)                                           AS last_activity
        FROM app_usage_log l
        LEFT JOIN app_users u ON LOWER(u.email) = l.user_email
        WHERE l.user_email IS NOT NULL
        GROUP BY l.user_email, u.name, u.role
        ORDER BY total DESC;
    """)
    by_user = [dict(r) for r in cur.fetchall()]

    # Per-module breakdown
    cur.execute("""
        SELECT
          COALESCE(module, '(unknown)') AS module,
          COUNT(*)                      AS total,
          COUNT(DISTINCT user_email)    AS users,
          MAX(created_at)               AS last_activity
        FROM app_usage_log
        WHERE module IS NOT NULL AND module <> '' AND module <> 'None'
        GROUP BY module
        ORDER BY total DESC;
    """)
    by_module = [dict(r) for r in cur.fetchall()]

    # Last 30 days timeline
    cur.execute("""
        SELECT
          DATE(created_at AT TIME ZONE 'Asia/Kolkata') AS day,
          COUNT(*) AS events,
          COUNT(DISTINCT user_email) AS users
        FROM app_usage_log
        WHERE created_at >= NOW() - interval '30 days'
        GROUP BY day
        ORDER BY day ASC;
    """)
    by_day = [dict(r) for r in cur.fetchall()]

    cur.close()
    conn.close()

    # ISO-stringify timestamps
    for r in by_user:
        if r.get("last_activity"):
            r["last_activity"] = r["last_activity"].isoformat()
    for r in by_module:
        if r.get("last_activity"):
            r["last_activity"] = r["last_activity"].isoformat()
    for r in by_day:
        if r.get("day"):
            r["day"] = r["day"].isoformat()

    return {
        "overview":  overview,
        "by_user":   by_user,
        "by_module": by_module,
        "by_day":    by_day,
    }
