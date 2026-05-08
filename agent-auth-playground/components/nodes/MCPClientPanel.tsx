'use client';

import { useState, useEffect } from 'react';
import {
  WorkflowNode,
  MCPClientNodeData,
  AIAgentNodeData,
  Workflow,
  AgentCredential,
  OAuthConfig,
} from '@/lib/types';
import { workflowStore } from '@/lib/workflowStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface MCPClientPanelProps {
  node: WorkflowNode;
  onUpdate: (nodeId: string, updates: Partial<WorkflowNode>) => void;
  workflowId?: string;
  workflow?: Workflow | null;
  onMCPInitChange?: () => void;
}

function findConnectedAgentCreds(
  workflow: Workflow | null | undefined,
  mcpNodeId: string,
  credentials: AgentCredential[]
): { agentId?: string; agentSecret?: string } | null {
  if (!workflow) return null;
  const edge = workflow.edges.find((e) => e.target === mcpNodeId);
  if (!edge) return null;
  const agent = workflow.nodes.find((n) => n.id === edge.source && n.type === 'aiAgent');
  if (!agent) return null;
  const data = agent.data as AIAgentNodeData;
  if (data.agentCredentialId) {
    const cred = credentials.find((c) => c.id === data.agentCredentialId);
    if (cred) return { agentId: cred.agentId, agentSecret: cred.agentSecret };
  }
  const legacy = agent.data as Record<string, unknown>;
  return { agentId: legacy.agentId as string | undefined, agentSecret: legacy.agentSecret as string | undefined };
}

export default function MCPClientPanel({ node, onUpdate, workflowId, workflow, onMCPInitChange }: MCPClientPanelProps) {
  const mcpData = node.data as MCPClientNodeData;

  const [mcpInitInfo, setMcpInitInfo] = useState<{ count: number; discoveredAt: number } | null>(null);
  const [mcpInitLoading, setMcpInitLoading] = useState(false);
  const [mcpInitError, setMcpInitError] = useState<string | null>(null);

  const [credentials, setCredentials] = useState<AgentCredential[]>([]);
  const [oauthConfigs, setOAuthConfigs] = useState<OAuthConfig[]>([]);
  const [oauthConfigFormOpen, setOAuthConfigFormOpen] = useState(false);
  const [oauthConfigEditingId, setOAuthConfigEditingId] = useState<string | null>(null);
  const [oauthConfigForm, setOAuthConfigForm] = useState({ name: '', oauth2BaseUrl: '', oauth2ClientId: '', oauth2Scope: '' });
  const [oauthConfigFormError, setOAuthConfigFormError] = useState<string | null>(null);

  useEffect(() => {
    setCredentials(workflowStore.getAgentCredentials());
    setOAuthConfigs(workflowStore.getOAuthConfigs());
  }, []);

  useEffect(() => {
    setMcpInitError(null);
    if (workflowId) {
      const entry = workflowStore.getMCPTools(workflowId, node.id);
      setMcpInitInfo(entry ? { count: entry.tools.length, discoveredAt: entry.discoveredAt } : null);
    } else {
      setMcpInitInfo(null);
    }
  }, [workflowId, node.id]);

  const runMCPInit = async () => {
    if (!workflowId) return;
    const endpoint = mcpData.mcpServerEndpoint?.trim();
    if (!endpoint) {
      setMcpInitError('Add an MCP server endpoint above before initializing.');
      return;
    }

    let oauth2Body: Record<string, string> | undefined;
    if (mcpData.useOAuth2) {
      const config = mcpData.oauth2ConfigId ? oauthConfigs.find((c) => c.id === mcpData.oauth2ConfigId) : null;
      const baseUrl = config?.oauth2BaseUrl?.trim();
      const clientId = config?.oauth2ClientId?.trim();
      if (!baseUrl || !clientId) {
        setMcpInitError('Select an OAuth2 configuration before initializing.');
        return;
      }
      const agentCreds = findConnectedAgentCreds(workflow, node.id, credentials);
      if (!agentCreds || !agentCreds.agentId?.trim() || !agentCreds.agentSecret?.trim()) {
        setMcpInitError('Agent ID and Secret are required on the connected AI Agent node for OAuth2 init.');
        return;
      }
      oauth2Body = {
        flow: mcpData.oauth2Flow ?? 'agent',
        baseUrl,
        clientId,
        redirectUri: window.location.origin,
        scope: config?.oauth2Scope ?? '',
        agentId: agentCreds.agentId,
        agentSecret: agentCreds.agentSecret,
      };
    }

    setMcpInitLoading(true);
    setMcpInitError(null);
    try {
      const res = await fetch('/api/initialize-mcp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ endpoint, oauth2: oauth2Body }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) throw new Error(data?.error || `Initialization failed (${res.status})`);
      const tools = Array.isArray(data.tools) ? data.tools : [];
      const discoveredAt = Date.now();
      workflowStore.setMCPTools(workflowId, node.id, { endpoint, tools, discoveredAt });
      setMcpInitInfo({ count: tools.length, discoveredAt });
      onMCPInitChange?.();
    } catch (err) {
      setMcpInitError(err instanceof Error ? err.message : 'Initialization failed.');
    } finally {
      setMcpInitLoading(false);
    }
  };

  const clearMCPInit = () => {
    if (!workflowId) return;
    workflowStore.clearMCPTools(workflowId, node.id);
    setMcpInitInfo(null);
    setMcpInitError(null);
    onMCPInitChange?.();
  };

  const openAddOAuthConfigForm = () => {
    setOAuthConfigForm({ name: '', oauth2BaseUrl: '', oauth2ClientId: '', oauth2Scope: '' });
    setOAuthConfigEditingId(null);
    setOAuthConfigFormError(null);
    setOAuthConfigFormOpen(true);
  };

  const openEditOAuthConfigForm = (config: OAuthConfig) => {
    setOAuthConfigForm({ name: config.name, oauth2BaseUrl: config.oauth2BaseUrl, oauth2ClientId: config.oauth2ClientId, oauth2Scope: config.oauth2Scope ?? '' });
    setOAuthConfigEditingId(config.id);
    setOAuthConfigFormError(null);
    setOAuthConfigFormOpen(true);
  };

  const saveOAuthConfig = () => {
    if (!oauthConfigForm.name.trim() || !oauthConfigForm.oauth2BaseUrl.trim() || !oauthConfigForm.oauth2ClientId.trim()) {
      setOAuthConfigFormError('Name, Base URL, and Client ID are required.');
      return;
    }
    const config: OAuthConfig = {
      id: oauthConfigEditingId ?? `oauth-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: oauthConfigForm.name.trim(),
      oauth2BaseUrl: oauthConfigForm.oauth2BaseUrl.trim(),
      oauth2ClientId: oauthConfigForm.oauth2ClientId.trim(),
      oauth2Scope: oauthConfigForm.oauth2Scope.trim() || undefined,
    };
    workflowStore.saveOAuthConfig(config);
    setOAuthConfigs(workflowStore.getOAuthConfigs());
    setOAuthConfigFormOpen(false);
  };

  const deleteOAuthConfig = (id: string) => {
    workflowStore.deleteOAuthConfig(id);
    setOAuthConfigs(workflowStore.getOAuthConfigs());
    setOAuthConfigFormOpen(false);
    if (mcpData.oauth2ConfigId === id) {
      onUpdate(node.id, { data: { ...mcpData, oauth2ConfigId: undefined } });
    }
  };

  const selectedConfig = oauthConfigs.find((c) => c.id === mcpData.oauth2ConfigId);

  return (
    <div className="space-y-3">
      <div>
        <label className="text-sm font-semibold text-gray-700 mb-1 block">MCP Server Name</label>
        <Input
          value={mcpData.name || ''}
          onChange={(e) => onUpdate(node.id, { data: { ...mcpData, name: e.target.value } })}
          placeholder="e.g. Bookings API"
        />
        <p className="text-xs text-gray-500 mt-1">Optional friendly label shown in the auth flow diagram instead of the node ID.</p>
      </div>

      <div>
        <label className="text-sm font-semibold text-gray-700 mb-1 block">MCP Server Endpoint</label>
        <Input
          value={mcpData.mcpServerEndpoint || ''}
          onChange={(e) => onUpdate(node.id, { data: { ...mcpData, mcpServerEndpoint: e.target.value } })}
          placeholder="https://your-mcp-server.example.com/mcp"
        />
        <p className="text-xs text-gray-500 mt-1">Required. The AI Agent will connect here to discover and call tools dynamically.</p>
      </div>

      <div className="flex items-center justify-between rounded-md border border-gray-200 bg-gray-50 p-3">
        <div>
          <p className="text-sm font-semibold text-gray-700">Use MCP OAuth2</p>
          <p className="text-xs text-gray-500">Authenticate with Asgardeo before connecting</p>
        </div>
        <button
          type="button"
          role="switch"
          aria-checked={!!mcpData.useOAuth2}
          onClick={() => onUpdate(node.id, { data: { ...mcpData, useOAuth2: !mcpData.useOAuth2 } })}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${mcpData.useOAuth2 ? 'bg-blue-600' : 'bg-gray-300'}`}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${mcpData.useOAuth2 ? 'translate-x-6' : 'translate-x-1'}`} />
        </button>
      </div>

      {mcpData.useOAuth2 && (
        <div className="space-y-3">
          <div>
            <p className="text-sm font-semibold text-gray-700 mb-1">Auth Flow</p>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => onUpdate(node.id, { data: { ...mcpData, oauth2Flow: 'agent' } })}
                className={`flex-1 py-2 px-3 text-sm rounded-md border transition-colors ${(mcpData.oauth2Flow ?? 'agent') === 'agent' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'}`}
              >
                Agent Flow
              </button>
              <button
                type="button"
                onClick={() => onUpdate(node.id, { data: { ...mcpData, oauth2Flow: 'obo' } })}
                className={`flex-1 py-2 px-3 text-sm rounded-md border transition-colors ${mcpData.oauth2Flow === 'obo' ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'}`}
              >
                OBO Flow
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              {(mcpData.oauth2Flow ?? 'agent') === 'agent'
                ? 'Agent authenticates using its own credentials (no user interaction).'
                : 'Agent acts on behalf of a user — user consent is requested in the chat.'}
            </p>
          </div>

          <div>
            <label className="text-sm font-semibold text-gray-700 mb-1 block">OAuth2 Configuration</label>
            <div className="flex gap-2">
              <select
                value={mcpData.oauth2ConfigId || ''}
                onChange={(e) => {
                  setOAuthConfigFormOpen(false);
                  onUpdate(node.id, { data: { ...mcpData, oauth2ConfigId: e.target.value || undefined } });
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value="">Select configuration</option>
                {oauthConfigs.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              {selectedConfig && (
                <button
                  type="button"
                  title="Edit configuration"
                  onClick={() => openEditOAuthConfigForm(selectedConfig)}
                  className="flex items-center justify-center px-2 border border-gray-300 rounded-md hover:bg-gray-50 text-gray-500 hover:text-gray-700 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
              )}
              <Button type="button" size="sm" variant="outline" onClick={openAddOAuthConfigForm}>+ Add</Button>
            </div>
            {oauthConfigs.length === 0 && !oauthConfigFormOpen && (
              <p className="text-xs text-gray-500 mt-1">No configurations saved yet. Click + Add to create one.</p>
            )}
            {selectedConfig && !oauthConfigFormOpen && (
              <div className="mt-2 rounded-md border border-gray-100 bg-gray-50 px-3 py-2 space-y-0.5">
                <p className="text-xs text-gray-500 truncate"><span className="font-medium text-gray-600">Base URL:</span> {selectedConfig.oauth2BaseUrl}</p>
                <p className="text-xs text-gray-500 truncate"><span className="font-medium text-gray-600">Client ID:</span> {selectedConfig.oauth2ClientId}</p>
                {selectedConfig.oauth2Scope && (
                  <p className="text-xs text-gray-500 truncate"><span className="font-medium text-gray-600">Scope:</span> {selectedConfig.oauth2Scope}</p>
                )}
                <p className="text-xs text-gray-500 truncate">
                  <span className="font-medium text-gray-600">Redirect URI:</span> {typeof window !== 'undefined' ? window.location.origin : ''}
                </p>
              </div>
            )}
          </div>

          {oauthConfigFormOpen && (
            <div className="rounded-md border border-blue-200 bg-white p-3 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-800">{oauthConfigEditingId ? 'Edit OAuth2 Config' : 'New OAuth2 Config'}</p>
                <button type="button" onClick={() => setOAuthConfigFormOpen(false)} className="text-gray-400 hover:text-gray-600 text-base leading-none">✕</button>
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-700 mb-1 block">Name</label>
                <Input value={oauthConfigForm.name} onChange={(e) => setOAuthConfigForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Bookings API – Dev" />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-700 mb-1 block">Base URL</label>
                <Input value={oauthConfigForm.oauth2BaseUrl} onChange={(e) => setOAuthConfigForm((f) => ({ ...f, oauth2BaseUrl: e.target.value }))} placeholder="https://api.asgardeo.io/t/your-org" />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-700 mb-1 block">Client ID</label>
                <Input value={oauthConfigForm.oauth2ClientId} onChange={(e) => setOAuthConfigForm((f) => ({ ...f, oauth2ClientId: e.target.value }))} placeholder="vMH8K3zdIhlSiIDmmvnebNOI_bIa" />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-700 mb-1 block">
                  Scope <span className="ml-1 text-xs font-normal text-gray-400">(optional)</span>
                </label>
                <Input value={oauthConfigForm.oauth2Scope} onChange={(e) => setOAuthConfigForm((f) => ({ ...f, oauth2Scope: e.target.value }))} placeholder="openid read_bookings write_bookings" />
              </div>
              <div>
                <label className="text-xs font-semibold text-gray-700 mb-1 block">Redirect URI</label>
                <Input value={typeof window !== 'undefined' ? window.location.origin : ''} readOnly className="bg-white text-gray-500 cursor-not-allowed" />
              </div>
              {oauthConfigFormError && <p className="text-xs text-red-600">{oauthConfigFormError}</p>}
              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={saveOAuthConfig}>Save</Button>
                <Button type="button" size="sm" variant="outline" onClick={() => setOAuthConfigFormOpen(false)}>Cancel</Button>
                {oauthConfigEditingId && (
                  <Button type="button" size="sm" variant="outline" className="ml-auto text-red-600 border-red-200 hover:bg-red-50" onClick={() => deleteOAuthConfig(oauthConfigEditingId)}>Delete</Button>
                )}
              </div>
            </div>
          )}

          <p className="text-xs text-gray-500">
            Agent ID and Secret are taken from the connected AI Agent node.
            {(mcpData.oauth2Flow ?? 'agent') === 'obo' && ' For OBO flow, user consent will be requested in the chat before the first message is processed.'}
          </p>
        </div>
      )}

      <div className="rounded-md border border-gray-200 bg-gray-50 p-3 space-y-2">
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-gray-700">Initialization</p>
            {mcpInitInfo ? (
              <p className="text-xs text-gray-600">
                {mcpInitInfo.count} tool{mcpInitInfo.count === 1 ? '' : 's'} cached &middot;{' '}
                {new Date(mcpInitInfo.discoveredAt).toLocaleString()}
              </p>
            ) : (
              <p className="text-xs text-red-600">Not initialized. Tools must be discovered before this MCP client can be used in a chat.</p>
            )}
          </div>
          <div className="flex flex-shrink-0 gap-2">
            <Button
              type="button"
              size="sm"
              variant={mcpInitInfo ? 'outline' : 'default'}
              disabled={mcpInitLoading || !workflowId}
              onClick={runMCPInit}
            >
              {mcpInitLoading ? 'Connecting...' : mcpInitInfo ? 'Re-discover' : 'Initialize & Connect'}
            </Button>
            {mcpInitInfo && (
              <Button type="button" size="sm" variant="outline" disabled={mcpInitLoading} onClick={clearMCPInit}>Clear</Button>
            )}
          </div>
        </div>
        {mcpInitError && <p className="text-xs text-red-600 mt-1">{mcpInitError}</p>}
        <p className="text-xs text-gray-500">
          Tool schemas are cached locally. The agent only sees a <code>tool_search</code> meta-tool at chat time and pulls in matching schemas on demand.
        </p>
      </div>
    </div>
  );
}
