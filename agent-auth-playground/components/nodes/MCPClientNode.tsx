import { Handle, Position } from 'reactflow';
import mcplogo from '../assets/mcp.png';
import ActiveBorder from './ActiveBorder';
import ErrorBorder from './ErrorBorder';

export default function MCPClientNode({ data }: any) {
  const isActive = !!data?.isActive;
  const needsInit = !!data?.needsInit;
  return (
    <div className="flex flex-col items-center gap-2 text-slate-900">
      <ActiveBorder active={isActive} rx="50%">
        <ErrorBorder active={needsInit && !isActive} rx="50%">
          <div className="relative h-20 w-20 rounded-full bg-white shadow-lg border-2 border-slate-200">
            <div className="flex h-full w-full items-center justify-center overflow-hidden rounded-full">
              <img
                src={mcplogo.src}
                alt={"MCP Client"}
                className="h-12 w-12 object-contain"
              />
            </div>
            <Handle
              type="target"
              position={Position.Left}
              className="w-1.5! h-1.5! bg-slate-900! border-1! border-white! shadow-md!"
            />
          </div>
        </ErrorBorder>
      </ActiveBorder>
      <div className="flex flex-col items-center gap-0.25">
        <div className="text-xs font-medium text-slate-700">MCP Client</div>
        {data?.name && (
          <div className="text-xs text-slate-500 max-w-[120px] truncate text-center">
            {data.name}
          </div>
        )}
      </div>
    </div>
  );
}
