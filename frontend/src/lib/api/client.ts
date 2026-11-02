const BACKEND_URL = (process.env.NEXT_PUBLIC_BACKEND_API_URL || 'http://localhost:8000').replace(/\/+$/, '');

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = 'ApiError';
  }
}

async function getAuthHeader(): Promise<HeadersInit> {
  const { createClient } = await import('@/lib/supabase/client');
  const supabase = createClient();
  const { data: { session } } = await supabase.auth.getSession();
  if (!session?.access_token) return {};
  return { Authorization: `Bearer ${session.access_token}` };
}

export async function apiGet<T>(path: string): Promise<T> {
  const headers = await getAuthHeader();
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    headers: { 'Content-Type': 'application/json', ...headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? 'Request failed');
  }
  return res.json();
}

export async function apiPost<T>(path: string, body?: unknown, isFormData = false): Promise<T> {
  const headers = await getAuthHeader();
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    method: 'POST',
    headers: isFormData ? headers : { 'Content-Type': 'application/json', ...headers },
    body: isFormData ? (body as FormData) : JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? 'Request failed');
  }
  return res.json();
}

export async function apiDelete<T>(path: string): Promise<T> {
  const headers = await getAuthHeader();
  const res = await fetch(`${BACKEND_URL}/api/v1${path}`, {
    method: 'DELETE',
    headers: { ...headers },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(res.status, err.detail ?? 'Request failed');
  }
  return res.json();
}
