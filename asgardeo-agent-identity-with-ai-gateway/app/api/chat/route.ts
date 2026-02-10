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

import { GateWayType } from "@/app/components/ConfigurationModal";
import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    // Get the request body and headers from the client
    const body = await request.json();
    const gatewayType = request.headers.get("x-gateway-type") || GateWayType.KONG; 
    const model = request.headers.get("x-agent-type") || "Support-Coordinator";
    const targetUrl = request.headers.get("x-target-url") || "https://ai-gateway-url.com/chat";
    const accessToken = request.headers.get("authorization");

    // Build headers for AI Gateway
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };

    // Kong uses header-based routing; WSO2 uses separate URLs so no agent-type header needed
    if (gatewayType === GateWayType.KONG) {
      headers["x-agent-type"] = model;
    }

    // Add authorization header if provided
    if (accessToken) {
      headers["Authorization"] = accessToken;
    }

    // Make the request to AI Gateway from the server side (no CORS issues)
    const response = await fetch(targetUrl, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Error response:", errorText);
      return NextResponse.json(
        { error: `HTTP ${response.status}: ${errorText || response.statusText}` },
        { status: response.status }
      );
    }

    const data = await response.json();

    return NextResponse.json(data);
  } catch (error) {
    console.error("Proxy error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error occurred" },
      { status: 500 }
    );
  }
}

