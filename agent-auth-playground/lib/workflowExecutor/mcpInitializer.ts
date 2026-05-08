import { MCPClientNodeRuntime } from '../mcpClientNode';
import { authenticateAgent, AuthFlowError } from '../agentAuth';
import { MCPClientConfig, ConsentRequiredError } from './types';
import {
  WorkflowTrace,
  MCPNodeTrace,
  AuthErrorTrace,
  deriveIamUrls,
  extractErrorInfoFromMessage,
} from '../authTrace';

function recordError(traceEntry: MCPNodeTrace, error: unknown): void {
  if (error instanceof AuthFlowError) {
    traceEntry.authError = {
      stage: error.stage,
      statusCode: error.statusCode,
      errorCode: error.errorCode,
      errorDescription: error.errorDescription,
      url: error.url,
      message: error.message,
    };
    return;
  }

  const message = error instanceof Error ? error.message : String(error);
  const extracted = extractErrorInfoFromMessage(message);
  const stage: AuthErrorTrace['stage'] = traceEntry.flow === 'none' ? 'connect' : 'connect';
  traceEntry.authError = {
    stage,
    message,
    statusCode: extracted.statusCode,
    errorCode: extracted.errorCode,
    errorDescription: extracted.errorDescription,
  };
}

export async function connectMCPClient(
  config: MCPClientConfig,
  oboTokens: Record<string, string>,
  trace?: WorkflowTrace
): Promise<MCPClientNodeRuntime> {
  const { nodeId, endpoint, nodeData, agentData, cachedTools } = config;
  const runtime = new MCPClientNodeRuntime();

  const traceEntry: MCPNodeTrace = {
    nodeId,
    name: nodeData.name?.trim() || undefined,
    endpoint,
    flow: 'none',
    agentId: agentData.agentId,
  };

  // Push trace entry up-front so failures still appear in the diagram
  // even when no tool call is ever made (e.g. auth fails on first connect).
  const existingIdx = trace?.mcps.findIndex((m) => m.nodeId === nodeId) ?? -1;
  if (trace) {
    if (existingIdx >= 0) trace.mcps[existingIdx] = traceEntry;
    else trace.mcps.push(traceEntry);
  }

  try {
    if (nodeData.useOAuth2) {
      const flow = nodeData.oauth2Flow ?? 'agent';

      if (flow === 'obo') {
        traceEntry.flow = 'obo';
        if (nodeData.oauth2BaseUrl?.trim()) {
          const urls = deriveIamUrls(nodeData.oauth2BaseUrl.trim());
          traceEntry.iamBaseUrl = urls.iamBaseUrl;
          traceEntry.authorizeUrl = urls.authorizeUrl;
          traceEntry.tokenUrl = urls.tokenUrl;
        }

        const oboToken = oboTokens[nodeId];
        if (!oboToken) {
          throw new ConsentRequiredError(nodeId);
        }
        console.log(`[MCPClient:${nodeId}] Using OBO token`);
        runtime.setAccessToken(oboToken);
        traceEntry.oboToken = oboToken;
      } else {
        traceEntry.flow = 'agent';
        if (!nodeData.oauth2BaseUrl?.trim()) {
          throw new AuthFlowError({
            stage: 'config',
            errorCode: 'missing_base_url',
            errorDescription: 'OAuth2 base URL is required',
          });
        }
        if (!nodeData.oauth2ClientId?.trim()) {
          throw new AuthFlowError({
            stage: 'config',
            errorCode: 'missing_client_id',
            errorDescription: 'OAuth2 client ID is required',
          });
        }
        if (!nodeData.oauth2RedirectUri?.trim()) {
          throw new AuthFlowError({
            stage: 'config',
            errorCode: 'missing_redirect_uri',
            errorDescription: 'OAuth2 redirect URI is required',
          });
        }
        if (!agentData.agentId?.trim()) {
          throw new AuthFlowError({
            stage: 'config',
            errorCode: 'missing_agent_id',
            errorDescription: 'Agent ID is required on the connected AI Agent node',
          });
        }
        if (!agentData.agentSecret?.trim()) {
          throw new AuthFlowError({
            stage: 'config',
            errorCode: 'missing_agent_secret',
            errorDescription: 'Agent Secret is required on the connected AI Agent node',
          });
        }

        const urls = deriveIamUrls(nodeData.oauth2BaseUrl.trim());
        traceEntry.iamBaseUrl = urls.iamBaseUrl;
        traceEntry.authorizeUrl = urls.authorizeUrl;
        traceEntry.authnUrl = urls.authnUrl;
        traceEntry.tokenUrl = urls.tokenUrl;

        console.log(`[MCPClient:${nodeId}] Running OAuth2 agent authentication flow`);
        const accessToken = await authenticateAgent({
          baseUrl: nodeData.oauth2BaseUrl,
          clientId: nodeData.oauth2ClientId,
          redirectUri: nodeData.oauth2RedirectUri,
          agentId: agentData.agentId,
          agentSecret: agentData.agentSecret,
          scope: nodeData.oauth2Scope,
        });
        runtime.setAccessToken(accessToken);
        console.log(`[MCPClient:${nodeId}] Access token obtained`);
        traceEntry.agentToken = accessToken;
      }
    }

    console.log(`[MCPClient:${nodeId}] Connecting to ${endpoint} with ${cachedTools.length} cached tools`);
    await runtime.connect(endpoint, { cachedTools });
    console.log(`[MCPClient:${nodeId}] Connected`);

    return runtime;
  } catch (error) {
    if (error instanceof ConsentRequiredError) throw error;
    recordError(traceEntry, error);
    throw error;
  }
}
