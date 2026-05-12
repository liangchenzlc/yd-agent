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
