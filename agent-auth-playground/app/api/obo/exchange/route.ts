import { NextRequest, NextResponse } from 'next/server';
import { exchangeOBOCode } from '@/lib/oboAuth';

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { authCode, agentAccessToken, codeVerifier, baseUrl, clientId, redirectUri } = body;

    if (!authCode || !agentAccessToken || !codeVerifier || !baseUrl || !clientId || !redirectUri) {
      return NextResponse.json(
        { error: 'Missing required fields: authCode, agentAccessToken, codeVerifier, baseUrl, clientId, redirectUri' },
        { status: 400 }
      );
    }

    const { accessToken, expiresIn } = await exchangeOBOCode(
      baseUrl,
      clientId,
      redirectUri,
      authCode,
      agentAccessToken,
      codeVerifier
    );

    return NextResponse.json({ accessToken, expiresIn });
  } catch (error) {
    console.error('[OBO Exchange] Error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'OBO token exchange failed' },
      { status: 500 }
    );
  }
}
