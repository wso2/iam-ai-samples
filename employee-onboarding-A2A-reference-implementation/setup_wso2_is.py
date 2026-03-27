#!/usr/bin/env python3
"""
WSO2 Identity Server - Full Setup Script
=========================================
Creates and configures all resources for the A2A Reference Implementation:

  Resources created:
    1. API Resource  : onboarding-api  (with all scopes)
    2. Applications  : onboarding-orchestrator, token-exchanger, mcp-it-server
    3. AI Agents     : orchestrator-agent, hr-agent, it-agent, payroll-agent,
                       booking-agent, mcp-it-agent
    4. Authorized APIs configured on every application
    5. Generates a ready-to-use .env file

  Usage:
    python setup_wso2_is.py                          # interactive prompts
    python setup_wso2_is.py --base-url https://localhost:9443 --admin-user admin --admin-password admin

  Python deps (stdlib-only except requests):
    pip install requests
"""

import argparse
import base64
import json
import os
import random
import string
import sys
import time
import urllib3
from typing import Optional

try:
    import requests
    from requests.auth import HTTPBasicAuth
except ImportError:
    print("[ERROR] 'requests' package not found. Install it with:  pip install requests")
    sys.exit(1)

# Suppress insecure-request warnings (localhost TLS with self-signed cert)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    """ANSI color helper."""
    codes = {"green": "32", "yellow": "33", "red": "31", "cyan": "36", "bold": "1", "reset": "0"}
    return f"\033[{codes.get(code, '0')}m{text}\033[0m"


def banner(msg: str):
    width = 70
    print()
    print(_c("cyan", "─" * width))
    print(_c("bold", f"  {msg}"))
    print(_c("cyan", "─" * width))


def ok(msg: str):
    print(_c("green", f"  ✔  {msg}"))


def warn(msg: str):
    print(_c("yellow", f"  ⚠  {msg}"))


def err(msg: str):
    print(_c("red", f"  ✖  {msg}"))


def info(msg: str):
    print(f"     {msg}")


def generate_secret(length: int = 24) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choices(alphabet, k=length))


# ─────────────────────────────────────────────────────────────────────────────
# WSO2 IS API Client
# ─────────────────────────────────────────────────────────────────────────────

class WSO2ISClient:
    """Thin wrapper around the WSO2 IS Management REST API."""

    def __init__(self, base_url: str, admin_user: str, admin_password: str):
        self.base_url = base_url.rstrip("/")
        self.auth = HTTPBasicAuth(admin_user, admin_password)
        self.session = requests.Session()
        self.session.verify = False          # self-signed cert on localhost
        self.session.auth = self.auth
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    # ── generic request helpers ─────────────────────────────────────────

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _get(self, path: str, params: dict = None) -> dict:
        r = self.session.get(self._url(path), params=params)
        self._raise(r)
        return r.json() if r.text else {}

    def _post(self, path: str, body: dict) -> dict:
        r = self.session.post(self._url(path), json=body)
        self._raise(r)
        # Parse body
        try:
            data = r.json() if r.text and r.text.strip() else {}
        except Exception:
            data = {}
        # WSO2 IS often returns 201 with Location header and empty/minimal body
        # Follow Location to get the full resource with id
        if not data.get("id"):
            location = r.headers.get("Location", "")
            if location:
                # Location may be absolute URL or relative path
                if location.startswith("http"):
                    from urllib.parse import urlparse as _up
                    parsed = _up(location)
                    rel_path = parsed.path
                    # Strip base path prefix if present (e.g. /t/carbon.super)
                    for prefix in ("/t/carbon.super", "/t/wso2.com"):
                        if rel_path.startswith(prefix):
                            rel_path = rel_path[len(prefix):]
                            break
                else:
                    rel_path = location
                try:
                    fetched = self._get(rel_path)
                    if fetched:
                        data = fetched
                except Exception:
                    pass
        return data

    def _patch(self, path: str, body: dict) -> dict:
        r = self.session.patch(self._url(path), json=body)
        self._raise(r)
        return r.json() if r.text else {}

    def _put(self, path: str, body: dict) -> dict:
        r = self.session.put(self._url(path), json=body)
        self._raise(r)
        return r.json() if r.text else {}

    def _delete(self, path: str):
        r = self.session.delete(self._url(path))
        self._raise_permissive(r)

    @staticmethod
    def _raise(r: requests.Response):
        if not r.ok:
            try:
                detail = r.json()
            except Exception:
                detail = r.text
            raise RuntimeError(
                f"HTTP {r.status_code} {r.request.method} {r.url}\n{json.dumps(detail, indent=2)}"
            )

    @staticmethod
    def _raise_permissive(r: requests.Response):
        """Raise only on unexpected errors (allows 404)."""
        if not r.ok and r.status_code not in (404, 409):
            WSO2ISClient._raise(r)

    # ── connectivity check ───────────────────────────────────────────────

    def ping(self):
        r = self.session.get(self._url("/api/server/v1/applications?limit=1"))
        if not r.ok:
            raise RuntimeError(
                f"Cannot connect to WSO2 IS at {self.base_url}  "
                f"(HTTP {r.status_code}). Check base-url and credentials."
            )

    # ── Application Templates ─────────────────────────────────────────────

    def list_application_templates(self) -> list:
        """Return available app templates; returns [] on permission errors or missing endpoint."""
        r = self.session.get(self._url("/api/server/v1/application-templates"))
        if not r.ok:
            # 403 = no permission (common on default IS installs), 404 = not supported
            return []
        try:
            data = r.json() if r.text and r.text.strip() else {}
        except Exception:
            return []
        if isinstance(data, list):
            return data
        return data.get("templates") or data.get("applicationTemplates") or []

    def _find_template_id(self, keyword: str) -> Optional[str]:
        """Return templateId whose name contains keyword (case-insensitive)."""
        for t in self.list_application_templates():
            name = (t.get("name") or "").lower()
            if keyword.lower() in name:
                return t.get("id") or t.get("templateId")
        return None

    # ── API Resources ─────────────────────────────────────────────────────

    def find_api_resource(self, identifier: str) -> Optional[dict]:
        data = self._get("/api/server/v1/api-resources", params={"filter": f"identifier eq {identifier}"})
        resources = data.get("apiResources") or []
        return resources[0] if resources else None

    def create_api_resource(self, name: str, identifier: str, description: str = "") -> dict:
        existing = self.find_api_resource(identifier)
        if existing:
            warn(f"API resource '{identifier}' already exists – skipping creation")
            return existing
        body = {
            "name": name,
            "identifier": identifier,
            "description": description,
            "requiresAuthorization": True,
        }
        result = self._post("/api/server/v1/api-resources", body)
        ok(f"Created API resource: {identifier}  (id={result.get('id')})")
        return result

    def add_scopes_to_resource(self, resource_id: str, scopes: list[dict]):
        """
        scopes: [ {"name": "hr:read", "displayName": "HR Read", "description": "..."}, ... ]
        """
        # Fetch existing scopes to avoid duplicates
        existing_raw = self._get(f"/api/server/v1/api-resources/{resource_id}/scopes")
        # WSO2 IS may return a list directly or {"scopes": [...]}
        if isinstance(existing_raw, list):
            existing = existing_raw
        elif isinstance(existing_raw, dict):
            existing = existing_raw.get("scopes") or []
        else:
            existing = []
        existing_names = {s["name"] for s in existing}

        new_scopes = [s for s in scopes if s["name"] not in existing_names]
        if not new_scopes:
            warn("All scopes already exist on the resource")
            return

        # WSO2 IS accepts PUT to replace all scopes, or PATCH to add
        # We use PUT with all scopes combined (existing + new)
        all_scopes = list(existing) + new_scopes
        r = self.session.put(
            self._url(f"/api/server/v1/api-resources/{resource_id}/scopes"),
            json=all_scopes,
        )
        self._raise(r)
        ok(f"Scopes added: {[s['name'] for s in new_scopes]}")

    # ── Applications ──────────────────────────────────────────────────────

    def find_application(self, name: str) -> Optional[dict]:
        raw = self._get("/api/server/v1/applications", params={"filter": f"name eq {name}"})
        # Raw may be a list or a wrapper object
        if isinstance(raw, list):
            apps = raw
        elif isinstance(raw, dict):
            apps = raw.get("applications") or []
        else:
            apps = []
        if not apps:
            return None
        app = apps[0]
        # Normalise: older WSO2 IS uses 'applicationId', newer uses 'id'
        if "id" not in app and "applicationId" in app:
            app = dict(app, id=app["applicationId"])
        return app

    def create_oidc_application(
        self,
        name: str,
        description: str,
        grant_types: list[str],
        callback_urls: list[str] = None,
        template_id: Optional[str] = None,
    ) -> dict:
        existing = self.find_application(name)
        if existing:
            warn(f"Application '{name}' already exists – fetching full details")
            return self._get(f"/api/server/v1/applications/{existing['id']}")

        body: dict = {
            "name": name,
            "description": description,
            "inboundProtocolConfiguration": {
                "oidc": {
                    "grantTypes": grant_types,
                    "publicClient": False,
                    "pkce": {
                        "mandatory": False,
                        "supportPlainTransformAlgorithm": False,
                    },
                }
            },
        }

        if callback_urls:
            body["inboundProtocolConfiguration"]["oidc"]["callbackURLs"] = callback_urls

        if template_id:
            body["templateId"] = template_id

        result = self._post("/api/server/v1/applications", body)
        # If id is still missing, re-fetch by name
        if not result.get("id"):
            refetched = self.find_application(name)
            if refetched:
                result = self._get(f"/api/server/v1/applications/{refetched['id']}")
        ok(f"Created application: {name}  (id={result.get('id')})")
        return result

    def get_application_inbound_config(self, app_id: str) -> dict:
        return self._get(f"/api/server/v1/applications/{app_id}/inbound-protocols/oidc")

    def regenerate_client_secret(self, app_id: str) -> str:
        r = self.session.post(
            self._url(f"/api/server/v1/applications/{app_id}/inbound-protocols/oidc/regenerate-secret")
        )
        self._raise(r)
        return r.json().get("clientSecret", "")

    def authorize_api_for_app(
        self, app_id: str, api_resource_id: str, scopes: list[str], api_identifier: str = ""
    ):
        """Authorize an API resource and grant scopes to the application."""
        # Fetch existing authorized APIs — WSO2 IS returns either a list or
        # a wrapper object {"authorizedAPIs": [...]}
        raw = self._get(f"/api/server/v1/applications/{app_id}/authorized-apis")
        if isinstance(raw, list):
            existing_apis = raw
        elif isinstance(raw, dict):
            existing_apis = raw.get("authorizedAPIs") or raw.get("apis") or []
        else:
            existing_apis = []

        for existing_api in existing_apis:
            existing_id = existing_api.get("id") or existing_api.get("apiId") or ""
            if existing_id == api_resource_id:
                warn(f"API '{api_identifier}' already authorized for app – skipping")
                return
        body = {
            "id": api_resource_id,
            "policyIdentifier": "RBAC",
            "scopes": scopes,
        }
        r = self.session.post(
            self._url(f"/api/server/v1/applications/{app_id}/authorized-apis"),
            json=body,
        )
        self._raise(r)
        ok(f"Authorized API '{api_identifier}' on app with scopes: {scopes}")

    # ── AI Agents ─────────────────────────────────────────────────────────

    def _discover_agent_template_id(self) -> Optional[str]:
        """Attempt to find the AI Agent application template."""
        for keyword in ("agent", "ai agent", "aiagent"):
            tid = self._find_template_id(keyword)
            if tid:
                return tid
        return None

    def create_agent(
        self,
        name: str,
        description: str,
        linked_app_id: str,
        agent_secret: str,
        agent_template_id: Optional[str] = None,
    ) -> dict:
        """
        Create an AI Agent linked to an application.

        WSO2 IS 7.x stores agents as a specialised application sub-type.
        If the server exposes a dedicated /ai-agents endpoint it is used;
        otherwise the generic applications endpoint is used with the discovered
        agent template id.  The caller must provide a non-empty agent_secret
        which is written to the .env file for the agent authentication step.
        """
        # --- Try dedicated agent endpoint (WSO2 IS 7.0+ / Asgardeo) --------
        # Only use dedicated path when the endpoint explicitly returns 200.
        # 404 means the endpoint does not exist on this WSO2 IS version.
        r = self.session.get(self._url("/api/server/v1/agents?limit=1"))
        if r.status_code == 200:
            return self._create_agent_via_dedicated_api(name, description, linked_app_id, agent_secret)

        # --- Fallback: use applications endpoint with agent template ---------
        if not agent_template_id:
            agent_template_id = self._discover_agent_template_id()

        if agent_template_id:
            return self._create_agent_via_app_template(
                name, description, linked_app_id, agent_secret, agent_template_id
            )

        # --- Last resort: create as a service account (client-creds app) ----
        warn(
            f"Could not find an AI Agent template on this WSO2 IS instance. "
            f"Creating '{name}' as a client-credentials application instead. "
            f"Update agent_id manually in .env after the run."
        )
        return self._create_agent_as_service_account(name, description, linked_app_id)

    def _agents_list(self, params: dict = None) -> list:
        """Fetch agents list; handles both raw-list and wrapper-object responses."""
        r = self.session.get(self._url("/api/server/v1/agents"), params=params)
        if not r.ok:
            return []  # endpoint exists but filter returned nothing, or transient error
        try:
            raw = r.json() if r.text and r.text.strip() else {}
        except Exception:
            return []
        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            return raw.get("agents") or raw.get("resources") or []
        return []

    def _create_agent_via_dedicated_api(
        self, name: str, description: str, linked_app_id: str, agent_secret: str
    ) -> dict:
        for agent in self._agents_list(params={"filter": f"name eq {name}"}):
            if agent.get("name") == name:
                warn(f"Agent '{name}' already exists – skipping creation")
                agent_id = agent.get("id") or agent.get("agentId", "")
                return self._get(f"/api/server/v1/agents/{agent_id}")

        body = {
            "name": name,
            "description": description,
            "associatedApplicationId": linked_app_id,
            "password": agent_secret,
        }
        result = self._post("/api/server/v1/agents", body)
        # Re-fetch if id missing
        if not result.get("id"):
            for a in self._agents_list(params={"filter": f"name eq {name}"}):
                if a.get("name") == name:
                    result = self._get(f"/api/server/v1/agents/{a.get('id') or a.get('agentId')}")
                    break
        ok(f"Created agent via /agents API: {name}  (agent_id={result.get('id')})")
        return result

    def _create_agent_via_app_template(
        self, name: str, description: str, linked_app_id: str, agent_secret: str, template_id: str
    ) -> dict:
        existing = self.find_application(name)
        if existing:
            warn(f"Agent application '{name}' already exists")
            return self._get(f"/api/server/v1/applications/{existing['id']}")

        body = {
            "name": name,
            "description": description,
            "templateId": template_id,
            "associatedApplicationId": linked_app_id,
            "advancedConfigurations": {
                "agentSecret": agent_secret,
            },
        }
        result = self._post("/api/server/v1/applications", body)
        if not result.get("id"):
            refetched = self.find_application(name)
            if refetched:
                result = self._get(f"/api/server/v1/applications/{refetched['id']}")
        ok(f"Created agent via app template: {name}  (id={result.get('id')})")
        return result

    def _create_agent_as_service_account(
        self, name: str, description: str, linked_app_id: str
    ) -> dict:
        existing = self.find_application(name)
        if existing:
            warn(f"Agent application '{name}' already exists")
            return self._get(f"/api/server/v1/applications/{existing['id']}")

        body = {
            "name": name,
            "description": description,
            "inboundProtocolConfiguration": {
                "oidc": {
                    "grantTypes": ["client_credentials"],
                    "publicClient": False,
                }
            },
            "associatedApplicationId": linked_app_id,
        }
        result = self._post("/api/server/v1/applications", body)
        if not result.get("id"):
            refetched = self.find_application(name)
            if refetched:
                result = self._get(f"/api/server/v1/applications/{refetched['id']}")
        warn(f"Created '{name}' as service account app (id={result.get('id')})")
        return result

    def get_agent_id(self, agent_resource: dict) -> str:
        """Extract the agent_id (UUID) from an agent resource."""
        # Dedicated /agents API returns id directly
        if "id" in agent_resource:
            maybe = agent_resource["id"]
            # Prefer agentId field if present
            return agent_resource.get("agentId") or agent_resource.get("agent_id") or maybe
        return ""

    def set_agent_password(self, agent_id_or_username: str, new_password: str):
        """
        Set / reset the agent's authentication password.
        WSO2 IS SCIM 2.0 user endpoint can be used if agents are user entities.
        """
        # Try SCIM patch by username filter
        r = self.session.get(
            self._url(f"/scim2/Users?filter=userName+eq+{agent_id_or_username}")
        )
        if r.ok:
            users = r.json().get("Resources") or []
            if users:
                user_id = users[0]["id"]
                patch_body = {
                    "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                    "Operations": [
                        {
                            "op": "replace",
                            "value": {"password": new_password},
                        }
                    ],
                }
                pr = self.session.patch(
                    self._url(f"/scim2/Users/{user_id}"), json=patch_body
                )
                if pr.ok:
                    ok(f"Password set for agent '{agent_id_or_username}' via SCIM")
                    return
        warn(
            f"Could not set password for agent '{agent_id_or_username}' via SCIM. "
            f"Please set the agent secret manually in the WSO2 IS console."
        )

    # ── Audience configuration ─────────────────────────────────────────────

    def configure_app_audience(self, app_id: str, audiences: list[str]):
        """
        Configure the token audience (aud claim) for an application.

        WSO2 IS exposes audience via the OIDC inbound-protocol config:
          GET  /applications/{id}/inbound-protocols/oidc   -> current config
          PUT  same endpoint                               -> update with audience field

        Falls back to a root-application PATCH then PUT if the OIDC endpoint
        is unavailable, and logs a warning if everything fails (non-fatal).
        """
        # ── Primary: update OIDC inbound-protocol config ────────────────
        try:
            oidc_cfg = self._get(f"/api/server/v1/applications/{app_id}/inbound-protocols/oidc")
            oidc_cfg["audience"] = audiences
            # Remove read-only fields that WSO2 IS rejects on PUT
            for ro_key in ("clientId", "clientSecret"):
                oidc_cfg.pop(ro_key, None)
            pr = self.session.put(
                self._url(f"/api/server/v1/applications/{app_id}/inbound-protocols/oidc"),
                json=oidc_cfg,
            )
            if pr.ok:
                ok(f"Configured audience(s) {audiences} on app id={app_id}")
                return
            # Non-fatal; fall through to next strategy
            _audience_warn = f"{pr.status_code} {pr.text[:120]}"
        except Exception as exc:
            _audience_warn = str(exc)

        # ── Fallback 1: PATCH application root ───────────────────────────
        try:
            pr2 = self.session.patch(
                self._url(f"/api/server/v1/applications/{app_id}"),
                json={"advancedConfigurations": {"audience": audiences}},
            )
            if pr2.ok:
                ok(f"Configured audience(s) {audiences} on app id={app_id} (via PATCH)")
                return
        except Exception:
            pass

        # ── Fallback 2: full application PUT ─────────────────────────────
        try:
            full = self._get(f"/api/server/v1/applications/{app_id}")
            adv = full.get("advancedConfigurations") or {}
            adv["audience"] = audiences
            full["advancedConfigurations"] = adv
            pr3 = self.session.put(
                self._url(f"/api/server/v1/applications/{app_id}"),
                json=full,
            )
            if pr3.ok:
                ok(f"Configured audience(s) {audiences} on app id={app_id} (via full PUT)")
                return
        except Exception:
            pass

        warn(
            f"Could not set audience {audiences} on app {app_id} – "
            f"set it manually in the console. ({_audience_warn})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Setup Orchestration
# ─────────────────────────────────────────────────────────────────────────────

class A2ASetup:
    """Orchestrates the full WSO2 IS setup for the A2A reference implementation."""

    # All scopes grouped by service domain
    ALL_SCOPES: list[dict] = [
        {"name": "hr:read",       "displayName": "HR Read",           "description": "Read HR employee data"},
        {"name": "hr:write",      "displayName": "HR Write",          "description": "Write HR employee data"},
        {"name": "it:read",       "displayName": "IT Read",           "description": "Read IT provisioning data"},
        {"name": "it:write",      "displayName": "IT Write",          "description": "Provision IT accounts"},
        {"name": "approval:read", "displayName": "Approval Read",     "description": "Read approvals"},
        {"name": "approval:write","displayName": "Approval Write",    "description": "Create/manage approvals"},
        {"name": "booking:read",  "displayName": "Booking Read",      "description": "Read bookings"},
        {"name": "booking:write", "displayName": "Booking Write",     "description": "Create bookings"},
    ]

    API_RESOURCE_IDENTIFIER = "onboarding-api"
    API_RESOURCE_NAME       = "Onboarding API"
    API_CALLBACK_URL        = "http://localhost:8000/callback"

    def __init__(self, client: WSO2ISClient):
        self.c = client
        # Will be populated during setup
        self.results: dict = {
            "api_resource": {},
            "apps": {},
            "agents": {},
            "env": {},
        }

    # ── Step 1 : API Resource & Scopes ────────────────────────────────────

    def step_api_resource(self):
        banner("STEP 1 – Create API Resource: onboarding-api")
        resource = self.c.create_api_resource(
            name=self.API_RESOURCE_NAME,
            identifier=self.API_RESOURCE_IDENTIFIER,
            description="Shared API resource for the A2A onboarding workflow",
        )
        rid = resource["id"]
        info(f"Resource ID: {rid}")

        self.c.add_scopes_to_resource(rid, self.ALL_SCOPES)
        self.results["api_resource"] = {"id": rid, "identifier": self.API_RESOURCE_IDENTIFIER}

    # ── Step 2 : Applications ─────────────────────────────────────────────

    def step_applications(self):
        banner("STEP 2 – Create Applications")

        rid = self.results["api_resource"]["id"]
        all_scope_names = [s["name"] for s in self.ALL_SCOPES]

        # ── 2a. onboarding-orchestrator ──────────────────────────────────
        info("Creating onboarding-orchestrator …")
        orch_app = self.c.create_oidc_application(
            name="onboarding-orchestrator",
            description="Orchestrator application for the A2A employee onboarding workflow",
            grant_types=[
                "authorization_code",
                "client_credentials",
                "refresh_token",
                "urn:ietf:params:oauth:grant-type:token-exchange",
            ],
            callback_urls=[self.API_CALLBACK_URL],
        )
        orch_app_id = orch_app["id"]
        orch_inbound = self.c.get_application_inbound_config(orch_app_id)
        orch_client_id     = orch_inbound.get("clientId", "")
        orch_client_secret = orch_inbound.get("clientSecret", "")

        # Authorize onboarding-api (all scopes)
        self.c.authorize_api_for_app(orch_app_id, rid, all_scope_names, self.API_RESOURCE_IDENTIFIER)
        # Audience
        self.c.configure_app_audience(orch_app_id, [self.API_RESOURCE_IDENTIFIER])

        self.results["apps"]["orchestrator"] = {
            "id": orch_app_id,
            "client_id": orch_client_id,
            "client_secret": orch_client_secret,
        }
        info(f"  client_id     : {orch_client_id}")
        info(f"  client_secret : {orch_client_secret}")

        # ── 2b. token-exchanger ──────────────────────────────────────────
        info("Creating token-exchanger …")
        te_app = self.c.create_oidc_application(
            name="token-exchanger",
            description="Dedicated application for RFC 8693 token exchange between agents",
            grant_types=[
                "urn:ietf:params:oauth:grant-type:token-exchange",
                "client_credentials",
            ],
        )
        te_app_id = te_app["id"]
        te_inbound = self.c.get_application_inbound_config(te_app_id)
        te_client_id     = te_inbound.get("clientId", "")
        te_client_secret = te_inbound.get("clientSecret", "")

        # Authorize onboarding-api (all scopes)
        self.c.authorize_api_for_app(te_app_id, rid, all_scope_names, self.API_RESOURCE_IDENTIFIER)
        self.c.configure_app_audience(te_app_id, [self.API_RESOURCE_IDENTIFIER])

        self.results["apps"]["token_exchanger"] = {
            "id": te_app_id,
            "client_id": te_client_id,
            "client_secret": te_client_secret,
        }
        info(f"  client_id     : {te_client_id}")
        info(f"  client_secret : {te_client_secret}")

        # ── 2c. mcp-it-server ────────────────────────────────────────────
        info("Creating mcp-it-server …")
        mcp_app = self.c.create_oidc_application(
            name="mcp-it-server",
            description="MCP IT Server — intermediary between the IT Agent and the IT API",
            grant_types=[
                "client_credentials",
                "urn:ietf:params:oauth:grant-type:token-exchange",
            ],
        )
        mcp_app_id = mcp_app["id"]
        mcp_inbound = self.c.get_application_inbound_config(mcp_app_id)
        mcp_client_id     = mcp_inbound.get("clientId", "")
        mcp_client_secret = mcp_inbound.get("clientSecret", "")

        # Only authorize it: scopes for MCP server
        it_scopes = ["it:read", "it:write"]
        self.c.authorize_api_for_app(mcp_app_id, rid, it_scopes, self.API_RESOURCE_IDENTIFIER)
        self.c.configure_app_audience(mcp_app_id, [self.API_RESOURCE_IDENTIFIER])

        self.results["apps"]["mcp_it"] = {
            "id": mcp_app_id,
            "client_id": mcp_client_id,
            "client_secret": mcp_client_secret,
        }
        info(f"  client_id     : {mcp_client_id}")
        info(f"  client_secret : {mcp_client_secret}")

    # ── Step 3 : AI Agents ────────────────────────────────────────────────

    def step_agents(self):
        banner("STEP 3 – Create AI Agents")

        orch_app_id = self.results["apps"]["orchestrator"]["id"]
        mcp_app_id  = self.results["apps"]["mcp_it"]["id"]

        agents_spec = [
            {
                "key": "orchestrator_agent",
                "name": "orchestrator-agent",
                "description": "AI Director Agent — orchestrates the onboarding workflow",
                "linked_app_id": orch_app_id,
                "env_key_id": "ORCHESTRATOR_AGENT_ID",
                "env_key_secret": "ORCHESTRATOR_AGENT_SECRET",
            },
            {
                "key": "hr_agent",
                "name": "hr-agent",
                "description": "HR Agent — manages employee profiles",
                "linked_app_id": orch_app_id,
                "env_key_id": "HR_AGENT_ID",
                "env_key_secret": "HR_AGENT_SECRET",
            },
            {
                "key": "it_agent",
                "name": "it-agent",
                "description": "IT Agent — provisions IT accounts and VPN",
                "linked_app_id": orch_app_id,
                "env_key_id": "IT_AGENT_ID",
                "env_key_secret": "IT_AGENT_SECRET",
            },
            {
                "key": "payroll_agent",
                "name": "payroll-agent",
                "description": "Finance & Payroll Agent — registers payroll and expense accounts",
                "linked_app_id": orch_app_id,
                "env_key_id": "PAYROLL_AGENT_ID",
                "env_key_secret": "PAYROLL_AGENT_SECRET",
            },
            {
                "key": "booking_agent",
                "name": "booking-agent",
                "description": "Booking Agent — schedules tasks and deliveries",
                "linked_app_id": orch_app_id,
                "env_key_id": "BOOKING_AGENT_ID",
                "env_key_secret": "BOOKING_AGENT_SECRET",
            },
            {
                "key": "mcp_it_agent",
                "name": "mcp-it-agent",
                "description": "MCP IT Agent — authenticates MCP server against IT API",
                "linked_app_id": mcp_app_id,
                "env_key_id": "MCP_IT_AGENT_ID",
                "env_key_secret": "MCP_IT_AGENT_SECRET",
            },
        ]

        # Discover agent template once
        agent_template_id = self.c._discover_agent_template_id()
        if agent_template_id:
            info(f"Discovered AI Agent template ID: {agent_template_id}")
        else:
            warn("No AI Agent template found – will use fallback strategy")

        for spec in agents_spec:
            info(f"Creating {spec['name']} …")
            secret = generate_secret()

            agent_resource = self.c.create_agent(
                name=spec["name"],
                description=spec["description"],
                linked_app_id=spec["linked_app_id"],
                agent_secret=secret,
                agent_template_id=agent_template_id,
            )

            agent_id = self.c.get_agent_id(agent_resource)

            # Attempt to set password via SCIM if agent_id is known
            if agent_id:
                self.c.set_agent_password(agent_id, secret)

            self.results["agents"][spec["key"]] = {
                "agent_id": agent_id,
                "agent_secret": secret,
                "env_key_id": spec["env_key_id"],
                "env_key_secret": spec["env_key_secret"],
            }
            info(f"  agent_id : {agent_id or 'UNKNOWN – set manually'}")
            info(f"  secret   : {secret}")

    # ── Step 4 : Write .env ────────────────────────────────────────────────

    def step_write_env(self, base_url: str, output_path: str = ".env"):
        banner("STEP 4 – Write .env file")

        apps   = self.results["apps"]
        agents = self.results["agents"]

        def _a(key: str, sub: str = "agent_id") -> str:
            return agents.get(key, {}).get(sub, "")

        lines = [
            "# ─────────────────────────────────────────────────────",
            "# Auto-generated by setup_wso2_is.py",
            f"# Generated at: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "# ─────────────────────────────────────────────────────",
            "",
            "# App Settings",
            "APP_HOST=127.0.0.1",
            "APP_PORT=8000",
            "APP_CALLBACK_URL=http://localhost:8000/callback",
            "",
            "# WSO2 Identity Server",
            "ASGARDEO_ORG_NAME=carbon.super",
            f"ASGARDEO_BASE_URL={base_url}",
            f"ASGARDEO_TOKEN_URL={base_url}/oauth2/token",
            f"ASGARDEO_AUTHORIZE_URL={base_url}/oauth2/authorize",
            f"ASGARDEO_JWKS_URL={base_url}/oauth2/jwks",
            "",
            "# Orchestrator Application",
            f"ORCHESTRATOR_CLIENT_ID={apps.get('orchestrator', {}).get('client_id', '')}",
            f"ORCHESTRATOR_CLIENT_SECRET={apps.get('orchestrator', {}).get('client_secret', '')}",
            f"ORCHESTRATOR_AGENT_ID={_a('orchestrator_agent', 'agent_id')}",
            f"ORCHESTRATOR_AGENT_SECRET={_a('orchestrator_agent', 'agent_secret')}",
            "",
            "# Worker Agents",
            f"HR_AGENT_ID={_a('hr_agent', 'agent_id')}",
            f"HR_AGENT_SECRET={_a('hr_agent', 'agent_secret')}",
            "",
            f"IT_AGENT_ID={_a('it_agent', 'agent_id')}",
            f"IT_AGENT_SECRET={_a('it_agent', 'agent_secret')}",
            "",
            f"PAYROLL_AGENT_ID={_a('payroll_agent', 'agent_id')}",
            f"PAYROLL_AGENT_SECRET={_a('payroll_agent', 'agent_secret')}",
            "",
            f"BOOKING_AGENT_ID={_a('booking_agent', 'agent_id')}",
            f"BOOKING_AGENT_SECRET={_a('booking_agent', 'agent_secret')}",
            "",
            "# Token Exchanger Application",
            f"TOKEN_EXCHANGER_CLIENT_ID={apps.get('token_exchanger', {}).get('client_id', '')}",
            f"TOKEN_EXCHANGER_CLIENT_SECRET={apps.get('token_exchanger', {}).get('client_secret', '')}",
            "",
            "# MCP IT Server",
            f"MCP_IT_CLIENT_ID={apps.get('mcp_it', {}).get('client_id', '')}",
            f"MCP_IT_CLIENT_SECRET={apps.get('mcp_it', {}).get('client_secret', '')}",
            f"MCP_IT_AGENT_ID={_a('mcp_it_agent', 'agent_id')}",
            f"MCP_IT_AGENT_SECRET={_a('mcp_it_agent', 'agent_secret')}",
            "",
            "# API Audience",
            "API_AUDIENCE=onboarding-api",
            "",
            "# OpenAI",
            "OPENAI_API_KEY=",
            "",
            "# IT Admin Approval Gate",
            "IT_ADMIN_EMAIL=",
            "IT_APPROVAL_TIMEOUT=604800",
            "IT_SERVICE_BASE_URL=http://localhost:8002",
            "",
            "# Google Calendar (Booking Agent)",
            "GOOGLE_APPLICATION_CREDENTIALS=./google-service-account.json",
            "GOOGLE_CALENDAR_ID=",
            "",
            "# SMTP (optional)",
            "SMTP_HOST=",
            "SMTP_PORT=587",
            "SMTP_USER=",
            "SMTP_PASSWORD=",
        ]

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

        ok(f".env written to: {os.path.abspath(output_path)}")
        self.results["env"]["path"] = os.path.abspath(output_path)

    # ── Step 5 : Summary ──────────────────────────────────────────────────

    def print_summary(self):
        banner("SETUP COMPLETE – Summary")

        apps   = self.results["apps"]
        agents = self.results["agents"]

        def row(label: str, value: str):
            print(f"  {label:<38} {_c('cyan', value)}")

        print()
        print(_c("bold", "  Applications:"))
        row("onboarding-orchestrator client_id",  apps.get("orchestrator", {}).get("client_id", ""))
        row("onboarding-orchestrator secret",      apps.get("orchestrator", {}).get("client_secret", ""))
        row("token-exchanger client_id",           apps.get("token_exchanger", {}).get("client_id", ""))
        row("token-exchanger secret",              apps.get("token_exchanger", {}).get("client_secret", ""))
        row("mcp-it-server client_id",             apps.get("mcp_it", {}).get("client_id", ""))
        row("mcp-it-server secret",                apps.get("mcp_it", {}).get("client_secret", ""))

        print()
        print(_c("bold", "  Agents:"))
        for key, data in agents.items():
            row(f"{key} agent_id",     data.get("agent_id", "UNKNOWN"))
            row(f"{key} agent_secret", data.get("agent_secret", ""))

        print()
        print(_c("bold", "  API Resource:"))
        row("onboarding-api id",  self.results["api_resource"].get("id", ""))

        env_path = self.results.get("env", {}).get("path", ".env")
        print()
        print(f"  .env file written to: {_c('green', env_path)}")

        if any(not d.get("agent_id") for d in agents.values()):
            print()
            warn("Some agent IDs could not be retrieved automatically.")
            warn("Open the WSO2 IS console → User Management → Agents")
            warn("and copy each Agent ID into the .env file manually.")

        print()
        ok("All done! Review .env, fill in OPENAI_API_KEY, then run: python start_all_adk.ps1")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="WSO2 IS full setup for the A2A Reference Implementation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default="https://localhost:9443",
        help="WSO2 IS server base URL",
    )
    parser.add_argument(
        "--admin-user",
        default="admin",
        help="WSO2 IS admin username",
    )
    parser.add_argument(
        "--admin-password",
        default=None,
        help="WSO2 IS admin password (prompted if not provided)",
    )
    parser.add_argument(
        "--env-out",
        default=".env",
        help="Path for the generated .env file",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate connectivity and exit without creating resources",
    )
    parser.add_argument(
        "--skip-agents",
        action="store_true",
        help="Skip AI agent creation (manually create them later)",
    )
    return parser.parse_args()


def prompt_password(admin_user: str, base_url: str) -> str:
    import getpass
    return getpass.getpass(f"  WSO2 IS admin password for '{admin_user}' @ {base_url}: ")


def main():
    args = parse_args()

    banner("WSO2 IS Setup — A2A Reference Implementation")
    info(f"Target: {args.base_url}")
    info(f"Admin:  {args.admin_user}")
    info(f"Output: {args.env_out}")

    # Resolve password
    password = args.admin_password
    if not password:
        password = prompt_password(args.admin_user, args.base_url)

    client = WSO2ISClient(args.base_url, args.admin_user, password)

    # Connectivity check
    banner("Checking connectivity …")
    try:
        client.ping()
        ok(f"Connected to WSO2 IS at {args.base_url}")
    except RuntimeError as e:
        err(str(e))
        sys.exit(1)

    if args.dry_run:
        ok("Dry-run mode – no resources created")
        sys.exit(0)

    setup = A2ASetup(client)

    try:
        setup.step_api_resource()
        setup.step_applications()
        if not args.skip_agents:
            setup.step_agents()
        else:
            warn("Skipping agent creation (--skip-agents flag set)")
        setup.step_write_env(args.base_url, args.env_out)
        setup.print_summary()
    except RuntimeError as e:
        err("Setup failed:")
        print(_c("red", f"  {e}"))
        sys.exit(1)


if __name__ == "__main__":
    main()
