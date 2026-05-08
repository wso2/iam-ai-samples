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
import { NextRequest, NextResponse } from 'next/server';
import { authenticateAgent } from '@/lib/agentAuth';
import { buildOBOAuthorizationUrl } from '@/lib/oboAuth';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { baseUrl, clientId, redirectUri, scope, agentId, agentSecret } = body;

    if (!baseUrl || !clientId || !redirectUri || !agentId || !agentSecret) {
      return NextResponse.json(
        { error: 'Missing required fields: baseUrl, clientId, redirectUri, agentId, agentSecret' },
        { status: 400 }
      );
    }

    // Get agent's own access token first (needed as actor_token in OBO exchange)
    const agentAccessToken = await authenticateAgent({
      baseUrl,
      clientId,
      redirectUri,
      agentId,
      agentSecret,
      scope,
    });

    // Build authorization URL with PKCE and requested_actor = agentId
    const { authUrl, state, codeVerifier } = buildOBOAuthorizationUrl({
      baseUrl,
      clientId,
      redirectUri,
      scope,
      agentId,
    });

    return NextResponse.json({ authUrl, state, codeVerifier, agentAccessToken });
  } catch (error) {
    console.error('[OBO Init] Error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'OBO initialization failed' },
      { status: 500 }
    );
  }
}
