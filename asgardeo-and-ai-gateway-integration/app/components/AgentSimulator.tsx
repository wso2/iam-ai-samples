'use client';

import { useState } from 'react';
import { AppConfig } from './ConfigurationModal';
import {
  Header,
  ConfigWarning,
  SimulationPanel,
  ResultsPanel,
  SimulationCase,
  SimulationResult
} from './simulator';

interface AgentSimulatorProps {
  config: AppConfig;
  onOpenConfig: () => void;
}

export default function AgentSimulator({ config, onOpenConfig }: AgentSimulatorProps) {
  const [selectedCase, setSelectedCase] = useState<SimulationCase>('correct-agent');
  const [selectedAgent, setSelectedAgent] = useState<string>('Support-Coordinator');
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SimulationResult[]>([]);
  const [expandedResult, setExpandedResult] = useState<number | null>(null);

  const isConfigValid = (): boolean => {
    return !!(config.orgName && config.clientId && config.targetUrl &&
           config.coordinatorAgent.agentId && config.coordinatorAgent.agentSecret &&
           config.expertAgent.agentId && config.expertAgent.agentSecret);
  };

  const getAgentCredentials = (agentType: string) => {
    if (agentType === 'Support-Coordinator') {
      return {
        agentId: config.coordinatorAgent.agentId,
        agentSecret: config.coordinatorAgent.agentSecret
      };
    } else {
      return {
        agentId: config.expertAgent.agentId,
        agentSecret: config.expertAgent.agentSecret
      };
    }
  };

  const getWrongAgentCredentials = () => {
    // Support-Coordinator trying to act as Technical-Specialist
    // Uses Coordinator's credentials but sends as Technical-Specialist
    return {
      credentials: {
        agentId: config.coordinatorAgent.agentId,
        agentSecret: config.coordinatorAgent.agentSecret
      },
      claimedAgentType: 'Technical-Specialist'
    };
  };

  const authenticateAgent = async (agentId: string, agentSecret: string): Promise<string | null> => {
    try {
      const response = await fetch('/api/auth/agent-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          orgName: config.orgName,
          clientId: config.clientId,
          agentId: agentId,
          agentSecret: agentSecret
        })
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.error || 'Failed to authenticate');
      }

      const data = await response.json();
      return data.access_token;
    } catch (error) {
      console.error('Authentication error:', error);
      throw error;
    }
  };

  const sendChatRequest = async (token: string | null, agentType: string) => {
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'x-agent-type': agentType,
      'x-target-url': config.targetUrl
    };

    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch('/api/chat', {
      method: 'POST',
      headers,
      body: JSON.stringify({
        messages: [{ role: 'user', content: `Hello, I am ${agentType}. This is a test message.` }]
      })
    });

    const data = await response.json();
    return { data, statusCode: response.status };
  };

  const runSimulation = async () => {
    if (!isConfigValid()) {
      alert('Please configure all settings first');
      onOpenConfig();
      return;
    }

    setIsLoading(true);
    let result: SimulationResult;

    try {
      switch (selectedCase) {
        case 'correct-agent': {
          // Case 1: Agent calling as the correct agent
          const credentials = getAgentCredentials(selectedAgent);
          const token = await authenticateAgent(credentials.agentId, credentials.agentSecret);
          const { data, statusCode } = await sendChatRequest(token, selectedAgent);
          
          result = {
            caseType: 'correct-agent',
            agentType: selectedAgent,
            authUsed: `${selectedAgent} credentials`,
            tokenReceived: token,
            response: data,
            statusCode,
            timestamp: new Date()
          };
          break;
        }

        case 'wrong-agent': {
          // Case 2: Support-Coordinator trying to act as Technical-Specialist
          const { credentials, claimedAgentType } = getWrongAgentCredentials();
          const token = await authenticateAgent(credentials.agentId, credentials.agentSecret);
          const { data, statusCode } = await sendChatRequest(token, claimedAgentType);
          
          result = {
            caseType: 'wrong-agent',
            agentType: 'Technical-Specialist',
            authUsed: 'Support-Coordinator credentials',
            tokenReceived: token,
            response: data,
            statusCode,
            timestamp: new Date()
          };
          break;
        }

        case 'no-auth': {
          // Case 3: Agent calling without authentication
          const { data, statusCode } = await sendChatRequest(null, selectedAgent);
          
          result = {
            caseType: 'no-auth',
            agentType: selectedAgent,
            authUsed: 'No authentication',
            tokenReceived: null,
            response: data,
            statusCode,
            timestamp: new Date()
          };
          break;
        }

        default:
          throw new Error('Invalid simulation case');
      }

      setResults(prev => [result, ...prev]);
      setExpandedResult(0);
    } catch (error) {
      const errorResult: SimulationResult = {
        caseType: selectedCase,
        agentType: selectedAgent,
        authUsed: selectedCase === 'no-auth' ? 'No authentication' : `${selectedAgent} credentials`,
        tokenReceived: null,
        response: { error: error instanceof Error ? error.message : 'Unknown error' },
        statusCode: 500,
        timestamp: new Date()
      };
      setResults(prev => [errorResult, ...prev]);
      setExpandedResult(0);
    } finally {
      setIsLoading(false);
    }
  };

  const clearResults = () => {
    setResults([]);
    setExpandedResult(null);
  };

  const handleToggleResult = (index: number) => {
    setExpandedResult(expandedResult === index ? null : index);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-900 dark:to-gray-800">
      <Header onOpenConfig={onOpenConfig} />

      <main className="max-w-7xl mx-auto px-6 py-8">
        {!isConfigValid() && <ConfigWarning onOpenConfig={onOpenConfig} />}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <SimulationPanel
            selectedCase={selectedCase}
            selectedAgent={selectedAgent}
            isLoading={isLoading}
            isConfigValid={isConfigValid()}
            onCaseChange={setSelectedCase}
            onAgentChange={setSelectedAgent}
            onRunSimulation={runSimulation}
          />

          <ResultsPanel
            results={results}
            expandedResult={expandedResult}
            onToggleResult={handleToggleResult}
            onClearResults={clearResults}
          />
        </div>
      </main>
    </div>
  );
}
