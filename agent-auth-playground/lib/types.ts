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
// Workflow node types
export type NodeType = 'chatTrigger' | 'aiAgent' | 'llm' | 'mcpClient';

// Position interface for React Flow
export interface Position {
  x: number;
  y: number;
}

// Base node data structure
export interface BaseNodeData {
  label: string;
  [key: string]: any;
}

// Chat Trigger node data
export interface ChatTriggerNodeData extends BaseNodeData {
  label: 'Chat Trigger';
}

// Saved agent credential set (stored globally in localStorage, not per-workflow)
export interface AgentCredential {
  id: string;
  name: string;
  agentId: string;
  agentSecret: string;
  agentBaseUrl: string;
  agentAppClientId: string;
}

// AI Agent node data
export interface AIAgentNodeData extends BaseNodeData {
  label: 'AI Agent';
  systemPrompt: string;
  agentName?: string;
  agentCredentialId?: string;
  maxToolSteps?: number;
  maxMessages?: number;
}

// LLM credential — stored globally in localStorage, not per-workflow
export type LLMCredentialProvider = 'gemini' | 'gcp' | 'anthropic' | 'openai' | 'azure-openai';

export interface LLMCredential {
  id: string;
  name: string;
  provider: LLMCredentialProvider;
  apiKey?: string;             // gemini / anthropic / openai / azure-openai
  gcpAccessToken?: string;     // gcp
  gcpProjectId?: string;       // gcp
  azureResourceName?: string;  // azure-openai
  azureDeploymentName?: string;// azure-openai
  azureApiVersion?: string;    // azure-openai
}

// LLM node data
export interface LLMNodeData extends BaseNodeData {
  label: 'AI Service';
  provider: 'gemini' | 'openai' | 'anthropic' | 'azure-openai';
  model: string;
  temperature: number;
  maxTokens: number;
  geminiAuthType?: 'api-key' | 'gcp-access-token';
  llmCredentialId?: string;
}

// OAuth2 config — stored globally in localStorage, not per-workflow
export interface OAuthConfig {
  id: string;
  name: string;
  oauth2BaseUrl: string;
  oauth2ClientId: string;
  oauth2Scope?: string;
}

// MCP Client node data
export interface MCPClientNodeData extends BaseNodeData {
  label: 'MCP Client';
  name?: string;
  mcpServerEndpoint: string;
  useOAuth2?: boolean;
  oauth2Flow?: 'agent' | 'obo';
  oauth2ConfigId?: string;
}

// Node type union
export type NodeData =
  | ChatTriggerNodeData
  | AIAgentNodeData
  | LLMNodeData
  | MCPClientNodeData;

// React Flow node structure
export interface WorkflowNode {
  id: string;
  type: NodeType;
  position: Position;
  data: NodeData;
  selected?: boolean;
}

// React Flow edge structure
export interface WorkflowEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle?: string;
  targetHandle?: string;
  animated?: boolean;
}

// Complete workflow definition
export interface Workflow {
  id: string;
  name: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  createdAt: number;
  updatedAt: number;
}

// Chat message
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  workflowId?: string;
  type?: 'obo-consent';
  metadata?: { authUrl?: string };
}

// Execution context for workflow runner
export interface ExecutionContext {
  workflowId: string;
  variables: Record<string, any>;
  memoryMessages: ChatMessage[];
  currentInput: string;
}

export type ProviderName = 'gemini' | 'openai' | 'anthropic' | 'azure-openai';

// Workflow execution result
export interface ExecutionResult {
  success: boolean;
  output: string;
  error?: string;
  executionTime: number;
  requiresConsent?: boolean;
}
