import { configureStore, createSlice, type PayloadAction } from '@reduxjs/toolkit'
import type { ApiUser, DocumentRecord, HardCaseRecord, KnowledgeGapRecord, QaLogRecord } from './api'

type AuthState = {
  token: string
  user: ApiUser | null
}

type DocumentState = {
  items: DocumentRecord[]
}

type QaLogState = {
  items: QaLogRecord[]
}

type HardCaseState = {
  items: HardCaseRecord[]
}

type KnowledgeGapState = {
  items: KnowledgeGapRecord[]
}

type UserState = {
  items: ApiUser[]
}

const authSlice = createSlice({
  name: 'auth',
  initialState: {
    token: localStorage.getItem('yd_admin_token') || '',
    user: null,
  } as AuthState,
  reducers: {
    setAuth(state, action: PayloadAction<{ token: string; user: ApiUser }>) {
      state.token = action.payload.token
      state.user = action.payload.user
      localStorage.setItem('yd_admin_token', action.payload.token)
    },
    setUser(state, action: PayloadAction<ApiUser>) {
      state.user = action.payload
    },
    clearAuth(state) {
      state.token = ''
      state.user = null
      localStorage.removeItem('yd_admin_token')
    },
  },
})

const documentsSlice = createSlice({
  name: 'documents',
  initialState: {
    items: [],
  } as DocumentState,
  reducers: {
    setDocuments(state, action: PayloadAction<DocumentRecord[]>) {
      state.items = action.payload
    },
  },
})

const qaLogsSlice = createSlice({
  name: 'qaLogs',
  initialState: {
    items: [],
  } as QaLogState,
  reducers: {
    setQaLogs(state, action: PayloadAction<QaLogRecord[]>) {
      state.items = action.payload
    },
  },
})

const hardCasesSlice = createSlice({
  name: 'hardCases',
  initialState: {
    items: [],
  } as HardCaseState,
  reducers: {
    setHardCases(state, action: PayloadAction<HardCaseRecord[]>) {
      state.items = action.payload
    },
  },
})

const knowledgeGapsSlice = createSlice({
  name: 'knowledgeGaps',
  initialState: {
    items: [],
  } as KnowledgeGapState,
  reducers: {
    setKnowledgeGaps(state, action: PayloadAction<KnowledgeGapRecord[]>) {
      state.items = action.payload
    },
  },
})

const usersSlice = createSlice({
  name: 'users',
  initialState: {
    items: [],
  } as UserState,
  reducers: {
    setUsers(state, action: PayloadAction<ApiUser[]>) {
      state.items = action.payload
    },
  },
})

export const { setAuth, setUser, clearAuth } = authSlice.actions
export const { setDocuments } = documentsSlice.actions
export const { setQaLogs } = qaLogsSlice.actions
export const { setHardCases } = hardCasesSlice.actions
export const { setKnowledgeGaps } = knowledgeGapsSlice.actions
export const { setUsers } = usersSlice.actions

export const store = configureStore({
  reducer: {
    auth: authSlice.reducer,
    documents: documentsSlice.reducer,
    qaLogs: qaLogsSlice.reducer,
    hardCases: hardCasesSlice.reducer,
    knowledgeGaps: knowledgeGapsSlice.reducer,
    users: usersSlice.reducer,
  },
})

export type RootState = ReturnType<typeof store.getState>
