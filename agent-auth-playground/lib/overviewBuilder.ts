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
import { MCPNodeTrace, ToolCallTrace, AuthErrorTrace } from '@/lib/authTrace';

export type StepType = 'auth' | 'token' | 'consent' | 'secure' | 'unsecure' | 'response' | 'normal' | 'error';
export type StaticLane = 'agent' | 'iam' | 'user';
export type LaneId = StaticLane | string;

export interface AuthStep {
  from: LaneId;
  to: LaneId;
  num: number;
  type: StepType;
  label: string;
  detail: string;
  tokenType?: 'agent' | 'obo';
  mcpNodeId?: string;
  errorBadge?: string;
}

export interface Box {
  x: number; y: number; w: number; h: number;
  label: string; sublabel?: string;
  color: string; bg: string; border: string;
  inner?: string; lock?: boolean; hasError?: boolean;
}

export type Boxes = Record<LaneId, Box>;

export interface ArrowPath {
  sx: number; sy: number; mx: number; my: number; ex: number; ey: number;
}

export const KEYFRAMES = `
@keyframes authFlowOverviewFadeIn { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: translateY(0); } }
@keyframes authFlowOverviewGlow { 0%,100% { opacity: 0.6; } 50% { opacity: 0.2; } }
`;

export function stripNodeSuffix(name: string): string {
  return name.replace(/_node_[^_]+_[^_]+$/, '');
}

export function mcpDisplayName(m: MCPNodeTrace): string {
  return m.name?.trim() || m.nodeId;
}

export function perMcpFlow(m: MCPNodeTrace): 'agent' | 'obo' | 'none' {
  if (m.flow === 'obo') return 'obo';
  if (m.flow === 'agent' || m.flow === 'mixed') return 'agent';
  return 'none';
}

export function mcpLaneId(m: MCPNodeTrace): string {
  return `mcp:${m.nodeId}`;
}

export function errorBadgeText(err: AuthErrorTrace): string {
  const bits: string[] = [];
  if (err.statusCode) bits.push(`HTTP ${err.statusCode}`);
  if (err.errorCode) bits.push(err.errorCode);
  return bits.join(' · ') || 'failed';
}

function errorDetail(err: AuthErrorTrace): string {
  return err.errorDescription || err.message || 'Authentication failed';
}

export function stepColor(type: StepType): string {
  if (type === 'auth' || type === 'token') return '#f59e0b';
  if (type === 'secure') return '#7c3aed';
  if (type === 'unsecure') return '#ef4444';
  if (type === 'error') return '#dc2626';
  if (type === 'response') return '#22c55e';
  if (type === 'consent') return '#3b82f6';
  return '#94a3b8';
}

export function buildAuthStepsForMcp(
  mcp: MCPNodeTrace,
  tools: ToolCallTrace[],
  startNum: number,
): { steps: AuthStep[]; nextNum: number } {
  const steps: AuthStep[] = [];
  const tool = tools.find((t) => t.nodeId === mcp.nodeId);
  const flow = perMcpFlow(mcp);
  const mcpLabel = mcpDisplayName(mcp);
  const mcpLane = mcpLaneId(mcp);
  const err = mcp.authError;
  let n = startNum;

  const failHere = (from: LaneId, to: LaneId, label: string, e: AuthErrorTrace): AuthStep => ({
    from, to, num: n++, type: 'error',
    label, detail: errorDetail(e), mcpNodeId: mcp.nodeId, errorBadge: errorBadgeText(e),
  });

  if (flow === 'none') {
    if (tool) {
      const toolName = stripNodeSuffix(tool.publicName);
      steps.push({ from: 'agent', to: mcpLane, num: n++, type: 'unsecure', label: `Agent calls ${mcpLabel}`, detail: `Tool: ${toolName} — no identity proof attached. The service cannot verify who is calling.`, mcpNodeId: mcp.nodeId });
      if (tool.ok) {
        steps.push({ from: mcpLane, to: 'agent', num: n++, type: 'response', label: `${mcpLabel} returns result`, detail: 'Data returned, but service had no way to verify the caller.', mcpNodeId: mcp.nodeId });
      } else {
        steps.push({ from: mcpLane, to: 'agent', num: n++, type: 'error', label: `${mcpLabel} returned an error`, detail: tool.errorDescription || tool.result || 'Tool execution failed', mcpNodeId: mcp.nodeId, errorBadge: [tool.statusCode ? `HTTP ${tool.statusCode}` : null, tool.errorCode || null].filter(Boolean).join(' · ') || 'failed' });
      }
    }
    return { steps, nextNum: n };
  }

  steps.push({ from: 'agent', to: 'iam', num: n++, type: 'auth', label: `Agent authenticates — ${mcpLabel}`, detail: 'The agent securely proves its identity to the Auth Server using its credentials.', mcpNodeId: mcp.nodeId });

  if (err && (err.stage === 'config' || err.stage === 'authorize' || err.stage === 'authn' || err.stage === 'token')) {
    const stageLabel = err.stage === 'config' ? 'configuration' : err.stage === 'authn' ? 'credential rejection' : err.stage === 'authorize' ? 'authorize call' : 'token exchange';
    steps.push(failHere('iam', 'agent', `Agent auth failed — ${stageLabel}`, err));
    return { steps, nextNum: n };
  }

  steps.push({ from: 'iam', to: 'agent', num: n++, type: 'token', tokenType: 'agent', label: `Agent Token issued — ${mcpLabel}`, detail: "The Auth Server verifies the agent and issues an Access Token — the agent's digital ID badge.", mcpNodeId: mcp.nodeId });

  if (flow === 'obo') {
    steps.push({ from: 'agent', to: 'user', num: n++, type: 'consent', label: `Agent asks for your permission — ${mcpLabel}`, detail: `"I need to access ${mcpLabel} on your behalf." You see an Authorize button.`, mcpNodeId: mcp.nodeId });
    steps.push({ from: 'user', to: 'iam', num: n++, type: 'auth', label: `You log in and approve — ${mcpLabel}`, detail: 'You sign in, review what the agent wants to do, and grant permission.', mcpNodeId: mcp.nodeId });

    if (err?.stage === 'obo-consent') { steps.push(failHere('iam', 'user', `Consent rejected — ${mcpLabel}`, err)); return { steps, nextNum: n }; }
    if (err?.stage === 'obo-token') { steps.push(failHere('iam', 'agent', `OBO token exchange failed — ${mcpLabel}`, err)); return { steps, nextNum: n }; }

    steps.push({ from: 'iam', to: 'agent', num: n++, type: 'token', tokenType: 'obo', label: `OBO Token issued — ${mcpLabel}`, detail: 'The Auth Server issues a special token that carries both identities — the agent AND you.', mcpNodeId: mcp.nodeId });
  }

  if (tool) {
    const toolName = stripNodeSuffix(tool.publicName);
    const tokenType: 'agent' | 'obo' = mcp.oboToken ? 'obo' : 'agent';
    const tokenLabel = tokenType === 'obo' ? 'OBO Token' : 'Agent Token';
    steps.push({ from: 'agent', to: mcpLane, num: n++, type: 'secure', tokenType, label: `Agent calls ${toolName}`, detail: `Sends request with Authorization: Bearer <${tokenLabel}>. The service verifies the token before responding.`, mcpNodeId: mcp.nodeId });
    if (tool.ok) {
      steps.push({ from: mcpLane, to: 'agent', num: n++, type: 'response', label: `${mcpLabel} verifies and responds`, detail: `Token verified ✓ — service confirmed ${tokenType === 'obo' ? 'both the agent and user identity' : 'the agent is authorized'}. Data returned.`, mcpNodeId: mcp.nodeId });
    } else {
      const badge = [tool.statusCode ? `HTTP ${tool.statusCode}` : null, tool.errorCode || null].filter(Boolean).join(' · ') || 'failed';
      steps.push({ from: mcpLane, to: 'agent', num: n++, type: 'error', label: `${mcpLabel} rejected the call`, detail: tool.errorDescription || tool.result || 'Tool execution failed', mcpNodeId: mcp.nodeId, errorBadge: badge });
    }
  } else if (err?.stage === 'connect' || err?.stage === 'tool-call') {
    steps.push(failHere('agent', mcpLane, `Could not call ${mcpLabel}`, err));
  }

  return { steps, nextNum: n };
}

export function buildAllSteps(mcps: MCPNodeTrace[], tools: ToolCallTrace[]): AuthStep[] {
  const all: AuthStep[] = [];
  let n = 1;
  for (const mcp of mcps) {
    const { steps, nextNum } = buildAuthStepsForMcp(mcp, tools, n);
    all.push(...steps);
    n = nextNum;
  }
  return all;
}

export function getBoxes(mcps: MCPNodeTrace[], W: number, H: number): Boxes {
  const boxes: Boxes = {} as Boxes;
  const hasIAM = mcps.some((m) => perMcpFlow(m) !== 'none');
  const hasUser = mcps.some((m) => perMcpFlow(m) === 'obo');

  boxes.agent = { x: W / 2 - 85, y: H / 2 - 45, w: 170, h: 90, label: 'Smart Agent', sublabel: '(AI Assistant)', color: '#475569', bg: '#f1f5f9', border: '#94a3b8', inner: 'MCP Client' };

  const mcpW = 165, mcpH = 56, gap = 14;
  const totalH = mcps.length * mcpH + Math.max(0, mcps.length - 1) * gap;
  const startY = Math.max(20, H / 2 - totalH / 2);
  mcps.forEach((mcp, i) => {
    const endpointHost = mcp.endpoint.replace(/^https?:\/\//, '').split('/')[0];
    const hasError = !!mcp.authError;
    boxes[mcpLaneId(mcp)] = {
      x: W - mcpW - 30, y: startY + i * (mcpH + gap), w: mcpW, h: mcpH,
      label: mcpDisplayName(mcp), sublabel: `(${endpointHost})`,
      color: hasError ? '#b91c1c' : '#6d28d9',
      bg: hasError ? '#fef2f2' : '#fef9c3',
      border: hasError ? '#ef4444' : '#a3a3a3',
      hasError,
    };
  });

  if (hasIAM) boxes.iam = { x: 30, y: 24, w: 150, h: 70, label: 'Asgardeo IAM', sublabel: '(Auth Server)', color: '#b45309', bg: '#fffbeb', border: '#f59e0b', lock: true };
  if (hasUser) boxes.user = { x: 30, y: H - 90, w: 130, h: 65, label: 'You', sublabel: '(User)', color: '#2563eb', bg: '#eff6ff', border: '#3b82f6' };

  return boxes;
}

export function edgePoint(box: Box, angle: number): { x: number; y: number } {
  const cx = box.x + box.w / 2;
  const cy = box.y + box.h / 2;
  const hw = box.w / 2 + 8;
  const hh = box.h / 2 + 8;
  if (Math.abs(Math.cos(angle)) * hh > Math.abs(Math.sin(angle)) * hw) {
    const s = Math.sign(Math.cos(angle));
    return { x: cx + s * hw, y: cy + Math.tan(angle) * s * hw };
  }
  const s = Math.sign(Math.sin(angle));
  return { x: cx + (1 / Math.tan(angle)) * s * hh, y: cy + s * hh };
}

export function getArrowPath(fromBox: Box | undefined, toBox: Box | undefined, curveAmt: number): ArrowPath | null {
  if (!fromBox || !toBox) return null;
  const fc = { x: fromBox.x + fromBox.w / 2, y: fromBox.y + fromBox.h / 2 };
  const tc = { x: toBox.x + toBox.w / 2, y: toBox.y + toBox.h / 2 };
  const angle = Math.atan2(tc.y - fc.y, tc.x - fc.x);
  const s = edgePoint(fromBox, angle);
  const e = edgePoint(toBox, angle + Math.PI);
  const mx = (s.x + e.x) / 2 - Math.sin(angle) * (curveAmt || 0);
  const my = (s.y + e.y) / 2 + Math.cos(angle) * (curveAmt || 0);
  return { sx: s.x, sy: s.y, mx, my, ex: e.x, ey: e.y };
}
