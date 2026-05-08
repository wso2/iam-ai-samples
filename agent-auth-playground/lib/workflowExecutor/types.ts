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
import { MCPClientNodeData, AIAgentNodeData } from '../types';

export interface CachedMCPToolsEntry {
  endpoint: string;
  tools: MCPDiscoveredTool[];
}

export type CachedMCPToolsMap = Record<string, CachedMCPToolsEntry>;

export interface MCPClientConfig {
  nodeId: string;
  endpoint: string;
  nodeData: MCPClientNodeData;
  agentData: AIAgentNodeData;
  cachedTools: MCPDiscoveredTool[];
}

export interface ConnectedMCPClient {
  endpoint: string;
  nodeId: string;
  runtime: MCPClientNodeRuntime;
}

export interface AgentToolBinding {
  publicName: string;
  sourceToolName: string;
  description?: string;
  parameters: Record<string, unknown>;
  endpoint: string;
  nodeId: string;
}

export type AgentDecision =
  | { type: 'final'; response: string }
  | { type: 'tool'; name: string; arguments: Record<string, unknown> };

export class ConsentRequiredError extends Error {
  constructor(public readonly nodeId: string) {
    super(`OBO consent required for MCP node ${nodeId}`);
    this.name = 'ConsentRequiredError';
  }
}
