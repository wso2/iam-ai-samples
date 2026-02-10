/**
 * Copyright (c) 2020-2026, WSO2 LLC. (https://www.wso2.com).
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

import { AppConfig, GateWayType } from '../ConfigurationModal';

export type AgentType = 'Support-Coordinator' | 'Technical-Specialist';

export interface SimulationSelection {
  callingAgent: AgentType;
  targetRoute: AgentType;
  withAuthorization: boolean;
}

export interface SimulationResult {
  selection: SimulationSelection;
  gatewayType: GateWayType;
  scenarioLabel: string;
  tokenReceived: string | null;
  response: any;
  statusCode: number;
  timestamp: Date;
}

export interface AgentSimulatorProps {
  config: AppConfig;
  onOpenConfig: () => void;
}

/**
 * Derive the expected outcome description based on the selection and gateway type.
 */
export function getExpectedOutcome(
  selection: SimulationSelection,
  gatewayType: GateWayType
): {
  label: string;
  color: 'green' | 'yellow' | 'red';
} {
  if (!selection.withAuthorization) {
    return { label: 'Expected: Unauthorized (401)', color: 'red' };
  }
  if (gatewayType === GateWayType.WSO2) {
    // WSO2: separate URLs per agent. Calling the wrong agent's URL with your own token → denied.
    if (selection.callingAgent === selection.targetRoute) {
      return { label: 'Expected: Success (200)', color: 'green' };
    }
    return { label: 'Expected: Denied (403)', color: 'yellow' };
  }
  // Kong: header-based routing.
  if (selection.callingAgent === selection.targetRoute) {
    return { label: 'Expected: Success (200)', color: 'green' };
  }
  return { label: 'Expected: Denied (403)', color: 'yellow' };
}

/**
 * Build a human-readable label describing the scenario.
 */
export function getScenarioLabel(selection: SimulationSelection, gatewayType: GateWayType): string {
  const auth = selection.withAuthorization ? 'with auth' : 'without auth';
  const gw = gatewayType === GateWayType.KONG ? 'Kong' : 'WSO2';
  return ``;
}
