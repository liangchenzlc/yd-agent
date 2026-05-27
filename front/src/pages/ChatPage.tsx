import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useRef, useState } from 'react'
import { useDispatch, useSelector } from 'react-redux'
import { useNavigate } from 'react-router-dom'
import { api, chatStreamSSE, type ApiUser, type ChatArtifact, type ChatMessage, type ChatSession } from '../api'
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

function ThumbUpIcon({ filled }: { filled?: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 10v12" /><path d="M15 5.88 14 10h5.83a2 2 0 0 1 1.92 2.56l-2.33 8A2 2 0 0 1 17.5 22H4a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2h2.76a2 2 0 0 0 1.79-1.11L12 2h0a3.13 3.13 0 0 1 3 3.88Z" />
    </svg>
  )
}

function ThumbDownIcon({ filled }: { filled?: boolean }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17 14V2" /><path d="M9 18.12 10 14H4.17a2 2 0 0 1-1.92-2.56l2.33-8A2 2 0 0 1 6.5 2H20a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-2.76a2 2 0 0 0-1.79 1.11L12 22h0a3.13 3.13 0 0 1-3-3.88Z" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /><polyline points="7 10 12 15 17 10" /><line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`
}

function getFileIcon(_mimeType: string): string {
  return '📄'
}

function ArtifactRenderer({ artifacts }: { artifacts: ChatArtifact[] }) {
  const [lightboxUrl, setLightboxUrl] = useState<string | null>(null)
  const [failedIds, setFailedIds] = useState<Set<string>>(new Set())

  if (!artifacts || artifacts.length === 0) return null

  const handleImageError = (id: string) => {
    setFailedIds((prev) => new Set(prev).add(id))
  }

  return (
    <div className="artifacts">
      {artifacts.map((art) => {
        const isImage = art.kind === 'image'
        const isFailed = failedIds.has(art.id)

        if (isImage) {
          return (
            <div key={art.id} className="artifact-image-wrap">
              {isFailed ? (
                <div className="artifact-error">附件生成失败或文件不可用</div>
              ) : (
                <>
                  <img
                    className="artifact-image"
                    src={art.previewUrl || art.url}
                    alt={art.filename}
                    onClick={() => setLightboxUrl(art.previewUrl || art.url)}
                    onError={() => handleImageError(art.id)}
                    loading="lazy"
                  />
                  <div className="artifact-image-actions">
                    <button
                      className="artifact-action-btn"
                      onClick={() => window.open(art.previewUrl || art.url, '_blank')}
                      type="button"
                      title="放大预览"
                    >
                      放大
                    </button>
                    <a
                      className="artifact-action-btn"
                      href={art.url}
                      download={art.filename}
                      title="下载图片"
                    >
                      <DownloadIcon /> 下载
                    </a>
                  </div>
                </>
              )}
            </div>
          )
        }

        return (
          <div key={art.id} className="artifact-card">
            {isFailed ? (
              <div className="artifact-error">附件生成失败或文件不可用</div>
            ) : (
              <>
                <div className="artifact-card-icon">{getFileIcon(art.mimeType)}</div>
                <div className="artifact-card-info">
                  <div className="artifact-card-name">{art.filename}</div>
                  <div className="artifact-card-meta">
                    {formatFileSize(art.sizeBytes)} · {art.worker} · {art.mimeType}
                  </div>
                </div>
                <a
                  className="artifact-card-download"
                  href={art.url}
                  download={art.filename}
                  title="下载文件"
                >
                  <DownloadIcon /> 下载
                </a>
              </>
            )}
          </div>
        )
      })}
      {lightboxUrl && (
        <div className="lightbox-overlay" onClick={() => setLightboxUrl(null)}>
          <img className="lightbox-image" src={lightboxUrl} alt="预览" />
        </div>
      )}
    </div>
  )
}

const EXAMPLE_PROMPTS = [
  '公司的请假制度是怎样的？',
  '帮我写一份项目总结文档',
  '用 Python 计算本季度销售额',
  '介绍一下公司的人事政策',
]

function EmptyState({ onPromptClick }: { onPromptClick: (text: string) => void }) {
  return (
    <div className="empty-state">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4" /><path d="M12 8h.01" />
      </svg>
      <h3>企业知识问答系统</h3>
      <p>可以询问企业制度、流程规范、IT 支持或 HR 相关问题</p>
      <div className="example-prompts">
        {EXAMPLE_PROMPTS.map((prompt) => (
          <button
            key={prompt}
            className="prompt-chip"
            onClick={() => onPromptClick(prompt)}
            type="button"
          >
            {prompt}
          </button>
        ))}
      </div>
    </div>
  )
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
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const abortRef = useRef<(() => void) | null>(null)
  const chatListRef = useRef<HTMLElement>(null)

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (chatListRef.current) {
        chatListRef.current.scrollTop = chatListRef.current.scrollHeight
      }
    })
  }, [])

  useEffect(() => { scrollToBottom() }, [messages, streamContent, scrollToBottom])

  const onChatScroll = useCallback(() => {
    if (!chatListRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = chatListRef.current
    setShowScrollBtn(scrollHeight - scrollTop - clientHeight > 200)
  }, [])

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
    } catch { /* Auth checked by loadMe */ }
  }, [dispatch])

  async function deleteSession(id: string) {
    if (!window.confirm('确定删除此会话？')) return
    try {
      await api(`/api/sessions/${id}`, { method: 'DELETE' })
      if (id === sessionId) {
        dispatch(setSessionId(''))
        dispatch(setMessages([]))
      }
      await refreshSessions()
    } catch { /* ignore */ }
  }

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
      (doneSessionId, qaLogId, artifacts) => {
        setStreaming(false)
        setThinkingStatus('')
        dispatch(setSessionId(doneSessionId))
        if (accumulatedAnswer) {
          dispatch(addMessage({ role: 'assistant', content: accumulatedAnswer, qaLogId, artifacts }))
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
      // Silently handle feedback errors
    }
  }

  function handlePromptClick(prompt: string) {
    setText(prompt)
    const textarea = document.querySelector('.composer textarea') as HTMLTextAreaElement | null
    textarea?.focus()
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <h1>yd-Agent</h1>
        <div className="sub">企业知识问答</div>
        <span className="pill">{user ? `${user.username} · ${user.role}` : 'loading'}</span>
        <button className="secondary" onClick={newSession}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: 'middle', marginRight: 6 }}>
            <path d="M5 12h14" /><path d="M12 5v14" />
          </svg>
          新会话
        </button>
        <h2>历史会话</h2>
        <div className="session-list">
          {sessions.map((item) => (
            <div className="session-item" key={item.id}>
              <button className="secondary" onClick={() => loadSession(item.id)}>
                <span className="session-title">{item.title}</span>
                <span className="session-delete" onClick={(e) => { e.stopPropagation(); deleteSession(item.id) }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" /><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </span>
              </button>
            </div>
          ))}
          {sessions.length === 0 && <span className="muted" style={{ fontSize: 13 }}>暂无历史会话</span>}
        </div>
        <button className="secondary" onClick={logout} style={{ marginTop: 'auto' }}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ verticalAlign: 'middle', marginRight: 6 }}>
            <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><polyline points="16 17 21 12 16 7" /><line x1="21" y1="12" x2="9" y2="12" />
          </svg>
          退出登录
        </button>
      </aside>
      <main className="chat-main">
        <section className="chat-list" ref={chatListRef} onScroll={onChatScroll}>
          {messages.length === 0 && !streaming && <EmptyState onPromptClick={handlePromptClick} />}
          {messages.map((item, index) => (
            <article className={`message ${item.role === 'user' ? 'user' : ''}`} key={item.id ?? index}>
              <div className="stream-reveal">{item.content}</div>
              {item.artifacts && item.artifacts.length > 0 && (
                <ArtifactRenderer artifacts={item.artifacts} />
              )}
              {item.role === 'assistant' && item.qaLogId && (
                <div className="feedback-bar">
                  <button
                    className={item.feedbackRating === 1 ? 'feedback active' : 'feedback'}
                    onClick={() => sendFeedback(item.qaLogId!, 1)}
                    aria-label="有帮助"
                  >
                    <ThumbUpIcon filled={item.feedbackRating === 1} />
                    有帮助
                  </button>
                  <button
                    className={item.feedbackRating === -1 ? 'feedback active danger' : 'feedback'}
                    onClick={() => sendFeedback(item.qaLogId!, -1)}
                    aria-label="不准确"
                  >
                    <ThumbDownIcon filled={item.feedbackRating === -1} />
                    不准确
                  </button>
                  {item.feedbackRating && <span>已反馈</span>}
                </div>
              )}
            </article>
          ))}
          {showScrollBtn && (
            <button
              className="scroll-to-bottom"
              onClick={scrollToBottom}
              aria-label="滚动到最新消息"
              type="button"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <polyline points="6 9 12 15 18 9" />
              </svg>
            </button>
          )}
          {streaming && (
            <article className="message assistant">
              {thinkingStatus && (
                <div className="thinking-status">
                  {thinkingStatus}
                  <span className="thinking-dots"><span /><span /><span /></span>
                </div>
              )}
              {streamContent && <div className="stream-reveal">{streamContent}</div>}
              {!streamContent && !thinkingStatus && <div className="cursor-blink">▊</div>}
            </article>
          )}
        </section>
        <form className="composer" onSubmit={sendMessage}>
          <textarea
            rows={2}
            value={text}
            placeholder="询问企业制度、流程、IT 或 HR 问题..."
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
