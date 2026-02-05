'use client';

import { SimulationCase } from './types';

interface SimulationCaseCardProps {
  caseType: SimulationCase;
  title: string;
  description: string;
  expectedResult: string;
  expectedColor: 'green' | 'yellow' | 'red';
  isSelected: boolean;
  onSelect: () => void;
}

const colorClasses = {
  green: {
    border: 'border-green-500 bg-green-50 dark:bg-green-900/20',
    badge: 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-400'
  },
  yellow: {
    border: 'border-yellow-500 bg-yellow-50 dark:bg-yellow-900/20',
    badge: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/40 dark:text-yellow-400'
  },
  red: {
    border: 'border-red-500 bg-red-50 dark:bg-red-900/20',
    badge: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-400'
  }
};

export default function SimulationCaseCard({
  caseType,
  title,
  description,
  expectedResult,
  expectedColor,
  isSelected,
  onSelect
}: SimulationCaseCardProps) {
  const colors = colorClasses[expectedColor];

  return (
    <label className={`flex items-start gap-3 p-4 rounded-lg border-2 cursor-pointer transition-all ${
      isSelected
        ? colors.border
        : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
    }`}>
      <input
        type="radio"
        name="case"
        value={caseType}
        checked={isSelected}
        onChange={onSelect}
        className="mt-1"
      />
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-gray-900 dark:text-white">{title}</span>
          <span className={`px-2 py-0.5 text-xs font-medium rounded ${colors.badge}`}>
            {expectedResult}
          </span>
        </div>
        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
          {description}
        </p>
      </div>
    </label>
  );
}
