const BACKEND_BASE = process.env.NEXT_PUBLIC_BACKEND_BASE ?? "https://trace-x-api.onrender.com/api/v1";
export const API_BASE = process.env.NODE_ENV === "production" ? BACKEND_BASE : "/api/v1";

export async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const body = await response.text();
    throw new Error(body || `Request failed with status ${response.status}`);
  }

  return response.json() as Promise<T>;
}
