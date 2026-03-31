const BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const resp = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  });
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    throw new Error(err.detail || resp.statusText);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}

export interface AgentSummary {
  id: string;
  name: string;
  display_name: string;
  emoji: string;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface DocumentVersion {
  id: number;
  doc_type: string;
  content: string;
  version: number;
  message: string;
  created_by: string;
  created_at: string;
}

export interface AgentDetail extends AgentSummary {
  config: Record<string, unknown>;
  documents: Record<string, DocumentVersion | null>;
}

export interface AgentCreate {
  name: string;
  display_name: string;
  emoji?: string;
  config?: Record<string, unknown>;
  enabled?: boolean;
  soul?: string;
  identity?: string;
  user_doc?: string;
}

export const api = {
  listAgents: () => request<AgentSummary[]>('/agents'),
  createAgent: (data: AgentCreate) =>
    request<AgentSummary>('/agents', { method: 'POST', body: JSON.stringify(data) }),
  getAgent: (id: string) => request<AgentDetail>(`/agents/${id}`),
  updateAgent: (id: string, data: Partial<AgentCreate>) =>
    request<AgentSummary>(`/agents/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteAgent: (id: string) =>
    request<void>(`/agents/${id}`, { method: 'DELETE' }),
  getDocument: (agentId: string, docType: string) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}`),
  getDocumentHistory: (agentId: string, docType: string) =>
    request<DocumentVersion[]>(`/agents/${agentId}/documents/${docType}/history`),
  getDocumentVersion: (agentId: string, docType: string, version: number) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}/versions/${version}`),
  updateDocument: (agentId: string, docType: string, content: string, message?: string) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}`, {
      method: 'PUT',
      body: JSON.stringify({ content, message: message || '' }),
    }),
  rollbackDocument: (agentId: string, docType: string, version: number) =>
    request<DocumentVersion>(`/agents/${agentId}/documents/${docType}/rollback`, {
      method: 'POST',
      body: JSON.stringify({ version }),
    }),
};
