export type ApiUser = {
  id: number
  username: string
  role: string
}

export type ChatMessage = {
  id?: number
  role: 'user' | 'assistant'
  content: string
  qaLogId?: number
  feedbackRating?: -1 | 1
}

export type ChatSession = {
  id: string
  title: string
  updated_at: string
}

export type StreamEvent = {
  type: string
  session_id?: string
  worker?: string
  workers?: string[]
  reasoning?: string
  content?: string
  passed?: boolean
  feedback?: string
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = localStorage.getItem('yd_token') || ''
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

export function chatStreamSSE(
  message: string,
  sessionId: string,
  onEvent: (event: StreamEvent) => void,
  onError: (error: string) => void,
  onDone: (sessionId: string) => void,
): () => void {
  const params = new URLSearchParams({ message })
  if (sessionId) params.set('session_id', sessionId)
  const url = `/api/chat/stream?${params}`
  const eventSource = new EventSource(url)

  eventSource.addEventListener('meta', (e) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* skip malformed */ }
  })

  eventSource.addEventListener('supervisor', (e) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* skip malformed */ }
  })

  eventSource.addEventListener('worker', (e) => {
    try { onEvent({ ...JSON.parse(e.data), type: 'worker' }) } catch { /* skip malformed */ }
  })

  eventSource.addEventListener('summary', (e) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* skip malformed */ }
  })

  eventSource.addEventListener('refiner', (e) => {
    try { onEvent(JSON.parse(e.data)) } catch { /* skip malformed */ }
  })

  eventSource.addEventListener('done', (e) => {
    try {
      const data = JSON.parse(e.data)
      onDone(data.session_id || sessionId)
    } catch { /* skip malformed */ }
    eventSource.close()
  })

  eventSource.onerror = () => {
    onError('SSE 连接中断')
    eventSource.close()
  }

  return () => eventSource.close()
}
