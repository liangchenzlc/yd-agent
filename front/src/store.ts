import { configureStore, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { ApiUser, ChatMessage, ChatSession } from './api'

type AuthState = {
  token: string
  user: ApiUser | null
}

type ChatState = {
  sessionId: string
  sessions: ChatSession[]
  messages: ChatMessage[]
}

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    token: localStorage.getItem('yd_token') || '',
    user: null,
  } as AuthState,
  reducers: {
    setAuth(state, action: PayloadAction<{ token: string; user: ApiUser }>) {
      state.token = action.payload.token
      state.user = action.payload.user
      localStorage.setItem('yd_token', action.payload.token)
    },
    setUser(state, action: PayloadAction<ApiUser>) {
      state.user = action.payload
    },
    clearAuth(state) {
      state.token = ''
      state.user = null
      localStorage.removeItem('yd_token')
      localStorage.removeItem('yd_session')
    },
  },
})

const chatSlice = createSlice({
  name: 'chat',
  initialState: {
    sessionId: localStorage.getItem('yd_session') || '',
    sessions: [],
    messages: [],
  } as ChatState,
  reducers: {
    setSessionId(state, action: PayloadAction<string>) {
      state.sessionId = action.payload
      if (action.payload) {
        localStorage.setItem('yd_session', action.payload)
      } else {
        localStorage.removeItem('yd_session')
      }
    },
    setSessions(state, action: PayloadAction<ChatSession[]>) {
      state.sessions = action.payload
    },
    setMessages(state, action: PayloadAction<ChatMessage[]>) {
      state.messages = action.payload
    },
    addMessage(state, action: PayloadAction<ChatMessage>) {
      state.messages.push(action.payload)
    },
    setMessageFeedback(state, action: PayloadAction<{ qaLogId: number; rating: -1 | 1 }>) {
      const target = state.messages.find((message) => message.qaLogId === action.payload.qaLogId)
      if (target) {
        target.feedbackRating = action.payload.rating
      }
    },
  },
})

export const { setAuth, setUser, clearAuth } = authSlice.actions
export const { setSessionId, setSessions, setMessages, addMessage, setMessageFeedback } = chatSlice.actions

export const store = configureStore({
  reducer: {
    auth: authSlice.reducer,
    chat: chatSlice.reducer,
  },
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
