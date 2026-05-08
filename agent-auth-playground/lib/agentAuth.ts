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
import 'server-only';

import { randomBytes, createHash } from 'crypto';
import https from 'node:https';
import http from 'node:http';
import { AuthErrorStage, parseOAuthErrorBody } from './authTrace';

function isLocalHost(urlStr: string): boolean {
  try {
    const { hostname } = new URL(urlStr);
    return hostname === 'localhost' || hostname === '127.0.0.1' || hostname === '::1';
  } catch {
    return false;
  }
}

// Bypasses TLS certificate verification for local IS instances (self-signed certs).
function insecureFetch(url: string, init?: RequestInit): Promise<Response> {
  return new Promise<Response>((resolve, reject) => {
    const parsed = new URL(url);
    const useHttps = parsed.protocol === 'https:';
    const transport = useHttps ? https : http;

    const reqOptions: https.RequestOptions = {
      hostname: parsed.hostname,
      port: Number(parsed.port) || (useHttps ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method: (init?.method ?? 'GET').toUpperCase(),
      headers: init?.headers as Record<string, string> | undefined,
      rejectUnauthorized: false,
    };

    const req = transport.request(reqOptions, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => {
        const headers: Record<string, string> = {};
        const raw = res.rawHeaders ?? [];
        for (let i = 0; i + 1 < raw.length; i += 2) {
          headers[raw[i].toLowerCase()] = raw[i + 1];
        }
        resolve(new Response(Buffer.concat(chunks), { status: res.statusCode ?? 200, headers }));
      });
      res.on('error', reject);
    });

    req.on('error', reject);

    const body = init?.body;
    if (body != null) {
      req.write(body instanceof URLSearchParams ? body.toString() : body as string);
    }
    req.end();
  });
}

export function localAwareFetch(url: string, init?: RequestInit): Promise<Response> {
  return isLocalHost(url) ? insecureFetch(url, init) : fetch(url, init);
}

export interface AgentAuthConfig {
  baseUrl: string;
  clientId: string;
  redirectUri: string;
  agentId: string;
  agentSecret: string;
  scope?: string;
}

interface PKCEPair {
  codeVerifier: string;
  codeChallenge: string;
}

interface AuthorizeResult {
  flowId: string;
  authenticatorId: string;
}

interface AuthorizeResponse {
  flowId?: string;
  nextStep?: {
    authenticators?: Array<{ authenticatorId: string }>;
  };
}

interface AuthnResponse {
  authData?: { code?: string };
  code?: string;
  flowStatus?: string;
  failureReason?: string;
  error?: string;
  error_description?: string;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  scope?: string;
  [key: string]: unknown;
}

export interface AuthFlowErrorInit {
  stage: AuthErrorStage;
  statusCode?: number;
  errorCode?: string;
  errorDescription?: string;
  url?: string;
  body?: string;
  message?: string;
}

export class AuthFlowError extends Error {
  stage: AuthErrorStage;
  statusCode?: number;
  errorCode?: string;
  errorDescription?: string;
  url?: string;
  body?: string;

  constructor(init: AuthFlowErrorInit) {
    const headline =
      init.message ||
      init.errorDescription ||
      init.errorCode ||
      `${init.stage} failed${init.statusCode ? ` (HTTP ${init.statusCode})` : ''}`;
    super(headline);
    this.name = 'AuthFlowError';
    this.stage = init.stage;
    this.statusCode = init.statusCode;
    this.errorCode = init.errorCode;
    this.errorDescription = init.errorDescription;
    this.url = init.url;
    this.body = init.body;
  }
}

function generatePKCE(): PKCEPair {
  const codeVerifier = randomBytes(48).toString('base64url');
  const codeChallenge = createHash('sha256').update(codeVerifier).digest('base64url');
  return { codeVerifier, codeChallenge };
}

async function readErrorBody(res: Response): Promise<string> {
  try {
    return await res.text();
  } catch {
    return '';
  }
}

async function initiateAuthorize(
  baseUrl: string,
  clientId: string,
  redirectUri: string,
  scope: string,
  codeChallenge: string
): Promise<AuthorizeResult> {
  const url = `${baseUrl}/oauth2/authorize`;
  const body = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: redirectUri,
    scope,
    response_mode: 'direct',
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  const res = await localAwareFetch(url, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  });

  if (!res.ok) {
    const text = await readErrorBody(res);
    const parsed = parseOAuthErrorBody(text);
    throw new AuthFlowError({
      stage: 'authorize',
      statusCode: res.status,
      url,
      body: text,
      errorCode: parsed.errorCode,
      errorDescription: parsed.errorDescription,
      message: parsed.errorDescription || parsed.errorCode || `Authorize failed (${res.status})`,
    });
  }

  const data = (await res.json()) as AuthorizeResponse;

  if (!data.flowId) {
    throw new AuthFlowError({
      stage: 'authorize',
      statusCode: res.status,
      url,
      errorCode: 'missing_flow_id',
      errorDescription: 'Authorize response did not contain a flowId',
      body: JSON.stringify(data),
    });
  }

  const authenticatorId = data.nextStep?.authenticators?.[0]?.authenticatorId;
  if (!authenticatorId) {
    throw new AuthFlowError({
      stage: 'authorize',
      statusCode: res.status,
      url,
      errorCode: 'no_authenticator',
      errorDescription: 'Authorize response did not contain an authenticator',
      body: JSON.stringify(data),
    });
  }

  return { flowId: data.flowId, authenticatorId };
}

async function submitCredentials(
  baseUrl: string,
  flowId: string,
  authenticatorId: string,
  agentId: string,
  agentSecret: string
): Promise<string> {
  const url = `${baseUrl}/oauth2/authn`;
  const payload = {
    flowId,
    selectedAuthenticator: {
      authenticatorId,
      params: {
        username: agentId,
        password: agentSecret,
      },
    },
  };

  const res = await localAwareFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const text = await readErrorBody(res);
    const parsed = parseOAuthErrorBody(text);
    throw new AuthFlowError({
      stage: 'authn',
      statusCode: res.status,
      url,
      body: text,
      errorCode: parsed.errorCode || (res.status === 401 ? 'invalid_credentials' : undefined),
      errorDescription:
        parsed.errorDescription ||
        (res.status === 401 ? 'Agent ID or secret was rejected by the IAM' : undefined),
      message: parsed.errorDescription || parsed.errorCode || `Authn failed (${res.status})`,
    });
  }

  const data = (await res.json()) as AuthnResponse;

  // Asgardeo can return 200 OK with a FAIL_INCOMPLETE / INCOMPLETE flow status
  // when credentials don't pass. Detect those cases too.
  if (data.flowStatus && data.flowStatus !== 'SUCCESS_COMPLETED') {
    throw new AuthFlowError({
      stage: 'authn',
      statusCode: res.status,
      url,
      body: JSON.stringify(data),
      errorCode: data.error || data.flowStatus,
      errorDescription:
        data.error_description || data.failureReason || `Authn rejected: ${data.flowStatus}`,
    });
  }

  const code = data.authData?.code ?? data.code;
  if (!code) {
    throw new AuthFlowError({
      stage: 'authn',
      statusCode: res.status,
      url,
      body: JSON.stringify(data),
      errorCode: 'no_authorization_code',
      errorDescription: 'Authn succeeded but no authorization code was returned',
    });
  }

  return code;
}

async function exchangeCodeForToken(
  baseUrl: string,
  clientId: string,
  redirectUri: string,
  code: string,
  codeVerifier: string
): Promise<TokenResponse> {
  const url = `${baseUrl}/oauth2/token`;
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: clientId,
    code,
    code_verifier: codeVerifier,
    redirect_uri: redirectUri,
  });

  const res = await localAwareFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) {
    const text = await readErrorBody(res);
    const parsed = parseOAuthErrorBody(text);
    throw new AuthFlowError({
      stage: 'token',
      statusCode: res.status,
      url,
      body: text,
      errorCode: parsed.errorCode,
      errorDescription: parsed.errorDescription,
      message: parsed.errorDescription || parsed.errorCode || `Token exchange failed (${res.status})`,
    });
  }

  return res.json() as Promise<TokenResponse>;
}

export async function authenticateAgent(config: AgentAuthConfig): Promise<string> {
  const baseUrl = config.baseUrl.replace(/\/+$/, '');
  const scope = config.scope?.trim() || 'openid';

  const { codeVerifier, codeChallenge } = generatePKCE();
  const { flowId, authenticatorId } = await initiateAuthorize(
    baseUrl,
    config.clientId,
    config.redirectUri,
    scope,
    codeChallenge
  );
  const code = await submitCredentials(baseUrl, flowId, authenticatorId, config.agentId, config.agentSecret);
  const tokenResponse = await exchangeCodeForToken(baseUrl, config.clientId, config.redirectUri, code, codeVerifier);

  if (!tokenResponse.access_token) {
    throw new AuthFlowError({
      stage: 'token',
      url: `${baseUrl}/oauth2/token`,
      errorCode: 'no_access_token',
      errorDescription: 'Token endpoint returned 200 but no access_token field',
      body: JSON.stringify(tokenResponse),
    });
  }

  return tokenResponse.access_token;
}
