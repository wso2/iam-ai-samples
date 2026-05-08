import { Workflow, ChatMessage, AgentCredential, LLMCredential, OAuthConfig } from './types';

const WORKFLOW_KEY = 'workflow';
const WORKFLOW_MEMORY_KEY = 'workflowMemories';
const OBO_TOKENS_KEY = 'oboTokens';
const MCP_TOOLS_KEY = 'mcpDiscoveredTools';
const AGENT_CREDENTIALS_KEY = 'agentCredentials';
const LLM_CREDENTIALS_KEY = 'llmCredentials';
const OAUTH_CONFIGS_KEY = 'oauthConfigs';

type OBOTokenEntry = { accessToken: string; expiresAt: number };
type OBOTokenStore = Record<string, OBOTokenEntry>;

type WorkflowMemoryStore = Record<string, Record<string, ChatMessage[]>>;

export interface StoredMCPTool {
  name: string;
  description?: string;
  inputSchema: Record<string, unknown>;
  outputSchema?: Record<string, unknown>;
}

export interface MCPToolsEntry {
  endpoint: string;
  tools: StoredMCPTool[];
  discoveredAt: number;
}

type MCPToolsStore = Record<string, Record<string, MCPToolsEntry>>;

// Client-side storage utilities
export const workflowStore = {
  // Workflow management — single workflow only
  saveWorkflow(workflow: Workflow): void {
    if (typeof window === 'undefined') return;
    localStorage.setItem(WORKFLOW_KEY, JSON.stringify(workflow));
  },

  getWorkflow(): Workflow | null {
    if (typeof window === 'undefined') return null;
    const stored = localStorage.getItem(WORKFLOW_KEY);
    return stored ? JSON.parse(stored) : null;
  },

  // Workflow memory by workflowId -> memoryNodeId -> chat messages
  getWorkflowMemory(workflowId: string, memoryNodeId: string): ChatMessage[] {
    if (typeof window === 'undefined') return [];

    const stored = localStorage.getItem(WORKFLOW_MEMORY_KEY);
    const allMemory: WorkflowMemoryStore = stored ? JSON.parse(stored) : {};
    return allMemory[workflowId]?.[memoryNodeId] || [];
  },

  appendWorkflowMemory(
    workflowId: string,
    memoryNodeId: string,
    messages: ChatMessage[],
    maxMessages: number
  ): ChatMessage[] {
    if (typeof window === 'undefined') return [];

    const normalizedMax = Math.max(1, Math.floor(maxMessages || 1));
    const existing = this.getWorkflowMemory(workflowId, memoryNodeId);
    const next = [...existing, ...messages].slice(-normalizedMax);

    const stored = localStorage.getItem(WORKFLOW_MEMORY_KEY);
    const allMemory: WorkflowMemoryStore = stored ? JSON.parse(stored) : {};
    const workflowMemory = allMemory[workflowId] || {};

    allMemory[workflowId] = {
      ...workflowMemory,
      [memoryNodeId]: next,
    };

    localStorage.setItem(WORKFLOW_MEMORY_KEY, JSON.stringify(allMemory));
    return next;
  },

  clearWorkflowMemory(workflowId: string, memoryNodeId: string): void {
    if (typeof window === 'undefined') return;

    const stored = localStorage.getItem(WORKFLOW_MEMORY_KEY);
    if (!stored) return;

    const allMemory: WorkflowMemoryStore = JSON.parse(stored);
    if (!allMemory[workflowId]) return;

    delete allMemory[workflowId][memoryNodeId];

    if (Object.keys(allMemory[workflowId]).length === 0) {
      delete allMemory[workflowId];
    }

    localStorage.setItem(WORKFLOW_MEMORY_KEY, JSON.stringify(allMemory));
  },

  clearWorkflowMemories(workflowId: string): void {
    if (typeof window === 'undefined') return;

    const stored = localStorage.getItem(WORKFLOW_MEMORY_KEY);
    if (!stored) return;

    const allMemory: WorkflowMemoryStore = JSON.parse(stored);
    delete allMemory[workflowId];
    localStorage.setItem(WORKFLOW_MEMORY_KEY, JSON.stringify(allMemory));
  },

  // OBO token management — keyed by `${workflowId}_${nodeId}`
  getOBOToken(workflowId: string, nodeId: string): string | null {
    if (typeof window === 'undefined') return null;
    const stored = localStorage.getItem(OBO_TOKENS_KEY);
    if (!stored) return null;
    const store: OBOTokenStore = JSON.parse(stored);
    const entry = store[`${workflowId}_${nodeId}`];
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) return null;
    return entry.accessToken;
  },

  setOBOToken(workflowId: string, nodeId: string, accessToken: string, expiresIn: number): void {
    if (typeof window === 'undefined') return;
    const stored = localStorage.getItem(OBO_TOKENS_KEY);
    const store: OBOTokenStore = stored ? JSON.parse(stored) : {};
    store[`${workflowId}_${nodeId}`] = {
      accessToken,
      expiresAt: Date.now() + expiresIn * 1000,
    };
    localStorage.setItem(OBO_TOKENS_KEY, JSON.stringify(store));
  },

  clearOBOTokens(workflowId: string): void {
    if (typeof window === 'undefined') return;
    const stored = localStorage.getItem(OBO_TOKENS_KEY);
    if (!stored) return;
    const store: OBOTokenStore = JSON.parse(stored);
    const prefix = `${workflowId}_`;
    for (const key of Object.keys(store)) {
      if (key.startsWith(prefix)) delete store[key];
    }
    localStorage.setItem(OBO_TOKENS_KEY, JSON.stringify(store));
  },

  hasOBOTokens(): boolean {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem(OBO_TOKENS_KEY) !== null;
  },

  clearAllOBOTokens(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(OBO_TOKENS_KEY);
  },

  // MCP discovered tools — keyed by workflowId -> mcpClientNodeId -> entry
  getMCPTools(workflowId: string, nodeId: string): MCPToolsEntry | null {
    if (typeof window === 'undefined') return null;
    const stored = localStorage.getItem(MCP_TOOLS_KEY);
    if (!stored) return null;
    const store: MCPToolsStore = JSON.parse(stored);
    return store[workflowId]?.[nodeId] || null;
  },

  setMCPTools(workflowId: string, nodeId: string, entry: MCPToolsEntry): void {
    if (typeof window === 'undefined') return;
    const stored = localStorage.getItem(MCP_TOOLS_KEY);
    const store: MCPToolsStore = stored ? JSON.parse(stored) : {};
    const workflowEntries = store[workflowId] || {};
    workflowEntries[nodeId] = entry;
    store[workflowId] = workflowEntries;
    localStorage.setItem(MCP_TOOLS_KEY, JSON.stringify(store));
  },

  clearMCPTools(workflowId: string, nodeId: string): void {
    if (typeof window === 'undefined') return;
    const stored = localStorage.getItem(MCP_TOOLS_KEY);
    if (!stored) return;
    const store: MCPToolsStore = JSON.parse(stored);
    if (!store[workflowId]) return;
    delete store[workflowId][nodeId];
    if (Object.keys(store[workflowId]).length === 0) {
      delete store[workflowId];
    }
    localStorage.setItem(MCP_TOOLS_KEY, JSON.stringify(store));
  },

  clearAllMCPTools(workflowId: string): void {
    if (typeof window === 'undefined') return;
    const stored = localStorage.getItem(MCP_TOOLS_KEY);
    if (!stored) return;
    const store: MCPToolsStore = JSON.parse(stored);
    if (!store[workflowId]) return;
    delete store[workflowId];
    localStorage.setItem(MCP_TOOLS_KEY, JSON.stringify(store));
  },

  // Agent credential management — stored globally, not per-workflow
  getAgentCredentials(): AgentCredential[] {
    if (typeof window === 'undefined') return [];
    const stored = localStorage.getItem(AGENT_CREDENTIALS_KEY);
    return stored ? JSON.parse(stored) : [];
  },

  saveAgentCredential(cred: AgentCredential): void {
    if (typeof window === 'undefined') return;
    const creds = this.getAgentCredentials();
    const idx = creds.findIndex((c) => c.id === cred.id);
    if (idx >= 0) {
      creds[idx] = cred;
    } else {
      creds.push(cred);
    }
    localStorage.setItem(AGENT_CREDENTIALS_KEY, JSON.stringify(creds));
  },

  deleteAgentCredential(id: string): void {
    if (typeof window === 'undefined') return;
    const creds = this.getAgentCredentials().filter((c) => c.id !== id);
    localStorage.setItem(AGENT_CREDENTIALS_KEY, JSON.stringify(creds));
  },

  // LLM credential management — stored globally, not per-workflow
  getLLMCredentials(): LLMCredential[] {
    if (typeof window === 'undefined') return [];
    const stored = localStorage.getItem(LLM_CREDENTIALS_KEY);
    return stored ? JSON.parse(stored) : [];
  },

  saveLLMCredential(cred: LLMCredential): void {
    if (typeof window === 'undefined') return;
    const creds = this.getLLMCredentials();
    const idx = creds.findIndex((c) => c.id === cred.id);
    if (idx >= 0) {
      creds[idx] = cred;
    } else {
      creds.push(cred);
    }
    localStorage.setItem(LLM_CREDENTIALS_KEY, JSON.stringify(creds));
  },

  deleteLLMCredential(id: string): void {
    if (typeof window === 'undefined') return;
    const creds = this.getLLMCredentials().filter((c) => c.id !== id);
    localStorage.setItem(LLM_CREDENTIALS_KEY, JSON.stringify(creds));
  },

  // OAuth2 config management — stored globally, not per-workflow
  getOAuthConfigs(): OAuthConfig[] {
    if (typeof window === 'undefined') return [];
    const stored = localStorage.getItem(OAUTH_CONFIGS_KEY);
    return stored ? JSON.parse(stored) : [];
  },

  saveOAuthConfig(config: OAuthConfig): void {
    if (typeof window === 'undefined') return;
    const configs = this.getOAuthConfigs();
    const idx = configs.findIndex((c) => c.id === config.id);
    if (idx >= 0) {
      configs[idx] = config;
    } else {
      configs.push(config);
    }
    localStorage.setItem(OAUTH_CONFIGS_KEY, JSON.stringify(configs));
  },

  deleteOAuthConfig(id: string): void {
    if (typeof window === 'undefined') return;
    const configs = this.getOAuthConfigs().filter((c) => c.id !== id);
    localStorage.setItem(OAUTH_CONFIGS_KEY, JSON.stringify(configs));
  },

  clearAllData(): void {
    if (typeof window === 'undefined') return;
    localStorage.removeItem(WORKFLOW_KEY);
    localStorage.removeItem(WORKFLOW_MEMORY_KEY);
    localStorage.removeItem(OBO_TOKENS_KEY);
    localStorage.removeItem(MCP_TOOLS_KEY);
  },
};

// Generate unique IDs
export function generateId(prefix: string = ''): string {
  return `${prefix}${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

// Create default workflow with Chat Trigger → AI Agent → LLM pre-wired
export function createDefaultWorkflow(name: string = 'agentflow-1'): Workflow {
  const id = generateId('workflow-');
  const triggerId = generateId('node-');
  const agentId = generateId('node-');
  const llmId = generateId('node-');
  return {
    id,
    name,
    nodes: [
      { id: triggerId, type: 'chatTrigger', position: { x: 100, y: 250 }, data: { label: 'Chat Trigger' } },
      { id: agentId,   type: 'aiAgent',     position: { x: 350, y: 250 }, data: { label: 'AI Agent', systemPrompt: 'You are a helpful assistant.', maxToolSteps: 6 } },
      { id: llmId,     type: 'llm',         position: { x: 358, y: 0 }, data: { label: 'AI Service', provider: '' as any, model: '', temperature: 0.7, maxTokens: 1000 } },
    ],
    edges: [
      { id: generateId('edge-'), source: triggerId, target: agentId },
      { id: generateId('edge-'), source: agentId,   target: llmId },
    ],
    createdAt: Date.now(),
    updatedAt: Date.now(),
  };
}
