"use client";

import { useEffect, useState } from "react";
import { Camera, GraduationCap, Lightbulb, Mic, Plus, Square, Trash2, Wand2 } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, EssayResult, GradedAnswer, RubricCriterion, sourceLink, TeachBackResult } from "@/lib/api";
import { useSpeechRecognition } from "@/lib/speech";

const area = "w-full rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm";

function Bar({ value, max = 100 }: { value: number; max?: number }) {
  const pct = max ? (value / max) * 100 : 0;
  return (
    <div className="h-1.5 rounded-full bg-white/10">
      <div
        className={`h-1.5 rounded-full ${pct >= 80 ? "bg-emerald-400" : pct >= 50 ? "bg-amber-400" : "bg-red-400"}`}
        style={{ width: `${Math.max(2, pct)}%` }}
      />
    </div>
  );
}

function TopicInput({ value, onChange, topics }: { value: string; onChange: (v: string) => void; topics: string[] }) {
  return (
    <>
      <Input list="grader-topics" value={value} onChange={(e) => onChange(e.target.value)} placeholder="Topic (optional)" />
      <datalist id="grader-topics">
        {topics.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
    </>
  );
}

/** Dictation: each spoken phrase is appended to the text. */
function useDictation(append: (text: string) => void) {
  return useSpeechRecognition((text) => append(text));
}

function EssayTab({ topics }: { topics: string[] }) {
  const [topic, setTopic] = useState("");
  const [question, setQuestion] = useState("");
  const [rubric, setRubric] = useState<RubricCriterion[]>([]);
  const [answer, setAnswer] = useState("");
  const [photo, setPhoto] = useState<File | null>(null);
  const [result, setResult] = useState<EssayResult | null>(null);
  const [busy, setBusy] = useState<"" | "rubric" | "grade">("");
  const [error, setError] = useState("");

  const makeRubric = async () => {
    setBusy("rubric");
    setError("");
    try {
      setRubric((await api.makeRubric(question, topic || undefined)).criteria);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not make a rubric");
    } finally {
      setBusy("");
    }
  };

  const grade = async () => {
    setBusy("grade");
    setError("");
    setResult(null);
    try {
      const r = photo
        ? await api.gradeEssayPhoto(photo, question, rubric, topic || undefined)
        : await api.gradeEssay({ question, answer, rubric, topic: topic || undefined });
      setResult(r);
      if (!rubric.length) setRubric(r.rubric);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not grade the answer");
    } finally {
      setBusy("");
    }
  };

  const setCriterion = (i: number, patch: Partial<RubricCriterion>) =>
    setRubric((all) => all.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardContent className="space-y-3 p-5 text-sm">
          <TopicInput value={topic} onChange={setTopic} topics={topics} />
          <textarea rows={3} className={area} placeholder="Exam question" value={question} onChange={(e) => setQuestion(e.target.value)} />

          <div className="space-y-2 rounded-lg border border-white/10 p-3">
            <div className="flex items-center justify-between">
              <p className="text-xs font-medium">Rubric</p>
              <Button variant="ghost" size="sm" onClick={makeRubric} disabled={!question.trim() || !!busy}>
                <Wand2 className="h-3.5 w-3.5" /> {busy === "rubric" ? "Writing…" : rubric.length ? "Rewrite with AI" : "Make with AI"}
              </Button>
            </div>
            {rubric.length === 0 && (
              <p className="text-xs text-muted-foreground">Leave empty and the AI writes one from your notes when grading.</p>
            )}
            {rubric.map((c, i) => (
              <div key={i} className="flex items-start gap-2">
                <div className="flex-1 space-y-1">
                  <Input className="h-8 text-xs" value={c.name} onChange={(e) => setCriterion(i, { name: e.target.value })} placeholder="Criterion" />
                  <Input
                    className="h-8 text-xs"
                    value={c.description}
                    onChange={(e) => setCriterion(i, { description: e.target.value })}
                    placeholder="What earns full marks"
                  />
                </div>
                <Input
                  type="number"
                  min={1}
                  max={10}
                  className="h-8 w-16 text-xs"
                  value={c.points}
                  onChange={(e) => setCriterion(i, { points: Math.max(1, Math.min(10, Number(e.target.value) || 1)) })}
                  aria-label="Points"
                />
                <button aria-label="Remove criterion" className="mt-2" onClick={() => setRubric((all) => all.filter((_, j) => j !== i))}>
                  <Trash2 className="h-3.5 w-3.5 text-red-400" />
                </button>
              </div>
            ))}
            <Button variant="outline" size="sm" onClick={() => setRubric((r) => [...r, { name: "", description: "", points: 2 }])}>
              <Plus className="h-3.5 w-3.5" /> Add criterion
            </Button>
          </div>

          {photo ? (
            <div className="flex items-center justify-between rounded-lg bg-white/5 p-3 text-xs">
              <span className="flex items-center gap-2">
                <Camera className="h-4 w-4" /> {photo.name} (handwriting is read by your AI&apos;s vision)
              </span>
              <button className="text-red-300" onClick={() => setPhoto(null)}>
                Remove
              </button>
            </div>
          ) : (
            <textarea rows={8} className={area} placeholder="Your answer" value={answer} onChange={(e) => setAnswer(e.target.value)} />
          )}
          <div className="flex gap-2">
            <label className="cursor-pointer">
              <input
                type="file"
                accept=".png,.jpg,.jpeg,.webp"
                className="hidden"
                onChange={(e) => {
                  setPhoto(e.target.files?.[0] ?? null);
                  e.target.value = "";
                }}
              />
              <span className="inline-flex h-9 items-center gap-2 rounded-md border border-white/20 bg-white/5 px-3 text-xs hover:bg-white/10">
                <Camera className="h-3.5 w-3.5" /> Photo of handwritten answer
              </span>
            </label>
            <Button
              className="flex-1"
              onClick={grade}
              disabled={!!busy || !question.trim() || (!photo && !answer.trim()) || rubric.some((c) => !c.name.trim())}
            >
              {busy === "grade" ? "Grading…" : "Grade my answer"}
            </Button>
          </div>
          {error && <p className="text-xs text-red-400">{error}</p>}
        </CardContent>
      </Card>

      {result && <EssayResultView result={result} />}
    </div>
  );
}

function EssayResultView({ result }: { result: EssayResult }) {
  const [showModel, setShowModel] = useState(false);
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-baseline justify-between text-base">
          <span>
            {result.score} / {result.max_score}
          </span>
          <span className="text-2xl gradient-text">{Math.round(result.percentage)}%</span>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        {result.transcription && (
          <details className="rounded-lg bg-white/5 p-3 text-xs">
            <summary className="cursor-pointer">What the AI read from your photo</summary>
            <Markdown text={result.transcription} className="mt-2 text-muted-foreground" />
          </details>
        )}
        {result.criteria.map((c) => (
          <div key={c.name} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span className="font-medium">{c.name}</span>
              <span>
                {c.score} / {c.max}
              </span>
            </div>
            <Bar value={c.score} max={c.max} />
            {c.feedback && <Markdown text={c.feedback} className="text-xs text-muted-foreground" />}
            {c.evidence.length > 0 && (
              <p className="text-[11px] text-violet-300">
                Based on note{c.evidence.length > 1 ? "s" : ""} {c.evidence.map((n) => `[${n}]`).join(" ")}
              </p>
            )}
          </div>
        ))}
        {result.overall_feedback && <Markdown text={result.overall_feedback} className="rounded-lg bg-white/5 p-3" />}
        {result.model_answer && (
          <div>
            <Button variant="ghost" size="sm" onClick={() => setShowModel(!showModel)}>
              {showModel ? "Hide" : "Show"} a full-marks answer
            </Button>
            {showModel && <Markdown text={result.model_answer} className="mt-2 rounded-lg border border-emerald-500/20 p-3" />}
          </div>
        )}
        {result.sources.length > 0 && (
          <div className="flex flex-wrap gap-2 border-t border-white/10 pt-3 text-xs">
            {result.sources.map((s) => {
              const href = sourceLink(s);
              const label = `[${s.n}] ${s.source || s.title || "Notes"}${s.page_number ? ` · p.${s.page_number}` : ""}`;
              return href ? (
                <a key={s.n} href={href} target="_blank" rel="noreferrer" title={s.preview} className="rounded bg-white/5 px-2 py-1 hover:bg-white/10">
                  {label}
                </a>
              ) : (
                <span key={s.n} title={s.preview} className="rounded bg-white/5 px-2 py-1">
                  {label}
                </span>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function TeachBackTab({ topics }: { topics: string[] }) {
  const [concept, setConcept] = useState("");
  const [topic, setTopic] = useState("");
  const [explanation, setExplanation] = useState("");
  const [result, setResult] = useState<TeachBackResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const voice = useDictation((text) => setExplanation((e) => (e ? `${e} ${text}` : text)));

  const check = async () => {
    voice.stop();
    setBusy(true);
    setError("");
    try {
      setResult(await api.teachBack({ concept, explanation, topic: topic || undefined }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not check the explanation");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardContent className="space-y-3 p-5 text-sm">
          <p className="text-xs text-muted-foreground">
            Explain a concept as if teaching a 12-year-old. If you cannot explain it simply, you have found what to study
            next.
          </p>
          <Input value={concept} onChange={(e) => setConcept(e.target.value)} placeholder="Concept, e.g. Photosynthesis" />
          <TopicInput value={topic} onChange={setTopic} topics={topics} />
          <textarea
            rows={9}
            className={area}
            placeholder={voice.listening ? "Listening… speak your explanation" : "Your explanation, in plain words"}
            value={voice.listening && voice.interim ? `${explanation} ${voice.interim}` : explanation}
            onChange={(e) => setExplanation(e.target.value)}
            readOnly={voice.listening}
          />
          <div className="flex gap-2">
            {voice.supported && (
              <Button variant={voice.listening ? "default" : "outline"} onClick={voice.listening ? voice.stop : voice.start}>
                {voice.listening ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                {voice.listening ? "Stop" : "Explain out loud"}
              </Button>
            )}
            <Button className="flex-1" onClick={check} disabled={busy || !concept.trim() || !explanation.trim()}>
              {busy ? "Listening carefully…" : "Check my explanation"}
            </Button>
          </div>
          {voice.error && <p className="text-xs text-red-400">{voice.error}</p>}
          {error && <p className="text-xs text-red-400">{error}</p>}
        </CardContent>
      </Card>

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-baseline justify-between text-base">
              <span>{concept}</span>
              <span className="text-2xl gradient-text">{result.score}</span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            {!result.notes_found && (
              <p className="text-xs text-amber-300">No notes matched this concept, so it was judged from general knowledge.</p>
            )}
            {(["accuracy", "clarity", "completeness"] as const).map((k) => (
              <div key={k} className="space-y-1">
                <div className="flex justify-between text-xs capitalize">
                  <span>{k}</span>
                  <span>{result[k]}</span>
                </div>
                <Bar value={result[k]} />
              </div>
            ))}
            {result.verdict && <Markdown text={result.verdict} className="rounded-lg bg-white/5 p-3" />}
            {result.misconceptions.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-medium text-red-300">Not quite right</p>
                {result.misconceptions.map((m, i) => (
                  <Markdown key={i} text={`• ${m}`} className="text-xs" />
                ))}
              </div>
            )}
            {result.gaps.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-medium text-amber-300">You left out</p>
                {result.gaps.map((g, i) => (
                  <Markdown key={i} text={`• ${g}`} className="text-xs" />
                ))}
              </div>
            )}
            {result.jargon.length > 0 && (
              <div>
                <p className="mb-1 text-xs font-medium text-cyan-300">Jargon to explain</p>
                {result.jargon.map((j) => (
                  <p key={j.term} className="text-xs">
                    <span className="font-medium">{j.term}</span>
                    {j.suggestion && <span className="text-muted-foreground"> → try “{j.suggestion}”</span>}
                  </p>
                ))}
              </div>
            )}
            {result.follow_up_question && (
              <div className="rounded-lg border border-violet-500/30 p-3">
                <p className="mb-1 flex items-center gap-1 text-xs text-violet-300">
                  <Lightbulb className="h-3.5 w-3.5" /> A curious 12-year-old asks:
                </p>
                <Markdown text={result.follow_up_question} />
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2"
                  onClick={() => {
                    setConcept(result.follow_up_question);
                    setExplanation("");
                    setResult(null);
                  }}
                >
                  Answer it next
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function HistoryTab() {
  const [items, setItems] = useState<GradedAnswer[]>([]);
  useEffect(() => {
    api.gradingHistory().then(setItems).catch(() => {});
  }, []);
  if (!items.length) return <p className="text-sm text-muted-foreground">Graded answers appear here.</p>;
  return (
    <div className="space-y-2">
      {items.map((g) => (
        <Card key={g.id}>
          <CardContent className="flex items-center gap-4 p-4 text-sm">
            <span className="w-16 shrink-0 text-lg font-semibold">{Math.round((g.score / g.max_score) * 100)}%</span>
            <div className="min-w-0">
              <p className="truncate font-medium">{g.question}</p>
              <p className="text-xs text-muted-foreground">
                {g.kind === "essay" ? "Essay" : "Teach it back"}
                {g.topic ? ` · ${g.topic}` : ""} · {new Date(g.created_at + "Z").toLocaleString()}
              </p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export default function GraderPage() {
  const [tab, setTab] = useState<"essay" | "teach" | "history">("essay");
  const [topics, setTopics] = useState<string[]>([]);
  useEffect(() => {
    api.topics().then((r) => setTopics(r.topics)).catch(() => {});
  }, []);

  return (
    <div>
      <PageHeader
        title="Answer Grader"
        description="Long answers marked against a rubric from your notes, typed or photographed. Or explain a concept simply and find your gaps."
      />
      <div className="mb-6 flex gap-2">
        {([
          ["essay", "Essay answers", GraduationCap],
          ["teach", "Teach it back", Lightbulb],
          ["history", "History", null],
        ] as const).map(([key, label, Icon]) => (
          <Button key={key} variant={tab === key ? "default" : "outline"} size="sm" onClick={() => setTab(key)}>
            {Icon && <Icon className="h-4 w-4" />} {label}
          </Button>
        ))}
      </div>
      {tab === "essay" && <EssayTab topics={topics} />}
      {tab === "teach" && <TeachBackTab topics={topics} />}
      {tab === "history" && <HistoryTab />}
    </div>
  );
}
