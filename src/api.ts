export type Health = { status: 'ready'; storage: 'ready'; version: string; imaging: 'not_connected'|'configured'; analysis: 'not_connected' };
export type Study = { id: string; study_date: string | null; description: string | null };
export type Preferences = { show_structure: boolean };
export async function request<T>(path: string, signal?: AbortSignal, body?: unknown, method = 'PUT'): Promise<T> {
  const response = await fetch(`/api/${path}`, { signal, cache: 'no-store', ...(body !== undefined ? { method, headers: { 'Content-Type': 'application/json', 'X-Workspace-Request': '1' }, body: JSON.stringify(body) } : {}) });
  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    throw new Error(typeof detail?.detail === 'string' ? detail.detail : `요청 실패 (${response.status})`);
  }
  return response.json() as Promise<T>;
}
