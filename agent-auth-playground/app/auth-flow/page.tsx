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
'use client';

import { useEffect, useState } from 'react';
import { AuthFlowDiagram } from '@/components/AuthFlowDiagram';
import { AuthFlowOverview } from '@/components/AuthFlowOverview';
import { WorkflowTrace } from '@/lib/authTrace';

const STORAGE_KEY = 'lastAuthTrace';

export default function AuthFlowPage() {
  const [trace, setTrace] = useState<WorkflowTrace | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [showSequence, setShowSequence] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) setTrace(JSON.parse(raw) as WorkflowTrace);
    } catch {
      // ignore corrupted payload
    }
    setLoaded(true);

    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY && e.newValue) {
        try {
          setTrace(JSON.parse(e.newValue) as WorkflowTrace);
        } catch {
          // ignore
        }
      }
    };
    window.addEventListener('storage', handleStorage);
    return () => window.removeEventListener('storage', handleStorage);
  }, []);

  const flow = trace?.flow ?? 'none';
  const flowBadge =
    flow === 'obo'
      ? { label: 'OBO Flow', color: 'bg-purple-100 text-purple-800 border-purple-200' }
      : flow === 'agent'
      ? { label: 'Agent Flow', color: 'bg-cyan-100 text-cyan-800 border-cyan-200' }
      : { label: 'Direct', color: 'bg-slate-100 text-slate-700 border-black' };

  return (
    <div className="min-h-screen bg-slate-50">
      <main className="mx-auto max-w-7xl px-6 py-6">
        {!loaded ? (
          <div className="rounded-lg border border-black bg-white p-12 text-center text-sm text-slate-500">
            Loading trace…
          </div>
        ) : trace ? (
          <>
            <div className="rounded-xl border border-black bg-white p-6 shadow-sm">
              <AuthFlowOverview trace={trace} />
            </div>

            <div className="mt-4">
              <button
                onClick={() => setShowSequence((v) => !v)}
                className="w-full flex items-center justify-between px-5 py-3.5 rounded-xl border border-black bg-white shadow-sm text-sm font-semibold text-slate-700 hover:bg-slate-50 transition-colors group"
              >
                <span className="flex items-center gap-2">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-cyan-600">
                    <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                  </svg>
                  Detailed auth sequence flow
                </span>
                <svg
                  width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"
                  className={`text-slate-400 transition-transform duration-200 ${showSequence ? 'rotate-180' : ''}`}
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>

              {showSequence && (
                <div className="mt-2 rounded-xl border border-black bg-white p-6 shadow-sm">
                  <AuthFlowDiagram trace={trace} />
                </div>
              )}
            </div>
          </>
        ) : (
          <div className="rounded-lg border border-dashed border-black bg-white p-12 text-center">
            <p className="text-sm font-semibold text-slate-700 mb-1">No execution recorded yet</p>
            <p className="text-xs text-slate-500">
              Run a workflow from the editor, then click "View Auth Flow" to inspect the trace.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
