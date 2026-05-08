'use client';

import { useWorkflow } from '@/lib/useWorkflow';
import { useChat } from '@/lib/useChat';
import WorkflowEditor from '@/components/WorkflowEditor';
import NodePanel from '@/components/NodePanel';
import ChatPanel from '@/components/ChatPanel';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Download, Eye, MoreVertical, RotateCcw, Trash2, Upload, X } from 'lucide-react';
import Image from 'next/image';
import { validateWorkflow } from '@/lib/workflowValidation';
import { workflowStore, generateId, createDefaultWorkflow } from '@/lib/workflowStore';
import { useEffect, useRef, useState } from 'react';
import { Workflow, WorkflowNode, NodeType } from '@/lib/types';

export default function Home() {
  const {
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
  } = useWorkflow();

  const {
    messages,
    isLoading,
    error,
    oboConsentPending,
    lastTrace,
    activeNodeIds,
    executeWorkflow,
    clearMessages,
  } = useChat(workflow?.id || 'temp');

  const [validationError, setValidationError] = useState<string | null>(null);
  const [isNodePanelOpen, setIsNodePanelOpen] = useState(false);
  const [isChatVisible, setIsChatVisible] = useState(true);
  const [isOAuthCallback, setIsOAuthCallback] = useState(false);
  const [mcpInitVersion, setMcpInitVersion] = useState(0);
  const [hasOBOTokens, setHasOBOTokens] = useState(false);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const state = params.get('state');
    if (code && state) {
      window.history.replaceState({}, '', '/');
      const channel = new BroadcastChannel('obo-callback');
      channel.postMessage({ code, state });
      channel.close();
      // If opened as a popup, close automatically; otherwise show the banner
      if (window.opener) {
        window.close();
      } else {
        setIsOAuthCallback(true);
      }
    }
  }, []);

  const selectedNode =
    workflow?.nodes.find((n) => n.id === selectedNodeId) || null;

  useEffect(() => {
    if (!selectedNode) {
      setIsNodePanelOpen(false);
    }
  }, [selectedNode]);

  useEffect(() => {
    setHasOBOTokens(workflowStore.hasOBOTokens());
  }, []);

  useEffect(() => {
    if (!lastTrace) return;
    try {
      localStorage.setItem('lastAuthTrace', JSON.stringify(lastTrace));
    } catch {
      // ignore quota or disabled storage
    }
  }, [lastTrace]);

  const handleSendMessage = async (message: string) => {
    if (!workflow) return;

    setValidationError(null);

    // Skip workflow validation when the user is submitting an OBO authorization code
    if (!oboConsentPending) {
      const cachedToolsForValidation: Record<string, { tools: unknown[] }> = {};
      for (const node of workflow.nodes) {
        if (node.type !== 'mcpClient') continue;
        const entry = workflowStore.getMCPTools(workflow.id, node.id);
        if (entry) cachedToolsForValidation[node.id] = { tools: entry.tools };
      }
      const validation = validateWorkflow(workflow, {
        mcpDiscoveredTools: cachedToolsForValidation,
      });
      if (!validation.valid) {
        setValidationError(
          `Invalid workflow: ${validation.errors.join(', ')}`
        );
        return;
      }
    }

    await executeWorkflow(message, workflow);
  };

  const [importError, setImportError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const handleDownloadWorkflow = () => {
    if (!workflow) return;
    const json = JSON.stringify(workflow, null, 2);
    const blob = new Blob([json], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const safeName = (workflow.name || 'workflow').replace(/[^a-z0-9-_]+/gi, '_');
    const a = document.createElement('a');
    a.href = url;
    a.download = `${safeName}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handleImportClick = () => {
    setImportError(null);
    fileInputRef.current?.click();
  };

  const handleStartFresh = () => {
    workflowStore.clearAllData();
    importWorkflow(createDefaultWorkflow());
    setHasOBOTokens(false);
  };

  const handleImportFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;

    try {
      const text = await file.text();
      const parsed = JSON.parse(text) as Workflow;
      if (
        !parsed ||
        typeof parsed !== 'object' ||
        !Array.isArray(parsed.nodes) ||
        !Array.isArray(parsed.edges)
      ) {
        throw new Error('Invalid workflow file');
      }
      importWorkflow(parsed);
    } catch (err) {
      setImportError(
        err instanceof Error ? err.message : 'Failed to import workflow'
      );
    }
  };

  const handleAddNode = (type: NodeType) => {
    const position = { x: Math.random() * 300, y: Math.random() * 300 };
    let data: WorkflowNode['data'];
    switch (type) {
      case 'chatTrigger': data = { label: 'Chat Trigger' }; break;
      case 'aiAgent': data = { label: 'AI Agent', systemPrompt: 'You are a helpful assistant.', maxToolSteps: 6 }; break;
      case 'llm': data = { label: 'AI Service', provider: '' as any, model: '', temperature: 0.7, maxTokens: 1000 }; break;
      case 'mcpClient': data = { label: 'MCP Client', mcpServerEndpoint: '' }; break;
    }
    addNode({ id: generateId('node-'), type, position, data });
  };

  const hasChatTrigger = workflow?.nodes.some((n) => n.type === 'chatTrigger') ?? false;
  const hasAIAgent = workflow?.nodes.some((n) => n.type === 'aiAgent') ?? false;
  const hasLLM = workflow?.nodes.some((n) => n.type === 'llm') ?? false;

  if (!workflow) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-50">
        <p className="text-gray-500">Loading workflow...</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen bg-gray-100">
      {/* OAuth callback banner */}
      {isOAuthCallback && (
        <div className="bg-green-50 border-b border-green-200 px-6 py-3 flex items-center justify-between">
          <p className="text-sm text-green-800 font-medium">
            Authorization successful! You can close this tab and return to the previous one.
          </p>
          <button
            onClick={() => window.close()}
            className="text-xs text-green-700 underline hover:text-green-900"
          >
            Close tab
          </button>
        </div>
      )}

      {/* Main Content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Toolbar — sits above the canvas, never covered by the chat overlay */}
        <div className="border-b border-gray-200 px-3 py-2 flex gap-2 flex-wrap items-center bg-gray-50 shrink-0">
          {/* Brand */}
          <div className="flex items-center gap-2 pr-2 mr-1 border-r border-gray-200">
            <Image
              src="/icon-light-32x32.png"
              alt="Agent Auth Playground"
              width={24}
              height={24}
              priority
            />
            <span className="text-sm font-semibold text-black">Agent Auth Playground</span>
          </div>
          {/* Node buttons */}
          <Button onClick={() => handleAddNode('chatTrigger')} variant="outline" size="sm" className="text-xs" disabled={hasChatTrigger} title={hasChatTrigger ? 'Only one Chat Trigger allowed' : undefined}>+ Chat Trigger</Button>
          <Button onClick={() => handleAddNode('aiAgent')} variant="outline" size="sm" className="text-xs" disabled={hasAIAgent} title={hasAIAgent ? 'Only one AI Agent allowed' : undefined}>+ AI Agent</Button>
          <Button onClick={() => handleAddNode('llm')} variant="outline" size="sm" className="text-xs" disabled={hasLLM} title={hasLLM ? 'Only one AI Service allowed' : undefined}>+ AI Service</Button>
          <Button onClick={() => handleAddNode('mcpClient')} variant="outline" size="sm" className="text-xs">+ MCP Client</Button>
          <div className="relative inline-flex">
            <Button variant="outline" size="sm" className="text-xs opacity-50 cursor-not-allowed" disabled>+ AI Gateway</Button>
            <span className="absolute -bottom-1 -right-1 text-[9px] font-semibold bg-gray-100 text-gray-500 border border-gray-300 rounded px-1 leading-tight pointer-events-none">Coming Soon</span>
          </div>
          {selectedNodeId && (
            <>
              <div className="w-px h-6 bg-gray-300 mx-1 self-center" />
              <Button
                onClick={() => { deleteNode(selectedNodeId); setSelectedNodeId(null); }}
                variant="outline"
                size="sm"
                className="text-xs gap-1.5 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700 hover:border-red-300"
              >
                <Trash2 className="h-3.5 w-3.5" />
                Delete Node
              </Button>
            </>
          )}

          {/* Spacer */}
          <div className="flex-1" />

          {hasOBOTokens && (
            <Button
              variant="outline"
              size="sm"
              className="text-xs gap-1.5 border-amber-200 text-amber-700 hover:bg-amber-50 hover:text-amber-800 hover:border-amber-300"
              onClick={() => { workflowStore.clearAllOBOTokens(); setHasOBOTokens(false); }}
            >
              Remove obtained tokens
            </Button>
          )}

          {/* Workflow name + actions */}
          <div className="flex items-center gap-1 border border-gray-200 rounded-lg bg-white pl-2.5 pr-1 py-1">
            <Input
              value={workflow.name}
              onChange={(e) => updateWorkflow({ name: e.target.value })}
              placeholder="Untitled agent flow"
              className="h-7 w-44 border-0 shadow-none focus-visible:ring-0 px-0 text-sm font-medium bg-transparent"
            />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="h-7 w-7 text-gray-500 hover:text-gray-900" aria-label="Workflow actions">
                  <MoreVertical className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44">
                <DropdownMenuItem onClick={handleDownloadWorkflow}>
                  <Download className="h-4 w-4" />
                  Download
                </DropdownMenuItem>
                <DropdownMenuItem onClick={handleImportClick}>
                  <Upload className="h-4 w-4" />
                  Import
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={handleStartFresh} className="text-red-600 focus:text-red-600">
                  <RotateCcw className="h-4 w-4" />
                  Start Fresh
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            <input ref={fileInputRef} type="file" accept="application/json,.json" className="hidden" onChange={handleImportFile} />
          </div>
          {importError && (
            <p className="text-xs text-red-600">{importError}</p>
          )}
        </div>

        {/* Canvas + Chat overlay area */}
        <div className="flex-1 min-w-0 relative">

          <WorkflowEditor
            workflow={workflow}
            selectedNodeId={selectedNodeId}
            activeNodeIds={activeNodeIds}
            mcpInitVersion={mcpInitVersion}
            onNodeSelect={setSelectedNodeId}
            onNodeDoubleClick={(nodeId) => {
              setSelectedNodeId(nodeId);
              setIsNodePanelOpen(true);
            }}
            onNodeUpdate={updateNode}
            onNodeDelete={deleteNode}
            onEdgeAdd={addEdge}
            onEdgeDelete={deleteEdge}
          />

          {/* Chat panel — overlaid on the left, canvas never moves */}
          {isChatVisible && (
            <div className="absolute left-0 top-0 bottom-0 z-20 w-80 flex flex-col bg-white border-r border-gray-200 shadow-lg">
              <ChatPanel
                messages={messages}
                isLoading={isLoading}
                error={error || validationError}
                onSendMessage={handleSendMessage}
                onClear={clearMessages}
                disabled={!workflow || workflow.nodes.length === 0}
                oboConsentPending={oboConsentPending}
                hasTrace={!!lastTrace}
                onViewAuthFlow={() => {
                  if (lastTrace) {
                    try {
                      localStorage.setItem('lastAuthTrace', JSON.stringify(lastTrace));
                    } catch {
                      // storage may be full or disabled — proceed anyway
                    }
                  }
                  window.open('/auth-flow', '_blank', 'noopener,noreferrer');
                }}
                onHide={() => setIsChatVisible(false)}
              />
            </div>
          )}

          {/* Floating Show Chat button (bottom-left) — only when chat is hidden */}
          {!isChatVisible && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => setIsChatVisible(true)}
              className="absolute bottom-10 left-12 z-10 gap-2 bg-white/95 backdrop-blur-sm border border-gray-200 shadow-md hover:shadow-lg text-gray-700 hover:text-gray-900"
            >
              <Eye className="h-4 w-4" />
              Show Chat
            </Button>
          )}
        </div>
      </div>

      <Dialog open={isNodePanelOpen} onOpenChange={setIsNodePanelOpen}>
        <DialogContent
          showCloseButton={false}
          className="w-[95vw] max-w-2xl p-0 gap-0 overflow-hidden rounded-xl border border-gray-200 shadow-2xl"
        >
          <DialogTitle className="sr-only">
            {selectedNode ? `Configure ${selectedNode.data.label}` : 'Configure node'}
          </DialogTitle>
          <DialogDescription className="sr-only">
            Edit the selected node settings and behavior for this workflow.
          </DialogDescription>
          <NodePanel
            node={selectedNode}
            onUpdate={updateNode}
            workflowId={workflow.id}
            workflow={workflow}
            variant="modal"
            onMCPInitChange={() => setMcpInitVersion((v) => v + 1)}
          />
          <DialogClose
            aria-label="Close"
            className="absolute top-3 right-3 inline-flex h-8 w-8 items-center justify-center rounded-md text-gray-500 hover:bg-gray-200 hover:text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors"
          >
            <X className="h-4 w-4" />
          </DialogClose>
        </DialogContent>
      </Dialog>
    </div>
  );
}
