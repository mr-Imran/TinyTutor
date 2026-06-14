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

  chat: (message: string, topic?: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message, topic }),
    }),
  topics: () => request<{ topics: string[] }>("/api/chat/topics"),

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
  mentorChat: (message: string, topic?: string) =>
    request<ChatResponse>("/api/study/mentor/chat", {
      method: "POST",
      body: JSON.stringify({ message, topic }),
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

export async function mentorStream(
  message: string,
  topic: string | undefined,
  onUpdate: (fullText: string) => void
): Promise<string> {
  const res = await fetch(`${API}/api/study/mentor/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, topic }),
  });
  if (!res.ok) throw new Error(await res.text());
  const reader = res.body?.getReader();
  if (!reader) throw new Error("No stream");
  const decoder = new TextDecoder();
  let full = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    full += decoder.decode(value, { stream: true });
    onUpdate(full);
  }
  return full;
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
}

export interface TopicScore {
  topic: string;
  correct_answers: number;
  wrong_answers: number;
  mastery_percentage: number;
}

export interface Document {
  id: number;
  filename: string;
  title: string;
  topic: string;
  file_type: string;
  chunk_count: number;
  created_at: string;
}

export interface UploadResult {
  document_id: number;
  title: string;
  topic: string;
  chunk_count: number;
}

export interface ChatResponse {
  reply: string;
  sources: string[];
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
