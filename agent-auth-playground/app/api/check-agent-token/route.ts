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
import { NextRequest, NextResponse } from 'next/server';
import { authenticateAgent } from '@/lib/agentAuth';

export async function POST(req: NextRequest) {
  try {
    const { baseUrl, clientId, agentId, agentSecret, scope, redirectUri } = await req.json();

    if (!baseUrl || !clientId || !agentId || !agentSecret || !redirectUri) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 });
    }

    const token = await authenticateAgent({
      baseUrl,
      clientId,
      redirectUri,
      agentId,
      agentSecret,
      scope: scope || 'openid',
    });

    return NextResponse.json({ token });
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Failed to fetch agent token';
    console.log(message)
    return NextResponse.json({ error: message }, { status: 400 });
  }
}
