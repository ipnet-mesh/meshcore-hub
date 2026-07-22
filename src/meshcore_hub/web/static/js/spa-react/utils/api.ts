import type { AppConfig } from "@/types/config";

export function isAbortError(e: unknown): boolean {
  return e instanceof DOMException && e.name === "AbortError";
}

function checkAuthResponse(response: Response): void {
  const config: AppConfig | undefined = window.__APP_CONFIG__;
  if (config?.oidc_enabled && response.status === 401) {
    const next = encodeURIComponent(
      window.location.pathname + window.location.search,
    );
    window.location.href = `/auth/login?next=${next}`;
  }
}

export async function apiGet<T = unknown>(
  path: string,
  params: Record<string, unknown> = {},
  { signal }: { signal?: AbortSignal } = {},
): Promise<T> {
  const url = new URL(path, window.location.origin);
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined && v !== "") {
      if (Array.isArray(v)) {
        v.forEach((item) => url.searchParams.append(k, String(item)));
      } else {
        url.searchParams.set(k, String(v));
      }
    }
  }
  const response = await fetch(url, { signal });
  if (!response.ok) {
    throw new Error(`API error: ${response.status} ${response.statusText}`);
  }
  return response.json();
}

export async function apiPost<T = unknown>(
  path: string,
  body: unknown,
): Promise<T | null> {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  checkAuthResponse(response);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error: ${response.status} - ${text}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function apiPut<T = unknown>(
  path: string,
  body: unknown,
): Promise<T | null> {
  const response = await fetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  checkAuthResponse(response);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error: ${response.status} - ${text}`);
  }
  if (response.status === 204) return null;
  return response.json();
}

export async function apiDelete(path: string): Promise<void> {
  const response = await fetch(path, { method: "DELETE" });
  checkAuthResponse(response);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error: ${response.status} - ${text}`);
  }
}

export async function apiPostForm<T = unknown>(
  path: string,
  data: Record<string, string>,
): Promise<T | null> {
  const body = new URLSearchParams(data);
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: body.toString(),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API error: ${response.status} - ${text}`);
  }
  if (response.status === 204) return null;
  return response.json();
}
