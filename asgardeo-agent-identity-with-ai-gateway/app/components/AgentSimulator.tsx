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

import { useState } from 'react';
import { GateWayType } from '../config';
import {
  Header,
  SelectionPanel,
  ResultsPanel,
  SimulationSelection,
  SimulationResult,
  getScenarioLabel
} from './simulator';

export default function AgentSimulator() {
  const gatewayType = (process.env.NEXT_PUBLIC_GATEWAY_TYPE as GateWayType) || GateWayType.KONG;
  const orgName = process.env.NEXT_PUBLIC_ORG_NAME || '';
  const clientId = process.env.NEXT_PUBLIC_CLIENT_ID || '';
  const targetUrl = process.env.NEXT_PUBLIC_TARGET_URL || '';
  const wso2CoordinatorUrl = process.env.NEXT_PUBLIC_WSO2_COORDINATOR_URL || '';
  const wso2ExpertUrl = process.env.NEXT_PUBLIC_WSO2_EXPERT_URL || '';

  const [selection, setSelection] = useState<SimulationSelection>({
    callingAgent: 'Support-Coordinator',
    targetRoute: 'Support-Coordinator',
    withAuthorization: true
  });
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<SimulationResult[]>([]);
  const [expandedResult, setExpandedResult] = useState<number | null>(null);

  const authenticateAgent = async (callingAgent: string): Promise<string | null> => {
    try {
      const response = await fetch('/api/auth/agent-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          orgName,
          clientId,
          callingAgent,
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
    if (gatewayType === GateWayType.WSO2) {
      return targetAgent === 'Support-Coordinator'
        ? wso2CoordinatorUrl
        : wso2ExpertUrl;
    }
    return targetUrl;
  };

  const sendChatRequest = async (token: string | null, agentType: string) => {
    const url = getTargetUrl(agentType);

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'x-target-url': url,
      'x-gateway-type': gatewayType
    };

    // Kong uses header-based routing
    if (gatewayType === GateWayType.KONG) {
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
    setIsLoading(true);

    try {
      let token: string | null = null;

      // Authenticate using the calling agent's credentials (if authorization is enabled)
      if (selection.withAuthorization) {
        token = await authenticateAgent(selection.callingAgent);
      }

      // Send the request to the target route
      const { data, statusCode } = await sendChatRequest(token, selection.targetRoute);

      const result: SimulationResult = {
        selection: { ...selection },
        gatewayType,
        scenarioLabel: getScenarioLabel(selection, gatewayType),
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
        gatewayType,
        scenarioLabel: getScenarioLabel(selection, gatewayType),
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
      <Header />

      <main className="max-w-7xl mx-auto px-6 py-8">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          <SelectionPanel
            selection={selection}
            gatewayType={gatewayType}
            isLoading={isLoading}
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
