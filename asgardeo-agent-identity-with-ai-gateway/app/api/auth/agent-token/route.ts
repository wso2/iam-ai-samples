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

import { NextRequest, NextResponse } from 'next/server';

export async function POST(request: NextRequest) {
  try {
    const { orgName, clientId, agentId, agentSecret } = await request.json();

    if (!orgName || !clientId || !agentId || !agentSecret) {
      return NextResponse.json(
        { error: 'Missing required fields: orgName, clientId, agentId, agentSecret' },
        { status: 400 }
      );
    }

    // Validate orgName format
    const orgNamePattern = /^[a-z0-9-]+$/i;
    if (!orgNamePattern.test(orgName) || orgName.length > 50) {
      return NextResponse.json(
        { error: 'Invalid orgName. Ensure it matches the pattern /^[a-z0-9-]+$/i and is at most 50 characters long.' },
        { status: 400 }
      );
    }

    const baseUrl = `https://api.asgardeo.io/t/${orgName}`;

    // Get token using Resource Owner Password Credentials grant
    // Agent credentials are used as username/password
    // Application Client ID is used as the OAuth client
    const tokenResponse = await fetch(`${baseUrl}/oauth2/token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'password',
        client_id: clientId,
        username: agentId,
        password: agentSecret,
        scope: 'openid Support-Coordinator Technical-Specialist'
      }),
      signal: AbortSignal.timeout(15_000),
    });

    if (!tokenResponse.ok) {
      const errorData = await tokenResponse.text();
      console.error('Agent token request failed:', errorData);
      return NextResponse.json(
        { error: 'Failed to authenticate agent. Check agent credentials and client ID.', details: errorData },
        { status: tokenResponse.status }
      );
    }

    const tokens = await tokenResponse.json();

    return NextResponse.json({
      access_token: tokens.access_token,
      token_type: tokens.token_type,
      expires_in: tokens.expires_in,
      scope: tokens.scope
    });
  } catch (error) {
    console.error('Error getting agent token:', error);
    return NextResponse.json(
      { error: 'Failed to get agent token', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    );
  }
}
