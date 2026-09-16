import base64
import hashlib
import hmac
import secrets


class PasswordManager:
    """PBKDF2 for new accounts; existing bcrypt hashes remain verifiable."""

    @staticmethod
    def hash_password(password):
        salt = secrets.token_bytes(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 600_000)
        return (
            "pbkdf2_sha256$600000$"
            + base64.b64encode(salt).decode()
            + "$"
            + base64.b64encode(digest).decode()
        )

    @staticmethod
    def verify_password(password, encoded):
        try:
            if encoded.startswith("$2"):
                import bcrypt

                return bcrypt.checkpw(password.encode(), encoded.encode())
            method, iterations, salt, expected = encoded.split("$")
            if method != "pbkdf2_sha256" or int(iterations) > 1_000_000:
                return False
            actual = hashlib.pbkdf2_hmac("sha256", password.encode(), base64.b64decode(salt), int(iterations))
            return hmac.compare_digest(actual, base64.b64decode(expected))
        except (ValueError, TypeError):
            return False
