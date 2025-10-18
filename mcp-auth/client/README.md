# WSO2 MCP AI Agent Client

A Next.js web client for connecting to MCP (Model Context Protocol) servers with OAuth 2.0 authentication support. Chat with AI models that can automatically discover and use tools from your MCP server. Features WSO2's modern design system and branding.

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
     - **When running in Docker**: `http://host.docker.internal:8000/mcp`
     - **Local development**: `http://localhost:8000/mcp`
     - **Remote server**: `https://your-server.com/mcp`

3. **Optional: OAuth Authentication**
   - Enable OAuth Authentication checkbox
   - Click "Discover OAuth Server"
   - Enter your OAuth Client ID
   - Complete the OAuth flow in the popup

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

### Can't Connect to Localhost MCP Server (503 Error)

**Problem**: Getting 503 errors when trying to connect to your local MCP server.

**Solution**: When running the client in Docker, use `http://host.docker.internal:8000/mcp` instead of `http://localhost:8000/mcp`.

**Why**: Docker containers can't access `localhost` on the host machine directly. `host.docker.internal` is Docker's special hostname that resolves to the host machine's IP address.

**Examples**:
- ❌ Wrong: `http://localhost:8000/mcp`
- ✅ Correct: `http://host.docker.internal:8000/mcp`
- ✅ Also works: `http://host.docker.internal:3001/mcp` (if your MCP server runs on port 3001)

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