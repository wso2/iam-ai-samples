'use client';

import { useEffect, useMemo, useState } from 'react';
import { WorkflowTrace } from '@/lib/authTrace';
import { COLORS, ColorKind, DiagramItem, Lane, buildLanes, buildItems } from '@/lib/diagramBuilder';
import { Button } from '@/components/ui/button';
import { TraceMeta } from '@/components/auth-flow/TraceMeta';
import { MCPList } from '@/components/auth-flow/MCPList';
import { ToolCallList } from '@/components/auth-flow/ToolCallList';
import { JwtLink } from '@/components/auth-flow/JwtLink';

interface Props {
  trace: WorkflowTrace;
}

export function AuthFlowDiagram({ trace }: Props) {
  const lanes = useMemo(() => buildLanes(trace), [trace]);
  const items = useMemo(() => buildItems(trace), [trace]);

  const layout = useMemo(() => {
    const sectionRowH = 40;
    const startY = 110;
    let y = startY;
    let msgCount = 0;
    const rows = items.map((it) => {
      if (it.kind === 'section') {
        const row = { y, height: sectionRowH, messageNumber: 0 };
        y += sectionRowH;
        return row;
      }
      const hasExtra = !!(it.sublabel || it.token);
      const height = hasExtra ? 78 : 50;
      const row = { y, height, messageNumber: ++msgCount };
      y += height;
      return row;
    });
    return { rows, totalH: y + 30, totalMessages: msgCount };
  }, [items]);

  const [step, setStep] = useState(layout.totalMessages);
  const [autoplay, setAutoplay] = useState(false);

  useEffect(() => { setStep(layout.totalMessages); }, [layout.totalMessages]);

  useEffect(() => {
    if (!autoplay) return;
    const t = setInterval(() => {
      setStep((s) => (s >= layout.totalMessages ? 0 : s + 1));
    }, 1300);
    return () => clearInterval(t);
  }, [autoplay, layout.totalMessages]);

  const HEADER_H = 110;
  const width = lanes[lanes.length - 1].x + 120;
  const contentH = layout.totalH - HEADER_H;
  const lanesById = useMemo(() => new Map(lanes.map((l) => [l.id, l])), [lanes]);

  const arrowMarkers = (['default', 'auth', 'blue', 'green'] as ColorKind[]).map((k) => (
    <marker key={k} id={`arr-${k}`} markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
      <polygon points="0 0, 10 3.5, 0 7" fill={COLORS[k]} />
    </marker>
  ));

  return (
    <div className="w-full">
      <TraceMeta trace={trace} />
      <div className="flex items-center gap-3 mb-3">
        <h3 className="text-base font-bold text-slate-800">Sequence Flow</h3>
        <div className="ml-auto flex items-center gap-2">
          <Button onClick={() => { setStep(0); setAutoplay(true); }} size="sm" variant="outline" className="text-xs text-cyan-800 bg-cyan-50 hover:bg-cyan-100 border-cyan-200">
            ▶ Animate
          </Button>
          <Button onClick={() => { setAutoplay(false); setStep(layout.totalMessages); }} size="sm" variant="outline" className="text-xs">
            Show all
          </Button>
        </div>
      </div>

      <div className="overflow-auto bg-white rounded border border-slate-200 max-h-[68vh]">
        {/* Sticky entity header */}
        <div className="sticky top-0 z-10 bg-white border-b border-slate-100" style={{ width }}>
          <svg width={width} height={HEADER_H} viewBox={`0 0 ${width} ${HEADER_H}`} className="block">
            <defs>{arrowMarkers}</defs>
            {lanes.map((lane) => {
              const boxH = lane.sublabel ? 60 : 44;
              const boxY = lane.sublabel ? 12 : 18;
              return (
                <g key={lane.id}>
                  <line x1={lane.x} y1={boxY + boxH} x2={lane.x} y2={HEADER_H} stroke="#e2e8f0" strokeWidth="2" strokeDasharray="5,5" />
                  {lane.shape === 'circle' ? (
                    <>
                      <circle cx={lane.x} cy={40} r={22} fill={lane.fill} stroke={lane.stroke} />
                      <text x={lane.x} y={45} textAnchor="middle" fontSize="11" fontWeight="700" fill={lane.textColor}>{lane.label}</text>
                    </>
                  ) : (
                    <>
                      <rect x={lane.x - 80} y={boxY} width={160} height={boxH} rx={6} fill={lane.fill} stroke={lane.stroke} />
                      <foreignObject x={lane.x - 78} y={boxY + 2} width={156} height={boxH - 4}>
                        <div
                          // @ts-ignore
                          xmlns="http://www.w3.org/1999/xhtml"
                          className="h-full flex flex-col items-center justify-center text-center px-1"
                          title={lane.sublabel ? `${lane.label}\n${lane.sublabel}` : lane.label}
                        >
                          <div className="text-[11px] font-bold leading-tight truncate w-full" style={{ color: lane.textColor }}>{lane.label}</div>
                          {lane.sublabel && (
                            <div className="text-[8.5px] font-mono leading-tight mt-0.5 break-all line-clamp-2" style={{ color: lane.textColor, opacity: 0.7 }}>{lane.sublabel}</div>
                          )}
                        </div>
                      </foreignObject>
                    </>
                  )}
                </g>
              );
            })}
          </svg>
        </div>

        {/* Scrollable content */}
        <svg width={width} height={contentH} viewBox={`0 0 ${width} ${contentH}`} className="block">
          <defs>{arrowMarkers}</defs>
          {lanes.map((lane) => (
            <line key={lane.id} x1={lane.x} y1={0} x2={lane.x} y2={contentH - 10} stroke="#e2e8f0" strokeWidth="2" strokeDasharray="5,5" />
          ))}
          {items.map((item, idx) => {
            const rawRow = layout.rows[idx];
            const row = { ...rawRow, y: rawRow.y - HEADER_H };

            if (item.kind === 'section') {
              const sectionFill = item.failed ? '#fef2f2' : '#ecfeff';
              const sectionStroke = item.failed ? '#fca5a5' : '#67e8f9';
              const sectionTextColor = item.failed ? '#b91c1c' : '#0e7490';
              return (
                <g key={idx}>
                  <rect x={20} y={row.y + 6} width={width - 40} height={row.height - 12} fill={sectionFill} stroke={sectionStroke} strokeOpacity={0.7} rx={4} />
                  <text x={width / 2} y={row.y + row.height / 2 + 4} textAnchor="middle" fontSize="12" fontWeight="700" fill={sectionTextColor} letterSpacing="1.5">
                    — {item.label} —
                  </text>
                </g>
              );
            }

            const visible = step >= row.messageNumber;
            const fromLane = lanesById.get(item.from) ?? lanes[0];
            const toLane = lanesById.get(item.to) ?? lanes[lanes.length - 1];
            const x1 = fromLane.x;
            const x2 = toLane.x;
            const arrowY = row.y + row.height - 12;
            const labelLeft = Math.min(x1, x2);
            const labelWidth = Math.max(Math.abs(x2 - x1), 280);
            const stroke = COLORS[item.color || 'default'];

            return (
              <g key={idx} opacity={visible ? 1 : 0.18} className="transition-opacity duration-300">
                <foreignObject x={labelLeft - 80} y={row.y + 4} width={labelWidth + 160} height={row.height - 18}>
                  <div
                    // @ts-ignore
                    xmlns="http://www.w3.org/1999/xhtml"
                    className="text-center text-[10.5px] leading-snug px-1"
                  >
                    <div className="font-semibold" style={{ color: stroke }}>
                      <span className="inline-block px-1.5 py-0.5 mr-1 rounded bg-white border border-slate-200 text-slate-500 text-[9px] font-mono">
                        {row.messageNumber}
                      </span>
                      {item.label}
                    </div>
                    {item.sublabel && <div className="text-slate-500 font-mono text-[9.5px] mt-0.5 break-words">{item.sublabel}</div>}
                    {item.token && (
                      <div className="mt-0.5">
                        <JwtLink token={item.token} label={item.tokenLabel || 'Decode JWT'} />
                      </div>
                    )}
                  </div>
                </foreignObject>
                <line x1={x1} y1={arrowY} x2={x2} y2={arrowY} stroke={stroke} strokeWidth={item.color === 'blue' ? 2.2 : 1.8} strokeDasharray={item.dashed ? '5 4' : undefined} markerEnd={`url(#arr-${item.color || 'default'})`} />
              </g>
            );
          })}
        </svg>
      </div>

      <MCPList trace={trace} />
      <ToolCallList trace={trace} />
    </div>
  );
}
