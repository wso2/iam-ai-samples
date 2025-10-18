// app/api/mcp/route.ts - Proxy for MCP Server with SSE support
// Handles Streamable HTTP transport as used by MCP Inspector
import { NextRequest, NextResponse } from 'next/server';

// Store sessions in memory (in production, use Redis or similar)
const sessions = new Map<string, string>();

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const mcpUrl = request.headers.get('x-mcp-url');
    const mcpToken = request.headers.get('x-mcp-token');
    const sessionId = request.headers.get('x-session-id');

    console.log('=== MCP Proxy Request ===');
    console.log('URL:', mcpUrl);
    console.log('Session ID from client:', sessionId);
    console.log('Method:', body.method);
    console.log('Request ID:', body.id);
    console.log('Request params:', JSON.stringify(body.params));
    console.log('Full request body:', JSON.stringify(body));
    console.log('Has Token:', mcpToken ? 'Yes (Bearer ' + mcpToken.substring(0, 20) + '...)' : 'No');

    if (!mcpUrl) {
      return NextResponse.json(
        { error: 'MCP URL is required' },
        { status: 400 }
      );
    }

    const headers: HeadersInit = {
      'Content-Type': 'application/json',
      'Accept': 'application/json, text/event-stream',  // Required for MCP SSE transport
    };

    if (mcpToken) {
      headers['Authorization'] = `Bearer ${mcpToken}`;
      console.log('Adding Authorization header: Bearer', mcpToken.substring(0, 20) + '...');
    }

    // Add session ID using the correct header name for Streamable HTTP transport
    // Note: On first request (initialize), there is no session ID yet
    if (sessionId) {
      headers['mcp-session-id'] = sessionId;  // Streamable HTTP format
      console.log('Sending mcp-session-id header:', sessionId);
    } else {
      console.log('No session ID - this should be the initialize request');
    }

    let response;
    try {
      response = await fetch(mcpUrl, {
        method: 'POST',
        headers,
        body: JSON.stringify(body),
      });
    } catch (fetchError: any) {
      console.error('Fetch error:', fetchError);
      
      // Handle common fetch errors
      let errorMessage = 'Failed to connect to MCP server';
      if (fetchError.code === 'ECONNREFUSED') {
        errorMessage = `Connection refused: Cannot connect to ${mcpUrl}. Is the server running?`;
      } else if (fetchError.code === 'ENOTFOUND') {
        errorMessage = `Host not found: ${mcpUrl}`;
      } else if (fetchError.code === 'ETIMEDOUT') {
        errorMessage = `Connection timeout: ${mcpUrl}`;
      } else if (fetchError.message) {
        errorMessage = `Connection error: ${fetchError.message}`;
      }
      
      return NextResponse.json(
        { 
          error: {
            code: -32603,
            message: errorMessage,
            data: {
              url: mcpUrl,
              error: fetchError.message,
              code: fetchError.code
            }
          }
        },
        { status: 503 }
      );
    }

    console.log('Response status:', response.status);
    const mcpSessionIdFromServer = response.headers.get('mcp-session-id');
    console.log('Server returned mcp-session-id:', mcpSessionIdFromServer);
    
    // Log error responses
    if (!response.ok) {
      console.log('⚠️  HTTP Error Status:', response.status, response.statusText);
      
      // Try to read error response body
      const errorText = await response.text();
      console.log('Error response body:', errorText);
      
      // Handle 401 Unauthorized - OAuth required
      if (response.status === 401) {
        const wwwAuth = response.headers.get('WWW-Authenticate');
        console.log('WWW-Authenticate header:', wwwAuth);
        
        // Return OAuth error to client
        return NextResponse.json(
          {
            error: {
              code: -32001,
              message: 'Authentication required',
              data: {
                www_authenticate: wwwAuth,
                requires_oauth: true
              }
            }
          },
          { status: 401 }
        );
      }
      
      // Handle 404 Not Found
      if (response.status === 404) {
        return NextResponse.json(
          {
            error: {
              code: -32601,
              message: `MCP endpoint not found: ${mcpUrl}`,
              data: {
                statusCode: 404,
                statusText: response.statusText,
                body: errorText
              }
            }
          },
          { status: 404 }
        );
      }
      
      // Handle other HTTP errors
      return NextResponse.json(
        {
          error: {
            code: -32603,
            message: `Server error: ${response.status} ${response.statusText}`,
            data: {
              statusCode: response.status,
              statusText: response.statusText,
              body: errorText
            }
          }
        },
        { status: response.status }
      );
    }

    // Check if response is SSE stream
    const contentType = response.headers.get('content-type');
    
    if (contentType?.includes('text/event-stream')) {
      // Handle SSE stream
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
              const data = line.slice(6);
              if (data === '[DONE]') continue;
              
              try {
                const parsed = JSON.parse(data);
                // For MCP, we typically want the last complete message
                result = data;
              } catch (e) {
                // Skip malformed JSON
              }
            }
          }
        }
      }
      
      // Return the last complete JSON-RPC message with session info
      const jsonResponse = JSON.parse(result || '{}');
      const responseHeaders = new Headers();
      
      // Pass session ID back if present - check both header formats
      const responseSessionId = response.headers.get('mcp-session-id') || response.headers.get('x-session-id');
      if (responseSessionId) {
        responseHeaders.set('x-session-id', responseSessionId);
      }
      
      // Preserve the HTTP status code from the server
      return NextResponse.json(jsonResponse, { 
        status: response.status,
        headers: responseHeaders 
      });
    }

    // Handle regular JSON response
    let data;
    try {
      const text = await response.text();
      console.log('Response body length:', text.length);
      console.log('Response body:', text.substring(0, 500)); // Log first 500 chars
      
      // Check if response is empty
      if (!text || text.trim().length === 0) {
        console.error('Empty response body received');
        return NextResponse.json(
          { 
            error: {
              code: -32700,
              message: 'Parse error: Server returned empty response',
              data: {
                statusCode: response.status,
                statusText: response.statusText,
                contentType: response.headers.get('content-type'),
                bodyLength: 0
              }
            }
          },
          { status: 500 }
        );
      }
      
      // Try to parse as JSON
      try {
        data = JSON.parse(text);
      } catch (parseError) {
        console.error('Failed to parse response as JSON:', parseError);
        console.error('Response text:', text);
        
        // Return error with the actual response
        return NextResponse.json(
          { 
            error: {
              code: -32700,
              message: 'Parse error: Server returned non-JSON response',
              data: {
                statusCode: response.status,
                statusText: response.statusText,
                body: text,
                contentType: response.headers.get('content-type')
              }
            }
          },
          { status: 500 }
        );
      }
    } catch (readError: any) {
      console.error('Failed to read response body:', readError);
      return NextResponse.json(
        { 
          error: {
            code: -32603,
            message: 'Internal error: Could not read server response',
            data: { error: readError.message }
          }
        },
        { status: 500 }
      );
    }
    
    const responseHeaders = new Headers();
    
    // Pass session ID back if present - check both header formats
    const responseSessionId = response.headers.get('mcp-session-id') || response.headers.get('x-session-id');
    if (responseSessionId) {
      responseHeaders.set('x-session-id', responseSessionId);
    }
    
    // Preserve the HTTP status code from the server
    return NextResponse.json(data, { 
      status: response.status,
      headers: responseHeaders 
    });
  } catch (error: any) {
    console.error('MCP Proxy Error:', error);
    console.error('Error stack:', error?.stack);
    console.error('Error message:', error?.message);
    return NextResponse.json(
      { 
        error: `Proxy error: ${error?.message || error}`,
        details: error?.stack,
        type: error?.constructor?.name
      },
      { status: 500 }
    );
  }
}
