// app/lib/oauth-utils.ts - OAuth 2.0 utilities for MCP OAuth authentication
// Implements MCP OAuth specification with discovery and PKCE flow

/**
 * OAuth Protected Resource Metadata (RFC 8707)
 */
export interface ProtectedResourceMetadata {
  resource: string;
  authorization_servers: string[];
  scopes_supported?: string[];
  bearer_methods_supported?: string[];
  [key: string]: any;
}

/**
 * OAuth Authorization Server Metadata
 */
export interface AuthorizationServerMetadata {
  issuer: string;
  authorization_endpoint: string;
  token_endpoint: string;
  response_types_supported?: string[];
  grant_types_supported?: string[];
  code_challenge_methods_supported?: string[];
  scopes_supported?: string[]; // Scopes from protected resource metadata
  [key: string]: any;
}

/**
 * OAuth Token Response
 */
export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in?: number;
  refresh_token?: string;
  scope?: string;
}

/**
 * PKCE (Proof Key for Code Exchange) values
 */
export interface PKCEValues {
  codeVerifier: string;
  codeChallenge: string;
  codeChallengeMethod: string;
}

/**
 * OAuth State for managing the flow
 */
export interface OAuthState {
  state: string;
  codeVerifier: string;
  redirectUri: string;
  mcpUrl: string;
  clientId: string;
}

/**
 * Generate random string for state or code verifier
 */
function generateRandomString(length: number = 43): string {
  const charset = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~';
  const randomValues = new Uint8Array(length);
  crypto.getRandomValues(randomValues);
  return Array.from(randomValues)
    .map(v => charset[v % charset.length])
    .join('');
}

/**
 * Generate SHA-256 hash and return base64url encoded string
 */
async function sha256(plain: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(plain);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return base64urlEncode(hash);
}

/**
 * Base64URL encode an ArrayBuffer
 */
function base64urlEncode(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

/**
 * Generate PKCE values (code verifier and challenge)
 */
export async function generatePKCE(): Promise<PKCEValues> {
  const codeVerifier = generateRandomString(43);
  const codeChallenge = await sha256(codeVerifier);
  
  return {
    codeVerifier,
    codeChallenge,
    codeChallengeMethod: 'S256'
  };
}

/**
 * Generate OAuth state parameter
 */
export function generateState(): string {
  return generateRandomString(32);
}

/**
 * Discover OAuth authorization server for an MCP resource URL
 * Implements the MCP OAuth discovery flow:
 * 1. Try to access the protected resource (will return 401 with WWW-Authenticate)
 * 2. Check /.well-known/oauth-protected-resource (RFC 8707)
 * 3. Check /.well-known/oauth-authorization-server (RFC 8414)
 * 4. Check /.well-known/openid-configuration (OpenID Connect)
 * 
 * @param mcpUrl - The MCP server URL
 * @returns Authorization server metadata or null if not found
 */
export async function discoverAuthorizationServer(
  mcpUrl: string
): Promise<AuthorizationServerMetadata | null> {
  try {
    const url = new URL(mcpUrl);
    const baseUrl = `${url.protocol}//${url.host}`;
    const resourcePath = url.pathname.split('/').slice(0, -1).join('/');
    
    console.log('🔍 Starting OAuth discovery for:', mcpUrl);
    console.log('Base URL:', baseUrl);
    console.log('Resource path:', resourcePath || '(none)');
    
    // Step 1: Try to access the protected resource
    // This should return 401 with WWW-Authenticate header pointing to auth server
    try {
      console.log('Step 1: Trying to access protected resource:', mcpUrl);
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
      
      console.log('Protected resource response status:', protectedResponse.status);
      
      if (protectedResponse.status === 401) {
        const wwwAuth = protectedResponse.headers.get('WWW-Authenticate');
        console.log('WWW-Authenticate header:', wwwAuth);
        
        if (wwwAuth) {
          // Parse WWW-Authenticate header to extract authorization server URL
          // Format: Bearer realm="https://auth.example.com"
          const realmMatch = wwwAuth.match(/realm="([^"]+)"/);
          if (realmMatch && realmMatch[1]) {
            const authServerUrl = realmMatch[1];
            console.log('✅ Found auth server in WWW-Authenticate:', authServerUrl);
            
            // Try to fetch metadata from the realm URL
            const metadata = await fetchAuthServerMetadata(authServerUrl);
            if (metadata) {
              return metadata;
            }
          }
        }
      }
    } catch (error) {
      console.log('❌ Protected resource access failed:', error);
    }
    
    // Step 2: Try /.well-known/oauth-protected-resource (RFC 8707)
    // This endpoint describes the resource server and its authorization servers
    console.log('Step 2: Trying /.well-known/oauth-protected-resource');
    
    // Try at base URL
    let protectedResourceMeta = await tryFetchProtectedResourceMetadata(`${baseUrl}/.well-known/oauth-protected-resource`);
    if (protectedResourceMeta) {
      return protectedResourceMeta;
    }
    
    // Try with resource path
    if (resourcePath) {
      protectedResourceMeta = await tryFetchProtectedResourceMetadata(`${baseUrl}${resourcePath}/.well-known/oauth-protected-resource`);
      if (protectedResourceMeta) {
        return protectedResourceMeta;
      }
    }
    
    // Step 3: Try /.well-known/oauth-authorization-server
    console.log('Step 3: Trying /.well-known/oauth-authorization-server');
    const oauthWellKnown = `${baseUrl}/.well-known/oauth-authorization-server`;
    try {
      const response = await fetch(oauthWellKnown);
      if (response.ok) {
        const metadata = await response.json();
        console.log('✅ Found OAuth metadata at:', oauthWellKnown);
        return metadata;
      }
      console.log('❌ OAuth well-known not found:', response.status);
    } catch (error) {
      console.log('❌ OAuth well-known fetch failed:', error);
    }
    
    // Try with resource path
    if (resourcePath) {
      const oauthWellKnownWithPath = `${baseUrl}${resourcePath}/.well-known/oauth-authorization-server`;
      console.log('Trying with resource path:', oauthWellKnownWithPath);
      try {
        const response = await fetch(oauthWellKnownWithPath);
        if (response.ok) {
          const metadata = await response.json();
          console.log('✅ Found OAuth metadata at:', oauthWellKnownWithPath);
          return metadata;
        }
      } catch (error) {
        console.log('OAuth well-known with path fetch failed:', error);
      }
    }
    
    // Step 4: Try /.well-known/openid-configuration
    console.log('Step 4: Trying /.well-known/openid-configuration');
    const oidcWellKnown = `${baseUrl}/.well-known/openid-configuration`;
    try {
      const response = await fetch(oidcWellKnown);
      if (response.ok) {
        const metadata = await response.json();
        console.log('✅ Found OpenID Connect metadata at:', oidcWellKnown);
        return metadata;
      }
      console.log('❌ OIDC well-known not found:', response.status);
    } catch (error) {
      console.log('❌ OIDC well-known fetch failed:', error);
    }
    
    // Try with resource path
    if (resourcePath) {
      const oidcWellKnownWithPath = `${baseUrl}${resourcePath}/.well-known/openid-configuration`;
      console.log('Trying with resource path:', oidcWellKnownWithPath);
      try {
        const response = await fetch(oidcWellKnownWithPath);
        if (response.ok) {
          const metadata = await response.json();
          console.log('✅ Found OpenID Connect metadata at:', oidcWellKnownWithPath);
          return metadata;
        }
      } catch (error) {
        console.log('OIDC well-known with path fetch failed:', error);
      }
    }
    
    console.log('❌ No authorization server metadata found');
    return null;
  } catch (error) {
    console.error('Discovery error:', error);
    return null;
  }
}

/**
 * Try to fetch OAuth protected resource metadata (RFC 8707)
 * This endpoint describes the resource server and points to authorization servers
 */
async function tryFetchProtectedResourceMetadata(
  url: string
): Promise<AuthorizationServerMetadata | null> {
  try {
    console.log('Trying:', url);
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Accept': 'application/json'
      },
      mode: 'cors', // Explicitly set CORS mode
    });
    
    if (response.ok) {
      const metadata = await response.json();
      console.log('Protected resource metadata received:', metadata);
      
      // RFC 8707 format: {"resource": "...", "authorization_servers": ["https://as.example.com"], "scopes_supported": ["openid", "email"]}
      if (metadata.authorization_servers && Array.isArray(metadata.authorization_servers)) {
        const authServerUrl = metadata.authorization_servers[0];
        const scopes = metadata.scopes_supported || [];
        
        console.log('✅ Found authorization server from protected resource metadata:', authServerUrl);
        if (scopes.length > 0) {
          console.log('✅ Found required scopes:', scopes.join(', '));
        }
        
        // Fetch the actual authorization server metadata and attach scopes
        const authServerMetadata = await fetchAuthServerMetadata(authServerUrl);
        if (authServerMetadata) {
          // Attach scopes from protected resource to auth server metadata
          authServerMetadata.scopes_supported = scopes;
          return authServerMetadata;
        }
      }
      
      // Some servers might directly return auth server metadata here
      if (metadata.authorization_endpoint && metadata.token_endpoint) {
        console.log('✅ Found authorization server metadata directly');
        return metadata;
      }
      
      console.log('❌ Invalid protected resource metadata (missing authorization_servers)');
    } else {
      console.log('❌ Not found:', url, response.status);
    }
  } catch (error: any) {
    console.log('❌ Fetch failed:', url);
    if (error.name === 'TypeError' && error.message.includes('Failed to fetch')) {
      console.log('⚠️  CORS error or network issue. Check:');
      console.log('   1. Server CORS headers allow origin:', window.location.origin);
      console.log('   2. Server responds to OPTIONS preflight for:', url);
      console.log('   3. Server endpoint exists and is accessible');
    } else {
      console.log('   Error:', error.message);
    }
  }
  
  return null;
}

/**
 * Fetch authorization server metadata from a given URL
 */
async function fetchAuthServerMetadata(
  authServerUrl: string
): Promise<AuthorizationServerMetadata | null> {
  try {
    // Try the base URL first (might be the metadata endpoint itself)
    try {
      const response = await fetch(authServerUrl);
      if (response.ok) {
        const metadata = await response.json();
        if (metadata.authorization_endpoint && metadata.token_endpoint) {
          console.log('✅ Found metadata at base URL:', authServerUrl);
          return metadata;
        }
      }
    } catch (e) {
      console.log('Base URL fetch failed:', e);
    }
    
    // Try well-known endpoints relative to the auth server
    const url = new URL(authServerUrl);
    const baseUrl = `${url.protocol}//${url.host}`;
    const fullPath = url.pathname.replace(/\/$/, ''); // Remove trailing slash if present
    
    // Try /.well-known/oauth-authorization-server at origin
    try {
      const oauthWellKnown = `${baseUrl}/.well-known/oauth-authorization-server`;
      console.log('Trying OAuth well-known at origin:', oauthWellKnown);
      const response = await fetch(oauthWellKnown);
      if (response.ok) {
        const metadata = await response.json();
        console.log('✅ Found OAuth metadata at:', oauthWellKnown);
        return metadata;
      }
    } catch (e) {
      console.log('OAuth well-known fetch failed:', e);
    }
    
    // Try /.well-known/oauth-authorization-server at full path
    if (fullPath) {
      try {
        const oauthWellKnownFull = `${baseUrl}${fullPath}/.well-known/oauth-authorization-server`;
        console.log('Trying OAuth well-known at full path:', oauthWellKnownFull);
        const response = await fetch(oauthWellKnownFull);
        if (response.ok) {
          const metadata = await response.json();
          console.log('✅ Found OAuth metadata at:', oauthWellKnownFull);
          return metadata;
        }
      } catch (e) {
        console.log('OAuth well-known with full path fetch failed:', e);
      }
    }
    
    // Try /.well-known/openid-configuration at origin
    try {
      const oidcWellKnown = `${baseUrl}/.well-known/openid-configuration`;
      console.log('Trying OIDC well-known at origin:', oidcWellKnown);
      const response = await fetch(oidcWellKnown);
      if (response.ok) {
        const metadata = await response.json();
        console.log('✅ Found OpenID metadata at:', oidcWellKnown);
        return metadata;
      }
    } catch (e) {
      console.log('OIDC well-known fetch failed:', e);
    }
    
    // Try /.well-known/openid-configuration at full path
    if (fullPath) {
      try {
        const oidcWellKnownFull = `${baseUrl}${fullPath}/.well-known/openid-configuration`;
        console.log('Trying OIDC well-known at full path:', oidcWellKnownFull);
        const response = await fetch(oidcWellKnownFull);
        if (response.ok) {
          const metadata = await response.json();
          console.log('✅ Found OpenID metadata at:', oidcWellKnownFull);
          return metadata;
        }
      } catch (e) {
        console.log('OIDC well-known with full path fetch failed:', e);
      }
    }
    
    return null;
  } catch (error) {
    console.error('Error fetching auth server metadata:', error);
    return null;
  }
}

/**
 * Build authorization URL for OAuth flow
 */
export function buildAuthorizationUrl(
  authorizationEndpoint: string,
  clientId: string,
  redirectUri: string,
  state: string,
  codeChallenge: string,
  codeChallengeMethod: string = 'S256',
  scope?: string
): string {
  const params = new URLSearchParams({
    response_type: 'code',
    client_id: clientId,
    redirect_uri: redirectUri,
    state: state,
    code_challenge: codeChallenge,
    code_challenge_method: codeChallengeMethod,
  });
  
  if (scope) {
    params.append('scope', scope);
  }
  
  return `${authorizationEndpoint}?${params.toString()}`;
}

/**
 * Exchange authorization code for access token
 */
export async function exchangeCodeForToken(
  tokenEndpoint: string,
  code: string,
  codeVerifier: string,
  clientId: string,
  redirectUri: string,
  clientSecret?: string
): Promise<TokenResponse> {
  const params = new URLSearchParams({
    grant_type: 'authorization_code',
    code: code,
    redirect_uri: redirectUri,
    code_verifier: codeVerifier,
    client_id: clientId,
  });
  
  if (clientSecret) {
    params.append('client_secret', clientSecret);
  }
  
  const response = await fetch(tokenEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Token exchange failed: ${error.error_description || error.error || response.statusText}`);
  }
  
  return await response.json();
}

/**
 * Refresh access token using refresh token
 */
export async function refreshAccessToken(
  tokenEndpoint: string,
  refreshToken: string,
  clientId: string,
  clientSecret?: string
): Promise<TokenResponse> {
  const params = new URLSearchParams({
    grant_type: 'refresh_token',
    refresh_token: refreshToken,
    client_id: clientId,
  });
  
  if (clientSecret) {
    params.append('client_secret', clientSecret);
  }
  
  const response = await fetch(tokenEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: params.toString(),
  });
  
  if (!response.ok) {
    const error = await response.json();
    throw new Error(`Token refresh failed: ${error.error_description || error.error || response.statusText}`);
  }
  
  return await response.json();
}

/**
 * Store OAuth state in sessionStorage
 */
export function storeOAuthState(state: OAuthState): void {
  sessionStorage.setItem('oauth_state', JSON.stringify(state));
}

/**
 * Retrieve OAuth state from sessionStorage
 */
export function retrieveOAuthState(): OAuthState | null {
  const stateStr = sessionStorage.getItem('oauth_state');
  if (!stateStr) return null;
  
  try {
    return JSON.parse(stateStr);
  } catch (error) {
    console.error('Failed to parse OAuth state:', error);
    return null;
  }
}

/**
 * Clear OAuth state from sessionStorage
 */
export function clearOAuthState(): void {
  sessionStorage.removeItem('oauth_state');
}

/**
 * Store OAuth tokens securely
 */
export function storeTokens(mcpUrl: string, tokens: TokenResponse): void {
  const key = `oauth_tokens_${btoa(mcpUrl)}`;
  const tokenData = {
    ...tokens,
    timestamp: Date.now(),
  };
  localStorage.setItem(key, JSON.stringify(tokenData));
}

/**
 * Retrieve OAuth tokens
 */
export function retrieveTokens(mcpUrl: string): TokenResponse | null {
  const key = `oauth_tokens_${btoa(mcpUrl)}`;
  const tokenStr = localStorage.getItem(key);
  if (!tokenStr) return null;
  
  try {
    const tokenData = JSON.parse(tokenStr);
    
    // Check if token is expired
    if (tokenData.expires_in && tokenData.timestamp) {
      const expiresAt = tokenData.timestamp + (tokenData.expires_in * 1000);
      if (Date.now() >= expiresAt) {
        console.log('Token expired');
        clearTokens(mcpUrl);
        return null;
      }
    }
    
    return tokenData;
  } catch (error) {
    console.error('Failed to parse tokens:', error);
    return null;
  }
}

/**
 * Clear OAuth tokens
 */
export function clearTokens(mcpUrl: string): void {
  const key = `oauth_tokens_${btoa(mcpUrl)}`;
  localStorage.removeItem(key);
}
