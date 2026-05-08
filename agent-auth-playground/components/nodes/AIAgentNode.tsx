import { Handle, Position } from 'reactflow';
import aiAgentImage from '../assets/ai-agent.png';
import ActiveBorder from './ActiveBorder';
import PlusHandle from './PlusHandle';

export default function AIAgentNode({ data }: any) {
  const isActive = !!data?.isActive;
  const connected: string[] = data?.connectedSourceHandles ?? [];
  return (
    <div className="flex flex-col items-center gap-2">
      <ActiveBorder active={isActive} rx={20}>
        <div className="relative flex h-25 w-25 items-center justify-center rounded-[1.25rem] border border-slate-200 bg-white p-4 shadow-lg">
          <div className="flex h-17 w-17 items-center justify-center rounded-full border border-slate-100 bg-white shadow-[0_10px_28px_rgba(15,23,42,0.12)]">
            <img
              src={aiAgentImage.src}
              alt="AI Agent"
              className="h-12 w-12 object-contain"
            />
          </div>
          {/* Top handle → LLM: + disappears after connected */}
          <PlusHandle type="source" position={Position.Top} id="top" connected={connected.includes('top')} />
          <span className="absolute -top-4 left-1/3 -translate-x-1/2 text-[9px] font-medium text-slate-400 whitespace-nowrap pointer-events-none">LLM</span>
          <Handle type="target" position={Position.Left} id="left" />
          {/* Right handle → MCP: + always visible */}
          <PlusHandle type="source" position={Position.Right} id="right" alwaysShow />
          <span className="absolute top-1/3 -translate-y-1/2 -right-10 text-[9px] font-medium text-slate-400 whitespace-nowrap pointer-events-none">Services</span>
        </div>
      </ActiveBorder>
      <div className="text-xs font-medium text-slate-700">AI Agent</div>
    </div>
  );
}
