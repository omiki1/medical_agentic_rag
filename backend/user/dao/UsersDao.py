class UsersDao:
    def __init__(self, database):
        self.database = database

    def find_by_email(self, email):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT users_id,username,email,password_hash,role_name FROM users WHERE email=?",
                (email.lower(),),
            ).fetchone()

    def find_by_id(self, user_id):
        with self.database.connect() as conn:
            return conn.execute(
                "SELECT users_id,username,email,role_name FROM users WHERE users_id=?", (user_id,)
            ).fetchone()

    def create(self, username, email, password_hash):
        with self.database.connect() as conn:
            return conn.execute(
                "INSERT INTO users (username,email,password_hash,role_name) VALUES (?,?,?,'user')",
                (username, email.lower(), password_hash),
            ).lastrowid
