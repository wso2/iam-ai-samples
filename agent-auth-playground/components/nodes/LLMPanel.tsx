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

import { useState, useEffect, useRef } from 'react';
import { WorkflowNode, LLMNodeData, LLMCredential, LLMCredentialProvider } from '@/lib/types';
import { workflowStore } from '@/lib/workflowStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

interface LLMPanelProps {
  node: WorkflowNode;
  onUpdate: (nodeId: string, updates: Partial<WorkflowNode>) => void;
}

const providerModels: Record<string, string[]> = {
  gemini: [
    'gemini-2.5-flash',
    'gemini-2.5-flash-lite',
    'gemini-2.5-pro',
    'gemini-3-flash-preview',
    'gemini-3.1-flash-lite-preview',
    'gemini-3.1-pro-preview',
  ],
  openai: ['gpt-4o', 'gpt-4-turbo', 'gpt-3.5-turbo'],
  anthropic: ['claude-opus-4-7', 'claude-sonnet-4-6', 'claude-haiku-4-5-20251001'],
  'azure-openai': [],
};

function llmCredProvider(provider: string, geminiAuthType?: string): LLMCredentialProvider {
  if (provider === 'gemini') return geminiAuthType === 'gcp-access-token' ? 'gcp' : 'gemini';
  return provider as LLMCredentialProvider;
}

export default function LLMPanel({ node, onUpdate }: LLMPanelProps) {
  const llmData = node.data as LLMNodeData;
  const isGemini = llmData.provider === 'gemini';
  const isAzure = llmData.provider === 'azure-openai';
  const isGcpAuth = isGemini && llmData.geminiAuthType === 'gcp-access-token';

  const [modelDropdownOpen, setModelDropdownOpen] = useState(false);
  const [modelInputValue, setModelInputValue] = useState('');
  const modelComboboxRef = useRef<HTMLDivElement>(null);

  const [llmCredentials, setLLMCredentials] = useState<LLMCredential[]>([]);
  const [llmCredFormOpen, setLLMCredFormOpen] = useState(false);
  const [llmCredEditingId, setLLMCredEditingId] = useState<string | null>(null);
  const [llmCredForm, setLLMCredForm] = useState({ name: '', apiKey: '', gcpAccessToken: '', gcpProjectId: '', azureResourceName: '', azureDeploymentName: '', azureApiVersion: '' });
  const [llmCredFormError, setLLMCredFormError] = useState<string | null>(null);

  useEffect(() => {
    setLLMCredentials(workflowStore.getLLMCredentials());
  }, []);

  const applyLLMCredential = (cred: LLMCredential) => {
    onUpdate(node.id, { data: { ...llmData, llmCredentialId: cred.id } });
  };

  const openAddLLMCredForm = () => {
    setLLMCredForm({ name: '', apiKey: '', gcpAccessToken: '', gcpProjectId: '', azureResourceName: '', azureDeploymentName: '', azureApiVersion: '' });
    setLLMCredEditingId(null);
    setLLMCredFormError(null);
    setLLMCredFormOpen(true);
  };

  const openEditLLMCredForm = (cred: LLMCredential) => {
    setLLMCredForm({
      name: cred.name,
      apiKey: cred.apiKey ?? '',
      gcpAccessToken: cred.gcpAccessToken ?? '',
      gcpProjectId: cred.gcpProjectId ?? '',
      azureResourceName: cred.azureResourceName ?? '',
      azureDeploymentName: cred.azureDeploymentName ?? '',
      azureApiVersion: cred.azureApiVersion ?? '',
    });
    setLLMCredEditingId(cred.id);
    setLLMCredFormError(null);
    setLLMCredFormOpen(true);
  };

  const saveLLMCredential = (credType: LLMCredentialProvider) => {
    const f = llmCredForm;
    const isGCP = credType === 'gcp';
    const isAzureCred = credType === 'azure-openai';
    if (!f.name.trim()) { setLLMCredFormError('Name is required.'); return; }
    if (isGCP && (!f.gcpAccessToken.trim() || !f.gcpProjectId.trim())) { setLLMCredFormError('Access token and project ID are required.'); return; }
    if (isAzureCred && (!f.azureResourceName.trim() || !f.azureDeploymentName.trim() || !f.azureApiVersion.trim() || !f.apiKey.trim())) { setLLMCredFormError('All Azure fields are required.'); return; }
    if (!isGCP && !isAzureCred && !f.apiKey.trim()) { setLLMCredFormError('API key is required.'); return; }

    const cred: LLMCredential = {
      id: llmCredEditingId ?? `llmcred-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
      name: f.name.trim(),
      provider: credType,
      ...(isGCP ? { gcpAccessToken: f.gcpAccessToken, gcpProjectId: f.gcpProjectId } : {}),
      ...(isAzureCred ? { azureResourceName: f.azureResourceName.trim(), azureDeploymentName: f.azureDeploymentName.trim(), azureApiVersion: f.azureApiVersion.trim(), apiKey: f.apiKey } : {}),
      ...(!isGCP && !isAzureCred ? { apiKey: f.apiKey } : {}),
    };
    workflowStore.saveLLMCredential(cred);
    setLLMCredentials(workflowStore.getLLMCredentials());
    setLLMCredFormOpen(false);
    applyLLMCredential(cred);
  };

  const deleteLLMCredential = (id: string) => {
    workflowStore.deleteLLMCredential(id);
    setLLMCredentials(workflowStore.getLLMCredentials());
    setLLMCredFormOpen(false);
    if (llmData.llmCredentialId === id) {
      onUpdate(node.id, { data: { ...llmData, llmCredentialId: undefined } });
    }
  };

  const credType = llmData.provider ? llmCredProvider(llmData.provider, llmData.geminiAuthType) : null;
  const credLabel: Record<LLMCredentialProvider, string> = {
    gemini: 'Gemini Credentials',
    gcp: 'GCP Credentials',
    anthropic: 'Anthropic Credentials',
    openai: 'OpenAI Credentials',
    'azure-openai': 'Azure OpenAI Credentials',
  };
  const matching = credType ? llmCredentials.filter((c) => c.provider === credType) : [];
  const selectedCred = matching.find((c) => c.id === llmData.llmCredentialId);

  const azureEndpointPreview = isAzure
    ? `https://${selectedCred?.azureResourceName || 'resource-name'}.openai.azure.com/openai/deployments/${selectedCred?.azureDeploymentName || 'deployment-name'}/chat/completions?api-version=${selectedCred?.azureApiVersion || 'api-version'}`
    : '';
  void azureEndpointPreview;

  return (
    <div className="space-y-3">
      <div>
        <label className="text-sm font-semibold text-gray-700 mb-1 block">Provider</label>
        <select
          value={llmData.provider || ''}
          onChange={(e) =>
            onUpdate(node.id, {
              data: {
                ...llmData,
                provider: e.target.value as 'gemini' | 'openai' | 'anthropic' | 'azure-openai',
                model: '',
                geminiAuthType: undefined,
              },
            })
          }
          className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
        >
          <option value="" disabled>Select a provider</option>
          <option value="gemini">Google Gemini</option>
          <option value="anthropic">Anthropic</option>
          <option value="openai">OpenAI</option>
          <option value="azure-openai">Azure OpenAI</option>
        </select>
      </div>

      {!isAzure && (
        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">Model</label>
          <div className="relative" ref={modelComboboxRef}>
            <input
              type="text"
              value={modelInputValue !== '' ? modelInputValue : (llmData.model || '')}
              placeholder="Type or select a model…"
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
              onFocus={() => { setModelInputValue(llmData.model || ''); setModelDropdownOpen(true); }}
              onChange={(e) => {
                setModelInputValue(e.target.value);
                setModelDropdownOpen(true);
                onUpdate(node.id, { data: { ...llmData, model: e.target.value } });
              }}
              onBlur={() => { setTimeout(() => { setModelDropdownOpen(false); setModelInputValue(''); }, 150); }}
            />
            {modelDropdownOpen && (() => {
              const query = modelInputValue.toLowerCase();
              const suggestions = (providerModels[llmData.provider] ?? []).filter((m) => !query || m.toLowerCase().includes(query));
              return suggestions.length > 0 ? (
                <ul className="absolute z-50 w-full mt-1 bg-white border border-gray-200 rounded-md shadow-lg max-h-48 overflow-y-auto text-sm">
                  {suggestions.map((model) => (
                    <li
                      key={model}
                      className="px-3 py-2 cursor-pointer hover:bg-gray-100"
                      onMouseDown={() => { onUpdate(node.id, { data: { ...llmData, model } }); setModelInputValue(''); setModelDropdownOpen(false); }}
                    >
                      {model}
                    </li>
                  ))}
                </ul>
              ) : null;
            })()}
          </div>
        </div>
      )}

      {isGemini && (
        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">Authentication</label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => onUpdate(node.id, { data: { ...llmData, geminiAuthType: 'api-key' } })}
              className={`flex-1 py-2 px-3 text-sm rounded-md border transition-colors ${!isGcpAuth ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'}`}
            >
              Gemini API Key
            </button>
            <button
              type="button"
              onClick={() => onUpdate(node.id, { data: { ...llmData, geminiAuthType: 'gcp-access-token' } })}
              className={`flex-1 py-2 px-3 text-sm rounded-md border transition-colors ${isGcpAuth ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 border-gray-300 hover:border-gray-400'}`}
            >
              GCP Access Token
            </button>
          </div>
        </div>
      )}

      {credType && (
        <>
          <div>
            <label className="text-sm font-semibold text-gray-700 mb-1 block">{credLabel[credType]}</label>
            <div className="flex gap-2">
              <select
                value={llmData.llmCredentialId || ''}
                onChange={(e) => {
                  setLLMCredFormOpen(false);
                  const chosen = matching.find((c) => c.id === e.target.value);
                  if (chosen) {
                    applyLLMCredential(chosen);
                  } else {
                    onUpdate(node.id, { data: { ...llmData, llmCredentialId: undefined } });
                  }
                }}
                className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm"
              >
                <option value="">Select credentials</option>
                {matching.map((c) => (
                  <option key={c.id} value={c.id}>{c.name}</option>
                ))}
              </select>
              {selectedCred && (
                <button
                  type="button"
                  title="Edit credential"
                  onClick={() => openEditLLMCredForm(selectedCred)}
                  className="flex items-center justify-center px-2 border border-gray-300 rounded-md hover:bg-gray-50 text-gray-500 hover:text-gray-700 transition-colors"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                  </svg>
                </button>
              )}
              <Button type="button" size="sm" variant="outline" onClick={openAddLLMCredForm}>+ Add</Button>
            </div>
            {matching.length === 0 && !llmCredFormOpen && (
              <p className="text-xs text-gray-500 mt-1">No credentials saved yet. Click + Add to create one.</p>
            )}
          </div>

          {llmCredFormOpen && (
            <div className="rounded-md border border-blue-200 bg-white-50 p-3 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-800">{llmCredEditingId ? 'Edit Credential' : 'New Credential'}</p>
                <button type="button" onClick={() => setLLMCredFormOpen(false)} className="text-gray-400 hover:text-gray-600 text-base leading-none">✕</button>
              </div>

              <div>
                <label className="text-xs font-semibold text-gray-700 mb-1 block">Name</label>
                <Input value={llmCredForm.name} onChange={(e) => setLLMCredForm((f) => ({ ...f, name: e.target.value }))} placeholder="e.g. Production key" />
              </div>

              {credType === 'gcp' ? (
                <>
                  <div>
                    <label className="text-xs font-semibold text-gray-700 mb-1 block">GCP Access Token</label>
                    <Input type="password" value={llmCredForm.gcpAccessToken} onChange={(e) => setLLMCredForm((f) => ({ ...f, gcpAccessToken: e.target.value }))} placeholder="Paste your GCP access token" />
                    <p className="text-xs text-gray-500 mt-1">Obtain via <code>gcloud auth print-access-token</code></p>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-700 mb-1 block">GCP Project ID</label>
                    <Input value={llmCredForm.gcpProjectId} onChange={(e) => setLLMCredForm((f) => ({ ...f, gcpProjectId: e.target.value }))} placeholder="my-gcp-project" />
                    <p className="text-xs text-gray-500 mt-1">Calls Vertex AI in <code>us-central1</code></p>
                  </div>
                </>
              ) : credType === 'azure-openai' ? (
                <>
                  <div>
                    <label className="text-xs font-semibold text-gray-700 mb-1 block">Resource Name</label>
                    <Input value={llmCredForm.azureResourceName} onChange={(e) => setLLMCredForm((f) => ({ ...f, azureResourceName: e.target.value }))} placeholder="my-resource" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-700 mb-1 block">Deployment Name</label>
                    <Input value={llmCredForm.azureDeploymentName} onChange={(e) => setLLMCredForm((f) => ({ ...f, azureDeploymentName: e.target.value }))} placeholder="gpt-4o-deployment" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-700 mb-1 block">API Version</label>
                    <Input value={llmCredForm.azureApiVersion} onChange={(e) => setLLMCredForm((f) => ({ ...f, azureApiVersion: e.target.value }))} placeholder="2024-02-01" />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-gray-700 mb-1 block">API Key</label>
                    <Input type="password" value={llmCredForm.apiKey} onChange={(e) => setLLMCredForm((f) => ({ ...f, apiKey: e.target.value }))} placeholder="Enter Azure OpenAI API key" />
                  </div>
                </>
              ) : (
                <div>
                  <label className="text-xs font-semibold text-gray-700 mb-1 block">
                    API Key ({credType === 'gemini' ? 'Google' : credType === 'anthropic' ? 'Anthropic' : 'OpenAI'})
                  </label>
                  <Input type="password" value={llmCredForm.apiKey} onChange={(e) => setLLMCredForm((f) => ({ ...f, apiKey: e.target.value }))} placeholder="Enter API key" />
                </div>
              )}

              {llmCredFormError && <p className="text-xs text-red-600">{llmCredFormError}</p>}

              <div className="flex gap-2">
                <Button type="button" size="sm" onClick={() => saveLLMCredential(credType)}>Save</Button>
                <Button type="button" size="sm" variant="outline" onClick={() => setLLMCredFormOpen(false)}>Cancel</Button>
                {llmCredEditingId && (
                  <Button type="button" size="sm" variant="outline" className="ml-auto text-red-600 border-red-200 hover:bg-red-50" onClick={() => deleteLLMCredential(llmCredEditingId)}>Delete</Button>
                )}
              </div>
            </div>
          )}
        </>
      )}

      {llmData.provider !== 'azure-openai' && (
        <div>
          <label className="text-sm font-semibold text-gray-700 mb-1 block">Temperature</label>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={llmData.temperature ?? 0.7}
              onChange={(e) => onUpdate(node.id, { data: { ...llmData, temperature: parseFloat(e.target.value) } })}
              className="flex-1"
            />
            <span className="text-sm font-mono bg-gray-100 px-2 py-1 rounded">
              {(llmData.temperature ?? 0.7).toFixed(1)}
            </span>
          </div>
        </div>
      )}

      <div>
        <label className="text-sm font-semibold text-gray-700 mb-1 block">Max Tokens</label>
        <Input
          type="number"
          value={llmData.maxTokens || 1000}
          onChange={(e) => onUpdate(node.id, { data: { ...llmData, maxTokens: parseInt(e.target.value) || 1000 } })}
          min="1"
          max="4000"
        />
      </div>
    </div>
  );
}
