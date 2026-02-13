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
import StatusBadge from './StatusBadge';
import { ChevronDownIcon, ExternalLinkIcon } from '../../../assets/icons';

interface ResultCardProps {
  result: SimulationResult;
  isExpanded: boolean;
  onToggle: () => void;
}

export default function ResultCard({ result, isExpanded, onToggle }: ResultCardProps) {
  return (
    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Result Header */}
      <button
        onClick={onToggle}
        className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-700/50 flex items-center justify-between hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className={`w-3 h-3 rounded-full ${
            result.statusCode >= 200 && result.statusCode < 300
              ? 'bg-green-500'
              : result.statusCode >= 400 && result.statusCode < 500
              ? 'bg-yellow-500'
              : 'bg-red-500'
          }`} />
          <span className="font-medium text-gray-900 dark:text-white text-sm">
            {result.scenarioLabel}
          </span>
          <StatusBadge statusCode={result.statusCode} />
        </div>
        <ChevronDownIcon
          className={`text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Result Details */}
      {isExpanded && (
        <div className="px-4 py-3 space-y-3 text-sm">
          <div>
            <span className="text-gray-500 dark:text-gray-400">Calling Agent:</span>
            <span className="ml-2 text-gray-900 dark:text-white">{result.selection.callingAgent}</span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Target Route:</span>
            <span className="ml-2 text-gray-900 dark:text-white">{result.selection.targetRoute}</span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Authorization:</span>
            <span className="ml-2 text-gray-900 dark:text-white">
              {result.selection.withAuthorization ? 'With Token' : 'No Token'}
            </span>
          </div>
          <div>
            <span className="text-gray-500 dark:text-gray-400">Timestamp:</span>
            <span className="ml-2 text-gray-900 dark:text-white">
              {result.timestamp.toLocaleTimeString()}
            </span>
          </div>
          
          {result.tokenReceived && (
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-gray-500 dark:text-gray-400">Token Received:</span>
                <a
                  href={`https://jwt.io/#id_token=${result.tokenReceived}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/20 hover:bg-orange-100 dark:hover:bg-orange-900/40 rounded transition-colors"
                >
                  <ExternalLinkIcon />
                  Decode Token
                </a>
              </div>
              <code className="block p-2 bg-gray-100 dark:bg-gray-900 rounded text-xs break-all max-h-20 overflow-y-auto">
                {result.tokenReceived}
              </code>
            </div>
          )}
          
          <div>
            <span className="text-gray-500 dark:text-gray-400 block mb-1">Response:</span>
            <pre className="p-2 bg-gray-100 dark:bg-gray-900 rounded text-xs overflow-x-auto max-h-48 overflow-y-auto">
              {JSON.stringify(result.response, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
