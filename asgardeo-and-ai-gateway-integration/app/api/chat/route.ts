import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  try {
    // Get the request body and headers from the client
    const body = await request.json();
    const model = request.headers.get("x-agent-type") || "Support-Coordinator";
    const targetUrl = request.headers.get("x-target-url") || "https://ai-gateway-url.com/chat";
    const accessToken = request.headers.get("authorization");

    console.log("Proxy request to:", targetUrl);
    console.log("Model:", model);
    console.log("Has Access Token:", !!accessToken);
    console.log("Body:", body);

    // Build headers for AI Gateway
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      "x-agent-type": model,
    };

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

    console.log("Response status:", response.status);

    if (!response.ok) {
      const errorText = await response.text();
      console.error("Error response:", errorText);
      return NextResponse.json(
        { error: `HTTP ${response.status}: ${errorText || response.statusText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    console.log("Response data:", data);

    return NextResponse.json(data);
  } catch (error) {
    console.error("Proxy error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Unknown error occurred" },
      { status: 500 }
    );
  }
}
