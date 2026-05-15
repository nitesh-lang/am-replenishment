import os
import json
import hashlib
import secrets
import psycopg2
from psycopg2.extras import RealDictCursor


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
    "china-reorder-working",
    "cb-replenishment",
    "wm-replenishment",
    "fossil-replenishment",
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


def _conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


# =========================================================
# Schema + seed
# =========================================================
def ensure_table_and_seed():
    conn = _conn()
    cur = conn.cursor()
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

    # Seed initial users if table is empty
    cur.execute("SELECT COUNT(*) FROM app_users;")
    count = cur.fetchone()[0]
    if count == 0:
        seed = [
            {
                "email": "info@cambiumretail.com",
                "name":  "Admin",
                "password": "Cambium@109",
                "role":  "admin",
                "allowed_modules": ALL_MODULES,
            },
            {
                "email": "nitesh@cambiumretail.com",
                "name":  "Nitesh",
                "password": "Naresh@123",
                "role":  "user",
                "allowed_modules": [
                    "replenishment", "fc-allocation",
                    "cb-replenishment", "wm-replenishment",
                    "fossil-replenishment",
                ],
            },
            {
                "email": "kanwal@cambiumretail.com",
                "name":  "Kanwal",
                "password": "Kanwal@123",
                "role":  "user",
                "allowed_modules": [
                    "replenishment", "fc-allocation",
                    "cb-replenishment", "wm-replenishment",
                    "fossil-replenishment",
                ],
            },
            {
                "email": "zaid@cambiumretail.com",
                "name":  "Zaid",
                "password": "Zaid@123",
                "role":  "user",
                "allowed_modules": ["cb-replenishment"],
            },
        ]
        for u in seed:
            cur.execute(
                """
                INSERT INTO app_users (email, name, password_hash, role, allowed_modules)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (email) DO NOTHING;
                """,
                (u["email"], u["name"], _hash(u["password"]), u["role"], json.dumps(u["allowed_modules"])),
            )
        conn.commit()

    cur.close()
    conn.close()


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
    conn = _conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM app_users WHERE LOWER(email) = LOWER(%s);", (email.strip(),))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if not row:
        return None
    if not _verify(password, row["password_hash"]):
        return None
    return _row_to_user(row)


def get_user(email: str) -> dict | None:
    conn = _conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM app_users WHERE LOWER(email) = LOWER(%s);", (email.strip(),))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return _row_to_user(row)


def is_admin(email: str) -> bool:
    u = get_user(email)
    return bool(u and u["role"] == "admin")


def list_users() -> list:
    conn = _conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM app_users ORDER BY role DESC, email ASC;")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [_row_to_user(r) for r in rows]


def upsert_user(email: str, name: str, password: str | None, role: str, allowed_modules: list) -> dict:
    email = email.strip().lower()
    if role not in ("admin", "user"):
        raise ValueError("role must be 'admin' or 'user'")
    # Validate modules
    invalid = [m for m in allowed_modules if m not in ALL_MODULES]
    if invalid:
        raise ValueError(f"Unknown modules: {invalid}")

    conn = _conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
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
    cur.close()
    conn.close()
    return get_user(email)


def delete_user(email: str) -> bool:
    email = email.strip().lower()
    # Safety: don't allow deleting the last admin
    conn = _conn()
    cur = conn.cursor()
    cur.execute("SELECT role FROM app_users WHERE email = %s;", (email,))
    row = cur.fetchone()
    if not row:
        cur.close()
        conn.close()
        return False
    role = row[0]
    if role == "admin":
        cur.execute("SELECT COUNT(*) FROM app_users WHERE role = 'admin';")
        admin_count = cur.fetchone()[0]
        if admin_count <= 1:
            cur.close()
            conn.close()
            raise ValueError("Cannot delete the last admin user.")
    cur.execute("DELETE FROM app_users WHERE email = %s;", (email,))
    conn.commit()
    cur.close()
    conn.close()
    return True
