/**
 * Copyright (c) 2026, WSO2 LLC. (https://www.wso2.com).
 *
 * WSO2 LLC. licenses this file to you under the Apache License,
 * Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
import { WorkflowNode, AIAgentNodeData, LLMNodeData, LLMCredential, ExecutionContext } from '../types';
import { MCPClientNodeRuntime } from '../mcpClientNode';
import { MCPClientConfig, AgentToolBinding, ConsentRequiredError } from './types';
import { WorkflowTrace, extractErrorInfoFromMessage } from '../authTrace';
import { AuthFlowError } from '../agentAuth';
import { connectMCPClient } from './mcpInitializer';
import { executeMCPClient, buildToolBindingsFromCache } from './mcpClient';
import { CachedMCPToolsMap } from './types';
import type { WorkflowEventHandler } from './index';
import {
  getErrorMessage,
  formatMemoryMessages,
  getAgentStepLimit,
  parseAgentDecision,
  searchToolBindings,
} from './utils';

const TOOL_SEARCH_NAME = 'tool_search';
const TOOL_SEARCH_LIMIT = 10;

const TOOL_SEARCH_SCHEMA = {
  name: TOOL_SEARCH_NAME,
  description:
    'Search the catalogue of available MCP tools by keyword. Returns up to 10 tool schemas matching your query; matched tools then become callable on subsequent steps.',
  parameters: {
    type: 'object',
    properties: {
      query: {
        type: 'string',
        description: 'Keywords describing the capability you need (e.g., "send email", "list github issues").',
      },
    },
    required: ['query'],
  },
};

// ── LLM execution ─────────────────────────────────────────────────────────────

export async function executeLLM(
  node: WorkflowNode,
  context: ExecutionContext,
  llmCredentials: LLMCredential[],
  baseUrl: string,
  message?: string,
  systemPrompt?: string
): Promise<string> {
  const data = node.data as LLMNodeData;
  const resolvedMessage = message ?? context.currentInput;
  const resolvedSystemPrompt = systemPrompt ?? '';

  console.log(`[LLM:${node.id}] Calling ${data.provider}/${data.model}`);

  return invokeLLM(data, resolvedMessage, resolvedSystemPrompt, llmCredentials, baseUrl);
}

async function invokeLLM(
  data: LLMNodeData,
  message: string,
  systemPrompt: string,
  llmCredentials: LLMCredential[],
  baseUrl: string
): Promise<string> {
  const cred = llmCredentials.find((c) => c.id === data.llmCredentialId);
  const isAzure = data.provider === 'azure-openai';
  const isGcpAuth = data.provider === 'gemini' && data.geminiAuthType === 'gcp-access-token';
  const gcpAccessToken = isGcpAuth ? cred?.gcpAccessToken : undefined;
  const gcpProjectId = isGcpAuth ? cred?.gcpProjectId : undefined;
  const apiKey = isGcpAuth ? undefined : cred?.apiKey;

  if (isGcpAuth && (!gcpAccessToken || !gcpProjectId)) {
    throw new Error('GCP Access Token and Project ID are required for Vertex AI. Please configure them in the LLM node.');
  }

  if (isAzure) {
    if (!cred?.azureResourceName || !cred?.azureDeploymentName || !cred?.azureApiVersion) {
      throw new Error('Azure OpenAI requires Resource Name, Deployment Name, and API Version in the LLM credentials.');
    }
    if (!apiKey) {
      throw new Error('No API key configured for Azure OpenAI. Please set up your credentials.');
    }
  } else if (!isGcpAuth && !apiKey) {
    throw new Error(
      `No API key configured for ${data.provider}. Please set up your credentials.`
    );
  }

  const azureFields = isAzure
    ? {
        azureResourceName: cred?.azureResourceName,
        azureDeploymentName: cred?.azureDeploymentName,
        azureApiVersion: cred?.azureApiVersion,
      }
    : {};

  try {
    const response = await fetch(new URL('/api/execute-llm', baseUrl), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider: data.provider,
        model: data.model,
        message,
        systemPrompt,
        temperature: data.temperature,
        maxTokens: data.maxTokens,
        ...(isGcpAuth ? { gcpAccessToken, gcpProjectId } : { apiKey }),
        ...azureFields,
      }),
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.statusText}`);
    }

    const result = await response.json();

    if (!result.success) {
      throw new Error(result.error || 'LLM execution failed');
    }

    return result.output;
  } catch (error) {
    throw new Error(`LLM execution failed: ${getErrorMessage(error)}`);
  }
}

// ── Prompt builders ────────────────────────────────────────────────────────────

export function buildAgentSystemPrompt(systemPrompt: string): string {
  const basePrompt = systemPrompt?.trim() || 'You are a helpful assistant.';

  return [
    basePrompt,
    'You are an autonomous agent that can decide to answer directly or call tools.',
    'Respond with valid JSON only and no markdown code fences.',
    'Allowed response formats:',
    '{"type":"final","response":"..."}',
    '{"type":"tool","name":"tool_name","arguments":{}}',
    `You begin with only one tool: \`${TOOL_SEARCH_NAME}\`. The catalogue of MCP tools is large and not shown up-front.`,
    `To find a tool, call \`${TOOL_SEARCH_NAME}\` with {"query":"keywords"}. The result contains up to ${TOOL_SEARCH_LIMIT} matching tool schemas; once returned they remain available to call on later steps.`,
    'Only call tools whose schemas are listed in "Available function schemas" for the current step. If no listed tool fits, search for one first.',
    'If a tool call is not needed, return type "final".',
  ].join('\n');
}

export function buildAgentStepPrompt(
  userInput: string,
  memoryContext: string,
  exposedTools: AgentToolBinding[],
  toolExecutionLog: string[],
  step: number,
  maxSteps: number,
  totalToolCount: number
): string {
  const functionSchemas: Array<Record<string, unknown>> = [TOOL_SEARCH_SCHEMA];
  for (const tool of exposedTools) {
    functionSchemas.push({
      name: tool.publicName,
      description: tool.description || `MCP tool ${tool.sourceToolName} exposed by ${tool.endpoint}`,
      parameters: tool.parameters,
    });
  }

  return [
    `Step ${step} of ${maxSteps}. Decide the next best action for the user.`,
    `Current user request:\n${userInput}`,
    `Memory context:\n${memoryContext}`,
    `Tool catalogue size: ${totalToolCount} MCP tools available via \`${TOOL_SEARCH_NAME}\`.`,
    `Available function schemas (${functionSchemas.length}):\n${JSON.stringify(functionSchemas, null, 2)}`,
    `Tool execution context:\n${
      toolExecutionLog.length > 0 ? toolExecutionLog.join('\n\n') : '(no tools used yet)'
    }`,
    'Return only one JSON object in the required format.',
  ].join('\n\n');
}

export function buildAgentFallbackPrompt(
  userInput: string,
  memoryContext: string,
  toolExecutionLog: string[]
): string {
  return [
    'Create the final answer for the user based on all available context.',
    `Current user request:\n${userInput}`,
    `Memory context:\n${memoryContext}`,
    `Tool execution context:\n${
      toolExecutionLog.length > 0 ? toolExecutionLog.join('\n\n') : '(no tools were used)'
    }`,
    'Respond with plain text only.',
  ].join('\n\n');
}

// ── Lazy runtime cache ─────────────────────────────────────────────────────────

async function getOrConnectRuntime(
  nodeId: string,
  mcpConfigs: MCPClientConfig[],
  runtimeCache: Map<string, MCPClientNodeRuntime>,
  oboTokens: Record<string, string>,
  trace: WorkflowTrace | undefined
): Promise<MCPClientNodeRuntime> {
  const cacheKey = `${nodeId}:${oboTokens[nodeId] ?? ''}`;
  const cached = runtimeCache.get(cacheKey);
  if (cached) return cached;

  const config = mcpConfigs.find((c) => c.nodeId === nodeId);
  if (!config) throw new Error(`[MCPClient:${nodeId}] Config not found`);

  // connectMCPClient throws ConsentRequiredError for OBO nodes with no token
  const runtime = await connectMCPClient(config, oboTokens, trace);
  runtimeCache.set(cacheKey, runtime);
  return runtime;
}

// ── AI Agent execution loop ────────────────────────────────────────────────────

export async function executeAIAgent(
  node: WorkflowNode,
  llmNode: WorkflowNode,
  mcpConfigs: MCPClientConfig[],
  runtimeCache: Map<string, MCPClientNodeRuntime>,
  oboTokens: Record<string, string>,
  cachedToolsMap: CachedMCPToolsMap,
  context: ExecutionContext,
  llmCredentials: LLMCredential[],
  baseUrl: string,
  trace?: WorkflowTrace,
  onEvent?: WorkflowEventHandler
): Promise<string> {
  const data = node.data as AIAgentNodeData;
  const toolExecutionLog: string[] = [];
  const memoryContext = formatMemoryMessages(context.memoryMessages);
  const maxToolSteps = getAgentStepLimit(data);

  console.log(
    `[AIAgent:${node.id}] Starting — LLM: ${llmNode.id}, MCP configs: ${mcpConfigs.length}`
  );

  const allBindings = buildToolBindingsFromCache(mcpConfigs, cachedToolsMap);
  const exposedToolNames = new Set<string>();

  console.log(
    `[AIAgent:${node.id}] Tool catalogue: ${allBindings.length} tools (exposed via ${TOOL_SEARCH_NAME})`
  );

  for (let step = 1; step <= maxToolSteps; step += 1) {
    console.log(`[AIAgent:${node.id}] Step ${step}/${maxToolSteps}`);

    const exposedTools = allBindings.filter((t) => exposedToolNames.has(t.publicName));
    const stepPrompt = buildAgentStepPrompt(
      context.currentInput,
      memoryContext,
      exposedTools,
      toolExecutionLog,
      step,
      maxToolSteps,
      allBindings.length
    );

    onEvent?.({ type: 'node-start', nodeId: llmNode.id });
    let rawDecision: string;
    try {
      rawDecision = await executeLLM(
        llmNode,
        context,
        llmCredentials,
        baseUrl,
        stepPrompt,
        buildAgentSystemPrompt(data.systemPrompt)
      );
    } finally {
      onEvent?.({ type: 'node-end', nodeId: llmNode.id });
    }
    const decision = parseAgentDecision(rawDecision);

    if (!decision) {
      console.log(`[AIAgent:${node.id}] Step ${step}: unparseable LLM response, returning raw output`);
      const fallbackResponse = rawDecision.trim();
      context.variables['agentOutput'] = fallbackResponse;
      return fallbackResponse;
    }

    if (decision.type === 'final') {
      console.log(`[AIAgent:${node.id}] Step ${step}: final answer`);
      const finalResponse = decision.response.trim() || rawDecision.trim();
      context.variables['agentOutput'] = finalResponse;
      return finalResponse;
    }

    if (decision.name === TOOL_SEARCH_NAME) {
      const rawQuery = decision.arguments['query'];
      const query = typeof rawQuery === 'string' ? rawQuery.trim() : '';

      if (!query) {
        console.warn(`[AIAgent:${node.id}] Step ${step}: tool_search called without a query`);
        toolExecutionLog.push(
          `Step ${step} ${TOOL_SEARCH_NAME} call failed: missing required string argument "query".`
        );
        continue;
      }

      const matches = searchToolBindings(query, allBindings, TOOL_SEARCH_LIMIT);
      for (const m of matches) exposedToolNames.add(m.publicName);

      const matchSummary = matches.map((m) => ({
        name: m.publicName,
        description: m.description || `MCP tool ${m.sourceToolName} exposed by ${m.endpoint}`,
        parameters: m.parameters,
      }));

      console.log(
        `[AIAgent:${node.id}] Step ${step}: tool_search query="${query}" -> ${matches.length} match(es): [${matches.map((m) => m.publicName).join(', ') || 'none'}]`
      );

      toolExecutionLog.push(
        [
          `Step ${step} tool call`,
          `Tool: ${TOOL_SEARCH_NAME}`,
          `Arguments: ${JSON.stringify({ query })}`,
          `Result: ${JSON.stringify({ matches: matchSummary }, null, 2)}`,
        ].join('\n')
      );

      trace?.tools.push({
        step,
        publicName: TOOL_SEARCH_NAME,
        sourceToolName: TOOL_SEARCH_NAME,
        endpoint: 'local',
        nodeId: '',
        args: JSON.stringify({ query }),
        result: `${matches.length} match(es): ${matches.map((m) => m.publicName).join(', ')}`.slice(0, 500),
        ok: true,
      });

      continue;
    }

    const selectedTool = allBindings.find((t) => t.publicName === decision.name);

    if (!selectedTool || !exposedToolNames.has(selectedTool.publicName)) {
      const exposedList = Array.from(exposedToolNames).join(', ') || '(none yet)';
      console.warn(
        `[AIAgent:${node.id}] Step ${step}: tool "${decision.name}" not callable — exposed: [${exposedList}]`
      );
      toolExecutionLog.push(
        `Step ${step}: Tool "${decision.name}" is not currently exposed. Use ${TOOL_SEARCH_NAME} to discover and expose tools first. Currently exposed: ${exposedList}.`
      );
      continue;
    }

    console.log(
      `[AIAgent:${node.id}] Step ${step}: calling tool "${selectedTool.publicName}" with args ${JSON.stringify(decision.arguments)}`
    );

    const toolNodeId = selectedTool.nodeId;
    if (toolNodeId) onEvent?.({ type: 'node-start', nodeId: toolNodeId });

    try {
      // Lazy auth + connect — throws ConsentRequiredError for OBO nodes with no token
      const runtime = await getOrConnectRuntime(
        toolNodeId,
        mcpConfigs,
        runtimeCache,
        oboTokens,
        trace
      );

      const toolResult = await executeMCPClient(runtime, selectedTool, decision.arguments);
      console.log(`[AIAgent:${node.id}] Step ${step}: tool "${selectedTool.publicName}" succeeded`);
      toolExecutionLog.push(
        [
          `Step ${step} tool call`,
          `Tool: ${selectedTool.publicName} (${selectedTool.sourceToolName} @ ${selectedTool.endpoint})`,
          `Arguments: ${JSON.stringify(decision.arguments)}`,
          `Result: ${toolResult}`,
        ].join('\n')
      );
      trace?.tools.push({
        step,
        publicName: selectedTool.publicName,
        sourceToolName: selectedTool.sourceToolName,
        endpoint: selectedTool.endpoint,
        nodeId: toolNodeId,
        args: JSON.stringify(decision.arguments),
        result: typeof toolResult === 'string' ? toolResult.slice(0, 500) : '',
        ok: true,
      });
    } catch (error) {
      if (error instanceof ConsentRequiredError) {
        onEvent?.({ type: 'consent-required', nodeId: error.nodeId });
        throw error;
      }
      const errorMessage = getErrorMessage(error);
      console.error(
        `[AIAgent:${node.id}] Step ${step}: tool "${selectedTool.publicName}" failed: ${errorMessage}`
      );
      toolExecutionLog.push(
        `Step ${step} tool call failed for ${selectedTool.publicName}: ${errorMessage}`
      );

      // Determine HTTP status / OAuth error info. Auth-flow failures from
      // initial connect already record onto the MCP entry — only the in-flight
      // tool-call failures (401/403 on a previously-connected runtime) need to
      // be surfaced as a tool-level auth error.
      let statusCode: number | undefined;
      let errorCode: string | undefined;
      let errorDescription: string | undefined;
      if (error instanceof AuthFlowError) {
        statusCode = error.statusCode;
        errorCode = error.errorCode;
        errorDescription = error.errorDescription;
      } else {
        const extracted = extractErrorInfoFromMessage(errorMessage);
        statusCode = extracted.statusCode;
        errorCode = extracted.errorCode;
        errorDescription = extracted.errorDescription;
      }

      // Stamp an authError on the MCP entry when the tool call failed because
      // of an auth issue (401/403, or recognised OAuth error code) and the MCP
      // hasn't already recorded a more specific failure.
      const mcpEntry = trace?.mcps.find((m) => m.nodeId === toolNodeId);
      const looksAuthRelated =
        statusCode === 401 ||
        statusCode === 403 ||
        (errorCode && /^(invalid_token|insufficient_scope|invalid_client|invalid_grant|access_denied|unauthorized|forbidden)$/i.test(errorCode));
      if (mcpEntry && !mcpEntry.authError && looksAuthRelated) {
        mcpEntry.authError = {
          stage: 'tool-call',
          statusCode,
          errorCode,
          errorDescription,
          message: errorMessage,
          url: selectedTool.endpoint,
        };
      }

      trace?.tools.push({
        step,
        publicName: selectedTool.publicName,
        sourceToolName: selectedTool.sourceToolName,
        endpoint: selectedTool.endpoint,
        nodeId: toolNodeId,
        args: JSON.stringify(decision.arguments),
        result: errorMessage,
        ok: false,
        statusCode,
        errorCode,
        errorDescription,
      });
    } finally {
      if (toolNodeId) onEvent?.({ type: 'node-end', nodeId: toolNodeId });
    }
  }

  console.log(`[AIAgent:${node.id}] Max steps reached — generating fallback answer`);

  onEvent?.({ type: 'node-start', nodeId: llmNode.id });
  let fallbackOutput: string;
  try {
    fallbackOutput = await executeLLM(
      llmNode,
      context,
      llmCredentials,
      baseUrl,
      buildAgentFallbackPrompt(context.currentInput, memoryContext, toolExecutionLog),
      data.systemPrompt || 'You are a helpful assistant.'
    );
  } finally {
    onEvent?.({ type: 'node-end', nodeId: llmNode.id });
  }

  context.variables['agentOutput'] = fallbackOutput;
  return fallbackOutput;
}
