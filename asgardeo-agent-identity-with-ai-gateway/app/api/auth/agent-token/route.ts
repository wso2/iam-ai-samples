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

import { randomBytes, createHash } from 'crypto';
import { NextRequest, NextResponse } from "next/server";
import { getAppConfig } from "@/app/config";

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
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  scope?: string;
  [key: string]: unknown;
}

function generatePKCE(): PKCEPair {
  const codeVerifier = randomBytes(48).toString('base64url');
  const codeChallenge = createHash('sha256').update(codeVerifier).digest('base64url');
  return { codeVerifier, codeChallenge };
}

async function initiateAuthorize(
  baseUrl: string,
  clientId: string,
  redirectUri: string,
  scope: string,
  codeChallenge: string
): Promise<AuthorizeResult> {
  const body = new URLSearchParams({
    client_id: clientId,
    response_type: 'code',
    redirect_uri: redirectUri,
    scope,
    response_mode: 'direct',
    code_challenge: codeChallenge,
    code_challenge_method: 'S256',
  });

  const res = await fetch(`${baseUrl}/oauth2/authorize`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
  });

  if (!res.ok) {
    throw new Error(`Authorize failed: ${res.status} ${await res.text()}`);
  }

  const data = await res.json() as AuthorizeResponse;

  if (!data.flowId) {
    throw new Error(`No flowId in authorize response: ${JSON.stringify(data)}`);
  }

  const authenticatorId = data.nextStep?.authenticators?.[0]?.authenticatorId;
  if (!authenticatorId) {
    throw new Error('No authenticator found in authorize response');
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

  const res = await fetch(`${baseUrl}/oauth2/authn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    throw new Error(`Authn failed: ${res.status} ${await res.text()}`);
  }

  const data = await res.json() as AuthnResponse;

  const code = data.authData?.code ?? data.code;
  if (!code) {
    throw new Error(`No code in authn response: ${JSON.stringify(data)}`);
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
  const body = new URLSearchParams({
    grant_type: 'authorization_code',
    client_id: clientId,
    code,
    code_verifier: codeVerifier,
    redirect_uri: redirectUri,
  });

  const res = await fetch(`${baseUrl}/oauth2/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });

  if (!res.ok) {
    throw new Error(`Token exchange failed: ${res.status} ${await res.text()}`);
  }

  return res.json() as Promise<TokenResponse>;
}

export async function POST(request: NextRequest) {
  try {
    const config = getAppConfig();
    const body = await request.json();
    const { callingAgent } = body;

    const credentials = callingAgent === 'Support-Coordinator'
      ? config.coordinatorAgent
      : config.expertAgent;

    if (!credentials.agentId || !credentials.agentSecret) {
      return NextResponse.json(
        { error: `Missing agent credentials for ${callingAgent}. Check your .env.local file.` },
        { status: 400 }
      );
    }

    const baseUrl = `https://api.asgardeo.io/t/${config.orgName}`;
    const redirectUri = 'http://localhost:3000';
    const Scope = 'openid Technical-Specialist Support-Coordinator';

    const { codeVerifier, codeChallenge } = generatePKCE();
    const { flowId, authenticatorId } = await initiateAuthorize(
      baseUrl, config.clientId, redirectUri, Scope, codeChallenge
    );
    const code = await submitCredentials(
      baseUrl, flowId, authenticatorId, credentials.agentId, credentials.agentSecret
    );
    const tokenResponse = await exchangeCodeForToken(
      baseUrl, config.clientId, redirectUri, code, codeVerifier
    );

    if (!tokenResponse.access_token) {
      throw new Error(`No access_token in token response: ${JSON.stringify(tokenResponse)}`);
    }

    return NextResponse.json(tokenResponse);
  } catch (error) {
    console.error('Agent token error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error occurred' },
      { status: 500 }
    );
  }
}
