"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { BookMarked, Bot, Calendar, Clock, Send, User } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { HumanText } from "@/components/HumanText";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ExamPlanBody, StudyOverview, StudyTopic, mentorStream } from "@/lib/api";

type ChatMsg = { role: "user" | "mentor"; text: string };

function toLocalInput(iso: string) {
  if (!iso) return "";
  try {
    const d = new Date(iso);
    const pad = (n: number) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  } catch {
    return "";
  }
}

export default function StudyPage() {
  const [overview, setOverview] = useState<StudyOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTopic, setSelectedTopic] = useState<string | null>(null);
  const [expandedTopic, setExpandedTopic] = useState<string | null>(null);

  const [examStart, setExamStart] = useState("");
  const [examEnd, setExamEnd] = useState("");
  const [expectedCgpa, setExpectedCgpa] = useState("8.0");
  const [currentCgpa, setCurrentCgpa] = useState("6.5");
  const [savingPlan, setSavingPlan] = useState(false);

  const [messages, setMessages] = useState<ChatMsg[]>([
    {
      role: "mentor",
      text: "Hi! I am your AI mentor. Ask me what to study, how to plan your day, or anything from your uploaded materials.",
    },
  ]);
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [logFxOpen, setLogFxOpen] = useState(false);
  const [logFxProgress, setLogFxProgress] = useState(0);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    Promise.all([api.studyOverview(), api.getExamPlan()])
      .then(([ov, planRes]) => {
        setOverview(ov);
        if (planRes.plan) {
          setExamStart(toLocalInput(planRes.plan.exam_start));
          setExamEnd(toLocalInput(planRes.plan.exam_end));
          setExpectedCgpa(String(planRes.plan.expected_cgpa));
          setCurrentCgpa(String(planRes.plan.current_cgpa));
        }
        if (ov.topics[0]) setSelectedTopic(ov.topics[0].topic);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const savePlan = async () => {
    if (!examStart || !examEnd) return;
    setSavingPlan(true);
    try {
      const body: ExamPlanBody = {
        exam_start: new Date(examStart).toISOString(),
        exam_end: new Date(examEnd).toISOString(),
        expected_cgpa: parseFloat(expectedCgpa),
        current_cgpa: parseFloat(currentCgpa),
      };
      await api.saveExamPlan(body);
      load();
    } finally {
      setSavingPlan(false);
    }
  };

  const log30Min = async () => {
    setLogFxOpen(true);
    setLogFxProgress(0);
    const steps = [20, 45, 70, 100];
    const timer = setInterval(() => {
      setLogFxProgress((prev) => {
        const next = steps.find((s) => s > prev) ?? 100;
        return next;
      });
    }, 280);

    try {
      await Promise.all([
        api.logStudySession(30, selectedTopic || undefined),
        new Promise((resolve) => setTimeout(resolve, 1400)),
      ]);
      load();
    } finally {
      clearInterval(timer);
      setLogFxProgress(100);
      setTimeout(() => setLogFxOpen(false), 350);
    }
  };

  const sendMentor = async () => {
    if (!chatInput.trim() || chatLoading) return;
    const userMsg = chatInput.trim();
    setChatInput("");
    setMessages((m) => [...m, { role: "user", text: userMsg }]);
    setChatLoading(true);
    setMessages((m) => [...m, { role: "mentor", text: "" }]);

    try {
      await mentorStream(userMsg, selectedTopic || undefined, (full) => {
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "mentor", text: full };
          return copy;
        });
      });
    } catch {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          role: "mentor",
          text: "Sorry, I could not connect. Please check that the backend and Ollama are running.",
        };
        return copy;
      });
    } finally {
      setChatLoading(false);
    }
  };

  const targets = overview?.study_targets;

  if (loading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-12 w-64" />
        <Skeleton className="h-40" />
        <Skeleton className="h-96" />
      </div>
    );
  }

  return (
    <div>
      <AnimatePresence>
        {logFxOpen && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 backdrop-blur-md"
          >
            <motion.div
              initial={{ scale: 0.92, y: 20 }}
              animate={{ scale: 1, y: 0 }}
              exit={{ scale: 0.96, y: 8, opacity: 0 }}
              className="mx-4 w-full max-w-md rounded-2xl border border-cyan-400/30 bg-slate-900/80 p-8 text-center shadow-2xl"
            >
              <motion.div
                animate={{ rotate: 360 }}
                transition={{ duration: 1.4, repeat: Number.POSITIVE_INFINITY, ease: "linear" }}
                className="mx-auto mb-4 h-16 w-16 rounded-full border-4 border-cyan-400/20 border-t-cyan-300"
              />
              <h2 className="text-2xl font-bold text-white">Study Time Logged</h2>
              <p className="mt-2 text-sm text-slate-300">Adding 30 minutes to your study hours...</p>
              <div className="mt-6 h-2 overflow-hidden rounded-full bg-white/10">
                <motion.div
                  className="h-full bg-gradient-to-r from-cyan-400 to-violet-500"
                  animate={{ width: `${logFxProgress}%` }}
                  transition={{ duration: 0.2 }}
                />
              </div>
              <p className="mt-2 text-xs text-cyan-200">{logFxProgress}%</p>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <PageHeader
        title="What to Study"
        description="All your topics and original material. Set exam dates, track study hours, and chat with your AI mentor."
      />

      <div className="mb-8 grid gap-6 lg:grid-cols-2">
        <Card className="border-violet-500/25">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Calendar className="h-5 w-5 text-violet-400" />
              Expected exam time
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Exam period starts</label>
                <Input type="datetime-local" value={examStart} onChange={(e) => setExamStart(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Exam period ends</label>
                <Input type="datetime-local" value={examEnd} onChange={(e) => setExamEnd(e.target.value)} />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Expected CGPA</label>
                <Input type="number" step="0.1" min="0" max="10" value={expectedCgpa} onChange={(e) => setExpectedCgpa(e.target.value)} />
              </div>
              <div>
                <label className="mb-1 block text-xs text-muted-foreground">Current CGPA</label>
                <Input type="number" step="0.1" min="0" max="10" value={currentCgpa} onChange={(e) => setCurrentCgpa(e.target.value)} />
              </div>
            </div>
            <Button onClick={savePlan} disabled={savingPlan}>
              Save exam plan
            </Button>
            {targets?.has_plan && (
              <HumanText
                className="text-muted-foreground"
                text={
                  targets.in_exam_window
                    ? `You are in your exam study window. Aim for about ${targets.hours_per_day} hours of study today to reach a ${targets.expected_cgpa} CGPA. You have logged ${targets.hours_logged} hours so far and about ${targets.hours_remaining} hours left to plan.`
                    : targets.days_until_exam_start
                      ? `Your exam window starts in ${targets.days_until_exam_start} days. Total study goal is about ${targets.total_hours_needed} hours (${targets.hours_per_day} hours per day once studying starts).`
                      : `Exam window ended. You logged ${targets.hours_logged} hours toward your goal of ${targets.total_hours_needed} hours.`
                }
              />
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock className="h-5 w-5 text-cyan-400" />
              Study hours
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {targets?.has_plan ? (
              <>
                <div className="grid grid-cols-2 gap-4 text-center">
                  <div className="rounded-lg bg-white/5 p-3">
                    <p className="text-2xl font-bold">{targets.hours_logged}h</p>
                    <p className="text-xs text-muted-foreground">Logged</p>
                  </div>
                  <div className="rounded-lg bg-white/5 p-3">
                    <p className="text-2xl font-bold">{targets.hours_per_day}h</p>
                    <p className="text-xs text-muted-foreground">Suggested per day</p>
                  </div>
                </div>
                <Button variant="outline" className="w-full" onClick={log30Min}>
                  Log 30 minutes of study
                </Button>
                <p className="text-xs text-muted-foreground">
                  During your exam window you get study reminders every 30 minutes on the dashboard.
                </p>
              </>
            ) : (
              <p className="text-sm text-muted-foreground">Save your exam dates above to calculate study hours.</p>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1fr_380px]">
        <div>
          <h2 className="mb-4 flex items-center gap-2 text-lg font-semibold">
            <BookMarked className="h-5 w-5 text-violet-400" />
            Topics and original material
          </h2>
          {overview?.topics.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                Upload PDFs or PPTX files first, or add context in Local DB.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-3">
              {overview?.topics.map((t: StudyTopic) => (
                <TopicCard
                  key={t.topic}
                  topic={t}
                  expanded={expandedTopic === t.topic}
                  selected={selectedTopic === t.topic}
                  onToggle={() => setExpandedTopic(expandedTopic === t.topic ? null : t.topic)}
                  onSelect={() => setSelectedTopic(t.topic)}
                />
              ))}
            </div>
          )}
        </div>

        <Card className="flex h-[520px] flex-col border-cyan-500/20 xl:sticky xl:top-4 xl:h-[calc(100vh-8rem)]">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Bot className="h-5 w-5 text-cyan-400" />
              AI Mentor
              {selectedTopic && (
                <span className="ml-auto text-xs font-normal text-muted-foreground">{selectedTopic}</span>
              )}
            </CardTitle>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col overflow-hidden p-0">
            <div className="flex-1 space-y-3 overflow-y-auto px-4 pb-2">
              {messages.map((msg, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 6 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={`flex gap-2 ${msg.role === "user" ? "justify-end" : ""}`}
                >
                  {msg.role === "mentor" && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-500/20">
                      <Bot className="h-4 w-4 text-violet-400" />
                    </div>
                  )}
                  <div
                    className={`max-w-[90%] rounded-xl px-3 py-2 ${
                      msg.role === "user" ? "bg-primary/30" : "bg-white/5"
                    }`}
                  >
                    <HumanText text={msg.text || (chatLoading && i === messages.length - 1 ? "…" : "")} />
                  </div>
                  {msg.role === "user" && (
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-500/20">
                      <User className="h-4 w-4 text-cyan-400" />
                    </div>
                  )}
                </motion.div>
              ))}
              <div ref={chatEndRef} />
            </div>
            <div className="flex gap-2 border-t border-white/10 p-4">
              <Input
                placeholder="Ask your mentor anything…"
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendMentor()}
                disabled={chatLoading}
              />
              <Button size="icon" onClick={sendMentor} disabled={chatLoading}>
                <Send className="h-4 w-4" />
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function TopicCard({
  topic,
  expanded,
  selected,
  onToggle,
  onSelect,
}: {
  topic: StudyTopic;
  expanded: boolean;
  selected: boolean;
  onToggle: () => void;
  onSelect: () => void;
}) {
  return (
    <Card className={selected ? "border-primary/40" : ""}>
      <CardHeader className="cursor-pointer py-4" onClick={onToggle}>
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{topic.topic}</CardTitle>
          <span className="text-xs text-muted-foreground">{topic.chunk_count} parts</span>
        </div>
        <p className="text-xs text-muted-foreground">
          Sources: {topic.sources.join(", ") || "—"}
        </p>
      </CardHeader>
      {expanded && (
        <CardContent className="space-y-3 border-t border-white/10 pt-0">
          {topic.materials.map((m) => (
            <div key={m.id} className="rounded-lg bg-black/20 p-3">
              <p className="text-xs font-medium text-violet-300">{m.title || m.source}</p>
              <HumanText text={m.preview} className="mt-2 text-muted-foreground" />
            </div>
          ))}
          <Button size="sm" variant={selected ? "default" : "outline"} onClick={onSelect}>
            {selected ? "Mentor focused on this topic" : "Ask mentor about this topic"}
          </Button>
        </CardContent>
      )}
    </Card>
  );
}
