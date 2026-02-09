'use client';

import { useState } from 'react';
import { AppConfig } from './ConfigurationModal';
import {
  Header,
  ConfigWarning,
  SelectionPanel,
  ResultsPanel,
  SimulationSelection,
  SimulationResult,
  getScenarioLabel
} from './simulator';

interface AgentSimulatorProps {
  config: AppConfig;
  onOpenConfig: () => void;
}

export default function AgentSimulator({ config, onOpenConfig }: AgentSimulatorProps) {
  const [selection, setSelection] = useState<SimulationSelection>({
    callingAgent: 'Support-Coordinator',
    targetRoute: 'Support-Coordinator',
    withAuthorization: true
  });
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SimulationResult[]>([]);
  const [expandedResult, setExpandedResult] = useState<number | null>(null);

  const isConfigValid = (): boolean => {
    const baseValid = !!(config.orgName && config.clientId &&
           config.coordinatorAgent.agentId && config.coordinatorAgent.agentSecret &&
           config.expertAgent.agentId && config.expertAgent.agentSecret);
    
    if (config.gatewayType === 'wso2') {
      return baseValid && !!(config.wso2CoordinatorUrl && config.wso2ExpertUrl);
    }
    return baseValid && !!config.targetUrl;
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

  const getTargetUrl = (targetAgent: string): string => {
    if (config.gatewayType === 'wso2') {
      return targetAgent === 'Support-Coordinator'
        ? config.wso2CoordinatorUrl
        : config.wso2ExpertUrl;
    }
    return config.targetUrl;
  };

  const sendChatRequest = async (token: string | null, agentType: string) => {
    const targetUrl = getTargetUrl(agentType);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'x-target-url': targetUrl,
      'x-gateway-type': config.gatewayType
    };

    // Kong uses header-based routing
    if (config.gatewayType === 'kong') {
      headers['x-agent-type'] = agentType;
    }

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

    try {
      let token: string | null = null;

      // Authenticate using the calling agent's credentials (if authorization is enabled)
      if (selection.withAuthorization) {
        const credentials = getAgentCredentials(selection.callingAgent);
        token = await authenticateAgent(credentials.agentId, credentials.agentSecret);
      }

      // Send the request to the target route
      const { data, statusCode } = await sendChatRequest(token, selection.targetRoute);

      const result: SimulationResult = {
        selection: { ...selection },
        gatewayType: config.gatewayType,
        scenarioLabel: getScenarioLabel(selection, config.gatewayType),
        tokenReceived: token,
        response: data,
        statusCode,
        timestamp: new Date()
      };

      setResults(prev => [result, ...prev]);
      setExpandedResult(0);
    } catch (error) {
      const errorResult: SimulationResult = {
        selection: { ...selection },
        gatewayType: config.gatewayType,
        scenarioLabel: getScenarioLabel(selection, config.gatewayType),
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
          <SelectionPanel
            selection={selection}
            gatewayType={config.gatewayType}
            isLoading={isLoading}
            isConfigValid={isConfigValid()}
            onSelectionChange={setSelection}
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
