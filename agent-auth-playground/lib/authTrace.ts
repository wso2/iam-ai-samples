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
export type AuthFlowKind = 'agent' | 'obo' | 'mixed' | 'none';

export type AuthErrorStage =
  | 'config'
  | 'authorize'
  | 'authn'
  | 'token'
  | 'obo-consent'
  | 'obo-token'
  | 'connect'
  | 'tool-call';

export interface AuthErrorTrace {
  stage: AuthErrorStage;
  statusCode?: number;
  errorCode?: string;
  errorDescription?: string;
  message: string;
  url?: string;
}

export interface MCPNodeTrace {
  nodeId: string;
  name?: string;
  endpoint: string;
  flow: AuthFlowKind;
  iamBaseUrl?: string;
  authorizeUrl?: string;
  authnUrl?: string;
  tokenUrl?: string;
  oboAuthUrl?: string;
  agentToken?: string;
  oboToken?: string;
  agentId?: string;
  authError?: AuthErrorTrace;
}

export interface ToolCallTrace {
  step: number;
  publicName: string;
  sourceToolName: string;
  endpoint: string;
  nodeId: string;
  args: string;
  result: string;
  ok: boolean;
  statusCode?: number;
  errorCode?: string;
  errorDescription?: string;
}

export interface WorkflowTrace {
  flow: AuthFlowKind;
  startedAt: number;
  finishedAt?: number;
  userMessage?: string;
  finalAnswer?: string;
  llm?: { provider: string; model: string };
  mcps: MCPNodeTrace[];
  tools: ToolCallTrace[];
  failure?: {
    stage: AuthErrorStage | 'workflow';
    nodeId?: string;
    message: string;
  };
}

export function emptyTrace(): WorkflowTrace {
  return { flow: 'none', startedAt: Date.now(), mcps: [], tools: [] };
}

export function previewToken(token?: string, headLen = 10, tailLen = 4): string {
  if (!token) return '—';
  if (token.length <= headLen + tailLen + 2) return token;
  return `${token.slice(0, headLen)}…${token.slice(-tailLen)}`;
}

export function deriveIamUrls(baseUrl: string): {
  iamBaseUrl: string;
  authorizeUrl: string;
  authnUrl: string;
  tokenUrl: string;
} {
  const iamBaseUrl = baseUrl.replace(/\/+$/, '');
  return {
    iamBaseUrl,
    authorizeUrl: `${iamBaseUrl}/oauth2/authorize`,
    authnUrl: `${iamBaseUrl}/oauth2/authn`,
    tokenUrl: `${iamBaseUrl}/oauth2/token`,
  };
}

export function dominantFlow(mcps: MCPNodeTrace[]): AuthFlowKind {
  const hasAgent = mcps.some((m) => m.flow === 'agent');
  const hasObo = mcps.some((m) => m.flow === 'obo');
  if (hasAgent && hasObo) return 'mixed';
  if (hasObo) return 'obo';
  if (hasAgent) return 'agent';
  return 'none';
}

// Parses an OAuth2-style error body. Most IAMs (Asgardeo included) return
// `{ "error": "invalid_client", "error_description": "..." }` or a
// trace-style payload. Returns whatever fields we can recognise.
export function parseOAuthErrorBody(text: string | undefined): {
  errorCode?: string;
  errorDescription?: string;
} {
  if (!text) return {};
  try {
    const body = JSON.parse(text) as Record<string, unknown>;
    const errorCode =
      typeof body.error === 'string'
        ? body.error
        : typeof body.code === 'string'
        ? body.code
        : undefined;
    const errorDescription =
      typeof body.error_description === 'string'
        ? body.error_description
        : typeof body.description === 'string'
        ? body.description
        : typeof body.message === 'string'
        ? body.message
        : undefined;
    return { errorCode, errorDescription };
  } catch {
    return {};
  }
}

// Best-effort extraction of HTTP status / OAuth error info from a free-form
// error message string (e.g. errors surfaced by the MCP runtime / fetch /
// MCP-protocol isError responses).
export function extractErrorInfoFromMessage(message: string): {
  statusCode?: number;
  errorCode?: string;
  errorDescription?: string;
} {
  if (!message) return {};
  const out: { statusCode?: number; errorCode?: string; errorDescription?: string } = {};

  const statusMatch =
    message.match(/\b(?:HTTP\s*)?(\d{3})\b(?:\s*[-:]?\s*(?:Unauthorized|Forbidden|Bad Request|Not Found|Internal Server Error))?/i) ||
    message.match(/status(?:Code)?[:\s=]+(\d{3})/i);
  if (statusMatch) {
    const n = Number(statusMatch[1]);
    if (n >= 400 && n < 600) out.statusCode = n;
  }

  const codeMatch = message.match(/"error"\s*:\s*"([^"]+)"/);
  if (codeMatch) out.errorCode = codeMatch[1];

  const descMatch = message.match(/"error_description"\s*:\s*"([^"]+)"/);
  if (descMatch) out.errorDescription = descMatch[1];

  // Heuristic detection for free-form auth errors that don't carry an HTTP
  // code or OAuth payload (common with MCP isError responses).
  const lower = message.toLowerCase();
  if (!out.errorCode) {
    if (/insufficient[_\s-]?scope|required\s+scope|missing\s+scope/i.test(message)) {
      out.errorCode = 'insufficient_scope';
      if (!out.statusCode) out.statusCode = 403;
    } else if (/invalid[_\s-]?token|expired\s+token|token\s+(?:is\s+)?(?:expired|invalid|revoked)/i.test(message)) {
      out.errorCode = 'invalid_token';
      if (!out.statusCode) out.statusCode = 401;
    } else if (/access[_\s-]?denied/i.test(message)) {
      out.errorCode = 'access_denied';
      if (!out.statusCode) out.statusCode = 403;
    } else if (/invalid[_\s-]?(?:client|grant|credentials)/i.test(message)) {
      const m = message.match(/invalid[_\s-]?(client|grant|credentials)/i);
      out.errorCode = `invalid_${m?.[1]?.toLowerCase() ?? 'grant'}`;
      if (!out.statusCode) out.statusCode = 401;
    } else if (lower.includes('unauthorized')) {
      out.errorCode = 'unauthorized';
      if (!out.statusCode) out.statusCode = 401;
    } else if (lower.includes('forbidden')) {
      out.errorCode = 'forbidden';
      if (!out.statusCode) out.statusCode = 403;
    }
  }

  // If we found a status but no description, use the trimmed message as the
  // description so the diagram shows something human-readable.
  if (!out.errorDescription && (out.errorCode || out.statusCode)) {
    const cleaned = message.trim().split(/\r?\n/)[0];
    if (cleaned) out.errorDescription = cleaned.slice(0, 200);
  }

  return out;
}
