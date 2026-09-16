class Schema:
    """Idempotent schema for an isolated project database; never alters old tables."""

    @staticmethod
    def initialize(database):
        mysql = database.dialect == "mysql"
        ident = "VARCHAR(64)" if mysql else "TEXT"
        short = "VARCHAR(255)" if mysql else "TEXT"
        large = "LONGTEXT" if mysql else "TEXT"
        number = "DOUBLE" if mysql else "REAL"
        auto = "BIGINT PRIMARY KEY AUTO_INCREMENT" if mysql else "INTEGER PRIMARY KEY AUTOINCREMENT"
        if database.dialect == "postgres":
            auto = "BIGSERIAL PRIMARY KEY"
            number = "DOUBLE PRECISION"
        with database.connect() as conn:
            conn.executescript(f"""
                CREATE TABLE IF NOT EXISTS users (
                    users_id {auto}, username {short} NOT NULL, email {short} NOT NULL UNIQUE,
                    password_hash {short} NOT NULL, role_name VARCHAR(20) NOT NULL DEFAULT 'user');
                CREATE TABLE IF NOT EXISTS sessions (
                    id {ident} PRIMARY KEY, token_hash {ident} UNIQUE, csrf {ident}, expires {number}, account_id BIGINT);
                CREATE TABLE IF NOT EXISTS user_model_settings (
                    account_id BIGINT PRIMARY KEY, base_url {short} NOT NULL, model {short} NOT NULL,
                    encrypted_key {large} NOT NULL,
                    FOREIGN KEY (account_id) REFERENCES users(users_id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS conversations (
                    id {ident} PRIMARY KEY, session_id {ident} NOT NULL,
                    title {short}, created {number}, updated {number},
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS runs (
                    id {ident} PRIMARY KEY, conversation_id {ident} NOT NULL, session_id {ident} NOT NULL,
                    request_id {ident}, question TEXT, status VARCHAR(32), result {large}, created {number},
                    UNIQUE(session_id,request_id),
                    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE);
                CREATE TABLE IF NOT EXISTS semantic_memory (
                    id {ident} PRIMARY KEY, session_id {ident} NOT NULL, kind VARCHAR(32) NOT NULL,
                    value TEXT NOT NULL, provenance VARCHAR(32) NOT NULL,
                    created {number} NOT NULL, updated {number} NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE)
            """)
            if database.dialect == "sqlite":
                columns = {row["name"] for row in conn.execute("PRAGMA table_info(runs)")}
            elif database.dialect == "mysql":
                columns = {row["Field"] for row in conn.execute("SHOW COLUMNS FROM runs")}
            else:
                columns = {
                    row["column_name"]
                    for row in conn.execute(
                        "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name='runs'"
                    )
                }
            if "mode" not in columns:
                conn.execute("ALTER TABLE runs ADD COLUMN mode VARCHAR(20) NOT NULL DEFAULT 'authoritative'")
