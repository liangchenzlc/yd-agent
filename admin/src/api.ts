export type ApiUser = {
  id: number
  username: string
  role: string
  enabled?: boolean
  created_at?: string
}

export type DocumentRecord = {
  id: string
  source: string
  chunks: number
  entities: number
  status?: string
  relationships?: number
  updated_at?: string
}

export type QaLogRecord = {
  id: number
  session_id: string
  user_id: number
  question: string
  answer: string
  workers: string
  dispatch_reasoning: string
  worker_results: string
  confidence: number | null
  created_at: string
}

export type HardCaseRecord = QaLogRecord & {
  rating?: number | null
  comment?: string | null
}

export type KnowledgeGapRecord = {
  question: string
  count: number
  reasons: {
    not_found: number
    low_confidence: number
    negative_feedback: number
  }
  latest_at: string
  suggestion: string
  examples: Array<{
    id: number
    question: string
    answer: string
    comment?: string | null
  }>
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('yd_admin_token') || ''
  const response = await fetch(path, {
    ...options,
    headers: {
      ...(options.headers || {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  })
  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json') ? await response.json() : await response.text()
  if (!response.ok) {
    const message = typeof data === 'string' ? data : data.detail || '请求失败'
    throw new Error(message)
  }
  return data as T
}
