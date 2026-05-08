'use client';

import { WorkflowNode, Workflow } from '@/lib/types';
import ChatTriggerPanel from '@/components/nodes/ChatTriggerPanel';
import AIAgentPanel from '@/components/nodes/AIAgentPanel';
import MCPClientPanel from '@/components/nodes/MCPClientPanel';
import LLMPanel from '@/components/nodes/LLMPanel';

interface NodePanelProps {
  node: WorkflowNode | null;
  onUpdate: (nodeId: string, updates: Partial<WorkflowNode>) => void;
  workflowId?: string;
  workflow?: Workflow | null;
  variant?: 'sidebar' | 'modal';
  onMCPInitChange?: () => void;
}

export default function NodePanel({
  node,
  onUpdate,
  workflowId,
  workflow,
  variant = 'sidebar',
  onMCPInitChange,
}: NodePanelProps) {
  const containerClassName =
    variant === 'modal'
      ? 'w-full bg-white overflow-hidden flex flex-col max-h-[80vh]'
      : 'w-80 bg-white border-l border-gray-200 p-6 overflow-y-auto';

  const emptyStateClassName =
    variant === 'modal'
      ? 'w-full min-h-72 bg-gray-50 p-6 flex flex-col items-center justify-center text-gray-500'
      : 'w-80 bg-gray-50 border-l border-gray-200 p-6 flex flex-col items-center justify-center text-gray-500';

  if (!node) {
    return (
      <div className={emptyStateClassName}>
        <div className="text-center">
          <p className="font-semibold mb-2">No node selected</p>
          <p className="text-sm">Click a node to configure it</p>
        </div>
      </div>
    );
  }

  const renderPanel = () => {
    switch (node.type) {
      case 'chatTrigger':
        return <ChatTriggerPanel />;
      case 'aiAgent':
        return <AIAgentPanel node={node} onUpdate={onUpdate} workflowId={workflowId} />;
      case 'mcpClient':
        return <MCPClientPanel node={node} onUpdate={onUpdate} workflowId={workflowId} workflow={workflow} onMCPInitChange={onMCPInitChange} />;
      case 'llm':
        return <LLMPanel node={node} onUpdate={onUpdate} />;
      default:
        return <p className="text-sm text-gray-500">Unknown node type</p>;
    }
  };

  if (variant === 'modal') {
    return (
      <div className={containerClassName}>
        <div className="flex items-center justify-between border-b border-gray-200 bg-gray-50 px-4 py-2.5 pr-12">
          <div>
            <h3 className="text-base font-bold text-gray-900 leading-tight">{node.data.label}</h3>
            <p className="text-xs text-gray-500 mt-0.5">Node configuration</p>
          </div>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-3">
          {renderPanel()}
        </div>
      </div>
    );
  }

  return (
    <div className={containerClassName}>
      <div className="mb-6">
        <h3 className="text-lg font-bold text-gray-900 mb-2">{node.data.label}</h3>
      </div>
      {renderPanel()}
    </div>
  );
}
