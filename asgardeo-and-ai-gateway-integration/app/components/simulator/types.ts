import { AppConfig } from '../ConfigurationModal';

export type SimulationCase = 'correct-agent' | 'wrong-agent' | 'no-auth';

export interface SimulationResult {
  caseType: SimulationCase;
  agentType: string;
  authUsed: string;
  tokenReceived: string | null;
  response: any;
  statusCode: number;
  timestamp: Date;
}

export interface AgentSimulatorProps {
  config: AppConfig;
  onOpenConfig: () => void;
}
