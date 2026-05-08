import { ReactNode } from 'react';

interface ErrorBorderProps {
  active: boolean;
  rx: number | string;
  className?: string;
  children: ReactNode;
}

export default function ErrorBorder({ active, rx, className, children }: ErrorBorderProps) {
  return (
    <div className={`relative ${className ?? ''}`}>
      {children}
      {active && (
        <svg
          aria-hidden
          className="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
        >
          <rect
            x="0"
            y="0"
            width="100%"
            height="100%"
            rx={rx}
            ry={rx}
            fill="none"
            stroke="#ef4444"
            strokeWidth={2.5}
            style={{
              filter: 'drop-shadow(0 0 6px rgba(239, 68, 68, 0.8))',
            }}
          />
        </svg>
      )}
    </div>
  );
}
