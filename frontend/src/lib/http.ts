/** Shared HTTP helpers (previously in loop/api.ts). Empty VITE_API_BASE = same origin (Vite proxy in dev, the backend in the single-port demo). */
export const API_BASE = import.meta.env.VITE_API_BASE ?? '';

let pilotStep = false;

/** Requests started inside `start` are the demo control's scripted steps: the backend answers them with the ready-made
    texts even in Claude mode, so Seuraava moves on at once (the header is read when the request starts). */
export function asPilotStep<T>(start: () => Promise<T>): Promise<T> {
  pilotStep = true;
  try {
    return start();
  } finally {
    pilotStep = false;
  }
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  const headers: Record<string, string> = {};
  if (init?.body) headers['Content-Type'] = 'application/json';
  if (pilotStep) headers['X-Demo-Pilot'] = '1';
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch {
    throw new Error('Could not connect to the server.');
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(typeof data.detail === 'string' ? data.detail : 'The request failed.');
  }
  return data as T;
}

export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

export const put = <T>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) });
