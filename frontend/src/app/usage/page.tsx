"use client";

import { useCallback, useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { AlertTriangle, Coins, Cpu, Hash } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, UsageBucket, UsageReport } from "@/lib/api";

const FEATURE_LABELS: Record<string, string> = {
  tutor: "AI Tutor",
  agent: "Tutor (agent mode)",
  mentor: "Mentor",
  quiz: "Quizzes & math",
  mock_exam: "Mock exams",
  flashcards: "Flashcards",
  documents: "Uploads (summaries, vision)",
  notes: "Notes",
  exam_hub: "Exam Hub",
  grading: "Answer Grader",
  misconceptions: "Mistakes",
  knowledge_graph: "Knowledge Map",
  search: "Search",
  settings: "Settings",
  scheduler: "Scheduled questions",
  other: "Other",
};

const tokens = (b: UsageBucket) => b.input_tokens + b.output_tokens;
const fmt = (n: number) => (n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n));
const money = (n: number) => `$${n < 0.01 && n > 0 ? n.toFixed(4) : n.toFixed(2)}`;

function costLabel(b: UsageBucket) {
  if (b.calls === 0) return "—";
  if (b.unpriced_calls === b.calls) return "no price set";
  return `${money(b.cost)}${b.unpriced_calls ? " +?" : ""}`;
}

export default function UsagePage() {
  const [report, setReport] = useState<UsageReport | null>(null);
  const [days, setDays] = useState(30);
  const [prices, setPrices] = useState<Record<string, { input: string; output: string }>>({});
  const [budget, setBudget] = useState("");
  const [message, setMessage] = useState("");

  const apply = useCallback((r: UsageReport) => {
    setReport(r);
    setBudget(r.budget ? String(r.budget) : "");
    const editable: Record<string, { input: string; output: string }> = {};
    for (const m of r.by_model) {
      if (m.provider === "ollama") continue;
      const p = r.prices[m.model];
      editable[m.model] = { input: p ? String(p.input) : "", output: p ? String(p.output) : "" };
    }
    for (const [model, p] of Object.entries(r.prices)) {
      editable[model] ??= { input: String(p.input), output: String(p.output) };
    }
    setPrices(editable);
  }, []);

  useEffect(() => {
    api.usage(days).then(apply).catch(() => {});
  }, [days, apply]);

  const savePrices = async () => {
    const clean: Record<string, { input: number; output: number }> = {};
    for (const [model, p] of Object.entries(prices)) {
      if (p.input === "" && p.output === "") continue;
      clean[model] = { input: Number(p.input) || 0, output: Number(p.output) || 0 };
    }
    apply(await api.saveUsagePrices(clean));
    setMessage("Prices saved.");
  };

  const saveBudget = async () => {
    apply(await api.saveBudget(budget ? Number(budget) : null));
    setMessage(budget ? "Budget saved." : "Budget removed.");
  };

  if (!report) return <PageHeader title="Usage" description="Loading…" />;

  return (
    <div>
      <PageHeader
        title="Usage"
        description="Tokens used by each feature and model. Local Ollama models are free; for paid APIs, enter prices to see estimated costs."
      />

      {report.budget_status && report.budget_status !== "ok" && (
        <div
          className={`mb-6 flex items-center gap-2 rounded-lg p-3 text-sm ${
            report.budget_status === "over" ? "bg-red-500/15 text-red-200" : "bg-amber-500/15 text-amber-200"
          }`}
        >
          <AlertTriangle className="h-4 w-4" />
          {report.budget_status === "over"
            ? `This month's estimated cost (${money(report.month.cost)}) is over your ${money(report.budget!)} budget.`
            : `This month's estimated cost (${money(report.month.cost)}) has passed 80% of your ${money(report.budget!)} budget.`}
        </div>
      )}

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard title={`Tokens, last ${days} days`} value={fmt(tokens(report.total))} icon={Hash} />
        <StatCard title={`AI calls, last ${days} days`} value={report.total.calls} icon={Cpu} />
        <StatCard title="Estimated cost this month" value={costLabel(report.month)} icon={Coins} />
      </div>

      <Card className="mb-6">
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Tokens per day</CardTitle>
          <div className="flex gap-1">
            {[7, 30, 90].map((d) => (
              <Button key={d} size="sm" variant={days === d ? "default" : "outline"} onClick={() => setDays(d)}>
                {d}d
              </Button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={report.by_day.map((d) => ({ date: d.date.slice(5), input: d.input_tokens, output: d.output_tokens }))}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
              <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#94a3b8" }} />
              <YAxis tickFormatter={fmt} tick={{ fontSize: 10, fill: "#94a3b8" }} width={44} />
              <Tooltip
                formatter={(v: number, name: string) => [fmt(v), name === "input" ? "Input tokens" : "Output tokens"]}
                contentStyle={{ background: "#0f172a", border: "1px solid rgba(255,255,255,0.1)", fontSize: 12 }}
              />
              <Bar dataKey="input" stackId="t" fill="#8b5cf6" />
              <Bar dataKey="output" stackId="t" fill="#22d3ee" />
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <div className="mb-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">By feature</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {report.by_feature.length === 0 && <p className="text-muted-foreground">No AI calls yet.</p>}
            {report.by_feature.map((f) => {
              const share = tokens(report.total) ? (tokens(f) / tokens(report.total)) * 100 : 0;
              return (
                <div key={f.feature}>
                  <div className="flex justify-between text-xs">
                    <span>{FEATURE_LABELS[f.feature] ?? f.feature}</span>
                    <span className="text-muted-foreground">
                      {fmt(tokens(f))} · {f.calls} calls · {costLabel(f)}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 rounded-full bg-white/10">
                    <div className="h-1.5 rounded-full bg-violet-400" style={{ width: `${Math.max(1, share)}%` }} />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">By model</CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-xs">
            {report.by_model.map((m) => (
              <div key={`${m.provider}/${m.model}`} className="flex justify-between border-t border-white/5 py-1.5 first:border-0">
                <span>
                  <span className="text-muted-foreground">{m.provider} · </span>
                  {m.model || "unknown"}
                </span>
                <span className="text-muted-foreground">
                  {fmt(m.input_tokens)} in · {fmt(m.output_tokens)} out · {m.provider === "ollama" ? "free" : costLabel(m)}
                </span>
              </div>
            ))}
            <p className="pt-2 text-muted-foreground">
              Some OpenAI-compatible servers do not report tokens for streamed answers; those calls count as 0 tokens.
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Prices (USD per 1 million tokens)</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-xs text-muted-foreground">
              TinyTutor ships no prices because they change often. Copy them from your provider&apos;s pricing page.
            </p>
            {Object.keys(prices).length === 0 && (
              <p className="text-xs text-muted-foreground">Models from paid APIs appear here after their first use.</p>
            )}
            {Object.entries(prices).map(([model, p]) => (
              <div key={model} className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-xs">{model}</span>
                <Input
                  className="h-8 w-24 text-xs"
                  type="number"
                  min={0}
                  step="0.01"
                  placeholder="input"
                  value={p.input}
                  onChange={(e) => setPrices((all) => ({ ...all, [model]: { ...p, input: e.target.value } }))}
                />
                <Input
                  className="h-8 w-24 text-xs"
                  type="number"
                  min={0}
                  step="0.01"
                  placeholder="output"
                  value={p.output}
                  onChange={(e) => setPrices((all) => ({ ...all, [model]: { ...p, output: e.target.value } }))}
                />
              </div>
            ))}
            <Button size="sm" onClick={savePrices} disabled={Object.keys(prices).length === 0}>
              Save prices
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Monthly budget</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <p className="text-xs text-muted-foreground">
              A warning shows here at 80% of the budget and again when it is passed. Nothing is blocked.
            </p>
            <div className="flex gap-2">
              <Input
                type="number"
                min={0}
                step="1"
                placeholder="e.g. 5"
                value={budget}
                onChange={(e) => setBudget(e.target.value)}
                className="w-32"
              />
              <Button size="sm" onClick={saveBudget}>
                Save
              </Button>
            </div>
            {message && <p className="text-xs text-cyan-300">{message}</p>}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
