'use client';

import { useCallback, useEffect, useState } from 'react';
import ReactFlow, {
  Node,
  Edge,
  Connection,
  MarkerType,
  useNodesState,
  useEdgesState,
  Background,
  Controls,
  MiniMap,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { Workflow, WorkflowNode, WorkflowEdge as WorkflowEdgeType } from '@/lib/types';
import { generateId, workflowStore } from '@/lib/workflowStore';
import ChatTriggerNode from '@/components/nodes/ChatTriggerNode';
import AIAgentNode from '@/components/nodes/AIAgentNode';
import LLMNode from '@/components/nodes/LLMNode';
import MCPClientNode from '@/components/nodes/MCPClientNode';

const nodeTypes = {
  chatTrigger: ChatTriggerNode,
  aiAgent: AIAgentNode,
  llm: LLMNode,
  mcpClient: MCPClientNode,
};

interface WorkflowEditorProps {
  workflow: Workflow | null;
  selectedNodeId: string | null;
  activeNodeIds?: Set<string>;
  mcpInitVersion?: number;
  onNodeSelect: (nodeId: string | null) => void;
  onNodeDoubleClick: (nodeId: string) => void;
  onNodeUpdate: (nodeId: string, updates: Partial<WorkflowNode>) => void;
  onNodeDelete: (nodeId: string) => void;
  onEdgeAdd: (edge: WorkflowEdgeType) => void;
  onEdgeDelete: (edgeId: string) => void;
}

export default function WorkflowEditor({
  workflow,
  selectedNodeId,
  activeNodeIds,
  mcpInitVersion,
  onNodeSelect,
  onNodeDoubleClick,
  onNodeUpdate,
  onNodeDelete,
  onEdgeAdd,
  onEdgeDelete,
}: WorkflowEditorProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState([]);

  // Convert workflow to React Flow format
  useEffect(() => {
    if (!workflow) return;

    // Track which source handles on each node already have an edge
    const nodeSourceHandles: Record<string, string[]> = {};
    for (const edge of workflow.edges) {
      if (!nodeSourceHandles[edge.source]) nodeSourceHandles[edge.source] = [];
      nodeSourceHandles[edge.source].push(edge.sourceHandle ?? '__default__');
    }

    const rfNodes: Node[] = workflow.nodes.map((node) => {
      const extra: Record<string, unknown> = {
        isActive: activeNodeIds?.has(node.id) ?? false,
        connectedSourceHandles: nodeSourceHandles[node.id] ?? [],
      };
      if (node.type === 'mcpClient') {
        const cached = workflowStore.getMCPTools(workflow.id, node.id);
        extra.needsInit = !cached || !Array.isArray(cached.tools) || cached.tools.length === 0;
      }
      return {
        id: node.id,
        data: { ...node.data, ...extra },
        position: node.position,
        type: node.type,
        selected: node.id === selectedNodeId,
      };
    });

    const rfEdges: Edge[] = workflow.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle,
      targetHandle: edge.targetHandle,
      animated: true,
      style: {
        stroke: '#565656',
        strokeWidth: 1,
      },
      markerEnd: {
        type: MarkerType.ArrowClosed,
        width: 20,
        height: 20,
        color: '#565656',
      },
    }));

    setNodes(rfNodes);
    setEdges(rfEdges);
  }, [workflow, selectedNodeId, activeNodeIds, mcpInitVersion, setNodes, setEdges]);

  // Handle node selection
  const handleNodeClick = useCallback(
    (event: React.MouseEvent, node: Node) => {
      onNodeSelect(node.id);
    },
    [onNodeSelect]
  );

  const handleNodeDoubleClick = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeDoubleClick(node.id);
    },
    [onNodeDoubleClick]
  );

  const handlePaneClick = useCallback(() => {
    onNodeSelect(null);
  }, [onNodeSelect]);

  // Persist position changes in workflow state so later updates don't reset node locations
  const handleNodeDragStop = useCallback(
    (_event: React.MouseEvent, node: Node) => {
      onNodeUpdate(node.id, { position: node.position });
    },
    [onNodeUpdate]
  );

  // Enforce handle-level connection rules
  const isValidConnection = useCallback(
    (connection: Connection) => {
      const sourceNode = nodes.find((n) => n.id === connection.source);
      const targetNode = nodes.find((n) => n.id === connection.target);
      if (!sourceNode || !targetNode) return false;

      // AIAgent top handle can only connect to LLM nodes (1:1)
      if (sourceNode.type === 'aiAgent' && connection.sourceHandle === 'top') {
        if (targetNode.type !== 'llm') return false;
        // AIAgent already has an LLM connected
        if (edges.some((e) => e.source === connection.source && e.sourceHandle === 'top')) return false;
        // LLM already connected to an AIAgent
        if (edges.some((e) => e.target === connection.target && nodes.find((n) => n.id === e.source)?.type === 'aiAgent')) return false;
        return true;
      }

      // AIAgent right handle can only connect to MCP nodes
      if (sourceNode.type === 'aiAgent' && connection.sourceHandle === 'right') {
        return targetNode.type === 'mcpClient';
      }

      // ChatTrigger → AIAgent: 1:1 constraint
      if (sourceNode.type === 'chatTrigger' && targetNode.type === 'aiAgent') {
        // ChatTrigger already connects to an AIAgent
        if (edges.some((e) => e.source === connection.source && nodes.find((n) => n.id === e.target)?.type === 'aiAgent')) return false;
        // AIAgent already has a ChatTrigger
        if (edges.some((e) => e.target === connection.target && nodes.find((n) => n.id === e.source)?.type === 'chatTrigger')) return false;
        return true;
      }

      return true;
    },
    [nodes, edges]
  );

  // Handle connection/edge creation
  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;

      const newEdge: WorkflowEdgeType = {
        id: generateId('edge-'),
        source: connection.source,
        target: connection.target,
        sourceHandle: connection.sourceHandle ?? undefined,
        targetHandle: connection.targetHandle ?? undefined,
        animated: true,
      };

      onEdgeAdd(newEdge);
    },
    [onEdgeAdd]
  );

  // Handle node deletion
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodeId) {
        onNodeDelete(selectedNodeId);
        onNodeSelect(null);
      }
    },
    [selectedNodeId, onNodeDelete, onNodeSelect]
  );

  return (
    <div
      className="flex flex-col h-full w-full bg-white"
      onKeyDown={handleKeyDown}
      tabIndex={0}
    >
      {/* Canvas */}
      <div className="flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={handleConnect}
          isValidConnection={isValidConnection}
          onNodeClick={handleNodeClick}
          onNodeDoubleClick={handleNodeDoubleClick}
          onPaneClick={handlePaneClick}
          onNodeDragStop={handleNodeDragStop}
          nodeTypes={nodeTypes}
          defaultEdgeOptions={{
            style: {
              stroke: '#565656',
              strokeWidth: 2,
            },
            markerEnd: {
              type: MarkerType.ArrowClosed,
              width: 20,
              height: 20,
              color: '#565656',
            },
          }}
          fitView
        >
          <Background />
          <Controls />
          <MiniMap />
        </ReactFlow>
      </div>
    </div>
  );
}
