import { AppConfig, GatewayType } from '../ConfigurationModal';

export type AgentType = 'Support-Coordinator' | 'Technical-Specialist';

export interface SimulationSelection {
  callingAgent: AgentType;
  targetRoute: AgentType;
  withAuthorization: boolean;
}

export interface SimulationResult {
  selection: SimulationSelection;
  gatewayType: GatewayType;
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
  gatewayType: GatewayType
): {
  label: string;
  color: 'green' | 'yellow' | 'red';
} {
  if (!selection.withAuthorization) {
    return { label: 'Expected: Unauthorized (401)', color: 'red' };
  }
  if (gatewayType === 'wso2') {
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
export function getScenarioLabel(selection: SimulationSelection, gatewayType: GatewayType): string {
  const auth = selection.withAuthorization ? 'with auth' : 'without auth';
  const gw = gatewayType === 'kong' ? 'Kong' : 'WSO2';
  return ``;
}
