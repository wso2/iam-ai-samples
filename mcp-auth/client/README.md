<!--
  Copyright (c) 2025, WSO2 LLC. (https://www.wso2.com).

  WSO2 LLC. licenses this file to you under the Apache License,
  Version 2.0 (the "License"); you may not use this file except
  in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing,
  software distributed under the License is distributed on an
  "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
  KIND, either express or implied. See the License for the
  specific language governing permissions and limitations
  under the License.
-->

# WSO2 MCP AI Agent Client

A Next.js web client for connecting to MCP (Model Context Protocol) servers with OAuth 2.0 authentication support. Chat with AI models that can automatically discover and use tools from your MCP server. Features WSO2's modern design system and branding.


### How It Works

**Hybrid Connection Approach:**
- **Local MCP servers** (localhost, 127.0.0.1, 192.168.x.x): Direct connection from your browser
- **Remote MCP servers**: Proxied through the backend

When deployed to the cloud and you enter `http://localhost:8000/mcp`, the app connects directly from your browser to your local machine (not the cloud server). This means:
- ✅ Works from any cloud deployment
- ✅ Users can connect to their local MCP servers
- ⚠️ Requires CORS enabled on local MCP servers (see [CORS Requirements](#connecting-to-local-mcp-server-cors-requirements))

## Quick Start with Docker

### Build and Run
```bash
# Navigate to the client directory
cd client

# Build the Docker image
docker build -t wso2-mcp-client .

# Run the container
docker run -p 3000:3000 wso2-mcp-client
```

Access at http://localhost:3000

### Background Deployment
```bash
# Run in background with auto-restart
docker run -d --restart unless-stopped -p 3000:3000 --name mcp-client wso2-mcp-client
```

### Local Development
```bash
npm install
npm run dev
```

## How to Use

1. **Configure AI Provider**
   - Select your AI provider (OpenAI, Google Gemini, or Azure OpenAI)
   - Enter your API key
   - Enter model name:
     - OpenAI: `gpt-4o-mini` or `gpt-4`
     - Google: `gemini-2.0-flash-exp` (without models/ prefix)
     - Azure: Your deployment name

2. **Connect to MCP Server**
   - Enter your MCP server URL
     - **Local MCP server**: `http://localhost:8000/mcp`
     - **Remote server**: `https://your-server.com/mcp`

   **Important for Cloud Deployments:**
   - The app automatically detects if you're connecting to a local server (localhost, 127.0.0.1, 192.168.x.x, etc.)
   - **Local servers**: Direct connection from your browser (requires CORS - see below)
   - **Remote servers**: Proxied through the backend server

3. **Optional: OAuth Authentication**
   - Enable OAuth Authentication checkbox
   - Click "Discover OAuth Server"
   - Enter your OAuth Client ID
   - Complete the OAuth flow in the popup

   **OAuth Callback URI Configuration:**

   You must configure the following callback URI in your Authorization Server (OAuth Provider):

   ```
   http://localhost:3000/api/oauth/callback
   ```

   If you're deploying to production or using a different port/domain, update the callback URI accordingly:
   - Production: `https://your-domain.com/api/oauth/callback`
   - Different port: `http://localhost:8080/api/oauth/callback`

   **Steps to configure in your Authorization Server:**
   - **Asgardeo/WSO2 Identity Server**: Add the callback URI to your application's "Authorized redirect URIs"
   - **Auth0**: Add to "Allowed Callback URLs" in your application settings
   - **Okta**: Add to "Sign-in redirect URIs" in your application configuration
   - **Azure AD**: Add to "Redirect URIs" in your app registration
   - **Keycloak**: Add to "Valid Redirect URIs" in your client configuration

4. **Start Chatting**
   - Click "Connect"
   - Available tools appear in the sidebar
   - AI automatically uses MCP tools when needed

## Docker Commands

### Basic Operations
```bash
# Build the image
docker build -t wso2-mcp-client .

# Run on default port (3000)
docker run -p 3000:3000 wso2-mcp-client

# Run on different port (e.g., 8080)
docker run -p 8080:3000 wso2-mcp-client

# Run in background with name
docker run -d --name mcp-client -p 3000:3000 wso2-mcp-client

# Run with auto-restart
docker run -d --restart unless-stopped --name mcp-client -p 3000:3000 wso2-mcp-client
```

### Container Management
```bash
# View running containers
docker ps

# View logs
docker logs mcp-client

# View real-time logs
docker logs -f mcp-client

# Stop container
docker stop mcp-client

# Start stopped container
docker start mcp-client

# Remove container
docker rm mcp-client

# Remove image
docker rmi wso2-mcp-client
```

### Rebuild and Update
```bash
# Build with no cache
docker build --no-cache -t wso2-mcp-client .

# Stop and remove old container, run new one
docker stop mcp-client && docker rm mcp-client
docker run -d --restart unless-stopped --name mcp-client -p 3000:3000 wso2-mcp-client
```

## Troubleshooting

### Port Already in Use
```powershell
# Find what's using the port
netstat -ano | findstr :3000

# Kill the process
taskkill /PID <PID> /F
```

Or change the port:
```bash
docker run -p 8080:3000 wso2-mcp-client
```

### Connecting to Local MCP Server (CORS Requirements)

**Important**: When you connect to a local MCP server (localhost, 127.0.0.1, 192.168.x.x, etc.) from the browser, your MCP server **must have CORS enabled**.

#### Why CORS is Required

This app uses a **hybrid connection approach**:
- **Local servers** (localhost, 127.0.0.1, local IPs): Direct connection from browser
- **Remote servers**: Proxied through the backend

When the app is deployed to the cloud and you connect to `http://localhost:8000/mcp`, the browser connects directly to YOUR local machine (not the cloud server's localhost). This requires CORS.

#### Required CORS Headers

Your MCP server must send these headers:

```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: POST, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization, mcp-session-id
Access-Control-Expose-Headers: mcp-session-id
```

#### Example: Python Flask Server

```python
from flask import Flask
from flask_cors import CORS

app = Flask(__name__)
CORS(app,
     origins="*",
     methods=["POST", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization", "mcp-session-id"],
     expose_headers=["mcp-session-id"])
```

#### Example: Node.js Express Server

```javascript
const cors = require('cors');

app.use(cors({
  origin: '*',
  methods: ['POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization', 'mcp-session-id'],
  exposedHeaders: ['mcp-session-id']
}));
```

#### CORS Error Messages

If you see errors like:
- `"CORS error"`
- `"Failed to fetch"`
- `"Network request failed"`
- `"OPTIONS /mcp 401 Unauthorized"`

Check that your MCP server has CORS enabled with the headers above.

**Important**: If you see `OPTIONS 401`, your server is requiring authentication for OPTIONS requests. OPTIONS requests (CORS preflight) **must not require authentication** and should return `200 OK`. See [CORS_FIX_EXAMPLES.md](CORS_FIX_EXAMPLES.md) for detailed fixes for Flask, Express, and FastAPI.

### Can't Connect to Local MCP Server (Other Issues)

If CORS is enabled but you still can't connect:

1. **Check if your MCP server is running**:
   ```bash
   curl http://localhost:8000/mcp
   ```

2. **Check firewall**: Ensure your firewall allows connections on port 8000

3. **Try different URL formats**:
   - `http://localhost:8000/mcp`
   - `http://127.0.0.1:8000/mcp`
   - Your local IP: `http://192.168.1.x:8000/mcp`

### Google Gemini CORS Error

Enter model name WITHOUT the models/ prefix:
- ✅ Correct: `gemini-2.0-flash-exp`
- ❌ Wrong: `models/gemini-2.0-flash-exp`

### Docker Build Fails

Clear cache and rebuild:
```bash
docker build --no-cache -t wso2-mcp-client .
```

### Permission Issues (Linux/Mac)
```bash
# Fix file permissions if needed
sudo chown -R $USER:$USER .
```

## WSO2 Design Features

- **Brand Colors**: WSO2 orange (#ff7300) as primary color
- **Typography**: Inter font family with WSO2 design principles
- **Components**: Modern cards, buttons, and form elements
- **Icons**: Custom WSO2-branded iconography
- **Theming**: Full dark/light mode support

## Technologies

- Next.js 15 with App Router
- React 19
- TypeScript
- Tailwind CSS with WSO2 Design System
- Model Context Protocol (MCP)
- Docker multi-stage builds

## Additional Documentation

- **OAUTH_README.md** - OAuth authentication setup
- **OAUTH_EXAMPLES.md** - OAuth configuration examples

## License

MIT

---

**Powered by WSO2** - Empowering digital transformation through open source innovation.