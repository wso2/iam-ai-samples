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
'use client';

import { useState, useEffect } from 'react';
import { WorkflowNode, AIAgentNodeData, AgentCredential } from '@/lib/types';
import { workflowStore } from '@/lib/workflowStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';

interface AIAgentPanelProps {
  node: WorkflowNode;
  onUpdate: (nodeId: string, updates: Partial<WorkflowNode>) => void;
  workflowId?: string;
}

export default function AIAgentPanel({ node, onUpdate, workflowId }: AIAgentPanelProps) {
  const agentData = node.data as AIAgentNodeData;

  const [memoryCount, setMemoryCount] = useState(0);
  const [agentTokenModalOpen, setAgentTokenModalOpen] = useState(false);
  const [agentToken, setAgentToken] = useState<string | null>(null);
  const [agentTokenLoading, setAgentTokenLoading] = useState(false);
  const [agentTokenError, setAgentTokenError] = useState<string | null>(null);
  const [agentTokenCopied, setAgentTokenCopied] = useState(false);

  const [credentials, setCredentials] = useState<AgentCredential[]>([]);
  const [credFormOpen, setCredFormOpen] = useState(false);
  const [credEditingId, setCredEditingId] = useState<string | null>(null);
  const [credForm, setCredForm] = useState({ name: '', agentId: '', agentSecret: '', agentBaseUrl: '', agentAppClientId: '' });
  const [credFormError, setCredFormError] = useState<string | null>(null);

  useEffect(() => {
    setCredentials(workflowStore.getAgentCredentials());
  }, []);

  useEffect(() => {
    if (workflowId) {
      setMemoryCount(workflowStore.getWorkflowMemory(workflowId, node.id).length);
    }
  }, [workflowId, node.id]);

  const checkAgentToken = async (cred: AgentCredential) => {
    setAgentTokenLoading(true);
    setAgentTokenError(null);
    try {
      const res = await fetch('/api/check-agent-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseUrl: cred.agentBaseUrl,
          clientId: cred.agentAppClientId,
          agentId: cred.agentId,
          agentSecret: cred.agentSecret,
          redirectUri: window.location.origin,
          scope: 'openid',
        }),
      });
      const json = await res.json();
      if (!res.ok || !json.token) throw new Error(json.error || 'Failed to fetch agent token');
      setAgentToken(json.token);
      setAgentTokenModalOpen(true);
    } catch (err) {
      setAgentTokenError(err instanceof Error ? err.message : 'Failed to fetch agent token');
    } finally {
      setAgentTokenLoading(false);
    }
  };

  const openAddCredModal = () => {
    setCredForm({ name: '', agentId: '', agentSecret: '', agentBaseUrl: '', agentAppClientId: '' });
    setCredEditingId(null);
    setCredFormError(null);
    setCredFormOpen(true);
  };

  const openEditCredModal = (cred: AgentCredential) => {
    setCredForm({ name: cred.name, agentId: cred.agentId, agentSecret: cred.agentSecret, agentBaseUrl: cred.agentBaseUrl, agentAppClientId: cred.agentAppClientId });
    setCredEditingId(cred.id);
    setCredFormError(null);
    setCredFormOpen(true);
  };

  const saveCredential = () => {
    if (!credForm.name.trim() || !credForm.agentId.trim() || !credForm.agentSecret.trim() || !credForm.agentBaseUrl.trim() || !credForm.agentAppClientId.trim()) {
      setCredFormError('All fields are required.');
      return;
    }
    const cred: AgentCredential = {
      id: credEditingId ?? `cred-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: credForm.name.trim(),
      agentId: credForm.agentId.trim(),
      agentSecret: credForm.agentSecret,
      agentBaseUrl: credForm.agentBaseUrl.trim(),
      agentAppClientId: credForm.agentAppClientId.trim(),
    };
    workflowStore.saveAgentCredential(cred);
    setCredentials(workflowStore.getAgentCredentials());
    setCredFormOpen(false);
  };

  const deleteCredential = (id: string) => {
    workflowStore.deleteAgentCredential(id);
    setCredentials(workflowStore.getAgentCredentials());
    setCredFormOpen(false);
    if (agentData.agentCredentialId === id) {
      onUpdate(node.id, { data: { ...agentData, agentCredentialId: undefined } });
    }
  };

  const selectedCred = credentials.find((c) => c.id === agentData.agentCredentialId);

  return (
    <>
      <div className="space-y-3">
        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">Agent Name</label>
          <Input
            value={agentData.agentName || ''}
            onChange={(e) => onUpdate(node.id, { data: { ...agentData, agentName: e.target.value } })}
            placeholder="Enter agent name"
          />
        </div>

        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">Agent Credentials</label>
          <div className="flex gap-2">
            <select
              value={agentData.agentCredentialId || ''}
              onChange={(e) => {
                setCredFormOpen(false);
                onUpdate(node.id, { data: { ...agentData, agentCredentialId: e.target.value || undefined } });
              }}
              className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm"
            >
              <option value="">Select credentials</option>
              {credentials.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
            {selectedCred && (
              <button
                type="button"
                title="Edit credential"
                onClick={() => openEditCredModal(selectedCred)}
                className="flex items-center justify-center px-2 border border-gray-300 rounded-md hover:bg-gray-50 text-gray-500 hover:text-gray-700 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                </svg>
              </button>
            )}
            <Button type="button" size="sm" variant="outline" onClick={openAddCredModal}>+ Add</Button>
          </div>
          {credentials.length === 0 && !credFormOpen && (
            <p className="text-xs text-gray-500 mt-1">No credentials saved yet. Click + Add to create one.</p>
          )}
          {!credFormOpen && selectedCred && (
            <div className="mt-2 flex flex-col gap-1">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={agentTokenLoading}
                onClick={() => checkAgentToken(selectedCred)}
              >
                {agentTokenLoading ? 'Fetching...' : 'Test Fetching an Agent Token'}
              </Button>
              {agentTokenError && <p className="text-xs text-red-600">{agentTokenError}</p>}
            </div>
          )}
        </div>

        {credFormOpen && (
          <div className="rounded-md border border-blue-200 bg-white p-3 space-y-3">
            <div className="flex items-center justify-between">
              <p className="text-sm font-semibold text-gray-800">
                {credEditingId ? 'Edit Credential' : 'New Credential'}
              </p>
              <button type="button" onClick={() => setCredFormOpen(false)} className="text-gray-400 hover:text-gray-600 text-base leading-none">✕</button>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 mb-1 block">Name</label>
              <Input value={credForm.name} onChange={(e) => setCredForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Travel Agent – Dev" />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 mb-1 block">Agent ID</label>
              <Input value={credForm.agentId} onChange={(e) => setCredForm((f) => ({ ...f, agentId: e.target.value }))} placeholder="e.g. f79d600c-e92c-4b58-..." />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 mb-1 block">Agent Secret</label>
              <Input type="password" value={credForm.agentSecret} onChange={(e) => setCredForm((f) => ({ ...f, agentSecret: e.target.value }))} placeholder="Enter agent secret" />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 mb-1 block">Base URL</label>
              <Input value={credForm.agentBaseUrl} onChange={(e) => setCredForm((f) => ({ ...f, agentBaseUrl: e.target.value }))} placeholder="https://api.asgardeo.io/t/your-org or https://localhost:9443" />
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 mb-1 block">Agent Application Client ID</label>
              <Input value={credForm.agentAppClientId} onChange={(e) => setCredForm((f) => ({ ...f, agentAppClientId: e.target.value }))} placeholder="Enter client ID" />
              <p className="text-xs text-gray-500 mt-1">Make sure you enable PKCE and public client in the application.</p>
            </div>
            <div>
              <label className="text-xs font-semibold text-gray-700 mb-1 block">Redirect URI</label>
              <Input value={window.location.origin} readOnly className="bg-white text-gray-500 cursor-not-allowed" />
            </div>
            {credFormError && <p className="text-xs text-red-600">{credFormError}</p>}
            <div className="flex gap-2">
              <Button type="button" size="sm" onClick={saveCredential}>Save</Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setCredFormOpen(false)}>Cancel</Button>
              {credEditingId && (
                <Button type="button" size="sm" variant="outline" className="ml-auto text-red-600 border-red-200 hover:bg-red-50" onClick={() => deleteCredential(credEditingId)}>Delete</Button>
              )}
            </div>
          </div>
        )}

        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">System Prompt</label>
          <Textarea
            value={agentData.systemPrompt || ''}
            onChange={(e) => onUpdate(node.id, { data: { ...agentData, systemPrompt: e.target.value } })}
            placeholder="Enter system prompt for the AI agent..."
            className="text-sm"
            rows={3}
          />
        </div>

        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">Max Tool Steps</label>
          <Input
            type="number"
            value={agentData.maxToolSteps || 6}
            onChange={(e) => onUpdate(node.id, { data: { ...agentData, maxToolSteps: Math.max(1, parseInt(e.target.value, 10) || 6) } })}
            min="1"
            max="12"
          />
          <p className="text-xs text-gray-500 mt-1">Maximum number of MCP tool calls allowed before forcing a final answer.</p>
        </div>

        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">Messages to Keep</label>
          <Input
            type="number"
            value={agentData.maxMessages || ''}
            onChange={(e) =>
              onUpdate(node.id, {
                data: {
                  ...agentData,
                  maxMessages: e.target.value === ''
                    ? undefined
                    : Math.min(100, Math.max(1, parseInt(e.target.value, 10) || 1)),
                },
              })
            }
            min="1"
            max="100"
            placeholder="Disabled"
          />
          <p className="text-xs text-gray-500 mt-1">Number of recent chat messages to include as memory context. Leave empty to disable memory.</p>
        </div>

        {agentData.maxMessages && workflowId && (
          <div className="rounded-md border border-gray-200 bg-gray-50 p-3">
            <p className="text-sm font-semibold text-gray-700 mb-1">Stored Messages</p>
            <p className="text-xs text-gray-600 mb-3">
              {`${memoryCount} message${memoryCount === 1 ? '' : 's'} currently saved.`}
            </p>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                workflowStore.clearWorkflowMemory(workflowId, node.id);
                setMemoryCount(0);
              }}
              disabled={memoryCount === 0}
            >
              Clear Memory
            </Button>
          </div>
        )}
      </div>

      {agentTokenModalOpen && agentToken && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-lg w-full mx-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-base font-bold text-gray-900">Agent Token</h3>
              <button type="button" onClick={() => setAgentTokenModalOpen(false)} className="text-gray-400 hover:text-gray-600 text-lg leading-none">✕</button>
            </div>
            <div className="bg-gray-50 rounded-md p-3 mb-4 max-h-40 overflow-auto border border-gray-200">
              <code className="text-xs text-gray-800 break-all select-all whitespace-pre-wrap">{agentToken}</code>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => {
                  navigator.clipboard.writeText(agentToken);
                  setAgentTokenCopied(true);
                  setTimeout(() => setAgentTokenCopied(false), 2000);
                }}
              >
                {agentTokenCopied ? 'Copied!' : 'Copy'}
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => window.open(`https://jwt.io/#id_token=${encodeURIComponent(agentToken)}`, '_blank')}
              >
                Decode
              </Button>
              <Button type="button" size="sm" variant="outline" onClick={() => setAgentTokenModalOpen(false)}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
