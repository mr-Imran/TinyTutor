"use client";

import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, RotateCcw, Search, Sparkles, X, XCircle } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, DrillResult, Misconception, MisconceptionOverview } from "@/lib/api";

function Drill({ item, needed, onChange }: { item: Misconception; needed: number; onChange: () => void }) {
  const [results, setResults] = useState<Record<number, DrillResult & { answer: string }>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const drill = item.drill;

  const start = async () => {
    setBusy(true);
    setError("");
    setResults({});
    try {
      await api.newDrill(item.id);
      onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not make a drill");
    } finally {
      setBusy(false);
    }
  };

  const answer = async (index: number, value: string) => {
    if (results[index] || drill?.answered.includes(index)) return;
    try {
      const r = await api.answerDrill(item.id, index, value);
      setResults((all) => ({ ...all, [index]: { ...r, answer: value } }));
      if (r.status === "resolved" || index === (drill?.questions.length ?? 0) - 1) onChange();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not check the answer");
    }
  };

  const allAnswered = drill && drill.questions.every((_, i) => results[i] || drill.answered.includes(i));

  if (!drill || (allAnswered && item.status === "open" && !Object.keys(results).length)) {
    return (
      <div>
        <Button size="sm" onClick={start} disabled={busy}>
          <Sparkles className="h-3.5 w-3.5" /> {busy ? "Writing questions…" : drill ? "New drill" : "Start a drill"}
        </Button>
        {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
      </div>
    );
  }
  return (
    <div className="space-y-3">
      <p className="text-xs text-muted-foreground">
        Streak {item.streak}/{needed}: {needed} correct answers in a row resolve this.
      </p>
      {drill.questions.map((q, i) => {
        const r = results[i];
        const done = r || drill.answered.includes(i);
        return (
          <div key={i} className="rounded-lg bg-white/5 p-3">
            <Markdown text={q.question} className="mb-2" />
            <div className="grid gap-1.5 sm:grid-cols-2">
              {q.options.map((o) => {
                const tone = !r
                  ? done
                    ? "opacity-50"
                    : "hover:bg-white/10"
                  : o === r.correct_answer
                    ? "bg-emerald-500/25"
                    : o === r.answer
                      ? "bg-red-500/25"
                      : "opacity-50";
                return (
                  <button
                    key={o}
                    disabled={!!done}
                    onClick={() => answer(i, o)}
                    className={`rounded-md border border-white/10 px-2 py-1.5 text-left text-xs ${tone}`}
                  >
                    <Markdown text={o} inline />
                  </button>
                );
              })}
            </div>
            {r && (
              <div className={`mt-2 flex gap-2 text-xs ${r.is_correct ? "text-emerald-300" : "text-red-300"}`}>
                {r.is_correct ? <CheckCircle2 className="h-4 w-4 shrink-0" /> : <XCircle className="h-4 w-4 shrink-0" />}
                <Markdown text={r.explanation} />
              </div>
            )}
          </div>
        );
      })}
      {allAnswered && item.status === "open" && (
        <Button size="sm" variant="outline" onClick={start} disabled={busy}>
          <RotateCcw className="h-3.5 w-3.5" /> Another drill
        </Button>
      )}
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}

function MisconceptionCard({ item, needed, onChange }: { item: Misconception; needed: number; onChange: () => void }) {
  const setStatus = async (status: "open" | "resolved" | "dismissed") => {
    await api.setMisconceptionStatus(item.id, status).catch(() => {});
    onChange();
  };
  const resolved = item.status === "resolved";
  return (
    <Card className={resolved ? "opacity-70" : ""}>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-start justify-between gap-3 text-base">
          <span>
            {resolved && <CheckCircle2 className="mr-1 inline h-4 w-4 text-emerald-400" />}
            {item.title}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              {item.topic} · from {item.evidence} wrong answer{item.evidence === 1 ? "" : "s"}
            </span>
          </span>
          {resolved ? (
            <Button variant="ghost" size="sm" onClick={() => setStatus("open")}>
              Reopen
            </Button>
          ) : (
            <button aria-label="Dismiss" title="Not a real misconception: dismiss" onClick={() => setStatus("dismissed")}>
              <X className="h-4 w-4 text-muted-foreground hover:text-foreground" />
            </button>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <div className="grid gap-3 md:grid-cols-2">
          <div className="rounded-lg bg-red-500/10 p-3">
            <p className="mb-1 text-xs font-medium text-red-300">What you seem to think</p>
            <Markdown text={item.description} />
          </div>
          <div className="rounded-lg bg-emerald-500/10 p-3">
            <p className="mb-1 text-xs font-medium text-emerald-300">The correct idea</p>
            <Markdown text={item.correction} />
          </div>
        </div>
        {item.examples.length > 0 && (
          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground">Your answers that showed this</summary>
            <div className="mt-2 space-y-2">
              {item.examples.slice(0, 5).map((e, i) => (
                <div key={i} className="border-l-2 border-white/10 pl-2">
                  <Markdown text={e.question} />
                  <p className="text-muted-foreground">
                    You: <span className="text-red-300">{e.user_answer}</span> · Correct:{" "}
                    <span className="text-emerald-300">{e.correct_answer}</span>
                  </p>
                </div>
              ))}
            </div>
          </details>
        )}
        {!resolved && <Drill item={item} needed={needed} onChange={onChange} />}
      </CardContent>
    </Card>
  );
}

export default function MisconceptionsPage() {
  const [data, setData] = useState<MisconceptionOverview | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const load = useCallback(() => {
    api.misconceptions().then(setData).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const analyze = async () => {
    setBusy(true);
    setMessage("");
    try {
      const r = await api.analyzeMisconceptions();
      setData(r);
      setMessage(
        r.message ??
          (r.created.length
            ? `Found ${r.created.length} new pattern${r.created.length === 1 ? "" : "s"}.`
            : r.updated.length
              ? "Added new mistakes to patterns you already have."
              : "No new patterns. Your mistakes look like one-off slips.")
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Analysis failed");
    } finally {
      setBusy(false);
    }
  };

  const open = data?.misconceptions.filter((m) => m.status === "open") ?? [];
  const resolved = data?.misconceptions.filter((m) => m.status === "resolved") ?? [];

  return (
    <div>
      <PageHeader
        title="Mistakes"
        description="Patterns behind your wrong answers, each with the correct idea and a short drill. Three right in a row resolves one."
      />
      <Card className="mb-6">
        <CardContent className="flex flex-wrap items-center justify-between gap-3 p-5 text-sm">
          <p className="text-muted-foreground">
            {data ? (
              <>
                {data.pending} wrong answer{data.pending === 1 ? "" : "s"} not analysed yet · {open.length} open ·{" "}
                {resolved.length} resolved
              </>
            ) : (
              "Loading…"
            )}
          </p>
          <Button onClick={analyze} disabled={busy}>
            <Search className="h-4 w-4" /> {busy ? "Looking for patterns…" : "Analyse my mistakes"}
          </Button>
          {message && <p className="w-full text-xs text-cyan-300">{message}</p>}
        </CardContent>
      </Card>

      <div className="space-y-4">
        {open.map((m) => (
          <MisconceptionCard key={m.id} item={m} needed={data!.resolve_streak} onChange={load} />
        ))}
        {data && open.length === 0 && (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              No open misconceptions. Answer quizzes and mock exams, then analyse your mistakes here.
            </CardContent>
          </Card>
        )}
        {data && open.length === 0 && data.recent_mistakes.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Recent mistakes</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-xs">
              {data.recent_mistakes.map((m) => (
                <div key={m.id} className="border-l-2 border-white/10 pl-2">
                  <Markdown text={m.question} />
                  <p className="text-muted-foreground">
                    {m.topic} · You: <span className="text-red-300">{m.user_answer}</span> · Correct:{" "}
                    <span className="text-emerald-300">{m.correct_answer}</span>
                  </p>
                </div>
              ))}
            </CardContent>
          </Card>
        )}
        {resolved.length > 0 && (
          <>
            <h2 className="pt-4 text-sm font-medium text-muted-foreground">Resolved</h2>
            {resolved.map((m) => (
              <MisconceptionCard key={m.id} item={m} needed={data!.resolve_streak} onChange={load} />
            ))}
          </>
        )}
      </div>
    </div>
  );
}
