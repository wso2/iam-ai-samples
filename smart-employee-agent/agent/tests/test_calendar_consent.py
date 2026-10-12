"""Offline regression checks for employee consent and federated Calendar access.

Run from agent/: python -m unittest discover -s tests -v
No Asgardeo, Gemini or Google requests are made.
"""

import copy
import importlib
import io
import logging
import os
from pathlib import Path
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
ENV = {
    "ASGARDEO_BASE_URL": "https://api.asgardeo.io/t/test",
    "ASGARDEO_CLIENT_ID": "mcp-client",
    "AGENT_ID": "test-agent", "AGENT_SECRET": "test-secret",
    "OBO_REDIRECT_URI": "http://localhost:5001/api/obo/callback",
    "TOKEN_AUDIENCE": "spa-client",
    "JWKS_URL": "https://api.asgardeo.io/t/test/oauth2/jwks",
    "AUTH_ISSUER": "https://api.asgardeo.io/t/test/oauth2/token",
    "GOOGLE_API_KEY": "test-key",
    "CIBA_ENABLED": "false", "GOOGLE_CALENDAR_ENABLED": "false",
    "DEBUG_TOKENS": "false", "DEBUG_TOKENS_RAW": "false",
    "DEBUG_FEDERATED_TOKENS_RAW": "false", "DISABLE_SSL_VERIFY": "false",
    "FEDERATED_IDP_NAME": "Google",
}
with patch.dict(os.environ, ENV, clear=True), patch("dotenv.load_dotenv", return_value=False):
    main = importlib.import_module("main")

calendar = main.google_calendar
SCOPE = calendar.CALENDAR_SCOPE


def federated(scope=SCOPE):
    return [{"idp": "Google", "scope": f"openid {scope}",
             "accessToken": "fake-google-token", "tokenValidityPeriod": "3599"}]


class FederatedCalendarTests(unittest.IsolatedAsyncioTestCase):
    async def test_obo_requests_google_scope_only_when_federation_is_enabled(self):
        manager = MagicMock()
        manager.__aenter__.return_value = manager
        manager.get_authorization_url_with_pkce.return_value = (
            "https://api.asgardeo.io/t/test/oauth2/authorize?client_id=mcp-client", "state", "verifier")
        from urllib.parse import parse_qs, urlparse
        for enabled in [False, True]:
            with self.subTest(enabled=enabled):
                with patch.object(main.obo_flow, "SHARE_FEDERATED", enabled), \
                        patch.object(main.obo_flow, "AgentAuthManager", return_value=manager):
                    url, _, _ = await main.obo_flow.get_authorization_url(main.agent_auth)
                params = parse_qs(urlparse(url).query)
                if enabled:
                    self.assertEqual(params["share_federated_token"], ["true"])
                    self.assertEqual(params["federated_token_scope"], ["Google;" + SCOPE])
                else:
                    self.assertNotIn("share_federated_token", params)

    async def test_event_uses_google_token_and_exclusive_end_date(self):
        requests = []
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"id": "event-id"})
        original_client = httpx.AsyncClient
        grant = main.obo_flow.google_grant_from(federated())
        with patch.object(calendar.httpx, "AsyncClient", side_effect=lambda **kw: original_client(
                transport=httpx.MockTransport(respond), **kw)):
            await calendar.GoogleCalendarClient().create_leave_event(
                grant, "Annual Leave", "2026-11-10", "2026-11-12")
        self.assertEqual(len(requests), 1)
        self.assertEqual(str(requests[0].url), calendar.EVENTS_ENDPOINT)
        self.assertEqual(requests[0].headers["Authorization"], "Bearer fake-google-token")
        import json
        self.assertEqual(json.loads(requests[0].content)["end"]["date"], "2026-11-13")

    async def test_expired_grant_never_calls_google_token_endpoint(self):
        grant = calendar.GoogleGrant("fake-google-token", time.time() - 1, SCOPE)
        with patch.object(calendar.httpx, "AsyncClient") as client:
            with self.assertRaisesRegex(calendar.GoogleCalendarError, "expired"):
                await calendar.GoogleCalendarClient().ensure_access_token(grant)
            client.assert_not_called()

    async def test_identity_only_scope_cannot_write_events(self):
        grant = calendar.GoogleGrant("fake-google-token", time.time() + 3600, "openid profile email")
        with patch.object(calendar.httpx, "AsyncClient") as client:
            with self.assertRaisesRegex(calendar.GoogleCalendarError, "missing Calendar"):
                await calendar.GoogleCalendarClient().create_leave_event(
                    grant, "Annual Leave", "2026-11-10", "2026-11-12")
            client.assert_not_called()

    async def test_accepts_event_write_scope_without_google_client_credentials(self):
        grant = main.obo_flow.google_grant_from(federated())
        self.assertEqual(await calendar.GoogleCalendarClient().ensure_access_token(grant), "fake-google-token")
        self.assertFalse(hasattr(calendar, "TOKEN_ENDPOINT"))
        self.assertIsNone(main.obo_flow.google_grant_from([{**federated()[0], "idp": "Other"}]))


class EmployeeConsentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        main.sessions.clear_all()
        self.event = {"employee_sub": "employee", "employee_name": "Alex",
                      "employee_email": "alex@example.com", "request_id": "LR001",
                      "start_date": "2026-11-10", "end_date": "2026-11-12"}
        self.verified = {"request_id": "LR001", "status": "Approved", "type": "Annual Leave",
                         "start_date": "2026-11-10", "end_date": "2026-11-12"}
        self.token = {"access_token": "fake-asgardeo-token", "scope": "openid hr_self_mcp",
                      "federated_tokens": federated()}
        self.client = SimpleNamespace(
            initiate=AsyncMock(return_value={"auth_req_id": "request", "interval": 2}),
            await_approval=AsyncMock(return_value=main.ciba_flow.CibaResult("approved", token=self.token)))
        self.patches = [patch.object(main, "CIBA_ENABLED", True),
                        patch.object(main, "GOOGLE_CALENDAR_ENABLED", True),
                        patch.object(main, "CIBA_CLIENT_ID", "ciba-client"),
                        patch.object(main, "CIBA_CLIENT_SECRET", "fake-secret"),
                        patch.object(main.ciba_flow, "CibaClient", return_value=self.client),
                        patch.object(main.agent_auth, "ensure_valid_token", AsyncMock(
                            return_value=SimpleNamespace(access_token="fake-actor-token")))]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    async def test_only_employee_is_contacted_and_leave_is_verified_before_sync(self):
        with patch.object(main, "_find_own_leave", AsyncMock(return_value=self.verified)) as verify, \
                patch.object(main, "_sync_leave_to_calendar", AsyncMock(return_value="Added")) as sync:
            await main._handle_leave_approved(self.event)
        self.assertEqual(self.client.initiate.call_args.kwargs["login_hint"], "alex@example.com")
        self.assertEqual(self.client.initiate.call_args.kwargs["actor_token"], "fake-actor-token")
        verify.assert_awaited_once_with("fake-asgardeo-token", "LR001")
        sync.assert_awaited_once()
        outcome, employee = sync.call_args.args
        self.assertEqual(outcome["employee_sub"], "employee")
        self.assertEqual(employee.google_grant.access_token, "fake-google-token")
        self.assertEqual(outcome["start_date"], self.verified["start_date"])

    async def test_declined_and_expired_consent_never_sync(self):
        for status in ["denied", "expired", "timeout"]:
            with self.subTest(status=status):
                self.client.await_approval.return_value = main.ciba_flow.CibaResult(status)
                with patch.object(main, "_find_own_leave", AsyncMock()) as verify, \
                        patch.object(main, "_sync_leave_to_calendar", AsyncMock()) as sync:
                    await main._handle_leave_approved(self.event)
                    verify.assert_not_called()
                    sync.assert_not_called()

    async def test_wrong_owner_or_pending_leave_never_syncs(self):
        for verified in [None, {**self.verified, "status": "Pending"}]:
            with self.subTest(verified=verified):
                with patch.object(main, "_find_own_leave", AsyncMock(return_value=verified)), \
                        patch.object(main, "_sync_leave_to_calendar", AsyncMock()) as sync:
                    await main._handle_leave_approved(self.event)
                    sync.assert_not_called()
                    self.assertIsNone(main.sessions.get("employee"))

    async def test_missing_hr_scope_or_google_token_never_syncs(self):
        for response in [{**self.token, "scope": "openid"},
                         {k: v for k, v in self.token.items() if k != "federated_tokens"}]:
            with self.subTest(response_keys=list(response)):
                self.client.await_approval.return_value = main.ciba_flow.CibaResult("approved", token=response)
                with patch.object(main, "_find_own_leave", AsyncMock(return_value=self.verified)), \
                        patch.object(main, "_sync_leave_to_calendar", AsyncMock()) as sync:
                    await main._handle_leave_approved(self.event)
                    sync.assert_not_called()

    async def test_no_fixed_admin_tool_or_direct_google_routes(self):
        self.assertFalse(hasattr(main, "_build_ciba_tool"))
        paths = [route.path for route in main.app.routes]
        self.assertFalse(any(path.startswith(("/api/google/", "/api/calendar-link")) for path in paths))
        prompt = main.build_system_prompt(main.UserSession(user_sub="employee"))
        self.assertNotIn("request_admin_approval", prompt)

    async def test_chat_approval_does_not_write_calendar_before_employee_consent(self):
        session = main.UserSession(user_sub="admin", user_role="HR Admin")
        session.obo_token = SimpleNamespace(access_token="fake-admin-obo-token")
        session.obo_expires_at = time.time() + 3600
        approval = SimpleNamespace(name="approve_leave_request")
        mcp = SimpleNamespace(get_tools=AsyncMock(return_value=[approval]))
        agent = SimpleNamespace(ainvoke=AsyncMock(return_value={
            "messages": [SimpleNamespace(content="Leave approved.")]}))
        main.app.dependency_overrides[main.get_session] = lambda: session
        self.addCleanup(main.app.dependency_overrides.clear)
        with patch.object(main, "_create_mcp_client", return_value=mcp), \
                patch.object(main, "ChatGoogleGenerativeAI"), \
                patch.object(main, "create_agent", return_value=agent) as create_agent, \
                patch.object(main.google_cal, "create_leave_event", AsyncMock()) as write:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                response = await client.post("/api/chat", json={"message": "Approve LR001"})
            self.assertEqual(response.status_code, 200)
            self.assertIs(create_agent.call_args.args[1][0], approval)
            write.assert_not_called()

    async def test_webhook_requires_matching_secret(self):
        with patch.object(main, "LEAVE_EVENT_SECRET", "fake-shared-secret"), \
                patch.object(main, "_handle_leave_approved", AsyncMock()) as handle:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url="http://test") as client:
                rejected = await client.post("/api/events/leave-approved", json=self.event,
                                             headers={"X-Webhook-Secret": "wrong"})
                self.assertEqual(rejected.status_code, 403)
                handle.assert_not_called()
                accepted = await client.post("/api/events/leave-approved", json=self.event,
                                             headers={"X-Webhook-Secret": "fake-shared-secret"})
                self.assertEqual(accepted.status_code, 200)
                import asyncio
                await asyncio.sleep(0)
                handle.assert_awaited_once_with(self.event)


class ITAudienceTests(unittest.IsolatedAsyncioTestCase):
    async def test_inbound_it_agent_accepts_hr_client_and_spa_not_separate_it_client(self):
        import importlib.util
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        path = Path(__file__).resolve().parents[2] / "it-agent/jwt_validator.py"
        spec = importlib.util.spec_from_file_location("it_audience_validator", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        issuer = "https://api.asgardeo.io/t/test/oauth2/token"
        validator = module.JWTValidator("https://test/jwks", issuer, ["hr-mcp-client", "spa-client"])
        with patch.object(validator, "_get_signing_key", AsyncMock(return_value=key.public_key())):
            for audience in ["hr-mcp-client", "spa-client"]:
                token = jwt.encode({"sub": "caller", "aud": audience, "iss": issuer,
                                    "exp": int(time.time()) + 300}, key, algorithm="RS256", headers={"kid": "test"})
                claims = await validator.validate_token(token)
                self.assertEqual(claims["aud"], audience)
            wrong = jwt.encode({"sub": "caller", "aud": "it-mcp-client", "iss": issuer,
                                "exp": int(time.time()) + 300}, key, algorithm="RS256", headers={"kid": "test"})
            with self.assertRaisesRegex(module.TokenError, "Invalid audience"):
                await validator.validate_token(wrong)


class FederatedLogTests(unittest.TestCase):
    def test_raw_federated_output_excludes_asgardeo_tokens(self):
        body = {"access_token": "fake-asgardeo-secret", "id_token": "fake-id-secret",
                "federated_tokens": federated()}
        original = copy.deepcopy(body)
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger = main.ciba_flow.logger
        logger.addHandler(handler)
        self.addCleanup(logger.removeHandler, handler)
        with patch.dict(os.environ, {"DEBUG_TOKENS_RAW": "false", "DEBUG_FEDERATED_TOKENS_RAW": "true"}):
            main.ciba_flow._log_token_response(body)
        logged = stream.getvalue()
        self.assertIn("fake-google-token", logged)
        self.assertIn(SCOPE, logged)
        self.assertNotIn("fake-asgardeo-secret", logged)
        self.assertNotIn("fake-id-secret", logged)
        self.assertEqual(body, original)

    def test_default_federated_output_redacts_credentials_but_keeps_scope(self):
        with patch.dict(os.environ, {"DEBUG_TOKENS_RAW": "false", "DEBUG_FEDERATED_TOKENS_RAW": "false"}):
            with self.assertLogs(main.ciba_flow.logger, level="INFO") as output:
                main.ciba_flow._log_token_response({"federated_tokens": federated()})
        logged = "\n".join(output.output)
        self.assertIn(SCOPE, logged)
        self.assertNotIn("fake-google-token", logged)
        self.assertIn("redacted", logged)


if __name__ == "__main__":
    unittest.main()
