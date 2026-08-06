import os
import json
import hashlib
import secrets

from psycopg2.extras import RealDictCursor

from app.services.db import get_conn


# =========================================================
# Modules the system supports (used for permission grants)
# =========================================================
ALL_MODULES = [
    "dashboard",
    "replenishment",
    "fc-allocation",
    "sales-analytics",
    "region-sales",
    "china-reorder",
    "cb-replenishment",
    "wm-replenishment",
    "fossil-replenishment",
    "blinkit-replenishment",
    # Plan approval workflow (Naresh proposes, Sagar approves;
    # push to OrderPilot is currently STUB — see plans_service.push_plan)
    "plans-editor",
    "plans-approver",
]


# =========================================================
# Password hashing — sha256 with per-user salt.
# Good enough for an internal tool, no extra dependency.
# =========================================================
def _hash(password: str, salt: str | None = None) -> str:
    if salt is None:
        salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}${digest}"


def _verify(password: str, stored: str) -> bool:
    try:
        salt, digest = stored.split("$", 1)
    except ValueError:
        # legacy / plaintext fallback
        return password == stored
    return hashlib.sha256((salt + password).encode()).hexdigest() == digest


# =========================================================
# Schema + seed
# =========================================================
def ensure_table_and_seed():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS app_users (
                    email           TEXT PRIMARY KEY,
                    name            TEXT,
                    password_hash   TEXT NOT NULL,
                    role            TEXT NOT NULL DEFAULT 'user',
                    allowed_modules JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                );
            """)
            conn.commit()

            # Seed initial admin if the users table is empty.
            # Passwords are NEVER hardcoded — they must be supplied via env vars.
            # If SEED_ADMIN_PASSWORD is not set, seeding is skipped and admins must be
            # bootstrapped manually (e.g. via a one-off psql insert) before first login.
            cur.execute("SELECT COUNT(*) FROM app_users;")
            count = cur.fetchone()[0]
            if count == 0:
                admin_email = os.environ.get("SEED_ADMIN_EMAIL", "").strip().lower()
                admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "")
                if admin_email and admin_password:
                    cur.execute(
                        """
                        INSERT INTO app_users (email, name, password_hash, role, allowed_modules)
                        VALUES (%s, %s, %s, 'admin', %s::jsonb)
                        ON CONFLICT (email) DO NOTHING;
                        """,
                        (admin_email, "Admin", _hash(admin_password), json.dumps(ALL_MODULES)),
                    )
                    conn.commit()
                    print(f"✅ Seeded admin user: {admin_email}")
                else:
                    print(
                        "⚠️ No SEED_ADMIN_PASSWORD env var set — skipping admin seed. "
                        "Bootstrap an admin manually before first login."
                    )


# =========================================================
# CRUD
# =========================================================
def _row_to_user(row: dict) -> dict:
    if not row:
        return None
    return {
        "email":  row["email"],
        "name":   row.get("name") or "",
        "role":   row["role"],
        "allowed_modules": row["allowed_modules"] if isinstance(row["allowed_modules"], list)
                          else json.loads(row["allowed_modules"]) if row["allowed_modules"] else [],
    }


def authenticate(email: str, password: str) -> dict | None:
    ensure_table_and_seed()
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM app_users WHERE LOWER(email) = LOWER(%s);", (email.strip(),))
            row = cur.fetchone()
    if not row:
        return None
    if not _verify(password, row["password_hash"]):
        return None
    return _row_to_user(row)


def get_user(email: str) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM app_users WHERE LOWER(email) = LOWER(%s);", (email.strip(),))
            row = cur.fetchone()
    return _row_to_user(row)


def is_admin(email: str) -> bool:
    u = get_user(email)
    return bool(u and u["role"] == "admin")


def list_users() -> list:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM app_users ORDER BY role DESC, email ASC;")
            rows = cur.fetchall()
    return [_row_to_user(r) for r in rows]


def upsert_user(email: str, name: str, password: str | None, role: str, allowed_modules: list) -> dict:
    email = email.strip().lower()
    if role not in ("admin", "user"):
        raise ValueError("role must be 'admin' or 'user'")
    # Silently drop unknown modules (e.g. legacy slugs like
    # 'china-reorder-working' that were retired but still linger in old
    # user records). Raising here made every edit — even a password
    # reset — fail because the frontend replays the full module list.
    invalid = [m for m in allowed_modules if m not in ALL_MODULES]
    if invalid:
        print(f"WARN: upsert_user dropping unknown modules for {email}: {invalid}")
        allowed_modules = [m for m in allowed_modules if m in ALL_MODULES]

    with get_conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Check if exists
            cur.execute("SELECT password_hash FROM app_users WHERE email = %s;", (email,))
            existing = cur.fetchone()
            if existing:
                if password:  # update password
                    cur.execute(
                        """
                        UPDATE app_users
                        SET name = %s, password_hash = %s, role = %s,
                            allowed_modules = %s::jsonb, updated_at = NOW()
                        WHERE email = %s;
                        """,
                        (name, _hash(password), role, json.dumps(allowed_modules), email),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE app_users
                        SET name = %s, role = %s, allowed_modules = %s::jsonb, updated_at = NOW()
                        WHERE email = %s;
                        """,
                        (name, role, json.dumps(allowed_modules), email),
                    )
            else:
                if not password:
                    raise ValueError("Password is required when creating a new user")
                cur.execute(
                    """
                    INSERT INTO app_users (email, name, password_hash, role, allowed_modules)
                    VALUES (%s, %s, %s, %s, %s::jsonb);
                    """,
                    (email, name, _hash(password), role, json.dumps(allowed_modules)),
                )
        conn.commit()
    return get_user(email)


def delete_user(email: str) -> bool:
    email = email.strip().lower()
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Safety: don't allow deleting the last admin
            cur.execute("SELECT role FROM app_users WHERE email = %s;", (email,))
            row = cur.fetchone()
            if not row:
                return False
            role = row[0]
            if role == "admin":
                cur.execute("SELECT COUNT(*) FROM app_users WHERE role = 'admin';")
                admin_count = cur.fetchone()[0]
                if admin_count <= 1:
                    raise ValueError("Cannot delete the last admin user.")
            cur.execute("DELETE FROM app_users WHERE email = %s;", (email,))
        conn.commit()
    return True
