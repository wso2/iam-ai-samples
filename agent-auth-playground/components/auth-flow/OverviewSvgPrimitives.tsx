import React from 'react';
import { Box, ArrowPath } from '@/lib/overviewBuilder';

export function BoxEl({ box, active, glowColor }: { box: Box; active: boolean; glowColor: string | null }) {
  return (
    <g>
      {active && glowColor && (
        <rect x={box.x - 5} y={box.y - 5} width={box.w + 10} height={box.h + 10}
          rx={14} fill="none" stroke={glowColor} strokeWidth={3} style={{ animation: 'authFlowOverviewGlow 1.2s infinite' }} />
      )}
      <rect x={box.x + 2} y={box.y + 3} width={box.w} height={box.h} rx={10} fill="rgba(0,0,0,0.04)" />
      <rect x={box.x} y={box.y} width={box.w} height={box.h}
        rx={10} fill={box.bg} stroke={box.border} strokeWidth={box.lock || box.hasError ? 2.5 : 1.5} />
      {box.lock && (
        <g transform={`translate(${box.x + 10}, ${box.y - 10})`}>
          <rect y={6} width={14} height={12} rx={2} fill="#f59e0b" />
          <path d="M2.5,6 V3 a4.5,4.5 0 0 1 9,0 V6" fill="none" stroke="#f59e0b" strokeWidth={1.8} strokeLinecap="round" />
        </g>
      )}
      {box.hasError && (
        <g transform={`translate(${box.x + box.w - 22}, ${box.y - 9})`}>
          <circle cx={9} cy={9} r={9} fill="#ef4444" />
          <text x={9} y={13} textAnchor="middle" fontSize={11} fontWeight={700} fill="#fff">!</text>
        </g>
      )}
      {box.inner && (
        <>
          <rect x={box.x + 20} y={box.y + box.h - 28} width={box.w - 40} height={20} rx={4} fill="#fff" stroke="#8b5cf6" strokeWidth={1} />
          <text x={box.x + box.w / 2} y={box.y + box.h - 14.5} textAnchor="middle" fontSize={9} fontWeight={600} fill="#7c3aed">{box.inner}</text>
        </>
      )}
      <text x={box.x + box.w / 2} y={box.y + (box.inner ? 24 : box.h / 2 - (box.sublabel ? 4 : 0))}
        textAnchor="middle" fontSize={12.5} fontWeight={700} fill={box.color}>{box.label}</text>
      {box.sublabel && (
        <text x={box.x + box.w / 2} y={box.y + (box.inner ? 37 : box.h / 2 + 12)}
          textAnchor="middle" fontSize={9} fill={box.color} opacity={0.7}>{box.sublabel}</text>
      )}
    </g>
  );
}

export function ArrowSVG({ path, color, dashed, thick, op }: { path: ArrowPath | null; color: string; dashed?: boolean; thick?: boolean; op: number }) {
  const id = React.useId();
  if (!path) return null;
  return (
    <g opacity={op}>
      <defs>
        <marker id={id} markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto">
          <polygon points="0 0,8 3,0 6" fill={color} />
        </marker>
      </defs>
      <path
        d={`M${path.sx},${path.sy} Q${path.mx},${path.my} ${path.ex},${path.ey}`}
        fill="none" stroke={color} strokeWidth={thick ? 2.8 : 1.6}
        strokeDasharray={dashed ? '6 4' : undefined} markerEnd={`url(#${id})`}
      />
    </g>
  );
}

export function Badge({ x, y, num, color }: { x: number; y: number; num: number; color: string }) {
  return (
    <g>
      <circle cx={x} cy={y} r={11} fill={color} />
      <text x={x} y={y + 3.5} textAnchor="middle" fontSize={9} fontWeight={700} fill="#fff" fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace">{num}</text>
    </g>
  );
}

export function TokenTag({ x, y, tokenType }: { x: number; y: number; tokenType: 'agent' | 'obo' }) {
  const isObo = tokenType === 'obo';
  return (
    <g>
      <rect x={x - 38} y={y - 9} width={76} height={18} rx={4}
        fill={isObo ? '#dcfce7' : '#fef3c7'} stroke={isObo ? '#22c55e' : '#f59e0b'} strokeWidth={1} />
      <text x={x} y={y + 3} textAnchor="middle" fontSize={8.5} fontWeight={700}
        fill={isObo ? '#16a34a' : '#b45309'}>{isObo ? 'OBO Token' : 'Agent Token'}</text>
    </g>
  );
}

export function WarningTag({ x, y }: { x: number; y: number }) {
  return (
    <g>
      <rect x={x - 32} y={y - 9} width={64} height={18} rx={4} fill="#fef2f2" stroke="#ef4444" strokeWidth={1} />
      <text x={x} y={y + 3} textAnchor="middle" fontSize={8.5} fontWeight={700} fill="#ef4444">⚠ No Auth</text>
    </g>
  );
}

export function ErrorTag({ x, y, text }: { x: number; y: number; text: string }) {
  const w = Math.max(64, Math.min(160, text.length * 6.2 + 14));
  return (
    <g>
      <rect x={x - w / 2} y={y - 10} width={w} height={20} rx={4} fill="#fef2f2" stroke="#ef4444" strokeWidth={1.2} />
      <text x={x} y={y + 3.5} textAnchor="middle" fontSize={9} fontWeight={700} fill="#b91c1c">❌ {text}</text>
    </g>
  );
}
