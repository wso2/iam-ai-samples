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
import { MCPClientNodeRuntime, MCPDiscoveredTool } from '../mcpClientNode';
import { AgentToolBinding, MCPClientConfig, CachedMCPToolsMap } from './types';
import {
  normalizeToolName,
  ensureUniqueToolName,
  normalizeInputSchema,
  stringifyToolResult,
} from './utils';

// Thrown when an MCP tool call returns isError=true (protocol-level failure).
// This is how MCP servers signal "scope insufficient", "unauthorized", etc.
// when the HTTP request itself succeeded.
export class MCPToolCallError extends Error {
  isMcpToolError = true as const;
  constructor(message: string) {
    super(message);
    this.name = 'MCPToolCallError';
  }
}

export async function executeMCPClient(
  runtime: MCPClientNodeRuntime,
  tool: Pick<AgentToolBinding, 'publicName' | 'sourceToolName'>,
  args: Record<string, unknown>
): Promise<string> {
  console.log(`[MCPClient] Calling tool "${tool.publicName}" with args: ${JSON.stringify(args)}`);
  const result = await runtime.callTool(tool.sourceToolName, args);
  console.log(`[MCPClient] Tool "${tool.publicName}" returned result: ${JSON.stringify(result)}`);
  const text = stringifyToolResult(result);
  if (result.isError) {
    throw new MCPToolCallError(text || 'MCP tool reported an error');
  }
  return text;
}

export function buildToolBindingsFromCache(
  configs: MCPClientConfig[],
  cachedToolsMap: CachedMCPToolsMap
): AgentToolBinding[] {
  const bindings: AgentToolBinding[] = [];
  const usedNames = new Set<string>();

  for (const config of configs) {
    const entry = cachedToolsMap[config.nodeId];
    const tools: MCPDiscoveredTool[] = entry?.tools ?? config.cachedTools;

    for (const tool of tools) {
      const generatedName = normalizeToolName(`${tool.name}_${config.nodeId}`);
      const publicName = ensureUniqueToolName(generatedName, usedNames);
      bindings.push({
        publicName,
        sourceToolName: tool.name,
        description: tool.description,
        parameters: normalizeInputSchema(tool.inputSchema),
        endpoint: config.endpoint,
        nodeId: config.nodeId,
      });
    }
  }

  return bindings;
}
