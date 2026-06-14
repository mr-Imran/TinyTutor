"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useRouter } from "next/navigation";
import { CheckCircle2, XCircle, RefreshCw, Sparkles, MessageSquare } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, QuizQuestion } from "@/lib/api";

const TYPES = [
  { id: "mcq", label: "MCQ" },
  { id: "true_false", label: "True / False" },
  { id: "short_answer", label: "Short Answer" },
];
const DIFFICULTIES = ["easy", "medium", "hard"];

export default function QuizPage() {
  const router = useRouter();
  const [topics, setTopics] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [questionType, setQuestionType] = useState("mcq");
  const [difficulty, setDifficulty] = useState("medium");
  const [question, setQuestion] = useState<QuizQuestion | null>(null);
  const [answer, setAnswer] = useState("");
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [examMode, setExamMode] = useState(false);
  const [examQuestions, setExamQuestions] = useState<QuizQuestion[]>([]);
  const [examIndex, setExamIndex] = useState(0);

  const [broadQuestion, setBroadQuestion] = useState("");
  const [broadAnswer, setBroadAnswer] = useState("");
  const [broadGenerating, setBroadGenerating] = useState(false);
  const [broadFeedback, setBroadFeedback] = useState<{
    matched: boolean;
    ok?: boolean;
    text: string;
  } | null>(null);

  const generateBroad = async (selectedTopic?: string) => {
    const t = selectedTopic || topic;
    if (!t) return;
    setBroadGenerating(true);
    setBroadFeedback(null);
    setBroadAnswer("");
    try {
      const res = await api.generateBroadQuestion(t, difficulty);
      setBroadQuestion(res.question);
    } catch {
      setBroadFeedback({
        matched: false,
        text: "Could not generate question. Upload materials or check Ollama.",
      });
    } finally {
      setBroadGenerating(false);
    }
  };

  const goAiHelp = (q: string, answer: string) => {
    const p = new URLSearchParams({ q });
    if (answer.trim()) p.set("answer", answer.trim());
    if (topic) p.set("topic", topic);
    router.push(`/quiz/ai-help?${p.toString()}`);
  };

  const checkBroad = async () => {
    if (!broadQuestion.trim() || !broadAnswer.trim()) return;
    setLoading(true);
    setBroadFeedback(null);
    try {
      const res = await api.broadCheck({
        question: broadQuestion.trim(),
        user_answer: broadAnswer.trim(),
        topic: topic || undefined,
      });
      if (res.matched) {
        setBroadFeedback({
          matched: true,
          ok: res.is_correct ?? undefined,
          text: res.feedback,
        });
      } else {
        setBroadFeedback({
          matched: false,
          text: res.feedback + " Opening AI Help…",
        });
        goAiHelp(broadQuestion, broadAnswer);
      }
    } catch {
      setBroadFeedback({
        matched: false,
        text: "Check failed. Try AI Help or ensure the backend is running.",
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    api.topics().then((r) => {
      setTopics(r.topics);
      const t = r.topics[0] || "General";
      setTopic(t);
      generateBroad(t);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (topic) generateBroad(topic);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [difficulty]);

  const generate = async () => {
    if (!topic) return;
    setLoading(true);
    setFeedback(null);
    setAnswer("");
    try {
      const q = await api.generateQuiz({ topic, question_type: questionType, difficulty });
      setQuestion(q);
    } catch (e) {
      setFeedback({ ok: false, text: "Failed to generate. Check Ollama." });
    } finally {
      setLoading(false);
    }
  };

  const submit = async () => {
    if (!question || !answer.trim()) return;
    setLoading(true);
    try {
      const res = await api.submitQuiz({
        ...question,
        user_answer: answer,
      });
      setFeedback({ ok: res.is_correct, text: res.feedback });
    } finally {
      setLoading(false);
    }
  };

  const startExam = async () => {
    const t = topics.length ? topics : ["General"];
    setLoading(true);
    setExamMode(true);
    setExamIndex(0);
    setFeedback(null);
    try {
      const res = await api.exam(t, 5, difficulty);
      setExamQuestions(res.questions);
      setQuestion(res.questions[0]);
      setAnswer("");
    } finally {
      setLoading(false);
    }
  };

  const nextExam = () => {
    const next = examIndex + 1;
    if (next >= examQuestions.length) {
      setExamMode(false);
      setQuestion(null);
      setFeedback({ ok: true, text: "Exam complete! Check Analytics for your progress." });
      return;
    }
    setExamIndex(next);
    setQuestion(examQuestions[next]);
    setAnswer("");
    setFeedback(null);
  };

  return (
    <div>
      <PageHeader
        title="Quiz Center"
        description="MCQ, True/False, and Short Answer — with AI evaluation."
      />

      <div className="mb-6 flex flex-wrap gap-4">
        <Card className="flex-1 min-w-[200px]">
          <CardHeader>
            <CardTitle className="text-sm">Topic</CardTitle>
          </CardHeader>
          <CardContent>
            {topics.length === 0 ? (
              <p className="text-sm text-muted-foreground">Upload materials first.</p>
            ) : (
              <select
                className="w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm"
                value={topic}
                onChange={(e) => {
                  setTopic(e.target.value);
                  generateBroad(e.target.value);
                }}
              >
                {topics.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            )}
          </CardContent>
        </Card>

        <Card className="flex-1 min-w-[200px]">
          <CardHeader>
            <CardTitle className="text-sm">Type</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {TYPES.map((t) => (
              <button
                key={t.id}
                onClick={() => setQuestionType(t.id)}
                className={`rounded-lg px-3 py-1.5 text-xs ${
                  questionType === t.id ? "bg-primary" : "bg-white/10"
                }`}
              >
                {t.label}
              </button>
            ))}
          </CardContent>
        </Card>

        <Card className="flex-1 min-w-[200px]">
          <CardHeader>
            <CardTitle className="text-sm">Difficulty</CardTitle>
          </CardHeader>
          <CardContent className="flex gap-2">
            {DIFFICULTIES.map((d) => (
              <button
                key={d}
                onClick={() => setDifficulty(d)}
                className={`rounded-lg px-3 py-1.5 text-xs capitalize ${
                  difficulty === d ? "bg-primary" : "bg-white/10"
                }`}
              >
                {d}
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="mb-6 flex flex-wrap gap-3">
        <Button onClick={generate} disabled={loading || !topic}>
          <RefreshCw className={`mr-2 h-4 w-4 ${loading ? "animate-spin" : ""}`} />
          Generate Question
        </Button>
        <Button variant="outline" onClick={startExam} disabled={loading}>
          Simulate Exam (5 questions)
        </Button>
      </div>

      {/* Broad question — write your own answer */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        className="mb-8"
      >
        <Card className="border-cyan-500/25">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <MessageSquare className="h-5 w-5 text-cyan-400" />
              Broad Question
            </CardTitle>
            <p className="text-sm text-muted-foreground">
              A question is generated automatically from your materials. Write your answer below — we
              check it against knowledge chunks. No match? AI Help opens with a simple explanation.
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <label className="text-xs text-muted-foreground">Question (auto-generated)</label>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => generateBroad()}
                  disabled={broadGenerating || !topic}
                >
                  <RefreshCw className={`mr-1 h-3.5 w-3.5 ${broadGenerating ? "animate-spin" : ""}`} />
                  New question
                </Button>
              </div>
              {broadGenerating && !broadQuestion ? (
                <div className="min-h-[80px] animate-pulse rounded-lg bg-white/10" />
              ) : (
                <div className="min-h-[80px] rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-4 text-sm leading-relaxed">
                  {broadQuestion || (
                    <span className="text-muted-foreground">
                      {topic ? "Generating question…" : "Select a topic or upload materials first."}
                    </span>
                  )}
                </div>
              )}
            </div>
            <div>
              <label className="mb-1 block text-xs text-muted-foreground">Your answer</label>
              <textarea
                className="min-h-[120px] w-full rounded-lg border border-white/15 bg-white/5 p-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                placeholder="Write your full answer here…"
                value={broadAnswer}
                onChange={(e) => setBroadAnswer(e.target.value)}
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={checkBroad}
                disabled={loading || !broadQuestion.trim() || !broadAnswer.trim()}
              >
                Check against my materials
              </Button>
              <Button
                variant="accent"
                onClick={() => goAiHelp(broadQuestion, broadAnswer)}
                disabled={!broadQuestion.trim()}
              >
                <Sparkles className="mr-2 h-4 w-4" />
                AI HELP
              </Button>
            </div>

            {broadFeedback && (
              <motion.div
                initial={{ opacity: 0, scale: 0.98 }}
                animate={{ opacity: 1, scale: 1 }}
                className={`rounded-lg p-4 text-sm ${
                  broadFeedback.matched
                    ? broadFeedback.ok
                      ? "bg-emerald-500/10 text-emerald-200"
                      : "bg-amber-500/10 text-amber-200"
                    : "bg-violet-500/10 text-violet-200"
                }`}
              >
                <div className="flex items-start gap-2">
                  {broadFeedback.matched && broadFeedback.ok ? (
                    <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
                  ) : (
                    <Sparkles className="mt-0.5 h-4 w-4 shrink-0" />
                  )}
                  <p>{broadFeedback.text}</p>
                </div>
                {!broadFeedback.matched && (
                  <Button
                    className="mt-3"
                    size="sm"
                    variant="outline"
                    onClick={() => goAiHelp(broadQuestion, broadAnswer)}
                  >
                    Open AI Help page
                  </Button>
                )}
              </motion.div>
            )}
          </CardContent>
        </Card>
      </motion.div>

      <AnimatePresence mode="wait">
        {question && (
          <motion.div
            key={question.question}
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
          >
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  {examMode && `Question ${examIndex + 1} / ${examQuestions.length} · `}
                  {question.topic} · {question.difficulty}
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <p className="text-lg">{question.question}</p>

                {question.options ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    {question.options.map((opt) => (
                      <button
                        key={opt}
                        onClick={() => setAnswer(opt)}
                        className={`rounded-lg border p-3 text-left text-sm transition-colors ${
                          answer === opt
                            ? "border-primary bg-primary/20"
                            : "border-white/10 hover:bg-white/5"
                        }`}
                      >
                        {opt}
                      </button>
                    ))}
                  </div>
                ) : (
                  <Input
                    placeholder="Your answer…"
                    value={answer}
                    onChange={(e) => setAnswer(e.target.value)}
                  />
                )}

                {!feedback ? (
                  <Button onClick={submit} disabled={loading || !answer}>
                    Submit Answer
                  </Button>
                ) : (
                  <motion.div
                    initial={{ scale: 0.95 }}
                    animate={{ scale: 1 }}
                    className={`flex items-start gap-3 rounded-lg p-4 ${
                      feedback.ok ? "bg-emerald-500/10" : "bg-red-500/10"
                    }`}
                  >
                    {feedback.ok ? (
                      <CheckCircle2 className="h-5 w-5 text-emerald-400" />
                    ) : (
                      <XCircle className="h-5 w-5 text-red-400" />
                    )}
                    <p className="text-sm">{feedback.text}</p>
                  </motion.div>
                )}

                {feedback && examMode && (
                  <Button onClick={nextExam}>Next Question</Button>
                )}
                {feedback && !examMode && (
                  <Button variant="outline" onClick={generate}>
                    Next Question
                  </Button>
                )}
              </CardContent>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
