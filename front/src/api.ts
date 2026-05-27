export type ApiUser = {
  id: number
  username: string
  role: string
}

export type ChatArtifact = {
  id: string
  sessionId: string
  messageId?: number
  qaLogId?: number
  tenantId: string
  userId: number
  worker: string
  kind: 'image' | 'file'
  filename: string
  mimeType: string
  sizeBytes: number
  url: string
  previewUrl?: string | null
  createdAt: string
  metadata?: Record<string, unknown>
}

export type ChatMessage = {
  id?: number
  role: 'user' | 'assistant'
  content: string
  qaLogId?: number
  feedbackRating?: -1 | 1
  artifacts?: ChatArtifact[]
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
  artifacts?: ChatArtifact[]
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
  onDone: (sessionId: string, qaLogId?: number, artifacts?: ChatArtifact[]) => void,
): () => void {
  const params = new URLSearchParams({ message })
  if (sessionId) params.set('session_id', sessionId)
  const url = `/api/chat/stream?${params}`
  let aborted = false

  const token = localStorage.getItem('yd_token')
  const headers: Record<string, string> = {}
  if (token) headers['Authorization'] = `Bearer ${token}`

  fetch(url, { headers }).then(async (response) => {
    if (!response.ok) {
      const text = await response.text().catch(() => '')
      const detail = text ? ` (${text})` : ''
      onError(`SSE 请求失败: ${response.status}${detail}`)
      return
    }

    const reader = response.body?.getReader()
    if (!reader) { onError('SSE 不支持当前浏览器'); return }

    const decoder = new TextDecoder()
    let buffer = ''
    let currentEvent = ''

    while (!aborted) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.slice(7).trim()
        } else if (line.startsWith('data: ')) {
          const data = line.slice(6)
          try {
            const parsed = JSON.parse(data)
            if (currentEvent === 'done') {
              onDone(parsed.session_id || sessionId, parsed.qa_log_id, parsed.artifacts)
              aborted = true
            } else if (currentEvent === 'worker') {
              onEvent({ ...parsed, type: 'worker' })
            } else {
              onEvent(parsed as StreamEvent)
            }
          } catch { /* skip malformed */ }
        }
      }
    }
  }).catch((err) => {
    if (!aborted) onError(`SSE 连接失败: ${err.message}`)
  })

  return () => { aborted = true }
}
