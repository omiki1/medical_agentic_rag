import json
import uuid
from unittest.mock import AsyncMock, patch

from Application import MedicalApplication
from common.ResponsePresentation import ResponsePresentation
from fastapi.testclient import TestClient

from tests.test_contracts import Fixtures


class RolesAndModels(Fixtures):
    def setUp(self):
        self.settings = self.settings.model_copy(
            update={"model_key_secret": "test-encryption-secret-32-characters-long"}
        )
        self.client = TestClient(
            MedicalApplication(self.settings, corpus=self.corpus, retriever=self.retriever).create()
        )
        self.client.__enter__()
        self.ctx = self.client.app.state.context
        self.session()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def session(self):
        self.client.headers["X-MediAtlas-CSRF"] = self.client.get("/api/session").json()["csrf"]

    def login(self, admin=False):
        credentials = {
            "email": f"{uuid.uuid4().hex}@example.test",
            "username": "权限测试",
            "password": "secure-test-password",
            "role_name": "admin",
        }
        self.assertEqual(self.client.post("/users/register", json=credentials).status_code, 201)
        row = self.ctx.users_dao.find_by_email(credentials["email"])
        self.assertEqual(row["role_name"], "user")
        if admin:
            with self.ctx.database.connect() as conn:
                conn.execute("UPDATE users SET role_name='admin' WHERE users_id=?", (row["users_id"],))
        login = self.client.post("/auth/login", json=credentials).json()
        self.client.headers["X-MediAtlas-CSRF"] = login["csrf"]
        return row["users_id"], login

    def test_guests_cannot_use_account_or_management_routes(self):
        for url in [
            "/api/conversations",
            "/api/memory",
            "/api/status",
            "/api/evaluation",
            "/api/metrics",
            "/api/knowledge",
            "/api/graph?entity=高血压",
            "/api/model-settings",
            "/api/ready",
        ]:
            self.assertEqual(self.client.get(url).status_code, 401, url)

    def test_regular_user_and_spoofed_registration_cannot_manage(self):
        self.login()
        for url in [
            "/api/memory",
            "/api/status",
            "/api/evaluation",
            "/api/metrics",
            "/api/knowledge",
            "/api/graph?entity=高血压",
            "/api/ready",
        ]:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(
            self.client.post(
                "/api/memory", json={"kind": "background", "value": "test", "confirmed": True}
            ).status_code,
            403,
        )
        self.assertEqual(self.client.get("/api/conversations").status_code, 200)

    def test_admin_access_and_immediate_revocation_cookie_and_bearer(self):
        aid, login = self.login(True)
        for url in ["/api/memory", "/api/status", "/api/evaluation", "/api/metrics"]:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        with self.ctx.database.connect() as conn:
            conn.execute("UPDATE users SET role_name='user' WHERE users_id=?", (aid,))
        self.assertEqual(self.client.get("/api/status").status_code, 403)
        self.assertEqual(
            self.client.get("/api/status", headers={"Authorization": "Bearer " + login["data"]}).status_code,
            403,
        )

    def test_key_encryption_isolation_updates_and_no_shared_gateway_mutation(self):
        aid, _ = self.login()
        body = {
            "provider_id": "deepseek",
            "model": "deepseek-flash",
            "api_key": "test-only-user-key-123",
        }
        saved = self.client.post("/api/model-settings", json=body)
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertNotIn(body["api_key"], saved.text)
        row = self.ctx.user_model_service.row(aid)
        self.assertNotIn(body["api_key"], row["encrypted_key"])
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as network:
            one = self.ctx.user_model_service.bind(aid, self.ctx.agent)
            self.assertEqual(one.gateway.api_key, body["api_key"])
            self.assertEqual(one.agent_gateway.api_key, body["api_key"])
            self.assertIsNot(one.gateway, self.ctx.agent.gateway)
            self.assertIs(one.retriever, self.ctx.agent.retriever)
            network.assert_not_called()
        self.assertEqual(
            self.client.post(
                "/api/model-settings", json={**body, "api_key": "", "model": "deepseek-reasoner"}
            ).status_code,
            422,
        )
        self.assertEqual(self.ctx.user_model_service.row(aid)["encrypted_key"], row["encrypted_key"])
        self.login()
        self.assertFalse(self.client.get("/api/model-settings").json()["configured"])
        self.assertEqual(
            self.client.post("/api/model-settings", json={**body, "api_key": ""}).status_code, 422
        )
        self.assertEqual(self.client.delete("/api/model-settings").status_code, 200)
        self.assertIsNotNone(self.ctx.user_model_service.row(aid))

    def test_missing_config_and_disallowed_endpoints_do_not_call_model(self):
        self.login()
        for payload in [
            {"provider_id": "internal", "model": "x", "api_key": "test-only-key"},
            {"provider_id": "deepseek", "model": "gpt-4.1", "api_key": "test-only-key"},
            {"provider_id": "openai", "model": "deepseek-v4-flash", "api_key": "test-only-key"},
            {"base_url": "http://127.0.0.1:5432", "model": "x", "api_key": "test-only-key"},
        ]:
            response = self.client.post("/api/model-settings", json=payload)
            self.assertEqual(response.status_code, 422, payload)
        cid = self.client.post("/api/conversations").json()["id"]
        response = self.client.post(
            "/api/chat",
            json={"conversation_id": cid, "request_id": str(uuid.uuid4()), "question": "甲亢是什么"},
        )
        self.assertEqual(response.status_code, 428)
        self.assertEqual(self.client.get(f"/api/conversations/{cid}").json()["runs"], [])

    def test_provider_catalog_drives_exact_model_choices(self):
        aid, _ = self.login()
        data = self.client.get("/api/model-settings").json()
        providers = {provider["id"]: provider for provider in data["providers"]}
        self.assertEqual(set(providers), {"opencode_go", "deepseek", "zhipu", "openai"})
        self.assertEqual(providers["opencode_go"]["models"][0]["id"], "deepseek-v4.1-flash")
        self.assertEqual(providers["deepseek"]["models"][0]["id"], "deepseek-flash")
        self.assertTrue(all(model["id"] != "deepseek-chat" for model in providers["deepseek"]["models"]))
        self.assertTrue(all(provider["base_url"].startswith("https://") for provider in providers.values()))
        self.client.post(
            "/api/model-settings",
            json={"provider_id": "deepseek", "model": "deepseek-flash", "api_key": "test-only-key"},
        )
        with self.ctx.database.connect() as conn:
            conn.execute("UPDATE user_model_settings SET model='retired-model' WHERE account_id=?", (aid,))
        with self.assertRaisesRegex(Exception, "重新选择服务商和模型"):
            self.ctx.user_model_service.bind(aid, self.ctx.agent)

    def test_public_stream_replay_history_and_sources_hide_diagnostics(self):
        self.login()
        cid = self.client.post("/api/conversations").json()["id"]
        with patch.object(self.ctx.user_model_service, "bind", return_value=self.ctx.agent):
            payload = {"conversation_id": cid, "request_id": str(uuid.uuid4()), "question": "糖尿病如何预防"}
            for _ in range(2):
                response = self.client.post("/api/chat", json=payload)
                self.assertEqual(response.status_code, 200)
                events = [
                    json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
                ]
                self.assertFalse(any(e["type"] == "trace" for e in events))
                result = next(e["data"] for e in events if e["type"] == "result")
                self.assertNotIn("analysis", result)
                self.assertNotIn("trace", result)
                ev = result["evidence"][0]
                self.assertNotIn("raw_scores", ev)
                self.assertNotIn("source_file", ev["document"])
                doc = self.client.get("/api/knowledge/" + ev["document"]["id"]).json()
                self.assertNotIn("source_file", doc)
                self.assertNotIn("source_id", doc)
        run = self.client.get(f"/api/conversations/{cid}").json()["runs"][0]
        self.assertNotIn("trace", run["result"])
        self.assertNotIn("trace", self.client.get("/api/runs/" + run["id"]).json()["result"])
        persisted = self.ctx.chat_dao.run(
            self.ctx.auth_service.dao.find_session(self.client.cookies["mediatlas_session"])["id"], run["id"]
        )
        self.assertIn("trace", persisted["result"])

    def test_internal_source_names_hidden(self):
        data = ResponsePresentation.document(
            {
                "id": "x",
                "source_title": "原始 medical.json（出处待核验）",
                "source_file": "C:/secret.json",
                "source_url": "file:///secret.json",
            }
        )
        self.assertEqual(data["source_title"], "医学知识资料")
        self.assertNotIn("source_file", data)
        self.assertNotIn("source_url", data)
