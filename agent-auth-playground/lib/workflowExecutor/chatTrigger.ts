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
import { WorkflowNode, Workflow } from '../types';
import type { WorkflowEventHandler } from './index';

export async function executeChatTrigger(
  node: WorkflowNode,
  workflow: Workflow,
  currentInput: string,
  executeNode: (nodeId: string) => Promise<string>,
  onEvent?: WorkflowEventHandler
): Promise<string> {
  onEvent?.({ type: 'node-start', nodeId: node.id });
  console.log(`[ChatTrigger:${node.id}] Received input: "${currentInput}"`);
  onEvent?.({ type: 'node-end', nodeId: node.id });

  const connectedEdges = workflow.edges.filter((e) => e.source === node.id);

  if (connectedEdges.length === 0) {
    return currentInput;
  }

  return executeNode(connectedEdges[0].target);
}
