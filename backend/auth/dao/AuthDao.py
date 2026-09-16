import hashlib
import secrets
import time
import uuid


class AuthDao:
    def __init__(self, database, session_days):
        self.database, self.session_days = database, session_days

    def find_session(self, token):
        if not token or len(token) > 200:
            return None
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT id,csrf,expires,account_id FROM sessions WHERE token_hash=? AND expires>?",
                (hashlib.sha256(token.encode()).hexdigest(), time.time()),
            ).fetchone()
        return dict(row) if row else None

    def get_by_id(self, sid):
        with self.database.connect() as conn:
            row = conn.execute(
                "SELECT id,csrf,expires,account_id FROM sessions WHERE id=? AND expires>?", (sid, time.time())
            ).fetchone()
            return dict(row) if row else None

    def issue_session(self, account_id=None):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        sid = (
            str(uuid.uuid5(uuid.NAMESPACE_URL, f"mediatlas:user:{account_id}"))
            if account_id
            else str(uuid.uuid4())
        )
        expires = time.time() + self.session_days * 86400
        digest = hashlib.sha256(token.encode()).hexdigest()
        with self.database.connect() as conn:
            existing = conn.execute("SELECT id FROM sessions WHERE id=?", (sid,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE sessions SET token_hash=?,csrf=?,expires=? WHERE id=?",
                    (digest, csrf, expires, sid),
                )
            else:
                conn.execute(
                    "INSERT INTO sessions VALUES (?,?,?,?,?)", (sid, digest, csrf, expires, account_id)
                )
        return token, {"id": sid, "csrf": csrf, "expires": expires, "account_id": account_id}

    def revoke(self, sid):
        with self.database.connect() as conn:
            conn.execute("UPDATE sessions SET expires=0 WHERE id=?", (sid,))
