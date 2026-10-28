"use client";

import { useState } from "react";
import Link from "next/link";
import { CheckCircle2, Circle, Layers, ListChecks, Target, XCircle } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AgentCard, api, QuizQuestion } from "@/lib/api";

function Shell({ icon: Icon, title, children }: { icon: typeof Layers; title: string; children: React.ReactNode }) {
  return (
    <div className="mt-3 rounded-lg border border-white/10 bg-black/20 p-3">
      <p className="mb-2 flex items-center gap-2 text-xs font-medium text-violet-300">
        <Icon className="h-3.5 w-3.5" /> {title}
      </p>
      {children}
    </div>
  );
}

function QuizQuestionCard({ q, index }: { q: QuizQuestion; index: number }) {
  const [answer, setAnswer] = useState("");
  const [result, setResult] = useState<{ is_correct: boolean; feedback: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (value: string) => {
    if (!value.trim() || result || busy) return;
    setBusy(true);
    setAnswer(value);
    try {
      setResult(await api.submitQuiz({ ...q, user_answer: value }));
    } catch {
      setResult({ is_correct: false, feedback: "Could not check that answer." });
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border-t border-white/10 py-2 first:border-0 first:pt-0">
      <div className="mb-2 flex gap-1 text-sm">
        <span className="text-muted-foreground">{index + 1}.</span>
        <Markdown text={q.question} />
      </div>
      {q.options?.length ? (
        <div className="grid gap-1.5 sm:grid-cols-2">
          {q.options.map((o) => {
            const chosen = answer === o;
            const tone = !result
              ? "bg-white/5 hover:bg-white/10"
              : o === q.correct_answer
                ? "bg-emerald-500/25"
                : chosen
                  ? "bg-red-500/25"
                  : "bg-white/5 opacity-60";
            return (
              <button
                key={o}
                disabled={!!result || busy}
                onClick={() => submit(o)}
                className={`rounded-md px-2 py-1.5 text-left text-xs ${tone}`}
              >
                <Markdown text={o} inline />
              </button>
            );
          })}
        </div>
      ) : (
        <div className="flex gap-2">
          <Input
            value={answer}
            disabled={!!result}
            onChange={(e) => setAnswer(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && submit(answer)}
            placeholder="Your answer"
            className="h-8 text-xs"
          />
          <Button size="sm" disabled={!!result || busy} onClick={() => submit(answer)}>
            Check
          </Button>
        </div>
      )}
      {result && (
        <div className={`mt-2 flex gap-2 text-xs ${result.is_correct ? "text-emerald-300" : "text-red-300"}`}>
          {result.is_correct ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <XCircle className="h-4 w-4 shrink-0" />}
          <div>
            <Markdown text={result.feedback} />
            {q.explanation && <Markdown text={q.explanation} className="mt-1 text-muted-foreground" />}
          </div>
        </div>
      )}
    </div>
  );
}

export function AgentCardView({ card }: { card: AgentCard }) {
  if (card.type === "flashcards") {
    return (
      <Shell icon={Layers} title={`${card.count} flashcard${card.count === 1 ? "" : "s"} added · ${card.topic}`}>
        <div className="space-y-1.5">
          {card.cards.map((c, i) => (
            <div key={i} className="rounded-md bg-white/5 px-2 py-1.5 text-xs">
              <Markdown text={c.front} className="font-medium" />
              <Markdown text={c.back} className="text-muted-foreground" />
            </div>
          ))}
        </div>
        <Link href="/flashcards" className="mt-2 inline-block text-xs text-cyan-300 hover:underline">
          Review them →
        </Link>
      </Shell>
    );
  }
  if (card.type === "quiz") {
    return (
      <Shell icon={Target} title={`Quiz · ${card.topic}`}>
        {card.questions.map((q, i) => (
          <QuizQuestionCard key={i} q={q} index={i} />
        ))}
      </Shell>
    );
  }
  if (card.type === "mastery") {
    return (
      <Shell icon={Target} title="Your mastery">
        {card.topics.length === 0 && <p className="text-xs text-muted-foreground">No answers recorded yet.</p>}
        <div className="space-y-1.5">
          {card.topics.map((t) => (
            <div key={t.topic} className="text-xs">
              <div className="flex justify-between">
                <span className="truncate">{t.topic}</span>
                <span className="text-muted-foreground">{Math.round(t.mastery)}%</span>
              </div>
              <div className="mt-0.5 h-1.5 rounded-full bg-white/10">
                <div
                  className={`h-1.5 rounded-full ${t.mastery >= 80 ? "bg-emerald-400" : t.mastery >= 50 ? "bg-amber-400" : "bg-red-400"}`}
                  style={{ width: `${Math.max(3, t.mastery)}%` }}
                />
              </div>
            </div>
          ))}
        </div>
      </Shell>
    );
  }
  return (
    <Shell icon={ListChecks} title="Today's plan">
      <div className="space-y-1">
        {card.tasks.map((t, i) => (
          <Link key={i} href={t.link} className="flex items-center gap-2 text-xs hover:text-cyan-300">
            {t.done ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : <Circle className="h-3.5 w-3.5" />}
            <span className={t.done ? "line-through opacity-60" : ""}>{t.title}</span>
            <span className="ml-auto text-muted-foreground">{t.minutes} min</span>
          </Link>
        ))}
      </div>
    </Shell>
  );
}
