import 'server-only';

import { randomBytes, createHash } from 'crypto';
import { AuthFlowError, localAwareFetch } from './agentAuth';
import { parseOAuthErrorBody } from './authTrace';

interface OBOAuthUrlConfig {
  baseUrl: string;
  clientId: string;
  redirectUri: string;
  scope?: string;
  agentId: string;
}

export interface OBOInitResult {
  authUrl: string;
  state: string;
  codeVerifier: string;
}

function generatePKCE(): { codeVerifier: string; codeChallenge: string } {
  const codeVerifier = randomBytes(48).toString('base64url');
  const codeChallenge = createHash('sha256').update(codeVerifier).digest('base64url');
  return { codeVerifier, codeChallenge };
}

function generateState(): string {
  return randomBytes(16).toString('base64url');
}

export function buildOBOAuthorizationUrl(config: OBOAuthUrlConfig): OBOInitResult {
  const baseUrl = config.baseUrl.replace(/\/+$/, '');
  const { codeVerifier, codeChallenge } = generatePKCE();
  const state = generateState();
  const scope = config.scope?.trim() || 'openid';

  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: config.redirectUri,
    response_type: 'code',
    scope,
    state,
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
    requested_actor: config.agentId,
  });

  return {
    authUrl: `${baseUrl}/oauth2/authorize?${params.toString()}`,
    state,
    codeVerifier,
  };
}

export async function exchangeOBOCode(
  baseUrl: string,
  clientId: string,
  redirectUri: string,
  authCode: string,
  agentAccessToken: string,
  codeVerifier: string
): Promise<{ accessToken: string; expiresIn: number }> {
  baseUrl = baseUrl.replace(/\/+$/, '');

  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: clientId,
    code: authCode,
    redirect_uri: redirectUri,
    code_verifier: codeVerifier,
    actor_token: agentAccessToken,
  });

  const url = `${baseUrl}/oauth2/token`;
  const res = await localAwareFetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) {
    const text = await res.text().catch(() => '');
    const parsed = parseOAuthErrorBody(text);
    throw new AuthFlowError({
      stage: 'obo-token',
      statusCode: res.status,
      url,
      body: text,
      errorCode: parsed.errorCode,
      errorDescription: parsed.errorDescription,
      message:
        parsed.errorDescription ||
        parsed.errorCode ||
        `OBO token exchange failed (${res.status})`,
    });
  }

  const data = await res.json();

  if (!data.access_token) {
    throw new AuthFlowError({
      stage: 'obo-token',
      url,
      errorCode: 'no_access_token',
      errorDescription: 'OBO token endpoint returned 200 but no access_token field',
      body: JSON.stringify(data),
    });
  }

  return {
    accessToken: data.access_token,
    expiresIn: data.expires_in || 3600,
  };
}
