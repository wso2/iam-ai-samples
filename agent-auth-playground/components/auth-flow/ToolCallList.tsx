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
import { WorkflowTrace } from '@/lib/authTrace';
import { stripNodeSuffix } from '@/lib/diagramBuilder';
import { JwtLink } from './JwtLink';

export function ToolCallList({ trace }: { trace: WorkflowTrace }) {
  const tools = trace.tools.filter((t) => t.publicName !== 'tool_search');
  if (tools.length === 0) return null;
  return (
    <details className="mt-2 text-xs">
      <summary className="cursor-pointer font-semibold text-slate-700">Tool Calls ({tools.length})</summary>
      <div className="mt-2 space-y-2">
        {tools.map((t, i) => {
          const mcp = trace.mcps.find((m) => m.nodeId === t.nodeId);
          const token = mcp?.oboToken || mcp?.agentToken;
          return (
            <div key={i} className="border border-slate-200 rounded p-2 bg-white">
              <div className="font-mono text-[11px] text-slate-600 flex items-center gap-2">
                <span className="font-bold text-blue-600">step {t.step}</span>
                <span>{stripNodeSuffix(t.publicName)}</span>
                <span className="text-slate-400">@</span>
                <span className="text-slate-500">{t.endpoint}</span>
                {token ? (
                  <span className="ml-auto inline-flex items-center gap-1">
                    <span className="text-amber-700">🔒 with auth</span>
                    <JwtLink token={token} label="Decode JWT" />
                  </span>
                ) : (
                  <span className="ml-auto text-slate-400">no auth</span>
                )}
              </div>
              <div className="font-mono text-[10px] text-slate-500 mt-1">args: {t.args}</div>
              {!t.ok && (t.statusCode || t.errorCode) && (
                <div className="font-mono text-[10px] mt-1 flex flex-wrap items-center gap-1">
                  {t.statusCode && <span className="px-1 py-0.5 bg-red-200 text-red-900 rounded text-[9px] font-bold">HTTP {t.statusCode}</span>}
                  {t.errorCode && <span className="ml-1 px-1 py-0.5 bg-red-200 text-red-900 rounded text-[9px] font-bold">{t.errorCode}</span>}
                  {t.errorDescription && <span className="text-red-700">{t.errorDescription}</span>}
                </div>
              )}
              <div className={`font-mono text-[10px] mt-1 break-all max-h-24 overflow-y-auto ${t.ok ? 'text-emerald-700' : 'text-red-600'}`}>
                {t.ok ? 'result' : 'error'}: {t.result}
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
}
