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
import { WorkflowTrace, MCPNodeTrace, ToolCallTrace, AuthErrorTrace } from '@/lib/authTrace';
import { STAGE_LABELS, stripNodeSuffix, mcpDisplayName, truncate } from '@/lib/diagramBuilder';

function FailureBanner({ trace, failedTools, failedMcps }: { trace: WorkflowTrace; failedTools: ToolCallTrace[]; failedMcps: MCPNodeTrace[] }) {
  return (
    <div className="text-[11px] font-mono bg-red-50 p-3 rounded border border-red-300">
      <div className="font-bold text-red-800 mb-1 text-[12px]">⛔  Authentication / execution failure detected</div>

      {trace.failure && (
        <div className="mb-2 text-red-900">
          <span className="text-red-600">workflow:</span>{' '}
          <span className="font-semibold">
            {trace.failure.stage === 'workflow' ? 'Workflow' : STAGE_LABELS[trace.failure.stage as AuthErrorTrace['stage']] || trace.failure.stage}
          </span>{' '}
          — {trace.failure.message}
        </div>
      )}

      {failedMcps.map((m) => {
        const err = m.authError!;
        return (
          <div key={`mcp-err-${m.nodeId}`} className="mb-1 text-red-900">
            <span className="text-red-600">{mcpDisplayName(m)}:</span>{' '}
            <span className="font-semibold">{STAGE_LABELS[err.stage] || err.stage}</span>
            {err.statusCode && <span className="ml-1 px-1 py-0.5 bg-red-200 text-red-900 rounded text-[10px]">HTTP {err.statusCode}</span>}
            {err.errorCode && <span className="ml-1 px-1 py-0.5 bg-red-200 text-red-900 rounded text-[10px]">{err.errorCode}</span>}
            <div className="text-[10px] text-red-800 mt-0.5 break-words">{err.errorDescription || err.message}</div>
            {err.url && <div className="text-[10px] text-red-700/80 mt-0.5 truncate" title={err.url}>@ {err.url}</div>}
          </div>
        );
      })}

      {failedTools
        .filter((t) => !failedMcps.some((m) => m.nodeId === t.nodeId && m.authError?.stage === 'tool-call'))
        .map((t, i) => (
          <div key={`tool-err-${i}`} className="mb-1 text-red-900">
            <span className="text-red-600">tool {stripNodeSuffix(t.publicName)}:</span>{' '}
            {t.statusCode && <span className="px-1 py-0.5 bg-red-200 text-red-900 rounded text-[10px]">HTTP {t.statusCode}</span>}
            {t.errorCode && <span className="ml-1 px-1 py-0.5 bg-red-200 text-red-900 rounded text-[10px]">{t.errorCode}</span>}
            <div className="text-[10px] text-red-800 mt-0.5 break-words">{t.errorDescription || truncate(t.result, 200)}</div>
          </div>
        ))}
    </div>
  );
}

export function TraceMeta({ trace }: { trace: WorkflowTrace }) {
  const failedTools = trace.tools.filter((t) => t.publicName !== 'tool_search' && !t.ok);
  const failedMcps = trace.mcps.filter((m) => m.authError);
  const hasFailure = !!trace.failure || failedTools.length > 0 || failedMcps.length > 0;

  return (
    <div className="space-y-2 mb-3">
      <div className="grid grid-cols-2 gap-2 text-[11px] font-mono bg-slate-50 p-3 rounded border border-slate-200">
        <div>
          <span className="text-slate-500">LLM:</span>{' '}
          {trace.llm ? `${trace.llm.provider}${trace.llm.model ? `/${trace.llm.model}` : ''}` : '—'}
        </div>
        <div className="col-span-2">
          <span className="text-slate-500">MCP servers:</span> {trace.mcps.length},{' '}
          <span className="text-slate-500">tool calls:</span> {trace.tools.filter((t) => t.publicName !== 'tool_search').length},{' '}
          <span className="text-slate-500">status:</span>{' '}
          {hasFailure ? <span className="text-red-700 font-bold">FAILED</span> : <span className="text-emerald-700 font-bold">OK</span>}
        </div>
      </div>
      {hasFailure && <FailureBanner trace={trace} failedTools={failedTools} failedMcps={failedMcps} />}
    </div>
  );
}
