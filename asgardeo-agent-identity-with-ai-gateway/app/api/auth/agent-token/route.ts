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

import { NextRequest, NextResponse } from "next/server";
import { getAppConfig, GateWayType } from "@/app/config";

export async function POST(request: NextRequest) {
  try {
    const config = getAppConfig();
    const body = await request.json();
    const { orgName, clientId, callingAgent } = body;

    // Pick credentials from env based on which agent is calling
    const credentials = callingAgent === 'Support-Coordinator'
      ? config.coordinatorAgent
      : config.expertAgent;

    if (!credentials.agentId || !credentials.agentSecret) {
      return NextResponse.json(
        { error: `Missing agent credentials for ${callingAgent}. Check your .env.local file.` },
        { status: 400 }
      );
    }

    // Exchange agent credentials for an access token via Asgardeo
    const tokenUrl = `https://api.asgardeo.io/t/${orgName}/oauth2/token`;

    const tokenResponse = await fetch(tokenUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({
        grant_type: 'password',
        client_id: clientId,
        username: credentials.agentId,
        password: credentials.agentSecret,
        scope: "openid Technical-Specialist Support-Coordinator",
      }),
    });

    if (!tokenResponse.ok) {
      const errorText = await tokenResponse.text();
      console.error('Agent token error:', errorText);
      return NextResponse.json(
        { error: `Agent token failed (${tokenResponse.status}): ${errorText}` },
        { status: tokenResponse.status }
      );
    }

    const data = await tokenResponse.json();
    return NextResponse.json(data);
  } catch (error) {
    console.error('Agent token error:', error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Unknown error occurred' },
      { status: 500 }
    );
  }
}
