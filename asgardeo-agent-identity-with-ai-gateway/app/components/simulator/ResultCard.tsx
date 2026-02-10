/**
 Copyright (c) 2026, WSO2 LLC. (http://www.wso2.com). All Rights Reserved.
 
 This software is the property of WSO2 LLC. and its suppliers, if any.
 Dissemination of any information or reproduction of any material contained
 herein is strictly forbidden, unless permitted by WSO2 in accordance with
 the WSO2 Commercial License available at http://wso2.com/licenses.
 For specific language governing the permissions and limitations under
 this license, please see the license as well as any agreement you’ve
 entered into with WSO2 governing the purchase of this software and any
 */

'use client';

import { SimulationResult } from './types';
import StatusBadge from './StatusBadge';

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
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          className={`text-gray-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
        >
          <polyline points="6 9 12 15 18 9"/>
        </svg>
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
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
                    <polyline points="15 3 21 3 21 9"/>
                    <line x1="10" y1="14" x2="21" y2="3"/>
                  </svg>
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
