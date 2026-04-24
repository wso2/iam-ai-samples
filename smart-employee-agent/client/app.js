/*
 * Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.
 *
 *  Smart Employee Agent v2 — Client Application
 *
 *  Handles PKCE login with Asgardeo, chat with the agent server,
 *  role-aware HR dashboard via MCP REST endpoint, and OBO popup flow.
 *  No internal employee IDs — all identity from JWT tokens.
 */

const app = (function () {
  "use strict";

  // ─── State ──────────────────────────────────────────────────────────────────

  let config = {};          // Loaded from /config endpoint
  let accessToken = null;   // JWT stored in memory only
  let idToken = null;       // Stored for OIDC logout
  let userScopes = [];      // Parsed from token
  let userRole = "";        // Derived from scopes
  let userName = "";        // From token claims
  let pkceVerifier = null;
  let pkceState = null;
  let pendingMessage = null; // Message that triggered OBO

  // ─── DOM References ─────────────────────────────────────────────────────────

  const $ = (id) => document.getElementById(id);

  // ─── Initialization ─────────────────────────────────────────────────────────

  async function init() {
    try {
      const resp = await fetch("/config");
      config = await resp.json();
    } catch (e) {
      console.error("Failed to load config:", e);
      return;
    }

    // Listen for OBO success messages from popup
    window.addEventListener("message", handlePostMessage);

    // Check if this is a callback redirect
    const params = new URLSearchParams(window.location.search);
    if (params.has("code") && params.has("state")) {
      await handleCallback(params);
      return;
    }
  }

  // ─── PKCE Utilities ─────────────────────────────────────────────────────────

  function generateRandomString(length) {
    const chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~";
    const array = new Uint8Array(length);
    crypto.getRandomValues(array);
    return Array.from(array, (b) => chars[b % chars.length]).join("");
  }

  async function generateCodeChallenge(verifier) {
    const encoder = new TextEncoder();
    const data = encoder.encode(verifier);
    const digest = await crypto.subtle.digest("SHA-256", data);
    return btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
  }

  function decodeJwtPayload(token) {
    try {
      const base64 = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
      return JSON.parse(atob(base64));
    } catch {
      return {};
    }
  }

  // ─── Login Flow ─────────────────────────────────────────────────────────────

  async function initiateLogin() {
    pkceVerifier = generateRandomString(128);
    pkceState = generateRandomString(32);
    const codeChallenge = await generateCodeChallenge(pkceVerifier);

    sessionStorage.setItem("pkce_verifier", pkceVerifier);
    sessionStorage.setItem("pkce_state", pkceState);

    // HR-only scopes (no IT scopes)
    const scopes = [
      "openid", "profile",
      "agent_access",
      "hr_basic_rest", "hr_self_rest", "hr_read_rest", "hr_approve_rest",
    ].join(" ");

    const authUrl = new URL(`${config.asgardeoBaseUrl}/oauth2/authorize`);
    authUrl.searchParams.set("response_type", "code");
    authUrl.searchParams.set("client_id", config.clientId);
    authUrl.searchParams.set("redirect_uri", config.redirectUri);
    authUrl.searchParams.set("scope", scopes);
    authUrl.searchParams.set("code_challenge", codeChallenge);
    authUrl.searchParams.set("code_challenge_method", "S256");
    authUrl.searchParams.set("state", pkceState);

    window.location.href = authUrl.toString();
  }

  async function handleCallback(params) {
    const code = params.get("code");
    const state = params.get("state");

    const savedState = sessionStorage.getItem("pkce_state");
    if (state !== savedState) {
      console.error("State mismatch");
      showError("Authentication failed: state mismatch. Please try again.");
      window.history.replaceState({}, "", "/");
      return;
    }

    const savedVerifier = sessionStorage.getItem("pkce_verifier");
    if (!savedVerifier) {
      console.error("No PKCE verifier found");
      showError("Authentication failed: missing verifier. Please try again.");
      window.history.replaceState({}, "", "/");
      return;
    }

    try {
      const tokenResp = await fetch(`${config.asgardeoBaseUrl}/oauth2/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          grant_type: "authorization_code",
          client_id: config.clientId,
          code: code,
          code_verifier: savedVerifier,
          redirect_uri: config.redirectUri,
        }),
      });

      if (!tokenResp.ok) {
        const err = await tokenResp.text();
        throw new Error(`Token exchange failed: ${err}`);
      }

      const tokenData = await tokenResp.json();
      accessToken = tokenData.access_token;
      idToken = tokenData.id_token || null;

      sessionStorage.removeItem("pkce_verifier");
      sessionStorage.removeItem("pkce_state");

      // Parse token claims
      const claims = decodeJwtPayload(accessToken);
      const idClaims = idToken ? decodeJwtPayload(idToken) : {};
      userScopes = (claims.scope || tokenData.scope || "").split(" ").filter(Boolean);
      userName = [idClaims.given_name, idClaims.last_name].filter(Boolean).join(" ")
                 || idClaims.name || idClaims.preferred_username
                 || [claims.given_name, claims.last_name].filter(Boolean).join(" ")
                 || claims.name || claims.preferred_username || "User";
      userRole = deriveRole(userScopes);

      window.history.replaceState({}, "", "/");
      onAuthenticated();

    } catch (e) {
      console.error("Token exchange error:", e);
      showError("Authentication failed. Please try again.");
      window.history.replaceState({}, "", "/");
    }
  }

  function onAuthenticated() {
    $("login-overlay").classList.add("hidden");

    // Show role badge
    const badge = $("role-badge");
    badge.textContent = userRole;
    badge.className = "role-badge " + roleClass(userRole);
    badge.style.display = "inline-block";

    // Show user name
    const nameEl = $("user-name");
    nameEl.textContent = userName;
    nameEl.style.display = "inline-block";

    // Enable chat
    $("message-input").disabled = false;
    $("send-btn").disabled = false;
    $("message-input").focus();

    let capabilities = "";
    if (userRole === "HR Admin") {
      capabilities =
        "Based on your permissions, here's what I can help you with:\n" +
        "- **View** company holidays and leave policy\n" +
        "- **Check** your leave balance and request history\n" +
        "- **Apply** for leave (Annual, Sick, or Personal)\n" +
        "- **Review** all employee leave requests\n" +
        "- **Approve or reject** pending leave requests";
    } else {
      capabilities =
        "Based on your permissions, here's what I can help you with:\n" +
        "- **View** company holidays and leave policy\n" +
        "- **Check** your leave balance and request history\n" +
        "- **Apply** for leave (Annual, Sick, or Personal)";
    }

    addAgentMessage(
      `Hello ${userName}! I'm your Corporate Concierge. ` +
      `You're signed in as **${userRole}**.\n\n${capabilities}`
    );

    refreshDashboard();
  }

  // ─── Role Helpers ───────────────────────────────────────────────────────────

  function deriveRole(scopes) {
    if (scopes.includes("hr_approve_rest")) return "HR Admin";
    return "Employee";
  }

  function roleClass(role) {
    const map = {
      "Employee": "employee",
      "HR Admin": "hr-admin",
    };
    return map[role] || "employee";
  }

  // ─── Chat ───────────────────────────────────────────────────────────────────

  function handleChatSubmit(e) {
    e.preventDefault();
    const input = $("message-input");
    const text = input.value.trim();
    if (!text) return false;

    input.value = "";
    sendMessage(text);
    return false;
  }

  async function sendMessage(text) {
    addUserMessage(text);
    showTypingIndicator();
    disableChat();

    try {
      const resp = await fetch(`${config.agentServerUrl}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ message: text }),
      });

      hideTypingIndicator();

      if (resp.status === 401) {
        addErrorMessage("Your session has expired. Please sign in again.");
        signOut();
        return;
      }

      if (resp.status === 403) {
        addErrorMessage("You are not authorized to use this service.");
        return;
      }

      const data = await resp.json();

      if (data.type === "obo_required") {
        addAgentMessage(data.message);
        pendingMessage = text;
        showAuthorizeButton();
      } else if (data.type === "error") {
        addErrorMessage(data.message);
      } else {
        addAgentMessage(data.message);
        hideAuthorizeButton();
        if (data.refresh_dashboard) {
          refreshDashboard();
        }
      }
    } catch (e) {
      hideTypingIndicator();
      addErrorMessage("Failed to reach the agent server. Please check if it's running.");
      console.error("Chat error:", e);
    }

    enableChat();
  }

  // ─── Chat UI Helpers ────────────────────────────────────────────────────────

  function addUserMessage(text) {
    const div = document.createElement("div");
    div.className = "message user";
    div.textContent = text;
    $("chat-messages").appendChild(div);
    scrollChat();
  }

  function addAgentMessage(text) {
    const div = document.createElement("div");
    div.className = "message agent";
    div.innerHTML = DOMPurify.sanitize(marked.parse(text));
    $("chat-messages").appendChild(div);
    scrollChat();
  }

  function addErrorMessage(text) {
    const div = document.createElement("div");
    div.className = "message error";
    div.textContent = text;
    $("chat-messages").appendChild(div);
    scrollChat();
  }

  function showTypingIndicator() {
    const div = document.createElement("div");
    div.className = "typing-indicator";
    div.id = "typing-indicator";
    div.innerHTML = "<span></span><span></span><span></span>";
    $("chat-messages").appendChild(div);
    scrollChat();
  }

  function hideTypingIndicator() {
    const el = $("typing-indicator");
    if (el) el.remove();
  }

  function scrollChat() {
    const el = $("chat-messages");
    el.scrollTop = el.scrollHeight;
  }

  function disableChat() {
    $("message-input").disabled = true;
    $("send-btn").disabled = true;
  }

  function enableChat() {
    $("message-input").disabled = false;
    $("send-btn").disabled = false;
    $("message-input").focus();
  }

  function showAuthorizeButton() {
    $("authorize-section").classList.add("visible");
  }

  function hideAuthorizeButton() {
    $("authorize-section").classList.remove("visible");
    pendingMessage = null;
  }

  function showError(msg) {
    if (!accessToken) {
      const box = document.querySelector(".login-box");
      let errEl = document.querySelector(".login-error");
      if (!errEl) {
        errEl = document.createElement("p");
        errEl.className = "login-error";
        errEl.style.cssText = "color:#ef4444;margin-top:12px;font-size:0.85rem;";
        box.appendChild(errEl);
      }
      errEl.textContent = msg;
    } else {
      addErrorMessage(msg);
    }
  }

  // ─── OBO Flow ───────────────────────────────────────────────────────────────

  async function initiateOBOFlow() {
    try {
      const resp = await fetch(`${config.agentServerUrl}/api/obo/url`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!resp.ok) {
        addErrorMessage("Failed to initiate authorization. Please try again.");
        return;
      }

      const data = await resp.json();
      window.open(data.auth_url, "obo_popup", "width=500,height=600,scrollbars=yes");
    } catch (e) {
      console.error("OBO flow error:", e);
      addErrorMessage("Failed to initiate authorization.");
    }
  }

  function handlePostMessage(event) {
    if (!event.data || !event.data.type) return;

    if (event.data.type === "obo_success") {
      const msg = pendingMessage; // save before hideAuthorizeButton clears it
      hideAuthorizeButton();
      addAgentMessage("Authorization successful! Let me process your request now.");

      if (msg) {
        sendMessage(msg);
      }
    } else if (event.data.type === "obo_failed") {
      addErrorMessage(`Authorization failed: ${event.data.error || "Unknown error"}`);
    }
  }

  // ─── Dashboard ──────────────────────────────────────────────────────────────

  async function refreshDashboard() {
    const container = $("dashboard-content");
    container.innerHTML = '<p class="dashboard-loading">Loading dashboard...</p>';

    let html = "";

    try {
      if (userScopes.includes("hr_read_rest")) {
        html += await buildLeavesSection("All Leave Requests", true);
      } else if (userScopes.includes("hr_self_rest")) {
        html += await buildLeavesSection("My Leave Requests", false);
      }

      container.innerHTML = html || '<p class="dashboard-loading">No dashboard data available for your role.</p>';
    } catch (e) {
      console.error("Dashboard error:", e);
      container.innerHTML = '<p class="dashboard-loading">Failed to load dashboard data.</p>';
    }
  }

  async function buildLeavesSection(title, isAdmin) {
    try {
      const resp = await fetch(`${config.hrMcpRestUrl}/api/leaves`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });

      if (!resp.ok) {
        if (resp.status === 401 || resp.status === 403) {
          return `<div class="dashboard-section"><h3>${title}</h3><p class="dashboard-loading">Authorization required for leave data.</p></div>`;
        }
        return "";
      }

      const data = await resp.json();
      const leaves = data.leaves || [];

      let tableHtml = '<table class="dashboard-table"><thead><tr>';
      if (isAdmin) {
        // HR Admin: Employee, Type, Start, End, Days, Status
        tableHtml += "<th>Employee</th><th>Type</th><th>Start</th><th>End</th><th>Days</th><th>Status</th>";
      } else {
        // Employee: Type, Start, End, Days, Status, Reason
        tableHtml += "<th>Type</th><th>Start</th><th>End</th><th>Days</th><th>Status</th><th>Reason</th>";
      }
      tableHtml += "</tr></thead><tbody>";

      if (leaves.length === 0) {
        const cols = 6;
        tableHtml += `<tr class="empty-row"><td colspan="${cols}">No leave requests found.</td></tr>`;
      } else {
        for (const l of leaves) {
          const statusClass = (l.status || "").toLowerCase().replace(/\s+/g, "-");
          if (isAdmin) {
            tableHtml += `<tr>
              <td>${esc(l.employee || "")}</td>
              <td>${esc(l.type || l.leave_type || "")}</td>
              <td>${esc(l.start_date || "")}</td>
              <td>${esc(l.end_date || "")}</td>
              <td>${l.days_requested || ""}</td>
              <td><span class="status-badge ${statusClass}">${esc(l.status || "")}</span></td>
            </tr>`;
          } else {
            tableHtml += `<tr>
              <td>${esc(l.type || l.leave_type || "")}</td>
              <td>${esc(l.start_date || "")}</td>
              <td>${esc(l.end_date || "")}</td>
              <td>${l.days_requested || ""}</td>
              <td><span class="status-badge ${statusClass}">${esc(l.status || "")}</span></td>
              <td>${esc(l.reason || "")}</td>
            </tr>`;
          }
        }
      }

      tableHtml += "</tbody></table>";
      return `<div class="dashboard-section"><h3>${title}</h3>${tableHtml}</div>`;

    } catch (e) {
      console.error("Leaves fetch error:", e);
      return `<div class="dashboard-section"><h3>${title}</h3><p class="dashboard-loading">Failed to load leave data.</p></div>`;
    }
  }

  // ─── Reset ──────────────────────────────────────────────────────────────────

  async function resetDatabase() {
    if (!confirm("Reset all data to default state? This will clear all sessions and you will need to sign in again.")) return;

    try {
      const resp = await fetch(`${config.agentServerUrl}/api/reset`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
        },
      });
      const data = await resp.json();

      if (data.success) {
        addAgentMessage("Data has been reset. Please sign in again.");
        setTimeout(() => signOut(), 1500);
      } else {
        addErrorMessage(`Reset failed: ${data.error || "Unknown error"}`);
      }
    } catch (e) {
      addErrorMessage("Failed to reset data.");
    }
  }

  // ─── Sign Out ───────────────────────────────────────────────────────────────

  function signOut() {
    const savedIdToken = idToken;

    accessToken = null;
    idToken = null;
    userScopes = [];
    userRole = "";
    userName = "";
    pendingMessage = null;

    sessionStorage.clear();

    const logoutUrl = new URL(`${config.asgardeoBaseUrl}/oidc/logout`);
    logoutUrl.searchParams.set("post_logout_redirect_uri", config.redirectUri);
    if (savedIdToken) {
      logoutUrl.searchParams.set("id_token_hint", savedIdToken);
    }
    window.location.href = logoutUrl.toString();
  }

  // ─── Utilities ──────────────────────────────────────────────────────────────

  function esc(str) {
    if (str == null) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  }

  // ─── Boot ───────────────────────────────────────────────────────────────────

  init();

  return {
    initiateLogin,
    handleChatSubmit,
    initiateOBOFlow,
    signOut,
    resetDatabase,
  };
})();
