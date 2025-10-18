// app/api/oauth/discover/route.ts - OAuth discovery endpoint
import { NextRequest, NextResponse } from 'next/server';

/**
 * Server-side OAuth discovery to avoid CORS issues
 * Discovers the authorization server for a given MCP URL
 */
export async function POST(request: NextRequest) {
  try {
    const { mcpUrl } = await request.json();
    
    if (!mcpUrl) {
      return NextResponse.json(
        { error: 'MCP URL is required' },
        { status: 400 }
      );
    }
    
    console.log('🔍 ========================================');
    console.log('🔍 Starting OAuth discovery for:', mcpUrl);
    console.log('🔍 ========================================');
    console.log('📡 Watch Network tab for these requests:');
    console.log('   1. GET /.well-known/oauth-protected-resource');
    console.log('   2. POST to MCP server (expect 401)');
    console.log('   3. GET /.well-known/oauth-authorization-server');
    console.log('   4. GET /.well-known/openid-configuration');
    console.log('');
    
    const url = new URL(mcpUrl);
    const baseUrl = `${url.protocol}//${url.host}`;
    
    // Step 1: Try /.well-known/oauth-protected-resource (RFC 8414)
    console.log('📍 Step 1: Checking protected resource metadata (RFC 8414)...');
    console.log('   → Trying:', `${baseUrl}/.well-known/oauth-protected-resource`);
    try {
      const protectedResourceResponse = await fetch(`${baseUrl}/.well-known/oauth-protected-resource`, {
        headers: {
          'Accept': 'application/json'
        }
      });
      
      if (protectedResourceResponse.ok) {
        const protectedResourceMetadata = await protectedResourceResponse.json();
        console.log('   ✅ Protected resource metadata found!');
        console.log('   📋 Metadata:', protectedResourceMetadata);
        
        if (protectedResourceMetadata.authorization_servers && 
            Array.isArray(protectedResourceMetadata.authorization_servers) &&
            protectedResourceMetadata.authorization_servers.length > 0) {
          
          const authServerUrl = protectedResourceMetadata.authorization_servers[0];
          console.log('   🎯 Found authorization server:', authServerUrl);
          
          // Fetch the authorization server metadata
          const metadata = await tryFetchMetadata(authServerUrl);
          if (metadata) {
            console.log('');
            console.log('✅ ========================================');
            console.log('✅ OAuth discovery successful via protected resource metadata!');
            console.log('✅ ========================================');
            return NextResponse.json(metadata);
          }
        } else {
          console.log('   ⚠️  No authorization_servers array in metadata');
        }
      } else {
        console.log('   ⚠️  Not found (HTTP', protectedResourceResponse.status + ')');
      }
    } catch (error) {
      console.log('   ❌ Failed:', error instanceof Error ? error.message : 'Unknown error');
    }
    
    // Step 2: Try to access the protected resource
    try {
      console.log('');
      console.log('📍 Step 2: Checking if resource is protected...');
      console.log('   → Sending POST to:', mcpUrl);
      const protectedResponse = await fetch(mcpUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          jsonrpc: '2.0',
          id: 0,
          method: 'initialize',
          params: {
            protocolVersion: '2024-11-05',
            capabilities: {},
            clientInfo: { name: 'mcp-oauth-client', version: '1.0.0' }
          }
        })
      });
      
      console.log('   ← Response status:', protectedResponse.status);
      console.log('   ← Response headers:', Object.fromEntries(protectedResponse.headers.entries()));
      
      if (protectedResponse.status === 401) {
        const wwwAuth = protectedResponse.headers.get('WWW-Authenticate');
        console.log('   ✅ Resource is protected!');
        console.log('   📋 WWW-Authenticate header:', wwwAuth);
        
        if (wwwAuth) {
          // Parse WWW-Authenticate header to extract authorization server URL
          const realmMatch = wwwAuth.match(/realm="([^"]+)"/);
          if (realmMatch && realmMatch[1]) {
            const authServerUrl = realmMatch[1];
            console.log('   🎯 Found auth server URL in realm:', authServerUrl);
            
            // Try to fetch metadata from the realm URL
            const metadata = await tryFetchMetadata(authServerUrl);
            if (metadata) {
              console.log('');
              console.log('✅ ========================================');
              console.log('✅ OAuth discovery successful via WWW-Authenticate!');
              console.log('✅ ========================================');
              return NextResponse.json(metadata);
            }
          } else {
            console.log('   ⚠️  WWW-Authenticate header found but no realm specified');
            console.log('   💡 Expected format: Bearer realm="https://..."');
          }
        } else {
          console.log('   ⚠️  No WWW-Authenticate header in 401 response');
          console.log('   💡 Server should return WWW-Authenticate header with realm');
        }
      } else if (protectedResponse.status === 200) {
        console.log('   ⚠️  Resource is NOT protected (returned 200)');
        console.log('   💡 If OAuth is required, server should return 401');
      } else {
        console.log('   ⚠️  Unexpected status code:', protectedResponse.status);
        console.log('   💡 Expected 401 for protected resources');
      }
    } catch (error) {
      console.log('   ❌ Protected resource check failed with error:');
      console.log('   ', error instanceof Error ? error.message : error);
    }
    
    // Step 3: Try /.well-known/oauth-authorization-server
    console.log('');
    console.log('📍 Step 3: Trying standard OAuth discovery endpoint...');
    console.log('   → Trying:', `${baseUrl}/.well-known/oauth-authorization-server`);
    let metadata = await tryFetchMetadata(`${baseUrl}/.well-known/oauth-authorization-server`);
    if (metadata) {
      console.log('');
      console.log('✅ ========================================');
      console.log('✅ OAuth discovery successful via .well-known!');
      console.log('✅ ========================================');
      return NextResponse.json(metadata);
    }
    
    // Try with resource path
    const resourcePath = url.pathname.split('/').slice(0, -1).join('/');
    if (resourcePath) {
      console.log('   → Trying with resource path:', `${baseUrl}${resourcePath}/.well-known/oauth-authorization-server`);
      metadata = await tryFetchMetadata(`${baseUrl}${resourcePath}/.well-known/oauth-authorization-server`);
      if (metadata) {
        console.log('');
        console.log('✅ ========================================');
        console.log('✅ OAuth discovery successful via resource path!');
        console.log('✅ ========================================');
        return NextResponse.json(metadata);
      }
    }
    
    // Step 4: Try /.well-known/openid-configuration
    console.log('');
    console.log('📍 Step 4: Trying OpenID Connect discovery...');
    console.log('   → Trying:', `${baseUrl}/.well-known/openid-configuration`);
    metadata = await tryFetchMetadata(`${baseUrl}/.well-known/openid-configuration`);
    if (metadata) {
      console.log('');
      console.log('✅ ========================================');
      console.log('✅ OAuth discovery successful via OpenID Connect!');
      console.log('✅ ========================================');
      return NextResponse.json(metadata);
    }
    
    // Try with resource path
    if (resourcePath) {
      console.log('   → Trying with resource path:', `${baseUrl}${resourcePath}/.well-known/openid-configuration`);
      metadata = await tryFetchMetadata(`${baseUrl}${resourcePath}/.well-known/openid-configuration`);
      if (metadata) {
        console.log('');
        console.log('✅ ========================================');
        console.log('✅ OAuth discovery successful!');
        console.log('✅ ========================================');
        return NextResponse.json(metadata);
      }
    }
    
    console.log('');
    console.log('❌ ========================================');
    console.log('❌ No authorization server metadata found');
    console.log('❌ ========================================');
    console.log('💡 Make sure your MCP server has one of:');
    console.log('   1. /.well-known/oauth-protected-resource (RFC 8414), OR');
    console.log('   2. Returns 401 with WWW-Authenticate header, OR');
    console.log('   3. /.well-known/oauth-authorization-server endpoint, OR');
    console.log('   4. /.well-known/openid-configuration endpoint');
    console.log('');
    return NextResponse.json(
      { error: 'No authorization server found' },
      { status: 404 }
    );
  } catch (error: any) {
    console.error('Discovery error:', error);
    return NextResponse.json(
      { error: `Discovery failed: ${error.message}` },
      { status: 500 }
    );
  }
}

/**
 * Try to fetch authorization server metadata from a URL
 */
async function tryFetchMetadata(url: string): Promise<any | null> {
  try {
    console.log('      🔄 Fetching:', url);
    const response = await fetch(url, {
      headers: {
        'Accept': 'application/json'
      }
    });
    
    if (response.ok) {
      const metadata = await response.json();
      
      // Validate that it has required OAuth endpoints
      if (metadata.authorization_endpoint && metadata.token_endpoint) {
        console.log('      ✅ Valid metadata found!');
        console.log('         - Authorization:', metadata.authorization_endpoint);
        console.log('         - Token:', metadata.token_endpoint);
        return metadata;
      } else {
        console.log('      ❌ Invalid metadata (missing required endpoints)');
      }
    } else {
      console.log('      ⚠️  Not found (HTTP', response.status + ')');
    }
  } catch (error) {
    console.log('      ❌ Fetch failed:', error instanceof Error ? error.message : 'Unknown error');
  }
  
  return null;
}
