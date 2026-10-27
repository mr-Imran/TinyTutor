const API = process.env.NEXT_PUBLIC_API_URL ?? "";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...options,
      headers: {
        ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
        ...options?.headers,
      },
    });
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    const method = options?.method ?? "GET";
    const url = `${API}${path}`;
    console.error("Network request failed", { url, method, error: e });
    throw new Error(`Network error fetching ${url} (${method}): ${msg}`);
  }
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err || res.statusText);
  }
  return res.json();
}

export const api = {
  dashboard: () => request<DashboardData>("/api/dashboard"),
  analytics: () => request<AnalyticsData>("/api/dashboard/analytics"),
  notifications: () => request<ScheduledQuestion[]>("/api/dashboard/notifications"),
  markNotificationRead: (id: number) =>
    request(`/api/dashboard/notifications/${id}/read`, { method: "POST" }),

  documents: () => request<Document[]>("/api/documents"),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<UploadResult>("/api/documents/upload", { method: "POST", body: fd });
  },
  deleteDocument: (id: number) =>
    request(`/api/documents/${id}`, { method: "DELETE" }),

  chat: (message: string, topic?: string, session_id?: number) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, topic, session_id }),
    }),
  topics: () => request<{ topics: string[] }>("/api/chat/topics"),
  chatSessions: (kind?: ChatKind) =>
    request<ChatSession[]>(`/api/chat/sessions${kind ? `?kind=${kind}` : ""}`),
  chatSession: (id: number) => request<ChatSessionDetail>(`/api/chat/sessions/${id}`),
  renameChatSession: (id: number, title: string) =>
    request<ChatSession>(`/api/chat/sessions/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
  deleteChatSession: (id: number) => request(`/api/chat/sessions/${id}`, { method: "DELETE" }),

  search: (q: string, limit = 20) =>
    request<{ query: string; results: SearchHit[] }>(`/api/search?q=${encodeURIComponent(q)}&limit=${limit}`),

  importUrl: (url: string, topic?: string) =>
    request<UploadResult>("/api/documents/import-url", { method: "POST", body: JSON.stringify({ url, topic }) }),
  document: (id: number) => request<Document>(`/api/documents/${id}`),
  resummarize: (id: number) => request<Document>(`/api/documents/${id}/summarize`, { method: "POST" }),

  llmSettings: () => request<LlmSettings>("/api/settings/llm"),
  saveLlmSettings: (body: LlmSettingsUpdate) =>
    request<LlmSettings>("/api/settings/llm", { method: "PUT", body: JSON.stringify(body) }),
  llmModels: (provider: LlmProvider) =>
    request<{ provider: LlmProvider; models: string[]; error: string | null }>(
      `/api/settings/llm/models?provider=${provider}`
    ),
  llmHealth: () => request<LlmHealth>("/api/settings/llm/health"),
  embeddingSettings: () => request<EmbeddingSettings>("/api/settings/embeddings"),
  saveEmbeddingSettings: (body: { provider?: string; model?: string }) =>
    request<EmbeddingSettings>("/api/settings/embeddings", { method: "PUT", body: JSON.stringify(body) }),
  reindexEmbeddings: () =>
    request<EmbeddingSettings & { embedded: number; error: string | null }>("/api/settings/embeddings/reindex", {
      method: "POST",
    }),
  visionSettings: () => request<Record<LlmProvider, string>>("/api/settings/vision"),
  saveVisionSettings: (provider: LlmProvider, model: string) =>
    request<Record<LlmProvider, string>>("/api/settings/vision", {
      method: "PUT",
      body: JSON.stringify({ provider, model }),
    }),

  todayPlan: () => request<DailyPlan>("/api/plan/today"),
  regeneratePlan: () => request<DailyPlan>("/api/plan/today/regenerate", { method: "POST" }),
  togglePlanTask: (taskId: string) =>
    request<DailyPlan>(`/api/plan/tasks/${encodeURIComponent(taskId)}/toggle`, { method: "POST" }),

  progress: () => request<Progress>("/api/progress"),
  setDailyGoal: (daily_goal: number) =>
    request<Progress>("/api/progress/goal", { method: "PUT", body: JSON.stringify({ daily_goal }) }),
  markBadgesSeen: () => request("/api/progress/badges/seen", { method: "POST" }),

  restoreBackup: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return request<{ documents: number; flashcards: number; files: number; safety_copy: string }>(
      "/api/data/restore",
      { method: "POST", body: fd }
    );
  },
  importFlashcards: (file: File, topic: string) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("topic", topic);
    return request<{ imported: number; skipped: number; topics: string[] }>("/api/data/flashcards/import", {
      method: "POST",
      body: fd,
    });
  },
  flashcardsFromHighlights: (document_id: number, marker_ids?: number[]) =>
    request<{ created: Flashcard[]; skipped: number; used_ai: boolean }>("/api/flashcards/from-highlights", {
      method: "POST",
      body: JSON.stringify({ document_id, marker_ids }),
    }),

  flashcards: (topic?: string) =>
    request<Flashcard[]>(`/api/flashcards${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`),
  dueFlashcards: (limit = 20, topic?: string) =>
    request<Flashcard[]>(
      `/api/flashcards/due?limit=${limit}${topic ? `&topic=${encodeURIComponent(topic)}` : ""}`
    ),
  flashcardStats: () => request<FlashcardStats>("/api/flashcards/stats"),
  generateFlashcards: (body: { topic?: string; document_id?: number; count?: number }) =>
    request<{ created: Flashcard[] }>("/api/flashcards/generate", { method: "POST", body: JSON.stringify(body) }),
  createFlashcard: (body: { topic: string; front: string; back: string }) =>
    request<Flashcard[]>("/api/flashcards", { method: "POST", body: JSON.stringify(body) }),
  reviewFlashcard: (id: number, grade: number) =>
    request<Flashcard>(`/api/flashcards/${id}/review`, { method: "POST", body: JSON.stringify({ grade }) }),
  deleteFlashcard: (id: number) => request(`/api/flashcards/${id}`, { method: "DELETE" }),

  createMockExam: (body: CreateMockExamBody) =>
    request<MockExam>("/api/mock-exams", { method: "POST", body: JSON.stringify(body) }),
  mockExam: (id: number) => request<MockExam>(`/api/mock-exams/${id}`),
  mockExams: () => request<MockExamSummary[]>("/api/mock-exams"),
  submitMockExam: (id: number, answers: Record<number, string>) =>
    request<MockExam>(`/api/mock-exams/${id}/submit`, { method: "POST", body: JSON.stringify({ answers }) }),

  generateQuiz: (body: GenerateQuizBody) =>
    request<QuizQuestion>("/api/quiz/generate", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  submitQuiz: (body: SubmitQuizBody) =>
    request<{ is_correct: boolean; feedback: string }>("/api/quiz/submit", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  exam: (topics: string[], count: number, difficulty: string) =>
    request<{ questions: QuizQuestion[] }>("/api/quiz/exam", {
      method: "POST",
      body: JSON.stringify({ topics, count, difficulty }),
    }),
  quizHistory: () => request<QuizAttempt[]>("/api/quiz/history"),

  generateBroadQuestion: (topic: string, difficulty: string) =>
    request<{ question: string; topic: string; difficulty: string }>("/api/quiz/broad/generate", {
      method: "POST",
      body: JSON.stringify({ topic, difficulty }),
    }),

  broadCheck: (body: BroadCheckBody) =>
    request<BroadCheckResult>("/api/quiz/broad/check", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  aiHelp: (body: AiHelpBody) =>
    request<AiHelpResult>("/api/quiz/broad/ai-help", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  dbOverview: () => request<DbOverview>("/api/db/overview"),
  dbTable: (table: string, limit = 50, offset = 0, search = "") => {
    const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
    if (search) params.set("search", search);
    return request<DbTableResult>(`/api/db/tables/${table}?${params}`);
  },
  dbRow: (table: string, id: number) => request<Record<string, unknown>>(`/api/db/tables/${table}/${id}`),
  addContext: (body: AddContextBody) =>
    request<{ id: number; message: string }>("/api/db/context", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateChunk: (id: number, body: Partial<AddContextBody>) =>
    request(`/api/db/chunks/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteChunk: (id: number) => request(`/api/db/chunks/${id}`, { method: "DELETE" }),

  studyOverview: () => request<StudyOverview>("/api/study/overview"),
  getExamPlan: () => request<ExamPlanResponse>("/api/study/exam-plan"),
  saveExamPlan: (body: ExamPlanBody) =>
    request<ExamPlanResponse>("/api/study/exam-plan", { method: "POST", body: JSON.stringify(body) }),
  logStudySession: (minutes: number, topic?: string) =>
    request<{ targets: StudyTargets }>("/api/study/sessions", {
      method: "POST",
      body: JSON.stringify({ minutes, topic }),
    }),
  mentorChat: (message: string, topic?: string, session_id?: number) =>
    request<ChatResponse>("/api/study/mentor/chat", {
      method: "POST",
      body: JSON.stringify({ message, topic, session_id }),
    }),

  semesterDashboard: () => request<SemesterDashboard>("/api/exam-tools/semester-dashboard"),
  calculateCgpa: (courses: CgpaCourse[]) =>
    request<{ cgpa: number; total_credits: number }>("/api/exam-tools/cgpa", {
      method: "POST",
      body: JSON.stringify({ courses }),
    }),
  analyzePreviousQuestions: (topic?: string) =>
    request<{ analysis: string }>(`/api/exam-tools/previous-questions${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`, { method: "POST" }),
  analyzePpt: (topic?: string) =>
    request<{ analysis: string }>(`/api/exam-tools/ppt-analysis${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`, { method: "POST" }),
  generateCq: (topic: string, count = 5) =>
    request<{ questions: Array<string | CqQuestion> }>("/api/exam-tools/cq-generate", {
      method: "POST",
      body: JSON.stringify({ topic, count }),
    }),
  predictMidterm: (topic?: string) =>
    request<{ prediction: string }>(`/api/exam-tools/predict/midterm${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`, { method: "POST" }),
  predictFinal: (topic?: string) =>
    request<{ prediction: string }>(`/api/exam-tools/predict/final${topic ? `?topic=${encodeURIComponent(topic)}` : ""}`, { method: "POST" }),
  vivaSimulator: (topic: string, count = 5) =>
    request<{ pairs: { question: string; model_answer: string }[] }>("/api/exam-tools/viva", {
      method: "POST",
      body: JSON.stringify({ topic, count }),
    }),
  explainSelection: (selected_text: string, question?: string, language = "bn") =>
    request<{ explanation: string }>("/api/exam-tools/explain-selection", {
      method: "POST",
      body: JSON.stringify({ selected_text, question, language }),
    }),
  listPdfs: () => request<PdfDoc[]>("/api/exam-tools/pdfs"),
  listReaderDocuments: (file_type?: "pdf" | "pptx") =>
    request<ReaderDoc[]>(
      `/api/exam-tools/documents${file_type ? `?file_type=${file_type}` : ""}`
    ),
  getDocumentChunks: (document_id: number) =>
    request<ReaderChunk[]>(`/api/exam-tools/document/${document_id}/chunks`),
  getDocumentMarkers: (document_id: number) =>
    request<ReaderMarker[]>(`/api/exam-tools/document/${document_id}/markers`),
  saveMarker: (body: SaveMarkerBody) =>
    request<{ id: number; message: string }>("/api/exam-tools/document/marker", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  deleteMarker: (marker_id: number) =>
    request<{ ok: boolean }>(`/api/exam-tools/document/marker/${marker_id}`, { method: "DELETE" }),
  saveReaderDocument: (body: SaveReaderDocumentBody) =>
    request<{ document_id: number; message: string }>("/api/exam-tools/save-document", {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export function pdfFileUrl(docId: number) {
  return `${API}/api/exam-tools/pdf/${docId}/file`;
}

export function pdfPageUrl(docId: number, page?: number | null) {
  return `${pdfFileUrl(docId)}${page ? `#page=${page}` : ""}`;
}

/** Where a cited note lives: a PDF page, a moment in a YouTube video, or the web page. */
export function sourceLink(s: {
  document_id?: number | null;
  file_type?: string | null;
  page_number?: number | null;
  source_url?: string | null;
  start_seconds?: number | null;
}): string | undefined {
  if (s.file_type === "pdf" && s.document_id) return pdfPageUrl(s.document_id, s.page_number);
  if (s.file_type === "youtube" && s.source_url) {
    return s.start_seconds != null ? `${s.source_url}&t=${s.start_seconds}s` : s.source_url;
  }
  if (s.source_url) return s.source_url;
  return undefined;
}

export function formatTimestamp(seconds: number) {
  const m = Math.floor(seconds / 60);
  return `${m}:${String(seconds % 60).padStart(2, "0")}`;
}

/** Plain links: the browser downloads these straight from the backend. */
export const downloads = {
  backup: () => `${API}/api/data/backup`,
  flashcardsCsv: () => `${API}/api/data/flashcards.csv`,
  flashcardsApkg: () => `${API}/api/data/flashcards.apkg`,
  quizHistoryCsv: () => `${API}/api/data/quiz-history.csv`,
  calendar: (days: number, hour: number, minute = 0) =>
    `${API}/api/plan/calendar.ics?days=${days}&hour=${hour}&minute=${minute}`,
};

function decodeSources(header: string | null): ChatSource[] {
  if (!header) return [];
  try {
    const bytes = Uint8Array.from(atob(header), (c) => c.charCodeAt(0));
    return JSON.parse(new TextDecoder().decode(bytes));
  } catch {
    return [];
  }
}

export interface StreamResult {
  text: string;
  sessionId: number | null;
  sources: ChatSource[];
}

/** Streams a tutor/mentor reply. Session id and citation sources arrive in headers. */
export async function streamChat(
  kind: ChatKind,
  body: { message: string; topic?: string; session_id?: number | null },
  onUpdate: (fullText: string, meta: Omit<StreamResult, "text">) => void,
  signal?: AbortSignal
): Promise<StreamResult> {
  const path = kind === "mentor" ? "/api/study/mentor/stream" : "/api/chat/stream";
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, session_id: body.session_id ?? undefined }),
    signal,
  });
  if (!res.ok || !res.body) throw new Error(await res.text());
  const meta = {
    sessionId: Number(res.headers.get("X-Session-Id")) || null,
    sources: decodeSources(res.headers.get("X-Sources")),
  };
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let full = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    full += decoder.decode(value, { stream: true });
    onUpdate(full, meta);
  }
  return { text: full, ...meta };
}

export async function mentorStream(
  message: string,
  topic: string | undefined,
  onUpdate: (fullText: string) => void,
  sessionId?: number | null
): Promise<StreamResult> {
  return streamChat("mentor", { message, topic, session_id: sessionId }, (full) => onUpdate(full));
}

export interface DashboardData {
  study_streak: number;
  total_documents: number;
  total_quizzes: number;
  total_chunks: number;
  weak_topics: TopicScore[];
  strong_topics: TopicScore[];
  readiness_score: number;
  study_targets?: StudyTargets;
  user?: { display_name?: string };
  flashcards?: FlashcardStats;
}

export interface TopicScore {
  topic: string;
  correct_answers: number;
  wrong_answers: number;
  mastery_percentage: number;
}

export interface Concept {
  term: string;
  definition: string;
  related: string[];
}

export interface Document {
  id: number;
  filename: string;
  title: string;
  topic: string;
  file_type: string;
  page_count?: number;
  chunk_count: number;
  created_at: string;
  summary?: string | null;
  summary_status?: "pending" | "running" | "done" | "failed" | "empty" | null;
  concepts?: Concept[];
  source_url?: string | null;
}

export interface UploadResult {
  document_id: number;
  title: string;
  topic: string;
  file_type: string;
  page_count: number;
  chunk_count: number;
  empty: boolean;
  warnings: string[];
}

export type ChatKind = "tutor" | "mentor";

export interface ChatSource {
  n: number;
  chunk_id: number | null;
  document_id: number | null;
  title?: string | null;
  source?: string | null;
  page_number?: number | null;
  file_type?: string | null;
  source_url?: string | null;
  start_seconds?: number | null;
  preview?: string;
}

export interface ChatResponse {
  reply: string;
  sources: ChatSource[];
  session_id: number;
}

export interface ChatSession {
  id: number;
  kind: ChatKind;
  title: string;
  created_at: string;
  updated_at: string;
  message_count?: number;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  sources: ChatSource[];
  created_at: string;
}

export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[];
}

export interface SearchHit {
  id: number;
  document_id: number | null;
  title: string;
  topic: string;
  source: string;
  page_number: number | null;
  file_type: string | null;
  source_url: string | null;
  start_seconds: number | null;
  snippet: string;
  semantic_score: number | null;
}

export interface EmbeddingSettings {
  choice: string;
  choices: string[];
  defaults: Record<string, string>;
  provider: string | null;
  model: string | null;
  indexed: number;
  total: number;
}

export interface PlanTask {
  id: string;
  kind: "upload" | "flashcards" | "study" | "quiz" | "mock_exam" | "read";
  title: string;
  detail: string;
  minutes: number;
  link: string;
  done: boolean;
  topic?: string;
}

export interface DailyPlan {
  date: string;
  tasks: PlanTask[];
  total_minutes: number;
  done_count: number;
  complete: boolean;
}

export interface Badge {
  id: string;
  name: string;
  description: string;
  icon: string;
  earned_at: string | null;
  new: boolean;
}

export interface Progress {
  xp: number;
  level: number;
  level_xp: number;
  level_size: number;
  today_xp: number;
  daily_goal: number;
  week: { date: string; xp: number }[];
  current_streak: number;
  longest_streak: number;
  badges: Badge[];
  earned_count: number;
}

export type LlmProvider = "ollama" | "openai" | "anthropic" | "gemini";

export interface LlmSettings {
  provider: LlmProvider;
  model: string;
  providers: Record<LlmProvider, { model: string; default_model: string }>;
  ollama_url: string;
  openai_base_url: string;
  keys: Record<"anthropic_api_key" | "gemini_api_key" | "openai_api_key", string>;
}

export interface LlmSettingsUpdate {
  provider?: LlmProvider;
  model?: string;
  ollama_url?: string;
  openai_base_url?: string;
  openai_api_key?: string;
  anthropic_api_key?: string;
  gemini_api_key?: string;
}

export interface LlmHealth {
  ok: boolean;
  provider: LlmProvider;
  model: string;
  error: string | null;
}

export interface Flashcard {
  id: number;
  document_id: number | null;
  topic: string;
  front: string;
  back: string;
  ease: number;
  interval_days: number;
  repetitions: number;
  due_at: string;
  last_reviewed_at: string | null;
}

export interface FlashcardStats {
  total: number;
  due: number;
  learned: number;
  topics: { topic: string; total: number; due: number }[];
}

export interface CreateMockExamBody {
  topics: string[];
  count: number;
  duration_minutes: number;
  difficulty: string;
  mix: string[];
}

export interface MockExamQuestion {
  id: number;
  position: number;
  topic: string;
  question_type: "mcq" | "true_false" | "short_answer";
  question: string;
  options: string[] | null;
  correct_answer?: string;
  explanation?: string;
  user_answer?: string | null;
  is_correct?: number | null;
  feedback?: string | null;
}

export interface MockExamReport {
  correct: number;
  total: number;
  percentage: number;
  topics: { topic: string; correct: number; total: number; percentage: number }[];
  weakest_topic: string | null;
}

export interface MockExamSummary {
  id: number;
  topics: string[];
  difficulty: string;
  duration_minutes: number;
  status: "in_progress" | "submitted";
  started_at: string;
  submitted_at: string | null;
  score: number | null;
  total: number;
  late: number;
}

export interface MockExam extends MockExamSummary {
  deadline_at: string;
  server_time: string;
  report: MockExamReport | null;
  questions: MockExamQuestion[];
}

export interface QuizQuestion {
  topic: string;
  question_type: string;
  difficulty: string;
  question: string;
  options: string[] | null;
  correct_answer: string;
  explanation?: string;
}

export interface GenerateQuizBody {
  topic: string;
  question_type: string;
  difficulty: string;
}

export interface SubmitQuizBody extends QuizQuestion {
  user_answer: string;
}

export interface QuizAttempt {
  id: number;
  topic: string;
  question_type: string;
  difficulty: string;
  question: string;
  is_correct: number;
  created_at: string;
}

export interface AnalyticsData {
  topic_scores: TopicScore[];
  quiz_history: { topic: string; is_correct: number; created_at: string }[];
  activity: { date: string; count: number }[];
  weak_topics: TopicScore[];
  mastery_trend?: { date: string; overall: number | null; topics: Record<string, number> }[];
}

export interface ScheduledQuestion {
  id: number;
  topic: string;
  question: string;
  question_type: string;
  notification_type?: string;
  options_json?: string;
  correct_answer: string;
  created_at: string;
}

export interface StudyTargets {
  has_plan: boolean;
  in_exam_window?: boolean;
  exam_start?: string;
  exam_end?: string;
  expected_cgpa?: number;
  current_cgpa?: number;
  days_left?: number;
  days_until_exam_start?: number;
  total_hours_needed?: number;
  hours_logged?: number;
  hours_remaining?: number;
  hours_per_day?: number;
  weak_topics?: string[];
  topic_count?: number;
}

export interface ExamPlanBody {
  exam_start: string;
  exam_end: string;
  expected_cgpa: number;
  current_cgpa: number;
}

export interface ExamPlanResponse {
  plan: ExamPlanBody | null;
  targets: StudyTargets;
}

export interface StudyMaterial {
  id: number;
  title?: string;
  source?: string;
  preview: string;
}

export interface StudyTopic {
  topic: string;
  chunk_count: number;
  sources: string[];
  materials: StudyMaterial[];
}

export interface StudyOverview {
  documents: Document[];
  topics: StudyTopic[];
  study_targets: StudyTargets;
}

export interface SemesterDashboard {
  readiness_score: number;
  weak_topics: TopicScore[];
  strong_topics: TopicScore[];
  study_targets: StudyTargets;
  documents: Document[];
  pdf_count: number;
  ppt_count: number;
}

export interface CgpaCourse {
  credit: number;
  grade_point: number;
  name?: string;
}

export interface PdfDoc {
  id: number;
  title: string;
  filename: string;
  topic: string;
  page_count: number;
}

export interface ReaderDoc {
  id: number;
  title: string;
  filename: string;
  topic: string;
  file_type: "pdf" | "pptx";
  page_count: number;
  chunk_count: number;
}

export interface ReaderChunk {
  id: number;
  title: string;
  topic: string;
  content: string;
  source: string;
}

export interface ReaderMarker {
  id: number;
  document_id: number;
  page_number?: number;
  marker_type: "highlight" | "underline" | "note";
  color?: string;
  selected_text: string;
  note?: string;
  created_at: string;
}

export interface SaveMarkerBody {
  document_id: number;
  page_number?: number;
  marker_type: "highlight" | "underline" | "note";
  color?: string;
  selected_text: string;
  note?: string;
}

export interface SaveReaderDocumentBody {
  title: string;
  topic?: string;
  content: string;
  source?: string;
}

export interface CqQuestion {
  title: string;
  question_type: string;
  answers: string[];
}

export interface DbOverview {
  db_path: string;
  tables: { name: string; row_count: number }[];
}

export interface DbTableResult {
  table: string;
  total: number;
  limit: number;
  offset: number;
  rows: Record<string, unknown>[];
}

export interface AddContextBody {
  title: string;
  topic: string;
  content: string;
  source?: string;
}

export interface BroadCheckBody {
  question: string;
  user_answer: string;
  topic?: string;
}

export interface BroadCheckResult {
  matched: boolean;
  match_score: number;
  feedback: string;
  chunks: { title?: string; topic?: string; source?: string }[];
  is_correct: boolean | null;
  alignment?: string;
}

export interface AiHelpBody {
  question: string;
  user_answer?: string;
  topic?: string;
}

export interface AiHelpResult {
  matched: boolean;
  question: string;
  explanation: string;
  chunks: { title?: string; topic?: string; source?: string }[];
}
