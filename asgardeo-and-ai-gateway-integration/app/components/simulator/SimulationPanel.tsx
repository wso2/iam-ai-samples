'use client';

import { SimulationCase } from './types';
import SimulationCaseCard from './SimulationCaseCard';

interface SimulationPanelProps {
  selectedCase: SimulationCase;
  selectedAgent: string;
  isLoading: boolean;
  isConfigValid: boolean;
  onCaseChange: (caseType: SimulationCase) => void;
  onAgentChange: (agent: string) => void;
  onRunSimulation: () => void;
}

export default function SimulationPanel({
  selectedCase,
  selectedAgent,
  isLoading,
  isConfigValid,
  onCaseChange,
  onAgentChange,
  onRunSimulation
}: SimulationPanelProps) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg p-6">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-white mb-6 flex items-center gap-2">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="5 3 19 12 5 21 5 3"/>
        </svg>
        Run Simulation
      </h2>

      {/* Case Selection */}
      <div className="space-y-4 mb-6">
        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
          Select Simulation Case
        </label>
        
        <SimulationCaseCard
          caseType="correct-agent"
          title="Case 1:Agent on Correct Path"
          description="Agent authenticates with its own credentials and calls the API as itself"
          expectedResult="Expected: Success"
          expectedColor="green"
          isSelected={selectedCase === 'correct-agent'}
          onSelect={() => onCaseChange('correct-agent')}
        />

        <SimulationCaseCard
          caseType="wrong-agent"
          title="Case 2: Agent on Wrong Path (Impersonation)"
          description="Support-Coordinator authenticates with its credentials but tries to act as Technical-Specialist"
          expectedResult="Expected: Denied"
          expectedColor="yellow"
          isSelected={selectedCase === 'wrong-agent'}
          onSelect={() => onCaseChange('wrong-agent')}
        />

        <SimulationCaseCard
          caseType="no-auth"
          title="Case 3: No Authentication"
          description="Agent calls the API without any authorization header"
          expectedResult="Expected: Unauthorized"
          expectedColor="red"
          isSelected={selectedCase === 'no-auth'}
          onSelect={() => onCaseChange('no-auth')}
        />
      </div>

      {/* Agent Selection (for Case 1 and Case 3) */}
      {(selectedCase === 'correct-agent' || selectedCase === 'no-auth') && (
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
            Select Agent to Simulate
          </label>
          <select
            value={selectedAgent}
            onChange={(e) => onAgentChange(e.target.value)}
            className="w-full px-4 py-2 bg-gray-50 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg text-gray-900 dark:text-white focus:ring-2 focus:ring-orange-500 focus:border-transparent"
          >
            <option value="Support-Coordinator">Support-Coordinator</option>
            <option value="Technical-Specialist">Technical-Specialist</option>
          </select>
        </div>
      )}

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
