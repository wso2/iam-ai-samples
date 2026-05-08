import { NextRequest, NextResponse } from 'next/server';

const WINDOW_MS = 60_000;       // 1-minute sliding window
const MAX_REQUESTS = 20;        // requests allowed per IP per window
const MAX_TRACKED_IPS = 10_000; // cap memory usage

// Module-level map — shared across requests within the same process/isolate.
// On serverless platforms with multiple instances each instance has its own map,
// so the effective limit is per-instance. For a true global limit use Redis.
const ipTimestamps = new Map<string, number[]>();
let lastCleanup = Date.now();

function getClientIp(request: NextRequest): string {
  return (
    request.headers.get('x-forwarded-for')?.split(',')[0].trim() ??
    request.headers.get('x-real-ip') ??
    '127.0.0.1'
  );
}

function checkRateLimit(ip: string): { limited: boolean; remaining: number; retryAfter: number } {
  const now = Date.now();
  const windowStart = now - WINDOW_MS;

  // Purge stale entries once per window to prevent unbounded memory growth
  if (now - lastCleanup > WINDOW_MS) {
    for (const [key, timestamps] of ipTimestamps) {
      if (timestamps[timestamps.length - 1] <= windowStart) {
        ipTimestamps.delete(key);
      }
    }
    lastCleanup = now;
  }

  // Fail open when the map is full — better to let an unknown IP through than
  // to block legitimate users because the server is very busy
  if (!ipTimestamps.has(ip) && ipTimestamps.size >= MAX_TRACKED_IPS) {
    return { limited: false, remaining: 1, retryAfter: 0 };
  }

  const recent = (ipTimestamps.get(ip) ?? []).filter((t) => t > windowStart);
  const remaining = MAX_REQUESTS - recent.length;

  if (remaining <= 0) {
    ipTimestamps.set(ip, recent);
    const retryAfter = Math.ceil((recent[0] + WINDOW_MS - now) / 1_000);
    return { limited: true, remaining: 0, retryAfter };
  }

  recent.push(now);
  ipTimestamps.set(ip, recent);
  return { limited: false, remaining: remaining - 1, retryAfter: 0 };
}

export function proxy(request: NextRequest) {
  const ip = getClientIp(request);
  const { limited, remaining, retryAfter } = checkRateLimit(ip);

  if (limited) {
    return new NextResponse(
      JSON.stringify({
        type: 'result',
        success: false,
        error: `Rate limit exceeded. Try again in ${retryAfter} second${retryAfter === 1 ? '' : 's'}.`,
      }),
      {
        status: 429,
        headers: {
          'Content-Type': 'application/json',
          'Retry-After': String(retryAfter),
          'X-RateLimit-Limit': String(MAX_REQUESTS),
          'X-RateLimit-Remaining': '0',
          'X-RateLimit-Reset': String(Math.ceil((Date.now() + retryAfter * 1_000) / 1_000)),
        },
      }
    );
  }

  const response = NextResponse.next();
  response.headers.set('X-RateLimit-Limit', String(MAX_REQUESTS));
  response.headers.set('X-RateLimit-Remaining', String(remaining));
  return response;
}

export const config = {
  matcher: '/api/:path*',
};
