import { NextRequest, NextResponse } from 'next/server';
import { MCPClientNodeRuntime } from '@/lib/mcpClientNode';
import { authenticateAgent } from '@/lib/agentAuth';

export const maxDuration = 60;

interface InitializeMCPBody {
  endpoint?: string;
  oauth2?: {
    flow?: 'agent' | 'obo';
    baseUrl?: string;
    clientId?: string;
    redirectUri?: string;
    scope?: string;
    agentId?: string;
    agentSecret?: string;
  };
}

export async function POST(request: NextRequest) {
  let runtime: MCPClientNodeRuntime | null = null;
  try {
    const body = (await request.json()) as InitializeMCPBody;
    const endpoint = body.endpoint?.trim();

    if (!endpoint) {
      return NextResponse.json(
        { success: false, error: 'MCP server endpoint is required.' },
        { status: 400 }
      );
    }

    runtime = new MCPClientNodeRuntime();

    if (body.oauth2) {
      const { baseUrl, clientId, redirectUri, scope, agentId, agentSecret } = body.oauth2;
      if (!baseUrl || !clientId || !redirectUri || !agentId || !agentSecret) {
        return NextResponse.json(
          {
            success: false,
            error:
              'OAuth2 configuration is incomplete. Provide baseUrl, clientId, redirectUri, agentId, and agentSecret.',
          },
          { status: 400 }
        );
      }

      const token = await authenticateAgent({
        baseUrl,
        clientId,
        redirectUri,
        scope,
        agentId,
        agentSecret,
      });
      runtime.setAccessToken(token);
    }

    await runtime.connect(endpoint);
    const tools = await runtime.listTools();

    return NextResponse.json({ success: true, tools });
  } catch (error) {
    console.error('MCP initialization error:', error);
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : 'Failed to initialize MCP client.' },
      { status: 500 }
    );
  } finally {
    if (runtime) {
      await runtime.disconnect().catch(() => undefined);
    }
  }
}
