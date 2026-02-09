'use client';

import { SimulationResult } from './types';
import ResultCard from './ResultCard';

interface ResultsPanelProps {
  results: SimulationResult[];
  expandedResult: number | null;
  onToggleResult: (index: number) => void;
  onClearResults: () => void;
}

export default function ResultsPanel({
  results,
  expandedResult,
  onToggleResult,
  onClearResults
}: ResultsPanelProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-white flex items-center gap-2">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
            <polyline points="10 9 9 9 8 9"/>
          </svg>
          Simulation Results
        </h2>
        {results.length > 0 && (
          <button
            onClick={onClearResults}
            className="text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300 transition-colors"
          >
            Clear All
          </button>
        )}
      </div>

      {results.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-center">
          <div className="w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-4">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-gray-400">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <line x1="9" y1="21" x2="9" y2="9"/>
            </svg>
          </div>
          <h3 className="text-gray-700 dark:text-gray-300 font-medium mb-1">No Results Yet</h3>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Run a simulation to see the results here
          </p>
        </div>
      ) : (
        <div className="space-y-4 max-h-[600px] overflow-y-auto">
          {results.map((result, index) => (
            <ResultCard
              key={index}
              result={result}
              isExpanded={expandedResult === index}
              onToggle={() => onToggleResult(index)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
