import { StepType, AuthStep } from '@/lib/overviewBuilder';

export const STEP_STYLES: Record<StepType, { bg: string; border: string; icon: string }> = {
  auth:     { bg: '#fffbeb', border: '#fcd34d', icon: '🔐' },
  token:    { bg: '#fef3c7', border: '#f59e0b', icon: '🎫' },
  consent:  { bg: '#eff6ff', border: '#60a5fa', icon: '👤' },
  secure:   { bg: '#f0fdf4', border: '#4ade80', icon: '🔒' },
  unsecure: { bg: '#fef2f2', border: '#f87171', icon: '⚠️' },
  response: { bg: '#f0fdf4', border: '#86efac', icon: '✅' },
  error:    { bg: '#fef2f2', border: '#ef4444', icon: '❌' },
  normal:   { bg: '#f8fafc', border: '#e2e8f0', icon: '➡️' },
};

export function StepCard({ step }: { step: AuthStep | null }) {
  if (!step) {
    return (
      <div className="px-[18px] py-3.5 rounded-xl bg-slate-50 border border-dashed border-slate-300 text-slate-400 text-xs text-center">
        Press <strong className="font-semibold">Play</strong> or <strong className="font-semibold">Show All</strong> to walk through the auth flow.
      </div>
    );
  }
  const s = STEP_STYLES[step.type] || STEP_STYLES.normal;
  return (
    <div
      className="px-[18px] py-3.5 rounded-xl flex gap-3 items-start"
      style={{ background: s.bg, border: `1.5px solid ${s.border}`, animation: 'authFlowOverviewFadeIn 0.3s ease' }}
    >
      <span className="text-[22px] flex-shrink-0">{s.icon}</span>
      <div className="min-w-0">
        <div className="text-sm font-bold text-slate-900 flex flex-wrap items-center gap-2">
          <span>Step {step.num} — {step.label}</span>
          {step.errorBadge && (
            <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-red-200 text-red-900">{step.errorBadge}</span>
          )}
        </div>
        {step.detail && <div className="text-xs text-slate-500 mt-0.5 leading-relaxed break-words">{step.detail}</div>}
      </div>
    </div>
  );
}
