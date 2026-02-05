/**
 * PKCE (Proof Key for Code Exchange) utility functions
 * For OAuth 2.0 public clients
 */

/**
 * Generate a cryptographically random code verifier
 * @returns Base64-URL encoded random string
 */
export function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return base64UrlEncode(array);
}

/**
 * Generate code challenge from verifier using SHA-256
 * @param verifier The code verifier string
 * @returns Base64-URL encoded SHA-256 hash
 */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const hash = await crypto.subtle.digest('SHA-256', data);
  return base64UrlEncode(new Uint8Array(hash));
}

/**
 * Base64-URL encode a byte array
 * @param buffer Byte array to encode
 * @returns Base64-URL encoded string
 */
function base64UrlEncode(buffer: Uint8Array): string {
  const base64 = btoa(String.fromCharCode(...buffer));
  return base64
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}

/**
 * Store PKCE code verifier in session storage
 * @param verifier The code verifier to store
 */
export function storePKCEVerifier(verifier: string): void {
  if (typeof window === 'undefined') return;
  sessionStorage.setItem('pkce_code_verifier', verifier);
}

/**
 * Retrieve PKCE code verifier from session storage
 * @returns The stored code verifier or null
 */
export function getPKCEVerifier(): string | null {
  if (typeof window === 'undefined') return null;
  return sessionStorage.getItem('pkce_code_verifier');
}

/**
 * Clear PKCE code verifier from session storage
 */
export function clearPKCEVerifier(): void {
  if (typeof window === 'undefined') return;
  sessionStorage.removeItem('pkce_code_verifier');
}
