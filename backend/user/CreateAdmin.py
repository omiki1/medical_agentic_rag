"""Local operator command; there is intentionally no public admin registration API."""

import argparse
import os
import secrets

from common.Database import Database
from common.HashPwdUtil import PasswordManager
from common.Schema import Schema
from common.Settings import PROJECT, Settings

from user.entity.UserEntity import LoginEntity


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", default="admin@mediatlas.local")
    args = parser.parse_args()
    password = secrets.token_urlsafe(24)
    email = LoginEntity(email=args.email, password=password).email
    settings = Settings()
    database = Database(settings)
    Schema.initialize(database)
    path = PROJECT / ".tools" / "admin-credentials.txt"
    path.parent.mkdir(exist_ok=True)
    with database.connect() as conn:
        if conn.execute("SELECT users_id FROM users WHERE email=?", (email,)).fetchone():
            raise SystemExit("Account already exists; no password or role was changed.")
        # Exclusive creation prevents accidentally replacing an earlier credential file.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            output.write(
                f"MediAtlas administrator\nEmail: {email}\nPassword: {password}\n"
                "Keep private. Do not include this file in uploads or deployment archives.\n"
            )
        conn.execute(
            "INSERT INTO users (username,email,password_hash,role_name) VALUES (?,?,?,'admin')",
            ("管理员", email, PasswordManager.hash_password(password)),
        )
    print(f"Created administrator: {email}\nCredentials: {path}\nDatabase: {database.dialect}")


if __name__ == "__main__":
    main()
