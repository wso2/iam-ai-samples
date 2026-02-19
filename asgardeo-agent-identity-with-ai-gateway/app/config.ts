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

export enum GateWayType {
  WSO2 = 'wso2',
  KONG = 'kong'
}

export interface AppConfig {
  gatewayType: GateWayType;
  orgName: string;
  clientId: string;
  targetUrl: string;
  wso2CoordinatorUrl: string;
  wso2ExpertUrl: string;
  coordinatorAgent: {
    agentId: string;
    agentSecret: string;
  };
  expertAgent: {
    agentId: string;
    agentSecret: string;
  };
}

export function getAppConfig(): AppConfig {
  return {
    gatewayType: (process.env.NEXT_PUBLIC_GATEWAY_TYPE as GateWayType) || GateWayType.KONG,
    orgName: process.env.NEXT_PUBLIC_ORG_NAME || '',
    clientId: process.env.NEXT_PUBLIC_CLIENT_ID || '',
    targetUrl: process.env.NEXT_PUBLIC_TARGET_URL || '',
    wso2CoordinatorUrl: process.env.NEXT_PUBLIC_WSO2_COORDINATOR_URL || '',
    wso2ExpertUrl: process.env.NEXT_PUBLIC_WSO2_EXPERT_URL || '',
    coordinatorAgent: {
      agentId: process.env.COORDINATOR_AGENT_ID || '',
      agentSecret: process.env.COORDINATOR_AGENT_SECRET || '',
    },
    expertAgent: {
      agentId: process.env.EXPERT_AGENT_ID || '',
      agentSecret: process.env.EXPERT_AGENT_SECRET || '',
    },
  };
}
