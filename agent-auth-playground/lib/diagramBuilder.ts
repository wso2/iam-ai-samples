/**
 * Copyright (c) 2026, WSO2 LLC. (https://www.wso2.com).
 *
 * WSO2 LLC. licenses this file to you under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { WorkflowTrace, MCPNodeTrace, ToolCallTrace, AuthErrorTrace, previewToken } from '@/lib/authTrace';

export type ColorKind = 'default' | 'auth' | 'blue' | 'green' | 'red';

export type DiagramItem =
  | { kind: 'section'; label: string; failed?: boolean }
  | {
      kind: 'message';
      from: string;
      to: string;
      label: string;
      sublabel?: string;
      color?: ColorKind;
      dashed?: boolean;
      token?: string;
      tokenLabel?: string;
      error?: { statusCode?: number; errorCode?: string; errorDescription?: string };
      skipped?: boolean;
    };

export interface Lane {
  id: string;
  label: string;
  sublabel?: string;
  x: number;
  shape: 'circle' | 'rect';
  fill: string;
  stroke: string;
  textColor: string;
}

export const COLORS: Record<ColorKind, string> = {
  default: '#475569',
  auth: '#d97706',
  blue: '#2563eb',
  green: '#059669',
  red: '#dc2626',
};

export const STAGE_LABELS: Record<AuthErrorTrace['stage'], string> = {
  config: 'Configuration',
  authorize: 'Authorize',
  authn: 'Authenticate (credentials are invalid)',
  token: 'Token Exchange',
  'obo-consent': 'OBO User Consent',
  'obo-token': 'OBO Token Exchange',
  connect: 'MCP Connect',
  'tool-call': 'Tool Call',
};

export function truncate(s: string | undefined, n: number): string {
  if (!s) return '';
  return s.length > n ? s.slice(0, n) + '…' : s;
}

export function stripNodeSuffix(name: string): string {
  return name.replace(/_node_[^_]+_[^_]+$/, '');
}

export function mcpDisplayName(m: MCPNodeTrace): string {
  return m.name?.trim() || m.nodeId;
}

export function mcpFullLabel(m: MCPNodeTrace): string {
  const name = m.name?.trim();
  return name ? `${name}  ·  ${m.endpoint}` : m.endpoint;
}

function buildFailureResponse(from: string, to: string, err: AuthErrorTrace, defaultLabel: string): DiagramItem {
  const codeBits = [err.statusCode ? `HTTP ${err.statusCode}` : null, err.errorCode || null].filter(Boolean);
  const headline = codeBits.length > 0
    ? `❌  ${codeBits.join('  ·  ')}  —  ${defaultLabel} failed`
    : `❌  ${defaultLabel} failed`;
  return {
    kind: 'message', from, to,
    label: headline,
    sublabel: err.errorDescription || err.message,
    color: 'red', dashed: true,
    error: { statusCode: err.statusCode, errorCode: err.errorCode, errorDescription: err.errorDescription },
  };
}

function pushSkippedNotice(items: DiagramItem[], mcpLabel: string, err: AuthErrorTrace) {
  const stage = STAGE_LABELS[err.stage] || err.stage;
  items.push({
    kind: 'message', from: 'Agent', to: 'Agent',
    label: `⏭  Subsequent steps skipped — flow halted at ${stage}`,
    sublabel: `Remaining auth + tool steps for ${mcpLabel} were never attempted`,
    color: 'red', dashed: true, skipped: true,
  });
}

export function buildLanes(trace: WorkflowTrace): Lane[] {
  const lanes: Lane[] = [
    { id: 'User', label: 'User', x: 0, shape: 'circle', fill: '#f97316', stroke: '#ea580c', textColor: '#ffffff' },
    { id: 'App',  label: 'App',  x: 0, shape: 'rect',   fill: '#fdf4f0', stroke: '#94a3b8', textColor: '#334155' },
    { id: 'Agent',label: 'Agent',x: 0, shape: 'rect',   fill: '#cbd5e1', stroke: '#64748b', textColor: '#1e293b' },
  ];

  if (trace.mcps.some((m) => m.flow !== 'none')) {
    lanes.push({ id: 'IAM', label: 'IAM (Asgardeo)', x: 0, shape: 'rect', fill: '#ffedd5', stroke: '#f59e0b', textColor: '#92400e' });
  }

  lanes.push({
    id: 'LLM',
    label: trace.llm ? `${trace.llm.provider}/${trace.llm.model}` : 'LLM',
    x: 0, shape: 'rect', fill: '#cffafe', stroke: '#06b6d4', textColor: '#155e75',
  });

  for (const m of trace.mcps) {
    lanes.push({ id: `MCP:${m.nodeId}`, label: mcpDisplayName(m), sublabel: m.endpoint, x: 0, shape: 'rect', fill: '#fef08a', stroke: '#a3a3a3', textColor: '#3f3f46' });
  }
  if (trace.mcps.length === 0) {
    lanes.push({ id: 'MCP:none', label: 'MCP', x: 0, shape: 'rect', fill: '#fef08a', stroke: '#a3a3a3', textColor: '#3f3f46' });
  }

  const startX = 100;
  const gap = 200;
  lanes.forEach((l, i) => { l.x = startX + i * gap; });
  return lanes;
}

function pushAgentAuthSteps(items: DiagramItem[], mcp: MCPNodeTrace) {
  const base = mcp.iamBaseUrl ?? '';
  const authorizeUrl = mcp.authorizeUrl ?? `${base}/oauth2/authorize`;
  const authnUrl    = mcp.authnUrl    ?? `${base}/oauth2/authn`;
  const tokenUrl    = mcp.tokenUrl    ?? `${base}/oauth2/token`;
  const mcpLabel = mcpDisplayName(mcp);
  const err = mcp.authError;

  const sectionLabel = `AGENT AUTHENTICATION  ·  ${mcpLabel}  (PKCE  ·  Asgardeo Direct Auth)`;
  const agentAuthFailed = !!err && (err.stage === 'authorize' || err.stage === 'authn' || err.stage === 'token' || err.stage === 'config');
  items.push({ kind: 'section', label: agentAuthFailed ? `${sectionLabel}  ·  FAILED` : sectionLabel, failed: agentAuthFailed });

  if (err?.stage === 'config') {
    items.push({ kind: 'message', from: 'Agent', to: 'Agent', label: `❌  Configuration error  —  ${err.errorCode || 'invalid config'}`, sublabel: err.errorDescription || err.message, color: 'red', dashed: true, error: { errorCode: err.errorCode, errorDescription: err.errorDescription } });
    pushSkippedNotice(items, mcpLabel, err);
    return;
  }

  items.push({ kind: 'message', from: 'Agent', to: 'IAM', label: `POST ${authorizeUrl}`, sublabel: 'client_id, redirect_uri, response_type=code, response_mode=direct, scope, code_challenge (S256)', color: 'auth' });
  if (err?.stage === 'authorize') { items.push(buildFailureResponse('IAM', 'Agent', err, 'Authorize')); pushSkippedNotice(items, mcpLabel, err); return; }
  items.push({ kind: 'message', from: 'IAM', to: 'Agent', label: 'flowId  +  authenticatorId', sublabel: 'response_mode=direct, returns flow handle', color: 'auth', dashed: true });

  items.push({ kind: 'message', from: 'Agent', to: 'IAM', label: `POST ${authnUrl}`, sublabel: `flowId, selectedAuthenticator { authenticatorId, params: { username: agentId, password: agentSecret } }`, color: 'auth' });
  if (err?.stage === 'authn') { items.push(buildFailureResponse('IAM', 'Agent', err, 'Credential authentication')); pushSkippedNotice(items, mcpLabel, err); return; }
  items.push({ kind: 'message', from: 'IAM', to: 'Agent', label: 'Authorization code', sublabel: 'authData.code (one-time use)', color: 'auth', dashed: true });

  items.push({ kind: 'message', from: 'Agent', to: 'IAM', label: `POST ${tokenUrl}`, sublabel: 'grant_type=authorization_code, client_id, code, code_verifier, redirect_uri', color: 'auth' });
  if (err?.stage === 'token') { items.push(buildFailureResponse('IAM', 'Agent', err, 'Token exchange')); pushSkippedNotice(items, mcpLabel, err); return; }
  items.push({ kind: 'message', from: 'IAM', to: 'Agent', label: 'Agent access_token', sublabel: mcp.agentToken ? `access_token = ${previewToken(mcp.agentToken)}` : '(no token captured)', color: 'auth', dashed: true, token: mcp.agentToken, tokenLabel: 'Agent JWT' });
}

function pushOBOConsentSteps(items: DiagramItem[], mcp: MCPNodeTrace) {
  const base = mcp.iamBaseUrl ?? '';
  const authorizeUrl = mcp.authorizeUrl ?? `${base}/oauth2/authorize`;
  const tokenUrl = mcp.tokenUrl ?? `${base}/oauth2/token`;
  const mcpLabel = mcpDisplayName(mcp);
  const err = mcp.authError;

  pushAgentAuthSteps(items, mcp);
  if (err && (err.stage === 'authorize' || err.stage === 'authn' || err.stage === 'token' || err.stage === 'config')) return;

  const consentFailed = err?.stage === 'obo-consent';
  items.push({ kind: 'section', label: consentFailed ? `USER AUTHORIZATION  ·  ${mcpLabel}  (OBO Consent)  ·  FAILED` : `USER AUTHORIZATION  ·  ${mcpLabel}  (OBO Consent)`, failed: consentFailed });
  items.push({ kind: 'message', from: 'Agent', to: 'App', label: 'Build /oauth2/authorize URL', sublabel: 'response_type=code, scope, state, code_challenge (S256), requested_actor=agentId' });
  items.push({ kind: 'message', from: 'App', to: 'User', label: 'Show "Authorize" button (chat consent prompt)', sublabel: mcp.oboAuthUrl ? truncate(mcp.oboAuthUrl, 130) : undefined });
  items.push({ kind: 'message', from: 'User', to: 'IAM', label: `GET ${authorizeUrl}`, sublabel: 'User opens auth URL in browser, IAM presents login + consent screen', color: 'auth' });
  if (consentFailed) { items.push(buildFailureResponse('IAM', 'User', err!, 'Login / consent')); pushSkippedNotice(items, mcpLabel, err!); return; }
  items.push({ kind: 'message', from: 'IAM', to: 'App', label: 'User authenticates & grants consent', sublabel: 'Login UI confirms requested_actor (Agent) + scopes', color: 'auth' });
  items.push({ kind: 'message', from: 'IAM', to: 'App', label: 'Redirect to redirect_uri with auth code', sublabel: 'redirect_uri?code=...&state=...', color: 'auth', dashed: true });
  items.push({ kind: 'message', from: 'App', to: 'Agent', label: 'Callback delivers auth code' });

  const oboTokenFailed = err?.stage === 'obo-token';
  items.push({ kind: 'section', label: oboTokenFailed ? `OBO TOKEN EXCHANGE  ·  ${mcpLabel}  ·  FAILED` : `OBO TOKEN EXCHANGE  ·  ${mcpLabel}`, failed: oboTokenFailed });
  items.push({ kind: 'message', from: 'Agent', to: 'IAM', label: `POST ${tokenUrl}`, sublabel: 'grant_type=authorization_code, client_id, code, code_verifier, redirect_uri,  actor_token = Agent Token', color: 'auth' });
  if (oboTokenFailed) { items.push(buildFailureResponse('IAM', 'Agent', err!, 'OBO token exchange')); pushSkippedNotice(items, mcpLabel, err!); return; }
  items.push({ kind: 'message', from: 'IAM', to: 'Agent', label: 'OBO access_token', sublabel: mcp.oboToken ? `access_token = ${previewToken(mcp.oboToken)}` : '(no token captured)', color: 'auth', dashed: true, token: mcp.oboToken, tokenLabel: 'OBO JWT' });
}

function pushToolCall(items: DiagramItem[], t: ToolCallTrace, trace: WorkflowTrace) {
  const mcp = trace.mcps.find((m) => m.nodeId === t.nodeId);
  const token = mcp?.oboToken || mcp?.agentToken;
  const laneId = mcp ? `MCP:${mcp.nodeId}` : `MCP:${t.nodeId}` || 'MCP:none';
  const tokenKind = mcp?.oboToken ? 'OBO' : mcp?.agentToken ? 'Agent' : '';
  const serverLabel = mcp ? mcpFullLabel(mcp) : t.endpoint;
  items.push({
    kind: 'message', from: 'Agent', to: laneId,
    label: token
      ? `Tool call: ${stripNodeSuffix(t.publicName)}  ·  Authorization: Bearer <${tokenKind} Token>`
      : `Tool call: ${stripNodeSuffix(t.publicName)}  ·  (no auth header)`,
    sublabel: `${serverLabel}    args: ${truncate(t.args, 80)}`,
    color: 'blue', token, tokenLabel: token ? `${tokenKind} JWT` : undefined,
  });

  if (t.ok) {
    items.push({ kind: 'message', from: laneId, to: 'Agent', label: `✓ Result (${stripNodeSuffix(t.publicName)})`, sublabel: truncate(t.result, 110), color: 'green', dashed: true });
  } else {
    const codeBits = [t.statusCode ? `HTTP ${t.statusCode}` : null, t.errorCode || null].filter(Boolean);
    const headline = codeBits.length > 0 ? `❌  ${codeBits.join('  ·  ')}  —  ${stripNodeSuffix(t.publicName)} failed` : `❌  Error (${stripNodeSuffix(t.publicName)})`;
    items.push({ kind: 'message', from: laneId, to: 'Agent', label: headline, sublabel: t.errorDescription ? `${t.errorDescription}  ·  ${truncate(t.result, 90)}` : truncate(t.result, 110), color: 'red', dashed: true, error: { statusCode: t.statusCode, errorCode: t.errorCode, errorDescription: t.errorDescription } });
  }
}

export function buildItems(trace: WorkflowTrace): DiagramItem[] {
  const items: DiagramItem[] = [];

  items.push({ kind: 'section', label: 'USER REQUEST' });
  items.push({ kind: 'message', from: 'User', to: 'App', label: 'Asks query', sublabel: trace.userMessage ? `"${truncate(trace.userMessage, 90)}"` : undefined });
  items.push({ kind: 'message', from: 'App', to: 'Agent', label: 'Forward request to Agent' });

  items.push({ kind: 'section', label: 'AGENT OPERATIONS' });
  items.push({ kind: 'message', from: 'Agent', to: 'LLM', label: 'Prompt + tool schemas + memory', sublabel: 'Builds JSON tool list, sends step prompt' });

  const realTools = trace.tools.filter((t) => t.publicName !== 'tool_search');
  if (realTools.length === 0) {
    items.push({ kind: 'message', from: 'LLM', to: 'Agent', label: 'No tool calls in this run', sublabel: 'Agent answered directly', color: 'default', dashed: true });
  } else {
    items.push({ kind: 'message', from: 'LLM', to: 'Agent', label: 'Tool decision (JSON)', sublabel: '{ Tool call is needed. }', dashed: true });
  }

  const shownMCPAuth = new Set<string>();
  for (const t of realTools) {
    const mcp = trace.mcps.find((m) => m.nodeId === t.nodeId);
    if (mcp && mcp.flow !== 'none' && !shownMCPAuth.has(mcp.nodeId)) {
      shownMCPAuth.add(mcp.nodeId);
      if (mcp.flow === 'agent') pushAgentAuthSteps(items, mcp);
      else if (mcp.flow === 'obo') pushOBOConsentSteps(items, mcp);
    }
    pushToolCall(items, t, trace);
  }

  for (const mcp of trace.mcps) {
    if (shownMCPAuth.has(mcp.nodeId)) continue;
    if (mcp.flow === 'none' && !mcp.authError) continue;
    if (mcp.flow === 'obo') pushOBOConsentSteps(items, mcp);
    else pushAgentAuthSteps(items, mcp);
    shownMCPAuth.add(mcp.nodeId);
  }

  if (trace.failure) {
    items.push({ kind: 'section', label: 'WORKFLOW HALTED', failed: true });
    const stage = trace.failure.stage === 'workflow' ? 'Workflow' : STAGE_LABELS[trace.failure.stage as AuthErrorTrace['stage']] || trace.failure.stage;
    items.push({ kind: 'message', from: 'Agent', to: 'App', label: `❌  Execution failed at: ${stage}`, sublabel: truncate(trace.failure.message, 140), color: 'red', dashed: true });
    items.push({ kind: 'message', from: 'App', to: 'User', label: 'Display error to user', sublabel: 'Workflow could not complete because of the failure above', color: 'red', dashed: true });
  } else {
    items.push({ kind: 'section', label: 'RESPONSE' });
    items.push({ kind: 'message', from: 'Agent', to: 'App', label: 'Final answer', sublabel: trace.finalAnswer ? `"${truncate(trace.finalAnswer, 90)}"` : undefined });
    items.push({ kind: 'message', from: 'App', to: 'User', label: 'Display response', dashed: true });
  }

  return items;
}
