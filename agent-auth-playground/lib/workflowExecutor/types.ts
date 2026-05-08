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
