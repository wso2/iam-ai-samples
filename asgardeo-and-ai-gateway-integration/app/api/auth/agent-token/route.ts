import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const { orgName, clientId, agentId, agentSecret } = await request.json();

    if (!orgName || !clientId || !agentId || !agentSecret) {
      return NextResponse.json(
        { error: 'Missing required fields: orgName, clientId, agentId, agentSecret' },
        { status: 400 }
      );
    }

    const baseUrl = `https://api.asgardeo.io/t/${orgName}`;

    // Get token using Resource Owner Password Credentials grant
    // Agent credentials are used as username/password
    // Application Client ID is used as the OAuth client
    const tokenResponse = await fetch(`${baseUrl}/oauth2/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'password',
        client_id: clientId,
        username: agentId,
        password: agentSecret,
        scope: 'openid'
      }),
    });

    if (!tokenResponse.ok) {
      const errorData = await tokenResponse.text();
      console.error('Agent token request failed:', errorData);
      return NextResponse.json(
        { error: 'Failed to authenticate agent. Check agent credentials and client ID.', details: errorData },
        { status: tokenResponse.status }
      );
    }

    const tokens = await tokenResponse.json();

    return NextResponse.json({
      access_token: tokens.access_token,
      token_type: tokens.token_type,
      expires_in: tokens.expires_in,
      scope: tokens.scope
    });
  } catch (error) {
    console.error('Error getting agent token:', error);
    return NextResponse.json(
      { error: 'Failed to get agent token', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
