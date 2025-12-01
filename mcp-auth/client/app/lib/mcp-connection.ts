/**
 * Copyright (c) 2025, WSO2 LLC. (https://www.wso2.com).
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

/**
 * MCP Connection utilities for hybrid proxy/direct connection approach
 */

/**
 * Detects if a URL is localhost/local network address
 */
export function isLocalUrl(url: string): boolean {
  try {
    const urlObj = new URL(url);
    const hostname = urlObj.hostname.toLowerCase();

    // Check for localhost variants
    if (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '::1' ||
      hostname.startsWith('localhost.') ||
      hostname.endsWith('.localhost')
    ) {
      return true;
    }

    // Check for local IP ranges (192.168.x.x, 10.x.x.x, 172.16-31.x.x)
    if (
      hostname.startsWith('192.168.') ||
      hostname.startsWith('10.') ||
      /^172\.(1[6-9]|2[0-9]|3[0-1])\./.test(hostname)
    ) {
      return true;
    }

    // Check for host.docker.internal
    if (hostname === 'host.docker.internal') {
      return true;
    }

    return false;
  } catch (e) {
    return false;
  }
}

/**
 * Makes an MCP request - uses direct connection for localhost, proxy for remote
 */
export async function makeMcpRequest(
  mcpUrl: string,
  requestBody: any,
  sessionId?: string,
  token?: string
): Promise<{ data: any; sessionId?: string }> {
  const isLocal = isLocalUrl(mcpUrl);

  if (isLocal) {
    // Direct connection from browser to local MCP server
    console.log('🔗 Direct connection to local MCP server:', mcpUrl);

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    if (sessionId) {
      headers['mcp-session-id'] = sessionId;
      console.log('📤 Sending mcp-session-id header to local server:', sessionId);
    } else {
      console.log('⚠️  No session ID to send (this should only happen on initialize)');
    }

    try {
      const response = await fetch(mcpUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        // Handle authentication errors
        if (response.status === 401) {
          const wwwAuth = response.headers.get('WWW-Authenticate');
          throw new Error(
            JSON.stringify({
              code: -32001,
              message: 'Authentication required',
              data: {
                www_authenticate: wwwAuth,
                requires_oauth: true,
              },
            })
          );
        }

        const errorText = await response.text();
        throw new Error(`HTTP ${response.status}: ${errorText}`);
      }

      // Handle SSE response
      const contentType = response.headers.get('content-type');
      let data;

      if (contentType?.includes('text/event-stream')) {
        // Parse SSE stream
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();
        let result = '';

        if (reader) {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
              if (line.startsWith('data: ')) {
                const dataStr = line.slice(6);
                if (dataStr === '[DONE]') continue;

                try {
                  result = dataStr;
                } catch (e) {
                  // Skip malformed JSON
                }
              }
            }
          }
        }

        data = JSON.parse(result || '{}');
      } else {
        // Regular JSON response
        data = await response.json();
      }

      // Get session ID from response
      const responseSessionId = response.headers.get('mcp-session-id') || response.headers.get('x-session-id');

      console.log('📥 Received session ID from server:', responseSessionId);
      console.log('📋 Final session ID to use:', responseSessionId || sessionId);

      return {
        data,
        sessionId: responseSessionId || sessionId,
      };
    } catch (error: any) {
      // Provide helpful error messages for common CORS issues
      if (error.message?.includes('CORS') || error.name === 'TypeError') {
        throw new Error(
          `Cannot connect to ${mcpUrl}. This appears to be a CORS error.\n\n` +
          `Since you're connecting to a local server, please ensure:\n` +
          `1. Your MCP server is running on ${new URL(mcpUrl).origin}\n` +
          `2. Your MCP server has CORS enabled with appropriate headers:\n` +
          `   - Access-Control-Allow-Origin: *\n` +
          `   - Access-Control-Allow-Methods: POST, OPTIONS\n` +
          `   - Access-Control-Allow-Headers: Content-Type, Authorization, mcp-session-id\n` +
          `   - Access-Control-Expose-Headers: mcp-session-id\n\n` +
          `Original error: ${error.message}`
        );
      }
      throw error;
    }
  } else {
    // Use proxy for remote servers
    console.log('🔀 Proxying request to remote MCP server via /api/mcp');

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'x-mcp-url': mcpUrl,
    };

    if (token) {
      headers['x-mcp-token'] = token;
    }

    if (sessionId) {
      headers['x-session-id'] = sessionId;
      console.log('📤 Sending x-session-id header to proxy:', sessionId);
    } else {
      console.log('⚠️  No session ID to send to proxy (this should only happen on initialize)');
    }

    console.log('🌐 Making proxy request to /api/mcp:', {
      mcpUrl: mcpUrl,
      method: requestBody.method,
      headers: headers,
      hasSessionId: !!sessionId,
      sessionIdValue: sessionId,
    });

    const response = await fetch('/api/mcp', {
      method: 'POST',
      headers,
      body: JSON.stringify(requestBody),
    });

    const data = await response.json();

    // Check for errors in response
    if (!response.ok || data.error) {
      throw new Error(data.error?.message || data.error || `HTTP ${response.status}`);
    }

    const responseSessionId = response.headers.get('x-session-id');

    console.log('📥 Received session ID from proxy:', responseSessionId);
    console.log('📋 Final session ID to use:', responseSessionId || sessionId);

    return {
      data,
      sessionId: responseSessionId || sessionId,
    };
  }
}

/**
 * Discovers OAuth metadata - uses direct connection for localhost, proxy for remote
 */
export async function discoverOAuth(mcpUrl: string): Promise<any> {
  const isLocal = isLocalUrl(mcpUrl);

  if (isLocal) {
    // Direct discovery from browser
    console.log('🔗 Direct OAuth discovery for local server:', mcpUrl);

    const urlObj = new URL(mcpUrl);
    const baseUrl = `${urlObj.protocol}//${urlObj.host}`;

    // Try discovery endpoints
    const discoveryUrls = [
      `${baseUrl}/.well-known/oauth-protected-resource`,
      `${baseUrl}/.well-known/oauth-authorization-server`,
      `${baseUrl}/.well-known/openid-configuration`,
      `${mcpUrl}/.well-known/oauth-authorization-server`,
      `${mcpUrl}/.well-known/openid-configuration`,
    ];

    for (const url of discoveryUrls) {
      try {
        const response = await fetch(url);
        if (response.ok) {
          const metadata = await response.json();
          return metadata;
        }
      } catch (e) {
        // Continue to next URL
      }
    }

    throw new Error('No OAuth metadata found at standard discovery endpoints');
  } else {
    // Use proxy for remote servers
    console.log('🔀 Proxying OAuth discovery via /api/oauth/discover');

    const response = await fetch('/api/oauth/discover', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mcpUrl }),
    });

    const data = await response.json();

    if (!response.ok || data.error) {
      throw new Error(data.error || 'Discovery failed');
    }

    return data.metadata;
  }
}
