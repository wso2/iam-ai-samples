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
import { Workflow, MCPClientNodeData } from './types';

export interface ValidationOptions {
  mcpDiscoveredTools?: Record<string, { tools: unknown[] }>;
}

export function validateWorkflow(
  workflow: Workflow,
  options: ValidationOptions = {}
): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];
  const cachedTools = options.mcpDiscoveredTools;

  if (!workflow.nodes || workflow.nodes.length === 0) {
    errors.push('Workflow must contain at least one node');
  }

  const hasTrigger = workflow.nodes.some((node) => node.type === 'chatTrigger');
  if (!hasTrigger) {
    errors.push('Workflow must contain a Chat Trigger node');
  }

  const nodesById = new Map(workflow.nodes.map((node) => [node.id, node]));
  const nodesWithEdges = new Set<string>();

  for (const edge of workflow.edges) {
    nodesWithEdges.add(edge.source);
    nodesWithEdges.add(edge.target);

    if (!nodesById.has(edge.source)) {
      errors.push(`Edge ${edge.id} references a missing source node.`);
    }

    if (!nodesById.has(edge.target)) {
      errors.push(`Edge ${edge.id} references a missing target node.`);
    }
  }

  for (const node of workflow.nodes) {
    if (node.type !== 'chatTrigger' && !nodesWithEdges.has(node.id)) {
      errors.push(`Node ${node.data.label} is not connected to the workflow`);
    }

    if (node.type === 'mcpClient') {
      const data = node.data as MCPClientNodeData;
      const label = data.name?.trim() || node.id;
      if (!data.mcpServerEndpoint?.trim()) {
        errors.push(`MCP Client node ${label} requires a server endpoint`);
      }

      if (cachedTools) {
        const entry = cachedTools[node.id];
        if (!entry || !Array.isArray(entry.tools) || entry.tools.length === 0) {
          errors.push(
            `MCP Client "${label}" is not initialized. Open the node and click "Initialize & Connect".`
          );
        }
      }
    }

    if (node.type === 'aiAgent') {
      const hasConnectedLLM = workflow.edges.some(
        (edge) => edge.source === node.id && nodesById.get(edge.target)?.type === 'llm'
      );

      if (!hasConnectedLLM) {
        errors.push(`AI Agent node ${node.id} must connect to an AI Service node`);
      }
    }

  }

  return {
    valid: errors.length === 0,
    errors,
  };
}
