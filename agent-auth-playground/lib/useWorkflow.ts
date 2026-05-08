'use client';

import { useState, useCallback, useEffect } from 'react';
import { Workflow, WorkflowNode, WorkflowEdge } from './types';
import { workflowStore, createDefaultWorkflow } from './workflowStore';

export function useWorkflow() {
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  // Initialize workflow on mount
  useEffect(() => {
    const stored = workflowStore.getWorkflow();
    if (stored) {
      setWorkflow(stored);
    } else {
      setWorkflow(createDefaultWorkflow());
    }
  }, []);

  // Auto-save whenever workflow state changes (debounced)
  useEffect(() => {
    if (!workflow) return;
    const timer = setTimeout(() => {
      workflowStore.saveWorkflow(workflow);
    }, 300);
    return () => clearTimeout(timer);
  }, [workflow]);

  const importWorkflow = useCallback((imported: Workflow) => {
    const replaced: Workflow = {
      ...imported,
      id: workflow?.id || imported.id,
      updatedAt: Date.now(),
    };
    setWorkflow(replaced);
    setSelectedNodeId(null);
    return replaced;
  }, [workflow?.id]);

  const updateWorkflow = useCallback((updates: Partial<Workflow>) => {
    setWorkflow((prev) => {
      if (!prev) return null;
      return { ...prev, ...updates, updatedAt: Date.now() };
    });
  }, []);

  const addNode = useCallback(
    (node: WorkflowNode) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return { ...prev, nodes: [...prev.nodes, node], updatedAt: Date.now() };
      });
    },
    []
  );

  const updateNode = useCallback(
    (nodeId: string, updates: Partial<WorkflowNode>) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          nodes: prev.nodes.map((n) => (n.id === nodeId ? { ...n, ...updates } : n)),
          updatedAt: Date.now(),
        };
      });
    },
    []
  );

  const deleteNode = useCallback(
    (nodeId: string) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          nodes: prev.nodes.filter((n) => n.id !== nodeId),
          edges: prev.edges.filter((e) => e.source !== nodeId && e.target !== nodeId),
          updatedAt: Date.now(),
        };
      });
      if (selectedNodeId === nodeId) {
        setSelectedNodeId(null);
      }
    },
    [selectedNodeId]
  );

  const addEdge = useCallback(
    (edge: WorkflowEdge) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return { ...prev, edges: [...prev.edges, edge], updatedAt: Date.now() };
      });
    },
    []
  );

  const deleteEdge = useCallback(
    (edgeId: string) => {
      setWorkflow((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          edges: prev.edges.filter((e) => e.id !== edgeId),
          updatedAt: Date.now(),
        };
      });
    },
    []
  );

  return {
    workflow,
    selectedNodeId,
    setSelectedNodeId,
    importWorkflow,
    updateWorkflow,
    addNode,
    updateNode,
    deleteNode,
    addEdge,
    deleteEdge,
  };
}
