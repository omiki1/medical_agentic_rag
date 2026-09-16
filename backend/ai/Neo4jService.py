class Neo4jService:
    """Fixed read-only templates; no model-generated Cypher is accepted."""

    def __init__(self, settings):
        self.settings = settings
        self.driver = None
        self.status = "disabled"
        if settings.neo4j_uri:
            try:
                from neo4j import GraphDatabase

                self.driver = GraphDatabase.driver(
                    settings.neo4j_uri,
                    auth=(settings.neo4j_username, settings.neo4j_password),
                    connection_timeout=settings.neo4j_timeout,
                )
                self.driver.verify_connectivity()
                self.status = "connected"
            except Exception:
                if self.driver:
                    self.driver.close()
                self.driver = None
                self.status = "unavailable"

    def query(self, entities, relations=None, limit=40):
        from create_data.BuildMedicalCorpus import RELATIONS
        from neo4j import READ_ACCESS, Query

        allowed = set(RELATIONS.values())
        relations = list(relations or allowed)
        if not set(relations) <= allowed:
            raise ValueError("Unknown graph relation")
        if not self.driver:
            return []
        query = Query(
            """MATCH (d:Disease)-[r]->(t)
            WHERE d.name IN $entities AND type(r) IN $relations
            RETURN d.name AS subject, type(r) AS relation, t.name AS object
            ORDER BY subject, relation, object LIMIT $limit""",
            timeout=self.settings.neo4j_timeout,
        )
        with self.driver.session(
            database=self.settings.neo4j_database, default_access_mode=READ_ACCESS
        ) as session:
            return session.run(
                query, entities=list(entities)[:6], relations=relations, limit=min(limit, 100)
            ).data()

    def close(self):
        if self.driver:
            self.driver.close()
