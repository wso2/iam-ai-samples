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
