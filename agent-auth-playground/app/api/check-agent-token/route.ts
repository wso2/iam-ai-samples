import { NextRequest, NextResponse } from 'next/server';
import { authenticateAgent } from '@/lib/agentAuth';

export async function POST(req: NextRequest) {
  try {
    const { baseUrl, clientId, agentId, agentSecret, scope, redirectUri } = await req.json();

    if (!baseUrl || !clientId || !agentId || !agentSecret || !redirectUri) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const token = await authenticateAgent({
      baseUrl,
      clientId,
      redirectUri,
      agentId,
      agentSecret,
      scope: scope || 'openid',
    });

    return NextResponse.json({ token });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to fetch agent token';
    console.log(message)
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
