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
import 'server-only';

import {
  Workflow,
  WorkflowNode,
  ExecutionContext,
  ExecutionResult,
  AIAgentNodeData,
  AgentCredential,
  ChatMessage,
  LLMNodeData,
  LLMCredential,
  MCPClientNodeData,
} from '../types';
import { executeChatTrigger } from './chatTrigger';
import { executeAIAgent, executeLLM } from './aiAgent';
import { getErrorMessage } from './utils';
import { WorkflowTrace, emptyTrace, dominantFlow } from '../authTrace';
import { AuthFlowError } from '../agentAuth';
import { CachedMCPToolsMap, MCPClientConfig, ConsentRequiredError } from './types';
import { MCPClientNodeRuntime } from '../mcpClientNode';

export type WorkflowEvent =
  | { type: 'node-start'; nodeId: string }
  | { type: 'node-end'; nodeId: string }
  | { type: 'consent-required'; nodeId: string };

export type WorkflowEventHandler = (event: WorkflowEvent) => void;

export class WorkflowExecutor {
  private workflow: Workflow;
  private context: ExecutionContext;
  private llmCredentials: LLMCredential[];
  private agentCredentials: AgentCredential[];
  private baseUrl: string;
  private oboTokens: Record<string, string>;
  private mcpDiscoveredTools: CachedMCPToolsMap;
  private trace: WorkflowTrace;
  private onEvent?: WorkflowEventHandler;

  constructor(
    workflow: Workflow,
    initialInput: string,
    workflowId: string,
    llmCredentials: LLMCredential[] = [],
    agentCredentials: AgentCredential[] = [],
    baseUrl?: string,
    memoryMessages: ChatMessage[] = [],
    oboTokens: Record<string, string> = {},
    onEvent?: WorkflowEventHandler,
    mcpDiscoveredTools: CachedMCPToolsMap = {}
  ) {
    this.workflow = workflow;
    this.llmCredentials = llmCredentials;
    this.agentCredentials = agentCredentials;
    this.baseUrl = baseUrl || process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:4829';
    this.oboTokens = oboTokens;
    this.mcpDiscoveredTools = mcpDiscoveredTools;
    this.onEvent = onEvent;
    this.trace = emptyTrace();
    this.trace.userMessage = initialInput;

    const llmNode = workflow.nodes.find((n) => n.type === 'llm');
    if (llmNode) {
      const data = llmNode.data as LLMNodeData;
      this.trace.llm = { provider: data.provider, model: data.model };
    }

    this.context = {
      workflowId,
      variables: {},
      memoryMessages,
      currentInput: initialInput,
    };
  }

  async execute(): Promise<ExecutionResult & { trace: WorkflowTrace }> {
    const startTime = Date.now();

    try {
      console.log('[Workflow] Starting execution');

      const chatTriggerNode = this.workflow.nodes.find((n) => n.type === 'chatTrigger');

      if (!chatTriggerNode) {
        throw new Error('No Chat Trigger node found in workflow');
      }

      const output = await this.executeNode(chatTriggerNode.id);
      const executionTime = Date.now() - startTime;

      console.log(`[Workflow] Completed in ${executionTime}ms`);

      this.trace.finishedAt = Date.now();
      this.trace.finalAnswer = output;
      this.trace.flow = dominantFlow(this.trace.mcps);

      return { success: true, output, executionTime, trace: this.trace };
    } catch (error) {
      const executionTime = Date.now() - startTime;

      if (error instanceof ConsentRequiredError) {
        console.log(`[Workflow] Paused — OBO consent required for node ${error.nodeId}`);
        this.trace.finishedAt = Date.now();
        this.trace.flow = dominantFlow(this.trace.mcps);
        return {
          success: false,
          output: '',
          requiresConsent: true,
          error: `OBO consent required for MCP node ${error.nodeId}`,
          executionTime,
          trace: this.trace,
        };
      }

      const errorMessage = getErrorMessage(error);
      console.error(`[Workflow] Failed after ${executionTime}ms: ${errorMessage}`);

      this.trace.finishedAt = Date.now();
      this.trace.flow = dominantFlow(this.trace.mcps);

      // Surface a workflow-level failure summary so the diagram can show a
      // top-level banner explaining what went wrong.
      const mcpWithError = this.trace.mcps.find((m) => m.authError);
      if (error instanceof AuthFlowError) {
        this.trace.failure = {
          stage: error.stage,
          nodeId: mcpWithError?.nodeId,
          message:
            error.errorDescription || error.errorCode || error.message || errorMessage,
        };
      } else if (mcpWithError?.authError) {
        this.trace.failure = {
          stage: mcpWithError.authError.stage,
          nodeId: mcpWithError.nodeId,
          message:
            mcpWithError.authError.errorDescription ||
            mcpWithError.authError.errorCode ||
            mcpWithError.authError.message,
        };
      } else {
        this.trace.failure = { stage: 'workflow', message: errorMessage };
      }

      return { success: false, output: '', error: errorMessage, executionTime, trace: this.trace };
    }
  }

  private async executeNode(nodeId: string): Promise<string> {
    const node = this.workflow.nodes.find((n) => n.id === nodeId);

    if (!node) {
      throw new Error(`Node not found: ${nodeId}`);
    }

    switch (node.type) {
      case 'chatTrigger':
        return executeChatTrigger(
          node,
          this.workflow,
          this.context.currentInput,
          (id) => this.executeNode(id),
          this.onEvent
        );

      case 'aiAgent':
        return this.runAIAgent(node);

      case 'llm': {
        this.onEvent?.({ type: 'node-start', nodeId: node.id });
        try {
          return await executeLLM(node, this.context, this.llmCredentials, this.baseUrl);
        } finally {
          this.onEvent?.({ type: 'node-end', nodeId: node.id });
        }
      }

      default:
        throw new Error(`Unknown node type: ${node.type}`);
    }
  }

  private async runAIAgent(node: WorkflowNode): Promise<string> {
    const llmNode = this.getOutgoingNodes(node.id).find((n) => n.type === 'llm');
    if (!llmNode) {
      throw new Error(`[AIAgent:${node.id}] Must connect to an AI Service node`);
    }

    const rawAgentData = node.data as AIAgentNodeData;
    const resolvedCred = rawAgentData.agentCredentialId
      ? this.agentCredentials.find((c) => c.id === rawAgentData.agentCredentialId)
      : undefined;
    const agentData = resolvedCred
      ? { ...rawAgentData, agentId: resolvedCred.agentId, agentSecret: resolvedCred.agentSecret }
      : rawAgentData;
    const mcpNodes = this.collectMCPNodes(node.id);
    const mcpConfigs: MCPClientConfig[] = mcpNodes.map((mcpNode) => {
      const nodeData = mcpNode.data as MCPClientNodeData;
      const endpoint = nodeData.mcpServerEndpoint?.trim() ?? '';
      const cached = this.mcpDiscoveredTools[mcpNode.id];
      return {
        nodeId: mcpNode.id,
        endpoint,
        nodeData,
        agentData,
        cachedTools: cached?.tools ?? [],
      };
    });

    const runtimeCache = new Map<string, MCPClientNodeRuntime>();

    this.onEvent?.({ type: 'node-start', nodeId: node.id });
    try {
      return await executeAIAgent(
        node,
        llmNode,
        mcpConfigs,
        runtimeCache,
        this.oboTokens,
        this.mcpDiscoveredTools,
        this.context,
        this.llmCredentials,
        this.baseUrl,
        this.trace,
        this.onEvent
      );
    } finally {
      this.onEvent?.({ type: 'node-end', nodeId: node.id });
      await Promise.all(
        [...runtimeCache.values()].map((r) => r.disconnect().catch(() => undefined))
      );
    }
  }

  private getOutgoingNodes(nodeId: string): WorkflowNode[] {
    return this.workflow.edges
      .filter((edge) => edge.source === nodeId)
      .map((edge) => this.workflow.nodes.find((n) => n.id === edge.target))
      .filter((n): n is WorkflowNode => Boolean(n));
  }

  private getIncomingNodes(nodeId: string): WorkflowNode[] {
    return this.workflow.edges
      .filter((edge) => edge.target === nodeId)
      .map((edge) => this.workflow.nodes.find((n) => n.id === edge.source))
      .filter((n): n is WorkflowNode => Boolean(n));
  }

  private collectMCPNodes(agentNodeId: string): WorkflowNode[] {
    const outgoing = this.getOutgoingNodes(agentNodeId).filter((n) => n.type === 'mcpClient');
    const incoming = this.getIncomingNodes(agentNodeId).filter((n) => n.type === 'mcpClient');
    return Array.from(new Map([...outgoing, ...incoming].map((n) => [n.id, n])).values());
  }
}
