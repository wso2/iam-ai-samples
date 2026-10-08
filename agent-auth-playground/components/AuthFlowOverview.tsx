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

import { useEffect, useMemo, useState } from 'react';
import { WorkflowTrace } from '@/lib/authTrace';
import {
  AuthStep, Boxes, LaneId, StepType,
  KEYFRAMES, buildAllSteps, getBoxes, getArrowPath, mcpDisplayName,
  perMcpFlow, mcpLaneId, stepColor, errorBadgeText,
} from '@/lib/overviewBuilder';
import { Button } from '@/components/ui/button';
import { StepCard } from '@/components/auth-flow/StepCard';
import { BoxEl, ArrowSVG, Badge, TokenTag, WarningTag, ErrorTag } from '@/components/auth-flow/OverviewSvgPrimitives';

interface Props {
  trace: WorkflowTrace;
}

export function AuthFlowOverview({ trace }: Props) {
  const realTools = useMemo(() => trace.tools.filter((t) => t.publicName !== 'tool_search'), [trace.tools]);
  const steps = useMemo(() => buildAllSteps(trace.mcps, realTools), [trace.mcps, realTools]);

  const [cur, setCur] = useState(-1);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    setCur(-1);
    setPlaying(false);
    if (trace.mcps.length === 0) return;
    const t = setTimeout(() => { setCur(0); setPlaying(true); }, 80);
    return () => clearTimeout(t);
  }, [trace]);

  useEffect(() => {
    if (!playing) return;
    const t = setInterval(() => {
      setCur((p) => (p >= steps.length - 1 ? 0 : p + 1));
    }, 1100);
    return () => clearInterval(t);
  }, [playing, steps.length]);

  const W = 720;
  const hasUser = trace.mcps.some((m) => perMcpFlow(m) === 'obo');
  const mcpCount = trace.mcps.length;
  const mcpAreaH = mcpCount * 56 + Math.max(0, mcpCount - 1) * 14;
  const H = Math.max(hasUser ? 360 : 260, mcpAreaH + 80);

  const boxes = useMemo(
    () => (mcpCount > 0 ? getBoxes(trace.mcps, W, H) : ({} as Boxes)),
    [trace.mcps, W, H, mcpCount],
  );

  const curveOffsets = useMemo(() => {
    const pairMap: Record<string, number[]> = {};
    steps.forEach((s, i) => {
      const key = [s.from, s.to].sort().join('|');
      if (!pairMap[key]) pairMap[key] = [];
      pairMap[key].push(i);
    });
    const offsets = new Array(steps.length).fill(0);
    Object.values(pairMap).forEach((indices) => {
      if (indices.length <= 1) return;
      const spread = 28;
      indices.forEach((idx, j) => { offsets[idx] = -spread + (j * (2 * spread)) / Math.max(1, indices.length - 1); });
    });
    return offsets;
  }, [steps]);

  if (trace.mcps.length === 0) {
    return (
      <>
        <style>{KEYFRAMES}</style>
        <div className="p-6 rounded-xl bg-white border border-dashed border-slate-300 text-center text-slate-500 text-sm">
          <div className="text-sm font-bold text-slate-700 mb-1">No Auth Flows in this run</div>
          The auth flow overview appears when the workflow connects to one or more authentication services.
        </div>
      </>
    );
  }

  const curStep = cur >= 0 && cur < steps.length ? steps[cur] : null;
  const activeSet = new Set<LaneId>();
  let glowClr: string | null = null;
  if (curStep) { activeSet.add(curStep.from); activeSet.add(curStep.to); glowClr = stepColor(curStep.type); }

  const play = () => { setCur(-1); setTimeout(() => { setCur(0); setPlaying(true); }, 80); };
  const showAll = () => { setPlaying(false); setCur(steps.length - 1); };

  const failedCount = trace.mcps.filter((m) => m.authError).length +
    realTools.filter((t) => !t.ok && !trace.mcps.find((m) => m.nodeId === t.nodeId && m.authError)).length;

  return (
    <div>
      <style>{KEYFRAMES}</style>
      <h2 className="text-lg font-bold text-slate-900 mb-1">Authentication Flow</h2>
      <p className="text-sm text-slate-500 mb-3">
        This workflow connects to {trace.mcps.length} service{trace.mcps.length > 1 ? 's' : ''}. All auth flows are shown together below — step numbers run in execution order.
        {failedCount > 0 && <span className="ml-1 text-red-700 font-semibold">{failedCount} step{failedCount > 1 ? 's' : ''} failed.</span>}
      </p>

      {/* MCP service badges */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {trace.mcps.map((mcp) => {
          const flow = perMcpFlow(mcp);
          const flowColor = flow === 'obo' ? '#22c55e' : flow === 'agent' ? '#f59e0b' : '#94a3b8';
          const flowLabel = flow === 'obo' ? 'OBO' : flow === 'agent' ? 'AGENT' : 'NONE';
          const hasError = !!mcp.authError;
          return (
            <span key={mcp.nodeId} className="px-2 py-1 rounded-md text-[11px] font-semibold flex items-center gap-1.5 border"
              style={{ background: hasError ? '#fef2f2' : '#f8fafc', borderColor: hasError ? '#ef4444' : '#e2e8f0', color: hasError ? '#b91c1c' : '#334155' }}>
              <span>{mcpDisplayName(mcp)}</span>
              <span className="text-[9px] font-bold px-1 py-0.5 rounded" style={{ background: flowColor + '22', color: flowColor }}>{flowLabel}</span>
              {hasError && <span className="text-[9px] font-bold px-1 py-0.5 rounded bg-red-200 text-red-900">⛔ {mcp.authError!.errorCode || `HTTP ${mcp.authError!.statusCode ?? 'err'}`}</span>}
            </span>
          );
        })}
      </div>

      {/* Playback controls */}
      <div className="flex gap-1.5 items-center mb-2.5 flex-wrap">
        <Button onClick={play} disabled={steps.length === 0} size="sm" className="bg-[#6c5ce7] hover:bg-[#5b4dd0] text-white text-xs font-semibold">▶ Play</Button>
        <Button onClick={showAll} disabled={steps.length === 0} size="sm" variant="outline" className="text-xs font-semibold">Show All</Button>
        <Button onClick={() => { setCur(-1); setPlaying(false); }} size="sm" variant="outline" className="text-xs font-semibold">Reset</Button>
        <div className="w-px h-5 bg-slate-200 mx-0.5" />
        <Button disabled={cur <= -1} onClick={() => setCur((s) => Math.max(-1, s - 1))} size="sm" variant="outline" className="text-xs px-2.5">‹</Button>
        <Button disabled={cur >= steps.length - 1} onClick={() => { setPlaying(false); setCur((s) => Math.min(steps.length - 1, s + 1)); }} size="sm" variant="outline" className="text-xs px-2.5">›</Button>
        <span className="ml-auto text-[11px] text-slate-400 font-mono">{Math.max(0, cur + 1)} / {steps.length}</span>
      </div>

      <div className="mb-2.5">
        <StepCard step={curStep} />
      </div>

      {/* Diagram */}
      <div className="max-w-[720px] mx-auto bg-white rounded-xl border border-slate-200 overflow-hidden mb-3.5">
        <svg width="100%" viewBox={`0 0 ${W} ${H}`} className="block">
          {(Object.entries(boxes) as [LaneId, (typeof boxes)[LaneId]][]).map(([id, box]) => (
            <BoxEl key={id} box={box} active={activeSet.has(id)} glowColor={activeSet.has(id) ? glowClr : null} />
          ))}
          {steps.map((step, i) => {
            if (i > cur) return null;
            const fromBox = boxes[step.from];
            const toBox = boxes[step.to];
            const path = getArrowPath(fromBox, toBox, curveOffsets[i]);
            if (!path) return null;
            const isCur = i === cur;
            const color = stepColor(step.type);
            return (
              <g key={i}>
                <ArrowSVG path={path} color={color} dashed={step.type !== 'normal'} thick={isCur} op={isCur ? 1 : 0.18} />
                <Badge x={path.mx} y={path.my} num={step.num} color={isCur ? color : '#cbd5e1'} />
                {isCur && (step.type === 'token' || step.type === 'secure') && step.tokenType && <TokenTag x={path.mx} y={path.my - 18} tokenType={step.tokenType} />}
                {isCur && step.type === 'unsecure' && <WarningTag x={path.mx} y={path.my - 18} />}
                {isCur && step.type === 'error' && step.errorBadge && <ErrorTag x={path.mx} y={path.my - 18} text={step.errorBadge} />}
              </g>
            );
          })}
        </svg>
      </div>

      {/* Legend */}
      <div className="mt-4 flex gap-3.5 flex-wrap text-[11px] text-slate-500">
        {[
          { color: '#f59e0b', label: 'Auth exchange' },
          { color: '#7c3aed', label: 'Secured call' },
          { color: '#22c55e', label: 'Response' },
          { color: '#3b82f6', label: 'User consent' },
          { color: '#ef4444', label: 'Unsecured' },
          { color: '#dc2626', label: 'Failure' },
        ].map((l, i) => (
          <div key={i} className="flex items-center gap-1.5">
            <svg width={24} height={8}>
              <line x1={0} y1={4} x2={24} y2={4} stroke={l.color} strokeWidth={2} strokeDasharray="4 3" />
            </svg>
            <span>{l.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
