import type { NextRequest } from "next/server";

const BACKEND_BASE = "http://127.0.0.1:8000/api/v1";

async function proxy(request: NextRequest) {
  const path = request.nextUrl.pathname.replace(/^\/api\/v1/, "");
  const targetUrl = `${BACKEND_BASE}${path}${request.nextUrl.search}`;
  const method = request.method.toUpperCase();
  const headers = new Headers(request.headers);
  headers.delete("host");

  const init: RequestInit = {
    method,
    headers,
  };

  if (method !== "GET" && method !== "HEAD") {
    init.body = await request.text();
  }

  const response = await fetch(targetUrl, init);
  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("transfer-encoding");

  return new Response(await response.arrayBuffer(), {
    status: response.status,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest) {
  return proxy(request);
}

export async function POST(request: NextRequest) {
  return proxy(request);
}

export async function PUT(request: NextRequest) {
  return proxy(request);
}

export async function PATCH(request: NextRequest) {
  return proxy(request);
}

export async function DELETE(request: NextRequest) {
  return proxy(request);
}

export async function OPTIONS(request: NextRequest) {
  return proxy(request);
}
