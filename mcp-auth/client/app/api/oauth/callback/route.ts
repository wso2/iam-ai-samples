// app/api/oauth/callback/route.ts - OAuth callback handler
import { NextRequest, NextResponse } from 'next/server';

/**
 * Handle OAuth callback from authorization server
 * This endpoint receives the authorization code and state parameter
 * The actual token exchange happens on the client side for security
 */
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const code = searchParams.get('code');
  const state = searchParams.get('state');
  const error = searchParams.get('error');
  const errorDescription = searchParams.get('error_description');
  
  console.log('OAuth callback received:', { code, state, error });
  
  // Handle OAuth errors
  if (error) {
    const errorMsg = errorDescription || error;
    return new NextResponse(
      `
      <!DOCTYPE html>
      <html>
        <head>
          <title>OAuth Error</title>
          <script>
            // Send error to parent window
            window.opener?.postMessage({
              type: 'oauth-error',
              error: '${error}',
              error_description: '${errorMsg}'
            }, window.location.origin);
            
            // Keep window open briefly to show error
            setTimeout(() => {
              try {
                window.close();
              } catch (e) {
                console.error('Could not close window:', e);
              }
            }, 2000);
          </script>
        </head>
        <body>
          <h1>OAuth Error</h1>
          <p>${errorMsg}</p>
          <p><small>This window will close automatically in 2 seconds.</small></p>
        </body>
      </html>
      `,
      {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      }
    );
  }
  
  // Handle successful authorization
  if (code && state) {
    return new NextResponse(
      `
      <!DOCTYPE html>
      <html>
        <head>
          <title>OAuth Success</title>
          <script>
            // Send code and state to parent window
            window.opener?.postMessage({
              type: 'oauth-callback',
              code: '${code}',
              state: '${state}'
            }, window.location.origin);
            
            // Keep window open briefly to ensure message is received
            setTimeout(() => {
              try {
                window.close();
              } catch (e) {
                console.error('Could not close window:', e);
              }
            }, 1000);
          </script>
        </head>
        <body>
          <h1>Authorization Successful</h1>
          <p>Redirecting back to application...</p>
          <p><small>This window will close automatically in 1 second.</small></p>
        </body>
      </html>
      `,
      {
        status: 200,
        headers: { 'Content-Type': 'text/html' },
      }
    );
  }
  
  // Invalid callback
  return new NextResponse(
    `
    <!DOCTYPE html>
    <html>
      <head>
        <title>Invalid OAuth Callback</title>
      </head>
      <body>
        <h1>Invalid OAuth Callback</h1>
        <p>Missing required parameters (code or state)</p>
      </body>
    </html>
    `,
    {
      status: 400,
      headers: { 'Content-Type': 'text/html' },
    }
  );
}
