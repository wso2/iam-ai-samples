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

import { SimulationResult } from './types';
import ResultCard from './ResultCard';
import DocumentIcon from '../../../assets/icons/document.svg';
import GridIcon from '../../../assets/icons/grid.svg';

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
          <DocumentIcon />
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
            <GridIcon className="text-gray-400" />
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
