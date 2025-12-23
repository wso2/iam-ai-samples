"""
 Copyright (c) 2025, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.

  This software is the property of WSO2 LLC. and its suppliers, if any.
  Dissemination of any information or reproduction of any material contained
  herein is strictly forbidden, unless permitted by WSO2 in accordance with
  the WSO2 Commercial License available at http://wso2.com/licenses.
  For specific language governing the permissions and limitations under
  this license, please see the license as well as any agreement you've
  entered into with WSO2 governing the purchase of this software and any


  OAuth Callback Listener

  This module provides a lightweight local HTTP server used to capture OAuth 2.1
  redirect responses during OBO agent authentication flow.

  This listens on a localhost port, receives the authorization code returned by the
  identity provider (Asgardeo), and makes it available to the application.

"""

import http.server
import socketserver
import threading
import asyncio
from urllib.parse import urlparse, parse_qs

class OAuthCallbackServer:
    def __init__(self, port: int = 6274, timeout: int = 120):
        self.port = port
        self.timeout = timeout
        self.auth_code = None
        self.state = None
        self._error = None
        self._httpd = None

    class _Handler(http.server.SimpleHTTPRequestHandler):
        parent = None

        def do_GET(self):
            url = urlparse(self.path)
            params = parse_qs(url.query)

            # OAuth error case
            if "error" in params:
                self.parent._error = params["error"][0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authorization cancelled or failed. You can close this window.")
                return

            # Success case
            if "code" in params:
                self.parent.auth_code = params["code"][0]
                self.parent.state = params.get("state", [None])[0]
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Authentication successful. You can close this window.")
                return

            # Invalid callback
            if url.path != "/oauth/callback":
                self.parent._error = "Invalid Callback URL"
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"Invalid redirect. You can close this window.")
                return

    def start(self):
        handler = self._Handler
        handler.parent = self

        self._httpd = socketserver.TCPServer(("localhost", self.port), handler)
        thread = threading.Thread(target=self._httpd.serve_forever)
        thread.daemon = True
        thread.start()

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()

    async def wait_for_code(self):
        """Returns (auth_code, state). auth_code==None means canceled, error, or timed out."""
        elapsed = 0
        while self.auth_code is None and self._error is None and elapsed < self.timeout:
            await asyncio.sleep(0.1)
            elapsed += 0.1

        return (self.auth_code, self.state, self._error)