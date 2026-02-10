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
