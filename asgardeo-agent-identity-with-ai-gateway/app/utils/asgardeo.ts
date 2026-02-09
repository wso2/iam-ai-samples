/**
 * Utility functions to manage Asgardeo configuration from session storage
 */

export interface AsgardeoConfig {
  orgName: string;
  clientId: string;
}

export interface UserInfo {
  sub?: string;
  email?: string;
  username?: string;
  given_name?: string;
  family_name?: string;
}

/**
 * Get Asgardeo configuration from session storage
 */
export function getAsgardeoConfig(): AsgardeoConfig | null {
  if (typeof window === 'undefined') return null;
  
  const config = sessionStorage.getItem('asgardeo-config');
  return config ? JSON.parse(config) : null;
}

/**
 * Save Asgardeo configuration to session storage
 */
export function saveAsgardeoConfig(config: AsgardeoConfig): void {
  if (typeof window === 'undefined') return;
  
  sessionStorage.setItem('asgardeo-config', JSON.stringify(config));
}

/**
 * Get user info from session storage
 */
export function getUserInfo(): UserInfo | null {
  if (typeof window === 'undefined') return null;
  
  const userInfo = sessionStorage.getItem('user-info');
  return userInfo ? JSON.parse(userInfo) : null;
}

/**
 * Get access token from session storage
 */
export function getAccessToken(): string | null {
  if (typeof window === 'undefined') return null;
  
  return sessionStorage.getItem('access-token');
}

/**
 * Check if user is authenticated
 */
export function isAuthenticated(): boolean {
  return !!getUserInfo() && !!getAccessToken();
}

/**
 * Clear all authentication data
 */
export function clearAuth(): void {
  if (typeof window === 'undefined') return;
  
  sessionStorage.removeItem('asgardeo-config');
  sessionStorage.removeItem('user-info');
  sessionStorage.removeItem('access-token');
  sessionStorage.removeItem('pkce_code_verifier');
  sessionStorage.removeItem('agent-config');
}
