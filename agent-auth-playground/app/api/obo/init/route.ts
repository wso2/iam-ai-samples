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
