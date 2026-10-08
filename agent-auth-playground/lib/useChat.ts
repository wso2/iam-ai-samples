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

import { useState, useCallback, useRef, useEffect } from 'react';
import {
  AIAgentNodeData,
  ChatMessage,
  MCPClientNodeData,
  Workflow,
  OAuthConfig,
} from './types';
import { workflowStore, generateId } from './workflowStore';
import { WorkflowTrace, MCPNodeTrace, dominantFlow } from './authTrace';

export interface UseChatOptions {
  onStreamChunk?: (chunk: string) => void;
  onComplete?: (fullMessage: string) => void;
  onError?: (error: string) => void;
}

interface MemoryBinding {
  nodeId: string;
  maxMessages: number;
}

interface OBOPendingNode {
  nodeId: string;
  name: string;
  baseUrl: string;
  clientId: string;
  redirectUri: string;
  scope?: string;
  authUrl: string;
  codeVerifier: string;
  agentAccessToken: string;
  state: string;
}

interface OBOConsentState {
  pendingMessage: string;
  pendingWorkflow: Workflow;
  pendingUserMsg: ChatMessage;
  pendingNodes: OBOPendingNode[];
  currentNodeIndex: number;
}

function resolveMemoryBinding(workflow: Workflow): MemoryBinding | null {
  const agentNode = workflow.nodes.find((node) => node.type === 'aiAgent');
  if (!agentNode) return null;

  const agentData = agentNode.data as AIAgentNodeData;
  if (!agentData.maxMessages) return null;

  const maxMessages = Math.min(100, Math.max(1, Math.floor(agentData.maxMessages)));
  return { nodeId: agentNode.id, maxMessages };
}

function findAgentFlowsWithMissingCredentials(workflow: Workflow): string[] {
  const credentials = workflowStore.getAgentCredentials();
  return workflow.nodes
    .filter((n) => {
      if (n.type !== 'mcpClient') return false;
      const data = n.data as MCPClientNodeData;
      return data.useOAuth2 && (data.oauth2Flow ?? 'agent') === 'agent';
    })
    .filter((mcpNode) => {
      const edge = workflow.edges.find((e) => e.target === mcpNode.id);
      if (!edge) return false;
      const agentNode = workflow.nodes.find((n) => n.id === edge.source && n.type === 'aiAgent');
      if (!agentNode) return false;
      const agentData = agentNode.data as AIAgentNodeData;
      if (agentData.agentCredentialId) {
        return !credentials.some((c) => c.id === agentData.agentCredentialId);
      }
      return !(agentData as Record<string, unknown>)['agentId'];
    })
    .map((n) => (n.data as MCPClientNodeData).name?.trim() || n.id);
}

function findUninitializedMCPNodes(workflow: Workflow, workflowId: string): string[] {
  return workflow.nodes
    .filter((n) => n.type === 'mcpClient')
    .filter((n) => {
      const entry = workflowStore.getMCPTools(workflowId, n.id);
      return !entry || !Array.isArray(entry.tools) || entry.tools.length === 0;
    })
    .map((n) => {
      const data = n.data as MCPClientNodeData;
      return data.name?.trim() || n.id;
    });
}

function collectCachedMCPTools(
  workflow: Workflow,
  workflowId: string
): Record<string, { endpoint: string; tools: unknown[] }> {
  const out: Record<string, { endpoint: string; tools: unknown[] }> = {};
  for (const node of workflow.nodes) {
    if (node.type !== 'mcpClient') continue;
    const entry = workflowStore.getMCPTools(workflowId, node.id);
    if (entry) {
      out[node.id] = { endpoint: entry.endpoint, tools: entry.tools };
    }
  }
  return out;
}

function findOBONodes(workflow: Workflow, oauthConfigs: OAuthConfig[]): Array<{
  nodeId: string;
  name: string;
  baseUrl: string;
  clientId: string;
  redirectUri: string;
  scope?: string;
  agentId: string;
  agentSecret: string;
}> {
  const agentCredentials = workflowStore.getAgentCredentials();
  return workflow.nodes
    .filter((n) => n.type === 'mcpClient')
    .filter((n) => {
      const data = n.data as MCPClientNodeData;
      return data.useOAuth2 && data.oauth2Flow === 'obo';
    })
    .map((n) => {
      const data = n.data as MCPClientNodeData;
      const oauthConfig = data.oauth2ConfigId
        ? oauthConfigs.find((c) => c.id === data.oauth2ConfigId)
        : undefined;
      const edge = workflow.edges.find((e) => e.target === n.id);
      const agentNode = edge
        ? workflow.nodes.find((an) => an.id === edge.source && an.type === 'aiAgent')
        : null;
      const agentData = agentNode?.data as AIAgentNodeData | undefined;
      const cred = agentData?.agentCredentialId
        ? agentCredentials.find((c) => c.id === agentData.agentCredentialId)
        : undefined;
      return {
        nodeId: n.id,
        name: data.name?.trim() || n.id,
        baseUrl: oauthConfig?.oauth2BaseUrl || '',
        clientId: oauthConfig?.oauth2ClientId || '',
        redirectUri: typeof window !== 'undefined' ? window.location.origin : '',
        scope: oauthConfig?.oauth2Scope,
        agentId: cred?.agentId || '',
        agentSecret: cred?.agentSecret || '',
      };
    });
}

function extractAuthCode(input: string): string {
  const trimmed = input.trim();
  try {
    const url = new URL(trimmed);
    const code = url.searchParams.get('code');
    if (code) return code;
  } catch {
    // Not a URL, treat as raw code
  }
  return trimmed;
}

function buildOBOConsentMessage(name: string, current: number, total: number): string {
  const multi = total > 1 ? ` (${current} of ${total})` : '';
  return `Authorization Required${multi}\n\nThe AI agent needs your consent to act on your behalf to use the "${name}" resource.\n\nClick the link below to log in.`;
}

const CHAT_STORAGE_PREFIX = 'chatMessages:';

function loadStoredMessages(workflowId: string): ChatMessage[] {
  if (typeof window === 'undefined') return [];
  try {
    const raw = window.localStorage.getItem(CHAT_STORAGE_PREFIX + workflowId);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

function saveStoredMessages(workflowId: string, messages: ChatMessage[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(CHAT_STORAGE_PREFIX + workflowId, JSON.stringify(messages));
  } catch {
    // storage may be full or disabled — drop silently
  }
}

export function useChat(workflowId: string, options: UseChatOptions = {}) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadStoredMessages(workflowId));
  const hydratedWorkflowIdRef = useRef<string>(workflowId);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [oboConsentPending, setOboConsentPending] = useState(false);
  const [lastTrace, setLastTrace] = useState<WorkflowTrace | null>(null);
  const [activeNodeIds, setActiveNodeIds] = useState<Set<string>>(new Set());
  const abortControllerRef = useRef<AbortController | null>(null);
  const oboConsentStateRef = useRef<OBOConsentState | null>(null);
  const oboClientPatchRef = useRef<Record<string, Partial<MCPNodeTrace>>>({});
  const processOBOCodeRef = useRef<((code: string, opts?: { silent?: boolean }) => Promise<void>) | null>(null);

  const addMessage = useCallback((message: ChatMessage) => {
    setMessages((prev) => [...prev, message]);
  }, []);

  useEffect(() => {
    if (hydratedWorkflowIdRef.current === workflowId) return;
    hydratedWorkflowIdRef.current = workflowId;
    setMessages(loadStoredMessages(workflowId));
  }, [workflowId]);

  useEffect(() => {
    saveStoredMessages(workflowId, messages);
  }, [workflowId, messages]);

  const doExecuteWorkflow = useCallback(
    async (
      userMessage: string,
      workflowDefinition: Workflow,
      oboTokens: Record<string, string> = {},
      existingUserMsg?: ChatMessage
    ) => {
      setIsLoading(true);
      setError(null);

      const userMsg: ChatMessage = existingUserMsg ?? {
        id: generateId('msg-'),
        role: 'user',
        content: userMessage,
        timestamp: Date.now(),
        workflowId,
      };

      if (!existingUserMsg) {
        addMessage(userMsg);
      }

      const memoryBinding = resolveMemoryBinding(workflowDefinition);
      const memoryMessages = memoryBinding
        ? workflowStore
            .getWorkflowMemory(workflowId, memoryBinding.nodeId)
            .slice(-memoryBinding.maxMessages)
        : [];

      const MIN_GLOW_MS = 1000;
      const startTimes = new Map<string, number>();
      const pendingRemovals = new Map<string, ReturnType<typeof setTimeout>>();

      const removeActive = (nodeId: string) => {
        setActiveNodeIds((prev) => {
          if (!prev.has(nodeId)) return prev;
          const next = new Set(prev);
          next.delete(nodeId);
          return next;
        });
      };

      const handleStart = (nodeId: string) => {
        const existing = pendingRemovals.get(nodeId);
        if (existing) {
          clearTimeout(existing);
          pendingRemovals.delete(nodeId);
        }
        startTimes.set(nodeId, Date.now());
        setActiveNodeIds((prev) => {
          if (prev.has(nodeId)) return prev;
          const next = new Set(prev);
          next.add(nodeId);
          return next;
        });
      };

      const handleEnd = (nodeId: string) => {
        const start = startTimes.get(nodeId) ?? Date.now();
        const elapsed = Date.now() - start;
        if (elapsed >= MIN_GLOW_MS) {
          removeActive(nodeId);
          return;
        }
        const timer = setTimeout(() => {
          pendingRemovals.delete(nodeId);
          removeActive(nodeId);
        }, MIN_GLOW_MS - elapsed);
        pendingRemovals.set(nodeId, timer);
      };

      try {
        abortControllerRef.current = new AbortController();

        // Resolve oauth2ConfigId → actual fields so the server executor can read them directly
        const resolvedOAuthConfigs = workflowStore.getOAuthConfigs();
        const resolvedWorkflow = {
          ...workflowDefinition,
          nodes: workflowDefinition.nodes.map((n) => {
            if (n.type !== 'mcpClient') return n;
            const data = n.data as MCPClientNodeData;
            if (!data.useOAuth2 || !data.oauth2ConfigId) return n;
            const config = resolvedOAuthConfigs.find((c) => c.id === data.oauth2ConfigId);
            if (!config) return n;
            return {
              ...n,
              data: {
                ...data,
                oauth2BaseUrl: config.oauth2BaseUrl,
                oauth2ClientId: config.oauth2ClientId,
                oauth2Scope: config.oauth2Scope,
                oauth2RedirectUri: typeof window !== 'undefined' ? window.location.origin : '',
              },
            };
          }),
        };

        const response = await fetch('/api/execute-workflow', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            workflow: resolvedWorkflow,
            input: userMessage,
            workflowId,
            llmCredentials: workflowStore.getLLMCredentials(),
            agentCredentials: workflowStore.getAgentCredentials(),
            memoryMessages,
            oboTokens,
            mcpDiscoveredTools: collectCachedMCPTools(workflowDefinition, workflowId),
          }),
          signal: abortControllerRef.current.signal,
        });

        if (!response.body) {
          throw new Error('No response body from workflow API');
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let data: any = null;

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });

          let sepIndex: number;
          while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
            const rawEvent = buffer.slice(0, sepIndex);
            buffer = buffer.slice(sepIndex + 2);
            const line = rawEvent.split('\n').find((l) => l.startsWith('data:'));
            if (!line) continue;
            let parsed: any;
            try {
              parsed = JSON.parse(line.slice(5).trim());
            } catch {
              continue;
            }

            if (parsed.type === 'node-start') {
              handleStart(parsed.nodeId);
            } else if (parsed.type === 'node-end') {
              handleEnd(parsed.nodeId);
            } else if (parsed.type === 'result') {
              data = parsed;
            }
            // consent-required is signalled via result.requiresConsent; no separate handling needed here
          }
        }

        if (!data) {
          throw new Error('Workflow stream ended without a result');
        }

        // Server aborted because an OBO MCP needs user consent
        if (data.requiresConsent) {
          await startOBOConsentFlow(userMessage, workflowDefinition, userMsg, oboTokens);
          return;
        }

        if (!data.success) {
          throw new Error(data.error || 'Workflow execution failed');
        }

        const assistantMsg: ChatMessage = {
          id: generateId('msg-'),
          role: 'assistant',
          content: data.output,
          timestamp: Date.now(),
          workflowId,
        };
        addMessage(assistantMsg);

        if (data.trace) {
          const trace: WorkflowTrace = data.trace;
          const patches = oboClientPatchRef.current;
          for (const m of trace.mcps) {
            const patch = patches[m.nodeId];
            if (patch) Object.assign(m, patch);
          }
          trace.flow = dominantFlow(trace.mcps);
          setLastTrace(trace);
        }

        if (memoryBinding) {
          workflowStore.appendWorkflowMemory(
            workflowId,
            memoryBinding.nodeId,
            [userMsg, assistantMsg],
            memoryBinding.maxMessages
          );
        }

        options.onComplete?.(data.output);
      } catch (err) {
        setActiveNodeIds(new Set());
        if (err instanceof Error && err.name === 'AbortError') return;
        const errorMsg = err instanceof Error ? err.message : 'Unknown error occurred';
        setError(errorMsg);
        options.onError?.(errorMsg);
      } finally {
        setIsLoading(false);
      }
    },
    [workflowId, addMessage, options]
  );

  // Starts the OBO consent flow for all OBO MCP nodes that still lack a valid token.
  // Called when the server emits requiresConsent=true (i.e. the agent tried to call
  // a tool on an OBO-protected MCP and had no token).
  const startOBOConsentFlow = useCallback(
    async (
      pendingMessage: string,
      pendingWorkflow: Workflow,
      pendingUserMsg: ChatMessage,
      existingOboTokens: Record<string, string>
    ) => {
      const oboNodes = findOBONodes(pendingWorkflow, workflowStore.getOAuthConfigs());
      const missingNodes = oboNodes.filter(
        (n) => !workflowStore.getOBOToken(workflowId, n.nodeId) && !existingOboTokens[n.nodeId]
      );

      if (missingNodes.length === 0) {
        // All tokens available — this shouldn't normally happen, but re-run just in case
        const allTokens: Record<string, string> = { ...existingOboTokens };
        for (const node of oboNodes) {
          const t = workflowStore.getOBOToken(workflowId, node.nodeId);
          if (t) allTokens[node.nodeId] = t;
        }
        await doExecuteWorkflow(pendingMessage, pendingWorkflow, allTokens, pendingUserMsg);
        return;
      }

      setIsLoading(true);
      setError(null);

      try {
        const initResults = await Promise.all(
          missingNodes.map(async (node) => {
            const res = await fetch('/api/obo/init', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify(node),
            });
            if (!res.ok) {
              const errData = await res.json().catch(() => ({}));
              throw new Error(
                (errData as { error?: string }).error ||
                  `OBO init failed for MCP node ${node.nodeId}`
              );
            }
            const resData = await res.json();
            return {
              nodeId: node.nodeId,
              name: node.name,
              baseUrl: node.baseUrl,
              clientId: node.clientId,
              redirectUri: node.redirectUri,
              scope: node.scope,
              authUrl: resData.authUrl as string,
              codeVerifier: resData.codeVerifier as string,
              agentAccessToken: resData.agentAccessToken as string,
              state: resData.state as string,
            } satisfies OBOPendingNode;
          })
        );

        for (const r of initResults) {
          oboClientPatchRef.current[r.nodeId] = {
            oboAuthUrl: r.authUrl,
            agentToken: r.agentAccessToken,
          };
        }

        oboConsentStateRef.current = {
          pendingMessage,
          pendingWorkflow,
          pendingUserMsg,
          pendingNodes: initResults,
          currentNodeIndex: 0,
        };
        setOboConsentPending(true);

        const first = initResults[0];
        addMessage({
          id: generateId('msg-'),
          role: 'assistant',
          content: buildOBOConsentMessage(first.name, 1, initResults.length),
          timestamp: Date.now(),
          workflowId,
          type: 'obo-consent',
          metadata: { authUrl: first.authUrl },
        });
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'OBO initialization failed';
        setError(errorMsg);
        options.onError?.(errorMsg);
      } finally {
        setIsLoading(false);
      }
    },
    [workflowId, addMessage, doExecuteWorkflow, options]
  );

  const processOBOCode = useCallback(
    async (codeInput: string, { silent = false }: { silent?: boolean } = {}) => {
      const state = oboConsentStateRef.current;
      if (!state) return;

      if (!silent) {
        addMessage({
          id: generateId('msg-'),
          role: 'user',
          content: codeInput,
          timestamp: Date.now(),
          workflowId,
        });
      }

      setIsLoading(true);
      setError(null);

      try {
        const currentNode = state.pendingNodes[state.currentNodeIndex];
        const code = extractAuthCode(codeInput);

        const exchangeRes = await fetch('/api/obo/exchange', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            authCode: code,
            agentAccessToken: currentNode.agentAccessToken,
            codeVerifier: currentNode.codeVerifier,
            baseUrl: currentNode.baseUrl,
            clientId: currentNode.clientId,
            redirectUri: currentNode.redirectUri,
          }),
        });

        if (!exchangeRes.ok) {
          const errData = await exchangeRes.json().catch(() => ({}));
          throw new Error(
            (errData as { error?: string }).error || `OBO exchange failed: ${exchangeRes.status}`
          );
        }

        const { accessToken, expiresIn } = await exchangeRes.json();
        workflowStore.setOBOToken(workflowId, currentNode.nodeId, accessToken, expiresIn || 3600);

        const nextIndex = state.currentNodeIndex + 1;

        if (nextIndex < state.pendingNodes.length) {
          oboConsentStateRef.current = { ...state, currentNodeIndex: nextIndex };
          const nextNode = state.pendingNodes[nextIndex];
          addMessage({
            id: generateId('msg-'),
            role: 'assistant',
            content: buildOBOConsentMessage(nextNode.name, nextIndex + 1, state.pendingNodes.length),
            timestamp: Date.now(),
            workflowId,
            type: 'obo-consent',
            metadata: { authUrl: nextNode.authUrl },
          });
        } else {
          oboConsentStateRef.current = null;
          setOboConsentPending(false);

          addMessage({
            id: generateId('msg-'),
            role: 'assistant',
            content: 'Authorization complete! Processing your request...',
            timestamp: Date.now(),
            workflowId,
          });

          // Collect all valid OBO tokens for the workflow and re-run
          const allOBONodes = findOBONodes(state.pendingWorkflow, workflowStore.getOAuthConfigs());
          const oboTokens: Record<string, string> = {};
          for (const node of allOBONodes) {
            const token = workflowStore.getOBOToken(workflowId, node.nodeId);
            if (token) oboTokens[node.nodeId] = token;
          }

          await doExecuteWorkflow(
            state.pendingMessage,
            state.pendingWorkflow,
            oboTokens,
            state.pendingUserMsg
          );
        }
      } catch (err) {
        const errorMsg = err instanceof Error ? err.message : 'OBO token exchange failed';
        setError(errorMsg);
        options.onError?.(errorMsg);
        oboConsentStateRef.current = null;
        setOboConsentPending(false);
      } finally {
        setIsLoading(false);
      }
    },
    [workflowId, addMessage, doExecuteWorkflow, options]
  );

  useEffect(() => {
    processOBOCodeRef.current = processOBOCode;
  }, [processOBOCode]);

  useEffect(() => {
    if (!oboConsentPending) return;

    const channel = new BroadcastChannel('obo-callback');
    channel.onmessage = (event: MessageEvent<{ code: string; state: string }>) => {
      const { code, state } = event.data;
      const pending = oboConsentStateRef.current;
      if (!pending) return;
      const currentNode = pending.pendingNodes[pending.currentNodeIndex];
      if (currentNode.state !== state) return;
      processOBOCodeRef.current?.(code, { silent: true });
    };

    return () => channel.close();
  }, [oboConsentPending]);

  const executeWorkflow = useCallback(
    async (userMessage: string, workflowDefinition: Workflow) => {
      if (oboConsentStateRef.current !== null) return;

      const uninitializedMCPs = findUninitializedMCPNodes(workflowDefinition, workflowId);
      if (uninitializedMCPs.length > 0) {
        const errorMsg = `Initialize MCP Client${
          uninitializedMCPs.length > 1 ? 's' : ''
        } before chatting: ${uninitializedMCPs.join(', ')}. Open each MCP node and click "Initialize & Connect".`;
        setError(errorMsg);
        options.onError?.(errorMsg);
        return;
      }

      const agentFlowsMissingCreds = findAgentFlowsWithMissingCredentials(workflowDefinition);
      if (agentFlowsMissingCreds.length > 0) {
        const errorMsg = `Agent credentials required for MCP Client${
          agentFlowsMissingCreds.length > 1 ? 's' : ''
        }: ${agentFlowsMissingCreds.join(', ')}. Open the connected AI Agent node and select or add credentials under "Agent Credentials".`;
        setError(errorMsg);
        options.onError?.(errorMsg);
        return;
      }

      // Collect any already-stored OBO tokens (from a prior consent in this session)
      const oboNodes = findOBONodes(workflowDefinition, workflowStore.getOAuthConfigs());
      const oboTokens: Record<string, string> = {};
      for (const node of oboNodes) {
        const token = workflowStore.getOBOToken(workflowId, node.nodeId);
        if (token) oboTokens[node.nodeId] = token;
      }

      await doExecuteWorkflow(userMessage, workflowDefinition, oboTokens);
    },
    [workflowId, doExecuteWorkflow, options]
  );

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
    oboConsentStateRef.current = null;
    setOboConsentPending(false);
    setLastTrace(null);
    setActiveNodeIds(new Set());
    oboClientPatchRef.current = {};
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(CHAT_STORAGE_PREFIX + workflowId);
      } catch {
        // ignore
      }
    }
  }, [workflowId]);

  const cancel = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsLoading(false);
    setActiveNodeIds(new Set());
  }, []);

  return {
    messages,
    isLoading,
    error,
    oboConsentPending,
    lastTrace,
    activeNodeIds,
    addMessage,
    executeWorkflow,
    clearMessages,
    cancel,
  };
}
