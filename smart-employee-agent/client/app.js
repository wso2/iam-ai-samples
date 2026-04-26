/*
 * Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.
 *
 *  Smart Employee Agent — Client Application
 *
 *  Sections:
 *    State + DOM helpers + utilities
 *    PKCE login & callback (Asgardeo)
 *    Tab router
 *    REST API client (talks to hr-server with the SPA token)
 *    Dashboard view (stat cards, holidays, leaves table, details drawer)
 *    Apply-leave form view
 *    Manage-requests view (pending queue, approve/reject)
 *    Chat view (talks to agent server, OBO popup flow)
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
  let balanceCache = null;

  // UI state
  let activeTab = "dashboard";
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

    // Initial tab
    switchTab("dashboard");

    // Greet in chat (chat tab content stays mounted; just doesn't show until selected)
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
    else if (name === "chat") setTimeout(() => $("message-input").focus(), 50);
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
    if (isAdmin) {
      html += `<th>Employee</th><th>Type</th><th>Start</th><th>End</th><th>Days</th><th>Status</th>`;
    } else {
      html += `<th>Type</th><th>Start</th><th>End</th><th>Days</th><th>Status</th>`;
    }
    html += `</tr></thead><tbody>`;

    if (rows.length === 0) {
      const cols = isAdmin ? 6 : 5;
      html += `<tr class="empty-row"><td colspan="${cols}">No leave requests match your filters.</td></tr>`;
    } else {
      for (const l of rows) {
        const statusClass = (l.status || "").toLowerCase();
        const reqId = l.request_id || "";
        const cells = isAdmin
          ? `<td>${esc(l.employee)}</td>
             <td>${esc(l.type || l.leave_type)}</td>
             <td>${esc(l.start_date)}</td>
             <td>${esc(l.end_date)}</td>
             <td>${esc(l.days_requested)}</td>
             <td><span class="status-badge ${statusClass}">${esc(l.status)}</span></td>`
          : `<td>${esc(l.type || l.leave_type)}</td>
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
        toast("error", "Couldn't load leave policy", e.message);
        return;
      }
    }
    populateLeaveTypes();
    populateApplySummary();
  }

  function populateLeaveTypes() {
    const sel = $("leave-type");
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
      `Hello ${userName}! I'm your Corporate Concierge. ` +
      `You're signed in as **${userRole}**.\n\n${capabilities}\n\n` +
      `_You can also use the tabs above to do these actions manually._`
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
          // Invalidate caches; refresh whichever tab is active.
          balanceCache = null;
          if (activeTab === "dashboard") refreshDashboard();
          else if (activeTab === "manage") refreshManageQueue();
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

  function handlePostMessage(event) {
    if (!event.data || !event.data.type) return;
    if (event.data.type === "obo_success") {
      const msg = pendingMessage;
      hideAuthorizeButton();
      addAgentMessage("Authorization successful! Let me process your request now.");
      if (msg) sendMessage(msg);
    } else if (event.data.type === "obo_failed") {
      addErrorMessage(`Authorization failed: ${event.data.error || "Unknown error"}`);
    }
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
      const data = await resp.json();
      if (data.success) {
        toast("success", "Demo data reset", "Signing you out…");
        setTimeout(() => signOut(), 1200);
      } else {
        toast("error", "Reset failed", data.error || "Unknown error");
      }
    } catch (e) {
      toast("error", "Reset failed", "Failed to reach the agent server.");
    }
  }

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
    if (savedIdToken) logoutUrl.searchParams.set("id_token_hint", savedIdToken);
    window.location.href = logoutUrl.toString();
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
    closeRejectModal,
    confirmReject,
    // details
    closeDetails,
    // chat
    handleChatSubmit,
    initiateOBOFlow,
    // user menu
    toggleUserMenu,
    resetDatabase,
  };
})();
