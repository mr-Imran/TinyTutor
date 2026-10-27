"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, Clock, Timer, XCircle } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { api, MockExam, MockExamSummary } from "@/lib/api";

const TYPE_LABELS: Record<string, string> = {
  mcq: "Multiple choice",
  true_false: "True / False",
  short_answer: "Short answer",
};

const answersKey = (examId: number) => `mock-exam-answers-${examId}`;

function loadAnswers(examId: number): Record<number, string> {
  try {
    return JSON.parse(localStorage.getItem(answersKey(examId)) || "{}");
  } catch {
    return {};
  }
}

function saveAnswers(examId: number, answers: Record<number, string>) {
  try {
    localStorage.setItem(answersKey(examId), JSON.stringify(answers));
  } catch {
    /* storage unavailable — answers stay in memory */
  }
}

function utc(ts: string) {
  return new Date(ts.endsWith("Z") ? ts : `${ts}Z`).getTime();
}

function formatClock(ms: number) {
  const total = Math.max(0, Math.ceil(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function MockExamPage() {
  const [topics, setTopics] = useState<string[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [count, setCount] = useState(10);
  const [minutes, setMinutes] = useState(15);
  const [difficulty, setDifficulty] = useState("medium");
  const [mix, setMix] = useState<string[]>(["mcq", "true_false", "short_answer"]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [exam, setExam] = useState<MockExam | null>(null);
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const [remaining, setRemaining] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [history, setHistory] = useState<MockExamSummary[]>([]);
  const clockOffset = useRef(0);
  const submittedRef = useRef(false);

  const loadHistory = useCallback(() => {
    api.mockExams().then(setHistory).catch(() => {});
  }, []);

  const openExam = useCallback((e: MockExam) => {
    clockOffset.current = utc(e.server_time) - Date.now();
    submittedRef.current = e.status === "submitted";
    setExam(e);
    setAnswers(e.status === "submitted" ? {} : loadAnswers(e.id));
  }, []);

  useEffect(() => {
    api.topics().then((r) => setTopics(r.topics)).catch(() => {});
    api
      .mockExams()
      .then((list) => {
        setHistory(list);
        const open = list.find((e) => e.status === "in_progress");
        if (open) api.mockExam(open.id).then(openExam).catch(() => {});
      })
      .catch(() => {});
  }, [openExam]);

  const submit = useCallback(async () => {
    if (!exam || submittedRef.current) return;
    submittedRef.current = true;
    setSubmitting(true);
    try {
      const done = await api.submitMockExam(exam.id, answers);
      try {
        localStorage.removeItem(answersKey(exam.id));
      } catch {
        /* ignore */
      }
      setExam(done);
      loadHistory();
    } catch (e) {
      submittedRef.current = false;
      setError(e instanceof Error ? e.message : "Submit failed");
    } finally {
      setSubmitting(false);
    }
  }, [exam, answers, loadHistory]);

  useEffect(() => {
    if (!exam || exam.status !== "in_progress") return;
    const tick = () => {
      const left = utc(exam.deadline_at) - (Date.now() + clockOffset.current);
      setRemaining(left);
      if (left <= 0) submit();
    };
    tick();
    const id = setInterval(tick, 500);
    return () => clearInterval(id);
  }, [exam, submit]);

  const start = async () => {
    setCreating(true);
    setError("");
    try {
      const e = await api.createMockExam({
        topics: selected.length ? selected : topics,
        count,
        duration_minutes: minutes,
        difficulty,
        mix,
      });
      openExam(e);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create the exam");
    } finally {
      setCreating(false);
    }
  };

  const answer = (qid: number, value: string) => {
    if (!exam) return;
    const next = { ...answers, [qid]: value };
    setAnswers(next);
    saveAnswers(exam.id, next);
  };

  const toggle = (list: string[], value: string, set: (v: string[]) => void) =>
    set(list.includes(value) ? list.filter((x) => x !== value) : [...list, value]);

  // ---------------------------------------------------------------- running
  if (exam && exam.status === "in_progress") {
    const answered = exam.questions.filter((q) => (answers[q.id] ?? "").trim()).length;
    const lowTime = remaining < 60_000;
    return (
      <div>
        <div className="glass sticky top-0 z-30 -mx-2 mb-6 flex items-center justify-between rounded-xl px-4 py-3">
          <div>
            <p className="font-semibold">Mock exam · {exam.topics.join(", ")}</p>
            <p className="text-xs text-muted-foreground">
              {answered}/{exam.total} answered · no feedback until you submit
            </p>
          </div>
          <div className="flex items-center gap-4">
            <span className={`flex items-center gap-2 font-mono text-2xl ${lowTime ? "text-red-400" : ""}`}>
              <Clock className="h-5 w-5" /> {formatClock(remaining)}
            </span>
            <Button onClick={submit} disabled={submitting}>
              {submitting ? "Grading…" : "Submit"}
            </Button>
          </div>
        </div>
        <Progress value={(answered / exam.total) * 100} className="mb-6" />
        <div className="space-y-4">
          {exam.questions.map((q, i) => (
            <Card key={q.id}>
              <CardContent className="space-y-3 p-5">
                <p className="text-xs text-muted-foreground">
                  Question {i + 1} · {TYPE_LABELS[q.question_type]} · {q.topic}
                </p>
                <Markdown text={q.question} className="font-medium" />
                {q.options ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {q.options.map((opt) => (
                      <button
                        key={opt}
                        onClick={() => answer(q.id, opt)}
                        className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                          answers[q.id] === opt ? "border-primary bg-primary/20" : "border-white/10 bg-white/5 hover:bg-white/10"
                        }`}
                      >
                        <Markdown text={opt} inline />
                      </button>
                    ))}
                  </div>
                ) : (
                  <Input placeholder="Your answer" value={answers[q.id] ?? ""} onChange={(e) => answer(q.id, e.target.value)} />
                )}
              </CardContent>
            </Card>
          ))}
        </div>
        {error && <p className="mt-4 text-sm text-red-400">{error}</p>}
      </div>
    );
  }

  // ---------------------------------------------------------------- report
  if (exam && exam.report) {
    const r = exam.report;
    return (
      <div>
        <PageHeader title="Exam report" description={`${exam.topics.join(", ")} · ${exam.difficulty}${exam.late ? " · submitted late" : ""}`} />
        <div className="mb-6 grid gap-4 md:grid-cols-3">
          <Card className="md:col-span-1">
            <CardContent className="p-6 text-center">
              <p className="text-sm text-muted-foreground">Score</p>
              <p className="mt-2 text-5xl font-bold">{r.percentage}%</p>
              <p className="mt-1 text-sm text-muted-foreground">
                {r.correct} of {r.total} correct
              </p>
            </CardContent>
          </Card>
          <Card className="md:col-span-2">
            <CardHeader>
              <CardTitle className="text-base">By topic</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {r.topics.map((t) => (
                <div key={t.topic}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span>{t.topic}</span>
                    <span className="text-muted-foreground">
                      {t.correct}/{t.total} · {t.percentage}%
                    </span>
                  </div>
                  <Progress value={t.percentage} />
                </div>
              ))}
              {r.weakest_topic && r.topics.length > 1 && (
                <p className="text-xs text-muted-foreground">Review {r.weakest_topic} next — it was your weakest area.</p>
              )}
            </CardContent>
          </Card>
        </div>

        <div className="space-y-3">
          {exam.questions.map((q, i) => (
            <Card key={q.id}>
              <CardContent className="space-y-2 p-5 text-sm">
                <p className="flex items-center gap-2 font-medium">
                  {q.is_correct ? <CheckCircle2 className="h-4 w-4 text-emerald-400" /> : <XCircle className="h-4 w-4 text-red-400" />}
                  {i + 1}. <Markdown text={q.question} inline />
                </p>
                <p className="text-muted-foreground">
                  Your answer: <span className="text-foreground">{q.user_answer || "—"}</span>
                </p>
                {!q.is_correct && (
                  <p className="text-muted-foreground">
                    Correct answer: <span className="text-emerald-300">{q.correct_answer}</span>
                  </p>
                )}
                {(q.explanation || q.feedback) && (
                  <Markdown text={q.explanation || q.feedback || ""} className="text-xs text-muted-foreground" />
                )}
              </CardContent>
            </Card>
          ))}
        </div>
        <Button className="mt-6" onClick={() => setExam(null)}>
          Take another exam
        </Button>
      </div>
    );
  }

  // ---------------------------------------------------------------- setup
  return (
    <div>
      <PageHeader title="Mock Exam" description="A timed practice exam with mixed questions. Answers are revealed only after you submit." />
      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Timer className="h-5 w-5 text-violet-400" /> Set up your exam
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-5 text-sm">
            <div>
              <p className="mb-2 text-xs text-muted-foreground">Topics (none selected = all)</p>
              {topics.length === 0 ? (
                <p className="text-muted-foreground">Upload study material first.</p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {topics.map((t) => (
                    <button
                      key={t}
                      onClick={() => toggle(selected, t, setSelected)}
                      className={`rounded-full px-3 py-1 text-xs ${selected.includes(t) ? "bg-primary text-white" : "bg-white/10"}`}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <label className="space-y-1">
                <span className="text-xs text-muted-foreground">Questions</span>
                <Input type="number" min={1} max={40} value={count} onChange={(e) => setCount(Number(e.target.value) || 1)} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-muted-foreground">Minutes</span>
                <Input type="number" min={1} max={240} value={minutes} onChange={(e) => setMinutes(Number(e.target.value) || 1)} />
              </label>
              <label className="space-y-1">
                <span className="text-xs text-muted-foreground">Difficulty</span>
                <select
                  value={difficulty}
                  onChange={(e) => setDifficulty(e.target.value)}
                  className="h-10 w-full rounded-lg border border-white/15 bg-white/5 px-3 text-sm"
                >
                  {["easy", "medium", "hard"].map((d) => (
                    <option key={d} value={d} className="bg-slate-900">
                      {d}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div>
              <p className="mb-2 text-xs text-muted-foreground">Question types</p>
              <div className="flex flex-wrap gap-2">
                {Object.entries(TYPE_LABELS).map(([id, label]) => (
                  <button
                    key={id}
                    onClick={() => toggle(mix, id, setMix)}
                    className={`rounded-full px-3 py-1 text-xs ${mix.includes(id) ? "bg-primary text-white" : "bg-white/10"}`}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <Button onClick={start} disabled={creating || topics.length === 0 || mix.length === 0}>
              {creating ? `Writing ${count} questions…` : "Start exam"}
            </Button>
            {creating && <p className="text-xs text-muted-foreground">The timer starts once all questions are ready.</p>}
            {error && <p className="text-sm text-red-400">{error}</p>}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Past exams</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {history.length === 0 && <p className="text-muted-foreground">No exams yet.</p>}
            {history.map((h) => (
              <motion.button
                key={h.id}
                whileHover={{ x: 3 }}
                onClick={() => api.mockExam(h.id).then(openExam)}
                className="flex w-full items-center justify-between rounded-lg bg-white/5 px-3 py-2 text-left hover:bg-white/10"
              >
                <span className="min-w-0">
                  <span className="block truncate">{h.topics.join(", ")}</span>
                  <span className="text-xs text-muted-foreground">{new Date(utc(h.started_at)).toLocaleDateString()}</span>
                </span>
                <span className="shrink-0 text-xs">
                  {h.status === "submitted" ? `${h.score}/${h.total}` : "In progress"}
                </span>
              </motion.button>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
