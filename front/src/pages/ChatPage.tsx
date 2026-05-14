import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { api, chatStreamSSE, type ApiUser, type ChatMessage, type ChatSession } from '../api'
import {
  addMessage,
  clearAuth,
  type RootState,
  setMessages,
  setMessageFeedback,
  setSessionId,
  setSessions,
  setUser,
} from '../store'

type ChatResponse = {
  answer: string
  session_id: string
  qa_log_id: number
  workers_used: string[]
}

export function ChatPage() {
  const dispatch = useDispatch()
  const navigate = useNavigate()
  const { sessionId, sessions, messages } = useSelector((state: RootState) => state.chat)
  const { user } = useSelector((state: RootState) => state.auth)
  const [text, setText] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [streamContent, setStreamContent] = useState('')
  const [thinkingStatus, setThinkingStatus] = useState('')
  const abortRef = useRef<(() => void) | null>(null)

  const logout = useCallback(() => {
    dispatch(clearAuth())
    navigate('/login', { replace: true })
  }, [dispatch, navigate])

  const loadMe = useCallback(async () => {
    try {
      dispatch(setUser(await api<ApiUser>('/api/me')))
    } catch {
      logout()
    }
  }, [dispatch, logout])

  const refreshSessions = useCallback(async () => {
    try {
      dispatch(setSessions(await api<ChatSession[]>('/api/sessions')))
    } catch {
      // Auth is checked by loadMe; avoid noisy session refresh errors.
    }
  }, [dispatch])

  useEffect(() => {
    loadMe()
    refreshSessions()
  }, [loadMe, refreshSessions])

  useEffect(() => {
    return () => abortRef.current?.()
  }, [])

  async function loadSession(id: string) {
    abortRef.current?.()
    dispatch(setSessionId(id))
    dispatch(setMessages(await api<ChatMessage[]>(`/api/sessions/${id}/messages`)))
  }

  function newSession() {
    abortRef.current?.()
    dispatch(setSessionId(''))
    dispatch(setMessages([]))
  }

  async function sendMessage(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault()
    const message = text.trim()
    if (!message || streaming) return
    dispatch(addMessage({ role: 'user', content: message }))
    setText('')
    setStreaming(true)
    setStreamContent('')
    setThinkingStatus('正在分析消息...')

    let currentSessionId = sessionId
    let accumulatedAnswer = ''

    abortRef.current = chatStreamSSE(
      message,
      currentSessionId,
      (event) => {
        if (event.type === 'supervisor' && event.workers) {
          setThinkingStatus(`调度 Worker: ${event.workers.join(', ')}`)
        } else if (event.type === 'worker' && event.worker) {
          setThinkingStatus(`运行中: ${event.worker}`)
        } else if (event.type === 'summary' && event.content) {
          accumulatedAnswer = event.content
          setStreamContent(accumulatedAnswer)
          setThinkingStatus('')
        } else if (event.type === 'refiner') {
          setThinkingStatus(event.passed ? '质量检查通过' : `正在优化: ${event.feedback?.slice(0, 60)}`)
        } else if (event.type === 'meta' && event.session_id) {
          currentSessionId = event.session_id
        }
      },
      (error) => {
        setStreaming(false)
        setThinkingStatus('')
        dispatch(addMessage({ role: 'assistant', content: error }))
      },
      (doneSessionId) => {
        setStreaming(false)
        setThinkingStatus('')
        dispatch(setSessionId(doneSessionId))
        if (accumulatedAnswer) {
          dispatch(addMessage({ role: 'assistant', content: accumulatedAnswer }))
        }
        setStreamContent('')
        refreshSessions()
      },
    )
  }

  function onComposerKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      sendMessage()
    }
  }

  async function sendFeedback(qaLogId: number, rating: -1 | 1) {
    try {
      await api('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ qa_log_id: qaLogId, rating }),
      })
      dispatch(setMessageFeedback({ qaLogId, rating }))
    } catch (err) {
      dispatch(addMessage({ role: 'assistant', content: err instanceof Error ? err.message : '反馈提交失败' }))
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>yd-Agent</h1>
        <div className="sub">企业知识问答</div>
        <span className="pill">{user ? `${user.username} · ${user.role}` : 'loading'}</span>
        <button className="secondary" onClick={newSession}>新会话</button>
        <button className="secondary" onClick={logout}>退出登录</button>
        <h2>历史会话</h2>
        <div className="session-list">
          {sessions.map((item) => (
            <button className="secondary" key={item.id} onClick={() => loadSession(item.id)}>
              {item.title}
            </button>
          ))}
        </div>
      </aside>
      <main className="chat-main">
        <section className="chat-list">
          {messages.map((item, index) => (
            <article className={`message ${item.role === 'user' ? 'user' : 'assistant'}`} key={index}>
              <div>{item.content}</div>
              {item.role === 'assistant' && item.qaLogId && (
                <div className="feedback-bar">
                  <button
                    className={item.feedbackRating === 1 ? 'feedback active' : 'feedback'}
                    onClick={() => sendFeedback(item.qaLogId!, 1)}
                  >
                    有帮助
                  </button>
                  <button
                    className={item.feedbackRating === -1 ? 'feedback active danger' : 'feedback'}
                    onClick={() => sendFeedback(item.qaLogId!, -1)}
                  >
                    不准确
                  </button>
                  {item.feedbackRating && <span>已反馈</span>}
                </div>
              )}
            </article>
          ))}
          {streaming && (
            <article className="message assistant">
              {thinkingStatus && <div className="thinking-status">{thinkingStatus}</div>}
              {streamContent && <div>{streamContent}</div>}
              {!streamContent && <div className="cursor-blink">▊</div>}
            </article>
          )}
        </section>
        <form className="composer" onSubmit={sendMessage}>
          <textarea
            rows={2}
            value={text}
            placeholder="询问企业制度、流程、IT 或 HR 问题"
            onChange={(event) => setText(event.target.value)}
            onKeyDown={onComposerKeyDown}
            disabled={streaming}
          />
          <button type="submit" disabled={streaming || !text.trim()}>
            {streaming ? '处理中' : '发送'}
          </button>
        </form>
      </main>
    </div>
  )
}
