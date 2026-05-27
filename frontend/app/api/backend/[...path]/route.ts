import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL = process.env.BACKEND_URL?.replace(/\/+$/, "");
const BACKEND_API_KEY = process.env.BACKEND_API_KEY;

// Headers the backend sends that the client needs to see.
const FORWARDED_RESPONSE_HEADERS = [
  "content-type",
  "content-disposition",
  "x-vercel-ai-data-stream",
  "x-request-id",
];

async function proxy(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
) {
  if (!BACKEND_URL) {
    return NextResponse.json({ detail: "Backend not configured." }, { status: 503 });
  }

  const { path } = await params;
  const search = request.nextUrl.searchParams.toString();
  const targetUrl = `${BACKEND_URL}/${path.join("/")}${search ? `?${search}` : ""}`;

  const outHeaders = new Headers();
  for (const name of ["content-type", "accept", "x-request-id"]) {
    const value = request.headers.get(name);
    if (value) outHeaders.set(name, value);
  }
  if (BACKEND_API_KEY) {
    outHeaders.set("X-API-Key", BACKEND_API_KEY);
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  try {
    const upstream = await fetch(targetUrl, {
      method: request.method,
      headers: outHeaders,
      body: hasBody ? request.body : undefined,
      signal: request.signal,
      // Required by Node.js when passing a ReadableStream as the request body.
      ...(hasBody ? { duplex: "half" } : {}),
    } as RequestInit);

    const respHeaders = new Headers();
    for (const name of FORWARDED_RESPONSE_HEADERS) {
      const value = upstream.headers.get(name);
      if (value) respHeaders.set(name, value);
    }

    return new NextResponse(upstream.body, {
      status: upstream.status,
      headers: respHeaders,
    });
  } catch (err) {
    // Client disconnected — browser navigation, tab close, or React StrictMode
    // dev remount. Return 499 silently rather than logging a server error.
    if (request.signal.aborted) {
      return new NextResponse(null, { status: 499 });
    }

    // Network-level failure: ECONNREFUSED, DNS error, backend unreachable.
    // Return a structured 503 so the client gets a readable error instead of
    // a raw 500 with a Node.js stack trace in the server logs.
    if (err instanceof TypeError) {
      return NextResponse.json(
        { detail: `Backend unreachable at ${targetUrl}. Is the server running and is BACKEND_URL correct?` },
        { status: 503 },
      );
    }

    throw err;
  }
}

export const GET = proxy;
export const POST = proxy;
export const DELETE = proxy;
