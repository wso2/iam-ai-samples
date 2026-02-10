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

import { GateWayType } from '../ConfigurationModal';
import { AgentType, SimulationSelection, getExpectedOutcome } from './types';

interface SelectionPanelProps {
  selection: SimulationSelection;
  gatewayType: GateWayType;
  isLoading: boolean;
  isConfigValid: boolean;
  onSelectionChange: (selection: SimulationSelection) => void;
  onRunSimulation: () => void;
}

export default function SelectionPanel({
  selection,
  gatewayType,
  isLoading,
  isConfigValid,
  onSelectionChange,
  onRunSimulation
}: SelectionPanelProps) {
  const expected = getExpectedOutcome(selection, gatewayType);

  const expectedColorClasses = {
    green: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800 text-green-700 dark:text-green-400',
    yellow: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800 text-yellow-700 dark:text-yellow-400',
    red: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-400'
  };

  const agentOptions: { value: AgentType; label: string; icon: string }[] = [
    { value: 'Support-Coordinator', label: 'Support-Coordinator', icon: '🤝' },
    { value: 'Technical-Specialist', label: 'Technical-Specialist', icon: '🔧' }
  ];

  const isKong = gatewayType === GateWayType.KONG;
 
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-2 flex items-center gap-2">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="5 3 19 12 5 21 5 3"/>
        </svg>
        Select Simulation
      </h2>

      {/* Gateway Badge */}
      <div className="mb-6">
        <span className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${
          isKong
            ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400'
            : 'bg-teal-100 text-teal-700 dark:bg-teal-900/30 dark:text-teal-400'
        }`}>
          <span className={`w-2 h-2 rounded-full ${isKong ? 'bg-indigo-500' : 'bg-teal-500'}`} />
          {isKong ? 'Kong AI Gateway' : 'WSO2 AI Gateway'}
        </span>
        {/* <p className="mt-1.5 text-xs text-gray-500 dark:text-gray-400">
          {isKong
            ? 'Agent routing via x-agent-type header'
            : 'Separate proxy URLs per agent'}
        </p> */}
      </div>

      <div className="space-y-6 mb-6">
        {/* Calling Agent */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Calling Agent
          </label>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
            Which agent is making the API call? This determines the credentials used for authentication.
          </p>
          <div className="grid grid-cols-2 gap-3">
            {agentOptions.map((agent) => (
              <button
                key={agent.value}
                onClick={() => onSelectionChange({ ...selection, callingAgent: agent.value })}
                className={`flex items-center gap-2 p-3 rounded-lg border-2 transition-all text-left ${
                  selection.callingAgent === agent.value
                    ? 'border-orange-500 bg-orange-50 dark:bg-orange-900/20'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
              >
                <span className="text-lg">{agent.icon}</span>
                <span className={`text-sm font-medium ${
                  selection.callingAgent === agent.value
                    ? 'text-orange-700 dark:text-orange-400'
                    : 'text-gray-700 dark:text-gray-300'
                }`}>
                  {agent.label}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Target Route / Target Agent URL */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            {isKong ? 'Target Route' : 'Target Agent URL'}
          </label>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
            {isKong
              ? <>Which agent&apos;s route is the request sent to? This sets the <code className="px-1 py-0.5 bg-gray-100 dark:bg-gray-700 rounded text-xs">x-agent-type</code> header.</>
              : 'Which agent\'s dedicated proxy URL will the request be sent to?'}
          </p>
          <div className="grid grid-cols-2 gap-3">
            {agentOptions.map((agent) => (
              <button
                key={agent.value}
                onClick={() => onSelectionChange({ ...selection, targetRoute: agent.value })}
                className={`flex items-center gap-2 p-3 rounded-lg border-2 transition-all text-left ${
                  selection.targetRoute === agent.value
                    ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                    : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
                }`}
              >
                <span className="text-lg">{agent.icon}</span>
                <div>
                  <span className={`text-sm font-medium block ${
                    selection.targetRoute === agent.value
                      ? 'text-blue-700 dark:text-blue-400'
                      : 'text-gray-700 dark:text-gray-300'
                  }`}>
                    {agent.label}
                  </span>
                  {!isKong && (
                    <span className="text-[10px] text-gray-400 dark:text-gray-500 block mt-0.5">
                      {agent.value === 'Support-Coordinator' ? 'Coordinator proxy URL' : 'Expert proxy URL'}
                    </span>
                  )}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Authorization Toggle */}
        <div>
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Authorization
          </label>
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
            Should the request include an authorization token?
          </p>
          <div className="grid grid-cols-2 gap-3">
            <button
              onClick={() => onSelectionChange({ ...selection, withAuthorization: true })}
              className={`flex items-center gap-2 p-3 rounded-lg border-2 transition-all text-left ${
                selection.withAuthorization
                  ? 'border-green-500 bg-green-50 dark:bg-green-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                className={selection.withAuthorization ? 'text-green-600 dark:text-green-400' : 'text-gray-400'}>
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
              </svg>
              <span className={`text-sm font-medium ${
                selection.withAuthorization
                  ? 'text-green-700 dark:text-green-400'
                  : 'text-gray-700 dark:text-gray-300'
              }`}>
                With Authorization
              </span>
            </button>
            <button
              onClick={() => onSelectionChange({ ...selection, withAuthorization: false })}
              className={`flex items-center gap-2 p-3 rounded-lg border-2 transition-all text-left ${
                !selection.withAuthorization
                  ? 'border-red-500 bg-red-50 dark:bg-red-900/20'
                  : 'border-gray-200 dark:border-gray-700 hover:border-gray-300 dark:hover:border-gray-600'
              }`}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
                className={!selection.withAuthorization ? 'text-red-600 dark:text-red-400' : 'text-gray-400'}>
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
                <path d="M7 11V7a5 5 0 0 1 9.9-1"/>
              </svg>
              <span className={`text-sm font-medium ${
                !selection.withAuthorization
                  ? 'text-red-700 dark:text-red-400'
                  : 'text-gray-700 dark:text-gray-300'
              }`}>
                Without Authorization
              </span>
            </button>
          </div>
        </div>
      </div>

      {/* Expected Outcome */}
      <div className={`mb-6 p-3 rounded-lg border text-sm font-medium ${expectedColorClasses[expected.color]}`}>
        <div className="flex items-center gap-2">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"/>
            <path d="M12 16v-4M12 8h.01"/>
          </svg>
          {expected.label}
        </div>
      </div>

      {/* Run Button */}
      <button
        onClick={onRunSimulation}
        disabled={isLoading || !isConfigValid}
        className="w-full py-3 px-4 bg-gradient-to-r from-orange-500 to-orange-600 hover:from-orange-600 hover:to-orange-700 disabled:from-gray-400 disabled:to-gray-500 text-white font-medium rounded-lg shadow-lg hover:shadow-xl disabled:shadow-none transition-all flex items-center justify-center gap-2"
      >
        {isLoading ? (
          <>
            <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/>
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"/>
            </svg>
            Running Simulation...
          </>
        ) : (
          <>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polygon points="5 3 19 12 5 21 5 3"/>
            </svg>
            Run Simulation
          </>
        )}
      </button>
    </div>
  );
}
