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
import { WorkflowTrace, previewToken } from '@/lib/authTrace';
import { STAGE_LABELS, mcpDisplayName } from '@/lib/diagramBuilder';
import { JwtLink } from './JwtLink';

export function MCPList({ trace }: { trace: WorkflowTrace }) {
  if (trace.mcps.length === 0) return null;
  return (
    <details className="mt-4 text-xs" open>
      <summary className="cursor-pointer font-semibold text-slate-700">MCP Nodes &amp; Tokens</summary>
      <div className="mt-2 space-y-2">
        {trace.mcps.map((m) => {
          const token = m.oboToken || m.agentToken;
          return (
            <div key={m.nodeId} className="border border-slate-200 rounded p-2 bg-white">
              <div className="font-mono text-[11px] text-slate-700">
                <span className="font-bold">{mcpDisplayName(m)}</span>
                {m.name && <span className="text-slate-400"> ({m.nodeId})</span>}{' '}
                ({m.flow}) → {m.endpoint}
              </div>
              {m.agentToken && (
                <div className="font-mono text-[10px] text-amber-700 mt-1 flex items-center gap-2">
                  <span title={m.agentToken}>Agent Token: {previewToken(m.agentToken)}</span>
                  <JwtLink token={m.agentToken} label="Decode" />
                </div>
              )}
              {m.oboToken && (
                <div className="font-mono text-[10px] text-amber-700 mt-1 flex items-center gap-2">
                  <span title={m.oboToken}>OBO Token: {previewToken(m.oboToken)}</span>
                  <JwtLink token={m.oboToken} label="Decode" />
                </div>
              )}
              {!token && m.flow !== 'none' && !m.authError && (
                <div className="font-mono text-[10px] text-slate-500 mt-1">No token captured</div>
              )}
              {m.authError && (
                <div className="font-mono text-[10px] mt-1 p-1.5 bg-red-50 border border-red-200 rounded">
                  <div className="text-red-800 font-bold flex flex-wrap items-center gap-1">
                    <span>⛔ {STAGE_LABELS[m.authError.stage] || m.authError.stage}</span>
                    {m.authError.statusCode && <span className="px-1 py-0.5 bg-red-200 text-red-900 rounded text-[9px]">HTTP {m.authError.statusCode}</span>}
                    {m.authError.errorCode && <span className="px-1 py-0.5 bg-red-200 text-red-900 rounded text-[9px]">{m.authError.errorCode}</span>}
                  </div>
                  {m.authError.errorDescription && <div className="text-red-800 mt-0.5 break-words">{m.authError.errorDescription}</div>}
                  {m.authError.url && <div className="text-red-700/80 mt-0.5 truncate" title={m.authError.url}>@ {m.authError.url}</div>}
                </div>
              )}
              {m.oboAuthUrl && <div className="font-mono text-[10px] text-slate-500 mt-1 truncate" title={m.oboAuthUrl}>Auth URL: {m.oboAuthUrl}</div>}
            </div>
          );
        })}
      </div>
    </details>
  );
}
