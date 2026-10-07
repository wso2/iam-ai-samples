/*
 * Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.
 *
 *  Employee Portal — Client Application
 *
 *  Sections:
 *    State + DOM helpers + utilities
 *    PKCE login & callback (Asgardeo)
 *    Tab router
 *    REST API client (talks to hr-server with the SPA token)
 *    Dashboard view (stat cards, holidays, leaves table, details drawer)
 *    Apply-leave form view
 *    Manage-requests view (pending queue, approve/reject)
 *    Assistant side panel (talks to agent server, OBO popup flow)
 *    Toast + modal + drawer utilities
 *    Sign-out + reset
 */

const app = (function () {
  "use strict";

  // ─── State ──────────────────────────────────────────────────────────────────

  let config = {};
  let accessToken = null;
  let idToken = null;
  let userScopes = [];
  let userRole = "";
  let userName = "";
  let userSub = "";
  let pkceVerifier = null;
  let pkceState = null;

  // Chat state
  let pendingMessage = null;

  // Dashboard state
  let leavePolicyCache = null;
  let leavesCache = [];
  let holidaysCache = [];
  let ticketsCache = [];
  let balanceCache = null;

  // UI state
  let activeTab = "dashboard";
  let assistantOpen = false;
  let pendingRejectId = null;

  // ─── DOM helpers ────────────────────────────────────────────────────────────

  const $ = (id) => document.getElementById(id);
  const esc = (str) => {
    if (str == null) return "";
    const div = document.createElement("div");
    div.textContent = String(str);
    return div.innerHTML;
  };

  // ─── Initialization ─────────────────────────────────────────────────────────

  async function init() {
    try {
      const resp = await fetch("/config");
      config = await resp.json();
    } catch (e) {
      console.error("Failed to load config:", e);
      return;
    }

    window.addEventListener("message", handlePostMessage);
    document.addEventListener("click", onDocumentClick);

    // Wire tab buttons
    document.querySelectorAll("#tabs .tab").forEach((btn) => {
      btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

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

    // Asgardeo grants the intersection of requested / app-authorized /
    // role-permitted, so asking for everything is safe — an employee simply
    // does not receive it_desk_access, and the desk tab stays hidden.
    const scopes = [
      "openid", "profile",
      "agent_access",
      "hr_basic_rest", "hr_self_rest", "hr_read_rest", "hr_approve_rest",
      "it_desk_access",
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
      showLoginError("Authentication failed: state mismatch. Please try again.");
      window.history.replaceState({}, "", "/");
      return;
    }

    const savedVerifier = sessionStorage.getItem("pkce_verifier");
    if (!savedVerifier) {
      console.error("No PKCE verifier found");
      showLoginError("Authentication failed: missing verifier. Please try again.");
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
          code,
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

      const claims = decodeJwtPayload(accessToken);
      const idClaims = idToken ? decodeJwtPayload(idToken) : {};
      userScopes = (claims.scope || tokenData.scope || "").split(" ").filter(Boolean);
      userSub = claims.sub || "";
      userName = [idClaims.given_name, idClaims.last_name].filter(Boolean).join(" ")
                 || idClaims.name || idClaims.preferred_username
                 || [claims.given_name, claims.last_name].filter(Boolean).join(" ")
                 || claims.name || claims.preferred_username || "User";
      userRole = deriveRole(userScopes);

      window.history.replaceState({}, "", "/");
      onAuthenticated();
    } catch (e) {
      console.error("Token exchange error:", e);
      showLoginError("Authentication failed. Please try again.");
      window.history.replaceState({}, "", "/");
    }
  }

  function showLoginError(msg) {
    const box = document.querySelector(".login-box");
    let errEl = document.querySelector(".login-error");
    if (!errEl) {
      errEl = document.createElement("p");
      errEl.className = "login-error";
      errEl.style.cssText = "color:#ef4444;margin-top:12px;font-size:0.85rem;";
      box.appendChild(errEl);
    }
    errEl.textContent = msg;
  }

  function onAuthenticated() {
    $("login-overlay").style.display = "none";
    $("app-shell").classList.add("visible");

    // Top bar
    $("user-name-label").textContent = userName;
    const badge = $("role-badge");
    badge.textContent = userRole;
    badge.className = "role-badge" + (userRole === "HR Admin" ? " admin" : "");

    // Hide tabs the user doesn't have scope for
    document.querySelectorAll("#tabs .tab[data-requires-scope]").forEach((tab) => {
      const req = tab.dataset.requiresScope;
      if (!userScopes.includes(req)) tab.hidden = true;
    });

    // Reveal the IT Tickets tab if the IT Agent is wired up (Pattern 4).
    probeItAgent();
    // Reveal the Google Calendar menu item if configured (Pattern 6).
    refreshGoogleStatus();
    // Reveal the IT Service Desk tab if this user may use it (Pattern 7).
    refreshDeskStatus();

    // Initial tab
    switchTab("dashboard");

    // Enable assistant input and greet
    $("message-input").disabled = false;
    $("send-btn").disabled = false;
    appendChatGreeting();
  }

  function deriveRole(scopes) {
    if (scopes.includes("hr_approve_rest")) return "HR Admin";
    return "Employee";
  }

  // ─── Tab Router ─────────────────────────────────────────────────────────────

  function switchTab(name) {
    activeTab = name;

    document.querySelectorAll("#tabs .tab").forEach((btn) => {
      const selected = btn.dataset.tab === name;
      btn.setAttribute("aria-selected", selected ? "true" : "false");
    });

    document.querySelectorAll(".tab-panel").forEach((p) => { p.hidden = true; });
    const panel = $(`tab-${name}`);
    if (panel) panel.hidden = false;

    if (name === "dashboard") refreshDashboard();
    else if (name === "apply") loadApplyTab();
    else if (name === "manage") refreshManageQueue();
    else if (name === "tickets") refreshTickets();
    else if (name === "desk") refreshDeskStatus();
  }

  // ─── IT tickets (Pattern 4) ────────────────────────────────────────────────

  // The agent server proxies this to the IT Agent using its own agent token —
  // the browser's user token never leaves the HR agent.
  async function fetchTickets() {
    const resp = await fetch(`${config.agentServerUrl}/api/it/tickets`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const text = await resp.text();
    let data = null;
    if (text) { try { data = JSON.parse(text); } catch {} }
    return { status: resp.status, ok: resp.ok, data };
  }

  // Reveal the tab only when the IT Agent is actually wired up: the endpoint
  // answers 404 when IT_AGENT_ENABLED is false, so no extra client config.
  async function probeItAgent() {
    try {
      const { status } = await fetchTickets();
      if (status === 404) return;
      const btn = $("tab-btn-tickets");
      if (btn) btn.hidden = false;
    } catch {
      /* agent server down — leave the tab hidden */
    }
  }

  async function refreshTickets() {
    renderTickets(null);
    try {
      const { ok, status, data } = await fetchTickets();
      if (!ok) {
        const msg = data?.message || `HTTP ${status}`;
        renderTickets([], msg);
        return;
      }
      ticketsCache = data?.tickets || [];
      renderTickets(ticketsCache);
    } catch (e) {
      renderTickets([], e.message);
    }
  }

  async function silentRefreshTickets() {
    try {
      const { ok, data } = await fetchTickets();
      if (!ok) return;
      ticketsCache = data?.tickets || [];
      renderTickets(ticketsCache);
    } catch { /* leave the current view in place */ }
  }

  function renderTickets(tickets, errorMsg) {
    const container = $("tickets-container");
    if (!container) return;
    if (tickets == null) { container.innerHTML = `<p class="muted">Loading…</p>`; return; }

    if (errorMsg) {
      container.innerHTML = `<p class="muted">Could not load IT tickets: ${esc(errorMsg)}</p>`;
      return;
    }

    let html = `<table class="dashboard-table"><thead><tr>
      <th>Ref</th><th>Subject</th><th>Category</th><th>Status</th>
      <th>Requested for</th><th>Filed by</th>
    </tr></thead><tbody>`;

    if (tickets.length === 0) {
      html += `<tr class="empty-row"><td colspan="6">No IT tickets yet. Ask the assistant to raise one.</td></tr>`;
    } else {
      for (const t of tickets) {
        const statusClass = (t.status || "").toLowerCase().replace(/\s+/g, "-");
        html += `<tr>
          <td>${esc(t.ticket_id)}</td>
          <td>${esc(t.subject)}</td>
          <td>${esc(t.category)}</td>
          <td><span class="status-badge ${statusClass}">${esc(t.status)}</span></td>
          <td>${esc(t.requested_for)}</td>
          <td class="muted">${esc(t.created_by)}</td>
        </tr>`;
      }
    }
    html += `</tbody></table>`;
    container.innerHTML = html;
  }

  // ─── REST API client ────────────────────────────────────────────────────────

  async function api(path, opts = {}) {
    const headers = Object.assign(
      { Authorization: `Bearer ${accessToken}` },
      opts.body ? { "Content-Type": "application/json" } : {},
      opts.headers || {},
    );
    const resp = await fetch(`${config.hrServerUrl}${path}`, {
      method: opts.method || "GET",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });

    let data = null;
    const text = await resp.text();
    if (text) {
      try { data = JSON.parse(text); }
      catch { data = { error: "invalid_response", message: text }; }
    }

    if (!resp.ok) {
      const err = new Error(data?.message || `HTTP ${resp.status}`);
      err.status = resp.status;
      err.payload = data;
      throw err;
    }
    return data;
  }

  // ─── Dashboard view ─────────────────────────────────────────────────────────

  async function refreshDashboard() {
    renderHolidays(null); // loading state
    renderLeavesTable(null);

    const isAdmin = userScopes.includes("hr_read_rest");

    // Stat cards: balance for employees, pending count for admins.
    if (!isAdmin && userScopes.includes("hr_self_rest")) {
      try {
        balanceCache = await api("/api/leave-balance");
        renderBalanceCards(balanceCache);
      } catch (e) {
        renderBalanceCards(null);
      }
    } else if (isAdmin) {
      // Admins see "pending requests" card; computed from leaves below.
      renderBalanceCards("admin-placeholder");
    }

    // Holidays
    try {
      const data = await api("/api/holidays");
      holidaysCache = data.holidays || [];
      renderHolidays(holidaysCache);
    } catch (e) {
      renderHolidays([]);
      console.error("Holidays load failed:", e);
    }

    // Leaves
    try {
      const data = await api("/api/leaves");
      leavesCache = data.leaves || [];
      renderLeavesTable(leavesCache);
      if (isAdmin) renderBalanceCards("admin-stats");
      updatePendingBadge();
    } catch (e) {
      renderLeavesTable([]);
      console.error("Leaves load failed:", e);
    }
  }

  async function silentRefreshDashboard() {
    const isAdmin = userScopes.includes("hr_read_rest");

    if (!isAdmin && userScopes.includes("hr_self_rest")) {
      try { balanceCache = await api("/api/leave-balance"); } catch {}
    }

    try {
      const data = await api("/api/holidays");
      holidaysCache = data.holidays || [];
    } catch {}

    try {
      const data = await api("/api/leaves");
      leavesCache = data.leaves || [];
    } catch {}

    renderBalanceCards(isAdmin ? "admin-stats" : balanceCache);
    renderHolidays(holidaysCache);
    renderLeavesTable(leavesCache);
    updatePendingBadge();
  }

  function renderBalanceCards(state) {
    const container = $("balance-cards");
    if (!container) return;

    if (state == null) { container.innerHTML = ""; return; }

    const isAdmin = userScopes.includes("hr_read_rest");

    if (isAdmin) {
      const pending  = leavesCache.filter((l) => l.status === "Pending").length;
      const approved = leavesCache.filter((l) => l.status === "Approved").length;
      const rejected = leavesCache.filter((l) => l.status === "Rejected").length;
      container.innerHTML = `
        ${statCard("Pending", pending, "requests")}
        ${statCard("Approved", approved, "requests")}
        ${statCard("Rejected", rejected, "requests")}
      `;
      return;
    }

    if (state && state.balance) {
      const b = state.balance;
      container.innerHTML = `
        ${statCard("Annual Leave", b.annual, "days")}
        ${statCard("Sick Leave", b.sick, "days")}
        ${statCard("Personal Leave", b.personal, "days")}
      `;
    } else {
      container.innerHTML = "";
    }
  }

  function statCard(label, value, unit) {
    return `
      <div class="stat-card">
        <div class="label">${esc(label)}</div>
        <div class="value">${esc(value)}<span class="unit"> ${esc(unit)}</span></div>
      </div>`;
  }

  function renderHolidays(list) {
    const container = $("holidays-list");
    if (!container) return;
    if (list == null) { container.innerHTML = `<p class="muted">Loading…</p>`; return; }

    if (list.length === 0) {
      container.innerHTML = `<p class="muted">No upcoming holidays.</p>`;
      return;
    }

    const today = new Date().toISOString().slice(0, 10);
    const upcoming = list
      .filter((h) => h.date >= today)
      .sort((a, b) => a.date.localeCompare(b.date))
      .slice(0, 8);

    container.innerHTML = (upcoming.length ? upcoming : list)
      .map((h) => `
        <div class="holiday-chip">
          <span class="date">${esc(formatDate(h.date))}</span>
          <span class="name">${esc(h.name)}</span>
        </div>`).join("");
  }

  function renderLeavesTable(leaves) {
    const container = $("leaves-table-container");
    if (!container) return;
    if (leaves == null) { container.innerHTML = `<p class="muted">Loading…</p>`; return; }

    const isAdmin = userScopes.includes("hr_read_rest");
    $("leaves-heading").textContent = isAdmin ? "All Leave Requests" : "My Leave Requests";
    if (isAdmin) $("leaves-search").hidden = false;

    const statusFilter = $("leaves-status-filter").value;
    const search = ($("leaves-search").value || "").trim().toLowerCase();

    let rows = leaves.slice();
    if (statusFilter) rows = rows.filter((l) => l.status === statusFilter);
    if (isAdmin && search) rows = rows.filter((l) => (l.employee || "").toLowerCase().includes(search));

    let html = `<table class="dashboard-table"><thead><tr>`;
    // Ref is shown so the user can quote it back to the assistant
    // ("get LR001 approved") — it was previously only in a fading toast.
    if (isAdmin) {
      html += `<th>Ref</th><th>Employee</th><th>Type</th><th>Start</th><th>End</th><th>Days</th><th>Status</th>`;
    } else {
      html += `<th>Ref</th><th>Type</th><th>Start</th><th>End</th><th>Days</th><th>Status</th>`;
    }
    html += `</tr></thead><tbody>`;

    if (rows.length === 0) {
      const cols = isAdmin ? 7 : 6;
      html += `<tr class="empty-row"><td colspan="${cols}">No leave requests match your filters.</td></tr>`;
    } else {
      for (const l of rows) {
        const statusClass = (l.status || "").toLowerCase();
        const reqId = l.request_id || "";
        const cells = isAdmin
          ? `<td>${esc(reqId)}</td>
             <td>${esc(l.employee)}</td>
             <td>${esc(l.type || l.leave_type)}</td>
             <td>${esc(l.start_date)}</td>
             <td>${esc(l.end_date)}</td>
             <td>${esc(l.days_requested)}</td>
             <td><span class="status-badge ${statusClass}">${esc(l.status)}</span></td>`
          : `<td>${esc(reqId)}</td>
             <td>${esc(l.type || l.leave_type)}</td>
             <td>${esc(l.start_date)}</td>
             <td>${esc(l.end_date)}</td>
             <td>${esc(l.days_requested)}</td>
             <td><span class="status-badge ${statusClass}">${esc(l.status)}</span></td>`;
        html += `<tr class="clickable" data-request-id="${esc(reqId)}">${cells}</tr>`;
      }
    }
    html += `</tbody></table>`;
    container.innerHTML = html;

    container.querySelectorAll("tr.clickable").forEach((row) => {
      row.addEventListener("click", () => openDetails(row.dataset.requestId));
    });
  }

  function onLeaveFilterChange() {
    renderLeavesTable(leavesCache);
  }

  function updatePendingBadge() {
    const badge = $("pending-badge");
    if (!badge) return;
    if (!userScopes.includes("hr_approve_rest")) { badge.hidden = true; return; }
    const count = leavesCache.filter((l) => l.status === "Pending").length;
    if (count > 0) {
      badge.hidden = false;
      badge.textContent = count;
    } else {
      badge.hidden = true;
    }
  }

  // ─── Apply-leave view ───────────────────────────────────────────────────────

  async function loadApplyTab() {
    if (!leavePolicyCache) {
      try {
        const data = await api("/api/leave-policy");
        leavePolicyCache = data.leave_types || [];
      } catch (e) {
        // A toast alone fades in 4s and leaves an empty dropdown behind, which
        // reads as "the app is broken" rather than "this call failed".
        const why = e.status === 403
          ? "your account is missing the 'hr_basic_rest' permission"
          : e.message;
        toast("error", "Couldn't load leave policy", why);
        showLeaveTypeError(why);
        return;
      }
    }
    if (leavePolicyCache.length === 0) {
      showLeaveTypeError("the server returned no leave types");
      return;
    }
    populateLeaveTypes();
    populateApplySummary();
  }

  // Make a failed policy load visible in the form itself, not just in a toast.
  function showLeaveTypeError(why) {
    const sel = $("leave-type");
    if (sel) {
      sel.innerHTML = `<option value="">Unavailable — ${esc(why)}</option>`;
      sel.disabled = true;
    }
  }

  function populateLeaveTypes() {
    const sel = $("leave-type");
    sel.disabled = false;
    sel.innerHTML = `<option value="">Select…</option>` +
      leavePolicyCache.map((p) => `<option value="${esc(p.leave_type)}">${esc(p.leave_type)}</option>`).join("");
    sel.onchange = populateApplySummary;
    ["start-date", "end-date", "reason"].forEach((id) => {
      $(id).addEventListener("input", populateApplySummary);
    });
  }

  function populateApplySummary() {
    const summary = $("apply-summary");
    const type = $("leave-type").value;
    const start = $("start-date").value;
    const end = $("end-date").value;

    if (!type) { summary.hidden = true; $("leave-type-hint").textContent = ""; return; }

    const policy = leavePolicyCache.find((p) => p.leave_type === type);
    if (policy) {
      $("leave-type-hint").textContent =
        `${policy.description} · Max ${policy.max_days_per_year} days/year · ` +
        `Min notice ${policy.min_notice_days} day(s).`;
    }

    if (!start || !end) { summary.hidden = true; return; }

    const startDate = new Date(start);
    const endDate = new Date(end);
    const today = new Date(new Date().toISOString().slice(0, 10));
    const days = Math.floor((endDate - startDate) / (1000 * 60 * 60 * 24)) + 1;
    const noticeDays = Math.floor((startDate - today) / (1000 * 60 * 60 * 24));

    let warnings = [];
    if (days <= 0) warnings.push("End date must be on or after start date.");
    if (policy && noticeDays < policy.min_notice_days) {
      warnings.push(`${type} requires at least ${policy.min_notice_days} day(s) notice; this request is ${noticeDays} day(s) away.`);
    }
    if (balanceCache && policy) {
      const key = type.split(" ")[0].toLowerCase();
      const remaining = balanceCache.balance?.[key];
      if (remaining != null && days > remaining) {
        warnings.push(`Only ${remaining} ${type} day(s) remaining.`);
      }
    }

    summary.hidden = false;
    summary.innerHTML = `
      <div><strong>${esc(days)}</strong> day(s) of <strong>${esc(type)}</strong>
        from <strong>${esc(formatDate(start))}</strong> to <strong>${esc(formatDate(end))}</strong>.</div>
      ${warnings.length ? `<div style="color:#92400e;margin-top:0.4rem;">⚠ ${warnings.map(esc).join("<br>")}</div>` : ""}
    `;
  }

  function resetApplyForm() {
    $("apply-form").reset();
    $("apply-summary").hidden = true;
    $("leave-type-hint").textContent = "";
  }

  async function submitApplyLeave(e) {
    e.preventDefault();
    const btn = $("apply-submit");
    const body = {
      leave_type: $("leave-type").value,
      start_date: $("start-date").value,
      end_date: $("end-date").value,
      reason: $("reason").value.trim(),
    };

    btn.disabled = true;
    btn.classList.add("loading");
    try {
      const result = await api("/api/leaves", { method: "POST", body });
      toast("success", "Leave request submitted", `Reference ${result.request_id}`);
      resetApplyForm();
      // Refresh balance cache so dashboard reflects post-application state.
      balanceCache = null;
      switchTab("dashboard");
    } catch (e) {
      const msg = e.payload?.message || e.message;
      toast("error", "Could not submit request", msg);
    } finally {
      btn.disabled = false;
      btn.classList.remove("loading");
    }
    return false;
  }

  // ─── Manage-requests view (HR Admin) ────────────────────────────────────────

  async function refreshManageQueue() {
    const container = $("manage-queue-container");
    container.innerHTML = `<p class="muted">Loading…</p>`;

    try {
      const data = await api("/api/leaves?status=Pending");
      const pending = (data.leaves || []).filter((l) => l.status === "Pending");

      if (pending.length === 0) {
        container.innerHTML = `<p class="muted">No pending requests. 🎉</p>`;
        return;
      }

      container.innerHTML = pending.map((l) => `
        <div class="queue-item" data-request-id="${esc(l.request_id || "")}">
          <div>
            <div class="who">${esc(l.employee)}</div>
            <div class="meta">${esc(l.type || l.leave_type)} ·
              ${esc(formatDate(l.start_date))} → ${esc(formatDate(l.end_date))} ·
              ${esc(l.days_requested)} day(s)</div>
            ${l.reason ? `<div class="reason">${esc(l.reason)}</div>` : ""}
          </div>
          <div class="actions">
            <button class="btn-success btn-small" data-action="approve">✓ Approve</button>
            <button class="btn-danger btn-small" data-action="reject">✗ Reject</button>
            <button class="btn-ghost btn-small" data-action="details">Details</button>
          </div>
        </div>
      `).join("");

      container.querySelectorAll(".queue-item").forEach((row) => {
        const id = row.dataset.requestId;
        row.querySelector('[data-action="approve"]').addEventListener("click", () => onApprove(id, row));
        row.querySelector('[data-action="reject"]').addEventListener("click", () => openRejectModal(id, row));
        row.querySelector('[data-action="details"]').addEventListener("click", () => openDetails(id));
      });

      leavesCache = data.leaves || leavesCache;
      updatePendingBadge();
    } catch (e) {
      container.innerHTML = `<p class="muted">Failed to load queue: ${esc(e.message)}</p>`;
    }
  }

  async function silentRefreshManageQueue() {
    try {
      const data = await api("/api/leaves?status=Pending");
      const pending = (data.leaves || []).filter((l) => l.status === "Pending");
      const container = $("manage-queue-container");

      if (pending.length === 0) {
        container.innerHTML = `<p class="muted">No pending requests. 🎉</p>`;
      } else {
        container.innerHTML = pending.map((l) => `
          <div class="queue-item" data-request-id="${esc(l.request_id || "")}">
            <div>
              <div class="who">${esc(l.employee)}</div>
              <div class="meta">${esc(l.type || l.leave_type)} ·
                ${esc(formatDate(l.start_date))} → ${esc(formatDate(l.end_date))} ·
                ${esc(l.days_requested)} day(s)</div>
              ${l.reason ? `<div class="reason">${esc(l.reason)}</div>` : ""}
            </div>
            <div class="actions">
              <button class="btn-success btn-small" data-action="approve">✓ Approve</button>
              <button class="btn-danger btn-small" data-action="reject">✗ Reject</button>
              <button class="btn-ghost btn-small" data-action="details">Details</button>
            </div>
          </div>
        `).join("");

        container.querySelectorAll(".queue-item").forEach((row) => {
          const id = row.dataset.requestId;
          row.querySelector('[data-action="approve"]').addEventListener("click", () => onApprove(id, row));
          row.querySelector('[data-action="reject"]').addEventListener("click", () => openRejectModal(id, row));
          row.querySelector('[data-action="details"]').addEventListener("click", () => openDetails(id));
        });
      }

      leavesCache = data.leaves || leavesCache;
      updatePendingBadge();
    } catch {}
  }

  async function onApprove(requestId, row) {
    const btn = row.querySelector('[data-action="approve"]');
    btn.disabled = true;
    btn.classList.add("loading");
    try {
      const result = await api(`/api/leaves/${encodeURIComponent(requestId)}/approve`, { method: "POST" });
      toast("success", "Request approved", `${result.employee} · ${requestId}`);
      row.style.transition = "opacity 0.25s";
      row.style.opacity = "0";
      setTimeout(() => refreshManageQueue(), 250);
      // Refresh dashboard stats next time it's opened.
      leavesCache = leavesCache.map((l) =>
        (l.request_id === requestId) ? { ...l, status: "Approved" } : l);
      updatePendingBadge();
    } catch (e) {
      const msg = e.payload?.message || e.message;
      toast("error", "Approve failed", msg);
      btn.disabled = false;
      btn.classList.remove("loading");
    }
  }

  function openRejectModal(requestId, row) {
    pendingRejectId = requestId;
    const employee = row.querySelector(".who")?.textContent || requestId;
    $("reject-modal-subject").textContent = `${employee} · ${requestId}`;
    $("reject-reason").value = "";
    $("reject-modal").hidden = false;
    setTimeout(() => $("reject-reason").focus(), 50);
  }

  function closeRejectModal() {
    $("reject-modal").hidden = true;
    pendingRejectId = null;
  }

  async function confirmReject() {
    if (!pendingRejectId) return;
    const reason = $("reject-reason").value.trim();
    if (!reason) {
      toast("warning", "Reason required", "Please give a reason for the rejection.");
      return;
    }
    const requestId = pendingRejectId;
    const btn = $("reject-confirm-btn");
    btn.disabled = true;
    btn.classList.add("loading");
    try {
      const result = await api(`/api/leaves/${encodeURIComponent(requestId)}/reject`,
        { method: "POST", body: { reason } });
      toast("success", "Request rejected", `${result.employee} · ${requestId}`);
      closeRejectModal();
      refreshManageQueue();
      leavesCache = leavesCache.map((l) =>
        (l.request_id === requestId) ? { ...l, status: "Rejected" } : l);
      updatePendingBadge();
    } catch (e) {
      const msg = e.payload?.message || e.message;
      toast("error", "Reject failed", msg);
    } finally {
      btn.disabled = false;
      btn.classList.remove("loading");
    }
  }

  // ─── Details drawer ─────────────────────────────────────────────────────────

  async function openDetails(requestId) {
    if (!requestId) return;
    const drawer = $("details-drawer");
    const body = $("details-body");
    body.innerHTML = `<p class="muted">Loading…</p>`;
    drawer.hidden = false;

    try {
      const d = await api(`/api/leaves/${encodeURIComponent(requestId)}`);
      $("details-title").textContent = `Leave request ${requestId}`;
      const statusClass = (d.status || "").toLowerCase();
      body.innerHTML = `
        ${detailRow("Employee", d.employee)}
        ${detailRow("Type", d.type)}
        ${detailRow("Start", formatDate(d.start_date))}
        ${detailRow("End", formatDate(d.end_date))}
        ${detailRow("Days", d.days_requested)}
        ${detailRow("Status", `<span class="status-badge ${statusClass}">${esc(d.status)}</span>`)}
        ${detailRow("Reason", d.reason || "—")}
        ${d.reviewed_by_name ? detailRow("Reviewed by", d.reviewed_by_name) : ""}
        ${d.reviewed_via ? detailRow("Approval route", `<span class="muted">${esc(d.reviewed_via)}</span>`) : ""}
        ${d.leave_balance ? `
          <h4 style="margin-top:1.25rem;font-size:0.85rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:0.05em;">
            Current balance
          </h4>
          ${detailRow("Annual", d.leave_balance.annual)}
          ${detailRow("Sick", d.leave_balance.sick)}
          ${detailRow("Personal", d.leave_balance.personal)}
        ` : ""}
      `;
    } catch (e) {
      body.innerHTML = `<p class="muted">Failed to load details: ${esc(e.message)}</p>`;
    }
  }

  function closeDetails() { $("details-drawer").hidden = true; }
  function detailRow(label, value) {
    return `<div class="detail-row"><div class="label">${esc(label)}</div><div>${value ?? ""}</div></div>`;
  }

  // ─── Assistant panel ────────────────────────────────────────────────────

  function toggleAssistant() {
    assistantOpen = !assistantOpen;
    const panel = $("assistant-panel");
    const toggle = $("assistant-toggle");
    const shell = $("app-shell");

    panel.hidden = !assistantOpen;
    toggle.classList.toggle("active", assistantOpen);
    shell.classList.toggle("panel-open", assistantOpen);

    if (assistantOpen) {
      setTimeout(() => $("message-input").focus(), 50);
    }
  }

  // ─── Chat view ──────────────────────────────────────────────────────────────

  function appendChatGreeting() {
    const capabilities = (userRole === "HR Admin")
      ? "Based on your permissions, here's what I can help you with:\n" +
        "- **View** company holidays and leave policy\n" +
        "- **Check** your leave balance and request history\n" +
        "- **Apply** for leave (Annual, Sick, or Personal)\n" +
        "- **Review** all employee leave requests\n" +
        "- **Approve or reject** pending leave requests"
      : "Based on your permissions, here's what I can help you with:\n" +
        "- **View** company holidays and leave policy\n" +
        "- **Check** your leave balance and request history\n" +
        "- **Apply** for leave (Annual, Sick, or Personal)";

    addAgentMessage(
      `Hello ${userName}! I'm your HR Assistant. ` +
      `You're signed in as **${userRole}**.\n\n${capabilities}\n\n` +
      `_Any actions I take will be reflected live in the main view._`
    );
  }

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
    setChatEnabled(false);

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

      if (resp.status === 401) { addErrorMessage("Your session has expired. Please sign in again."); signOut(); return; }
      if (resp.status === 403) { addErrorMessage("You are not authorized to use this service."); return; }

      const data = await resp.json();
      if (data.type === "google_required") {
        // The agent holds Asgardeo authority but no Google grant. A different
        // provider, a different consent — so a different button.
        addAgentMessage(data.message);
        pendingCalendarMessage = text;
        $("google-connect-section").hidden = false;
      } else if (data.type === "obo_required") {
        addAgentMessage(data.message);
        pendingMessage = text;
        showAuthorizeButton();
      } else if (data.type === "error") {
        addErrorMessage(data.message);
      } else {
        addAgentMessage(data.message);
        hideAuthorizeButton();
        if (data.refresh_dashboard) {
          balanceCache = null;
          silentRefreshDashboard();
          if (activeTab === "manage") silentRefreshManageQueue();
          if (activeTab === "tickets") silentRefreshTickets();
        }
      }
    } catch (e) {
      hideTypingIndicator();
      addErrorMessage("Failed to reach the agent server. Please check if it's running.");
      console.error("Chat error:", e);
    }

    setChatEnabled(true);
  }

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

  function setChatEnabled(enabled) {
    $("message-input").disabled = !enabled;
    $("send-btn").disabled = !enabled;
    if (enabled) $("message-input").focus();
  }

  function showAuthorizeButton() { $("authorize-section").hidden = false; }
  function hideAuthorizeButton() { $("authorize-section").hidden = true; pendingMessage = null; }

  // ─── OBO Flow ───────────────────────────────────────────────────────────────

  async function initiateOBOFlow() {
    try {
      const resp = await fetch(`${config.agentServerUrl}/api/obo/url`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!resp.ok) {
        toast("error", "Authorization failed", "Could not start the authorization flow.");
        return;
      }
      const data = await resp.json();
      window.open(data.auth_url, "obo_popup", "width=500,height=600,scrollbars=yes");
    } catch (e) {
      console.error("OBO flow error:", e);
      toast("error", "Authorization failed", e.message);
    }
  }

  // Origin of the agent server, which serves the OBO popup page. Returns null if
  // the configured URL is missing or unparseable, so the check below fails closed.
  // Origin of the IT agent, which serves the service-desk consent popup.
  function itAgentOrigin() {
    try {
      return new URL(config.itAgentUrl).origin;
    } catch {
      return null;
    }
  }

  function agentOrigin() {
    try { return new URL(config.agentServerUrl, window.location.origin).origin; }
    catch { return null; }
  }

  function handlePostMessage(event) {
    // Only a popup served by one of our own agent servers may drive these flows;
    // any other window holding a handle to ours could otherwise fake a result.
    // The IT desk consent popup is served by the IT Agent, on its own origin.
    const allowed = [agentOrigin(), itAgentOrigin()].filter(Boolean);
    if (!allowed.includes(event.origin)) return;
    if (!event.data || !event.data.type) return;

    if (event.data.type === "it_obo_success") {
      $("desk-authorize-section").hidden = true;
      addDeskMessage("agent", "Authorization successful. I can now act with your permissions.");
      refreshDeskStatus();
      const queued = deskPending;
      deskPending = null;
      if (queued) sendDeskMessage(queued);
      return;
    }
    if (event.data.type === "it_obo_failed") {
      addDeskMessage("error", `Authorization failed: ${event.data.error || "Unknown error"}`);
      return;
    }

    if (event.data.type === "obo_success") {
      // The Google popup posts the same message; refresh its state either way.
      refreshGoogleStatus();
      if (pendingCalendarMessage) {
        const queued = pendingCalendarMessage;
        pendingCalendarMessage = null;
        $("google-connect-section").hidden = true;
        addAgentMessage("Google Calendar connected. Adding it now\u2026");
        sendMessage(queued);
        return;
      }
      const msg = pendingMessage;
      hideAuthorizeButton();
      addAgentMessage("Authorization successful! Let me process your request now.");
      if (msg) sendMessage(msg);
    } else if (event.data.type === "obo_failed") {
      addErrorMessage(`Authorization failed: ${event.data.error || "Unknown error"}`);
    }
  }

  // The in-chat calendar prompt needs somewhere to queue the request while
  // the user completes Google consent.
  let pendingCalendarMessage = null;

  // Reached from the chat's connect prompt rather than the user menu, so the
  // queued request can run itself once the grant comes back.
  async function connectGoogleFromChat() {
    $("google-connect-section").hidden = true;
    await toggleGoogleCalendar();
  }

  // ─── Google Calendar (Pattern 6) ───────────────────────────────────────────

  // A SECOND consent, to Google — separate from the Asgardeo authorization.
  // The menu item stays hidden unless the agent has Google configured.
  let googleConnected = false;

  async function refreshGoogleStatus() {
    try {
      const resp = await fetch(`${config.agentServerUrl}/api/google/status`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!resp.ok) return;
      const data = await resp.json();
      const item = $("google-menu-item");
      if (!item) return;
      item.hidden = !data.enabled;
      googleConnected = !!data.connected;
      item.textContent = googleConnected
        ? "Disconnect Google Calendar"
        : "Connect Google Calendar";
    } catch { /* agent down — leave the item hidden */ }
  }

  async function toggleGoogleCalendar() {
    $("user-menu-popover").hidden = true;
    if (googleConnected) {
      try {
        await fetch(`${config.agentServerUrl}/api/google/disconnect`, {
          method: "POST",
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        toast("success", "Google Calendar disconnected",
              "Revoke access fully at myaccount.google.com/permissions.");
      } catch (e) {
        toast("error", "Could not disconnect", e.message);
      }
      refreshGoogleStatus();
      return;
    }

    try {
      const resp = await fetch(`${config.agentServerUrl}/api/google/url`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!resp.ok) {
        toast("error", "Google Calendar unavailable", "The agent has no Google configuration.");
        return;
      }
      const { auth_url } = await resp.json();
      // Same popup shape as the OBO flow; the callback posts back to us.
      window.open(auth_url, "google_popup", "width=520,height=640,scrollbars=yes");
    } catch (e) {
      toast("error", "Could not start Google authorization", e.message);
    }
  }

  // ─── IT Service Desk (Pattern 7) ───────────────────────────────────────────

  // The browser calls the IT Agent DIRECTLY here — the HR agent is not in the
  // path. The IT Agent then exchanges the user's consent for a delegated token
  // and acts with their permissions, so the IT server authorizes the person,
  // not the agent.

  let deskAuthorized = false;
  let deskPending = null;

  async function deskFetch(path, opts = {}) {
    return fetch(`${config.itAgentUrl}${path}`, {
      ...opts,
      headers: {
        Authorization: `Bearer ${accessToken}`,
        ...(opts.body ? { "Content-Type": "application/json" } : {}),
        ...(opts.headers || {}),
      },
    });
  }

  // The tab reveals itself only for users the IT Agent will actually serve:
  // a 403 here means the role lacks the desk scope, which is an authorization
  // answer, not an error to show.
  async function refreshDeskStatus() {
    try {
      const resp = await deskFetch("/api/desk/status");
      const btn = $("tab-btn-desk");
      if (!resp.ok) {
        if (btn) btn.hidden = true;
        return;
      }
      const data = await resp.json();
      if (btn) btn.hidden = false;
      deskAuthorized = !!data.authorized;

      const badge = $("desk-origin-badge");
      if (badge) {
        badge.hidden = false;
        badge.textContent = data.from_partner_org
          ? `Signed in via ${data.home_org} (partner org)`
          : `Signed in via ${data.home_org} org`;
        badge.className = "origin-badge" + (data.from_partner_org ? " partner" : "");
      }
      $("desk-authorize-section").hidden = deskAuthorized;
    } catch {
      /* IT agent unreachable — leave the tab hidden */
    }
  }

  function handleDeskSubmit(e) {
    e.preventDefault();
    const input = $("desk-input");
    const text = input.value.trim();
    if (!text) return false;
    input.value = "";
    sendDeskMessage(text);
    return false;
  }

  async function sendDeskMessage(text) {
    addDeskMessage("user", text);
    try {
      const resp = await deskFetch("/api/desk/chat", {
        method: "POST",
        body: JSON.stringify({ message: text }),
      });
      const data = await resp.json().catch(() => ({}));

      if (resp.status === 401) { signOut(); return; }
      if (resp.status === 403) {
        addDeskMessage("error", data.message || "You are not permitted to use the service desk.");
        return;
      }
      if (data.type === "obo_required") {
        // Queue the message so it runs itself once consent comes back.
        deskPending = text;
        $("desk-authorize-section").hidden = false;
        addDeskMessage("agent", data.message);
        return;
      }
      if (!resp.ok || data.type === "error") {
        addDeskMessage("error", data.message || `Request failed (${resp.status})`);
        return;
      }
      addDeskMessage("agent", data.message);
    } catch (err) {
      addDeskMessage("error", `Could not reach the IT service desk: ${err.message}`);
    }
  }

  async function initiateDeskOBO() {
    try {
      const resp = await deskFetch("/api/desk/obo/url");
      if (!resp.ok) {
        addDeskMessage("error", "Could not start authorization.");
        return;
      }
      const { auth_url } = await resp.json();
      window.open(auth_url, "it_obo_popup", "width=500,height=600,scrollbars=yes");
    } catch (err) {
      addDeskMessage("error", `Could not start authorization: ${err.message}`);
    }
  }

  function addDeskMessage(kind, text) {
    const log = $("desk-messages");
    if (!log) return;
    const who = kind === "user" ? "You" : kind === "error" ? "Error" : "IT Agent";
    const div = document.createElement("div");
    div.className = `msg ${kind}`;
    div.innerHTML = `<span class="who">${esc(who)}</span>${esc(text)}`;
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  // ─── Toast ──────────────────────────────────────────────────────────────────

  function toast(kind, title, desc, ms = 4000) {
    const container = $("toast-container");
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    const icon = ({ success: "✓", error: "✕", warning: "!" }[kind] || "•");
    el.innerHTML = `
      <div class="icon">${esc(icon)}</div>
      <div class="body">
        <div class="title">${esc(title)}</div>
        ${desc ? `<div class="desc">${esc(desc)}</div>` : ""}
      </div>`;
    container.appendChild(el);
    setTimeout(() => {
      el.classList.add("fading");
      el.addEventListener("animationend", () => el.remove(), { once: true });
    }, ms);
  }

  // ─── User menu ──────────────────────────────────────────────────────────────

  function toggleUserMenu() {
    const popover = $("user-menu-popover");
    popover.hidden = !popover.hidden;
  }

  function onDocumentClick(e) {
    const menu = $("user-menu");
    if (menu && !menu.contains(e.target)) {
      $("user-menu-popover").hidden = true;
    }
  }

  // ─── Sign-out + reset ───────────────────────────────────────────────────────

  async function resetDatabase() {
    if (!confirm("Reset all demo data to default state? This will clear all sessions and you will need to sign in again.")) return;
    try {
      // Use the agent's reset (it cascades to HR + clears agent sessions).
      const resp = await fetch(`${config.agentServerUrl}/api/reset`, {
        method: "POST",
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      // Read as text first — error responses aren't always JSON (proxy 5xx pages).
      const text = await resp.text();
      let data = null;
      if (text) { try { data = JSON.parse(text); } catch {} }

      if (!resp.ok) {
        // This endpoint's own 500 sends {error}; FastAPI's 403 sends {detail}.
        const detail = [data?.error, data?.detail].find((v) => typeof v === "string" && v)
          || (!text.startsWith("<") && text.length <= 200 ? text.trim() : "");
        toast("error", "Reset failed", detail ? `${detail} (HTTP ${resp.status})` : `HTTP ${resp.status}`);
        return;
      }

      if (data?.success) {
        toast("success", "Demo data reset", "Signing you out…");
        setTimeout(() => signOut(), 1200);
      } else {
        toast("error", "Reset failed", data?.error || "Unknown error");
      }
    } catch (e) {
      toast("error", "Reset failed", `Failed to reach the agent server: ${e.message}`);
    }
  }

  function signOut() {
    const savedIdToken = idToken;
    const savedAccessToken = accessToken;

    pendingCalendarMessage = null;

    accessToken = null;
    idToken = null;
    userScopes = [];
    userRole = "";
    userName = "";
    pendingMessage = null;
    sessionStorage.clear();

    const redirectToIdp = () => {
      const logoutUrl = new URL(`${config.asgardeoBaseUrl}/oidc/logout`);
      logoutUrl.searchParams.set("post_logout_redirect_uri", config.redirectUri);
      if (savedIdToken) logoutUrl.searchParams.set("id_token_hint", savedIdToken);
      window.location.href = logoutUrl.toString();
    };

    if (savedAccessToken) {
      fetch(`${config.agentServerUrl}/api/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${savedAccessToken}` },
      }).finally(redirectToIdp);
    } else {
      redirectToIdp();
    }
  }

  // ─── Utilities ──────────────────────────────────────────────────────────────

  function formatDate(iso) {
    if (!iso) return "";
    try {
      return new Date(iso + "T00:00:00").toLocaleDateString(undefined, {
        year: "numeric", month: "short", day: "numeric",
      });
    } catch { return iso; }
  }

  // ─── Boot ───────────────────────────────────────────────────────────────────

  init();

  return {
    // login + auth
    initiateLogin,
    signOut,
    // tab nav
    switchTab,
    // dashboard
    refreshDashboard,
    onLeaveFilterChange,
    // apply
    submitApplyLeave,
    resetApplyForm,
    // manage
    refreshManageQueue,
    // IT tickets
    refreshTickets,
    // IT service desk (Pattern 7)
    handleDeskSubmit,
    initiateDeskOBO,
    refreshDeskStatus,
    closeRejectModal,
    confirmReject,
    // details
    closeDetails,
    // assistant panel
    toggleAssistant,
    handleChatSubmit,
    initiateOBOFlow,
    // user menu
    toggleUserMenu,
    toggleGoogleCalendar,
    connectGoogleFromChat,
    resetDatabase,
  };
})();
