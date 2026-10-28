"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import { CalendarDays, CheckCircle2, Circle, Download, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { api, DailyPlan, downloads } from "@/lib/api";

const HOURS = Array.from({ length: 17 }, (_, i) => i + 6); // 06:00–22:00

export function TodayPlan({ onChange }: { onChange?: () => void }) {
  const [plan, setPlan] = useState<DailyPlan | null>(null);
  const [busy, setBusy] = useState(false);
  const [showCalendar, setShowCalendar] = useState(false);
  const [hour, setHour] = useState(18);
  const [days, setDays] = useState(7);

  useEffect(() => {
    api.todayPlan().then(setPlan).catch(() => {});
  }, []);

  const toggle = async (id: string) => {
    const updated = await api.togglePlanTask(id);
    setPlan(updated);
    onChange?.();
  };

  const regenerate = async () => {
    setBusy(true);
    try {
      setPlan(await api.regeneratePlan());
    } finally {
      setBusy(false);
    }
  };

  if (!plan) return null;
  const pct = plan.tasks.length ? (plan.done_count / plan.tasks.length) * 100 : 0;

  return (
    <Card className="mb-8">
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center justify-between gap-2">
          <span className="flex items-center gap-2">
            <CalendarDays className="h-5 w-5 text-violet-400" /> Today&apos;s plan
            <span className="text-xs font-normal text-muted-foreground">
              · about {plan.total_minutes} min · {plan.done_count}/{plan.tasks.length} done
            </span>
          </span>
          <span className="flex gap-2">
            <Button variant="ghost" size="sm" onClick={() => setShowCalendar((s) => !s)}>
              <Download className="h-3.5 w-3.5" /> Calendar
            </Button>
            <Button variant="ghost" size="sm" onClick={regenerate} disabled={busy} title="Rebuild from your latest progress">
              <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Refresh
            </Button>
          </span>
        </CardTitle>
        <Progress value={pct} />
      </CardHeader>
      <CardContent className="space-y-2">
        {showCalendar && (
          <div className="mb-3 flex flex-wrap items-center gap-2 rounded-lg bg-white/5 p-3 text-xs">
            <span>Add a daily study session at</span>
            <select
              value={hour}
              onChange={(e) => setHour(Number(e.target.value))}
              className="h-8 rounded-md border border-white/15 bg-white/5 px-2"
            >
              {HOURS.map((h) => (
                <option key={h} value={h} className="bg-slate-900">
                  {String(h).padStart(2, "0")}:00
                </option>
              ))}
            </select>
            <span>for the next</span>
            <select
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="h-8 rounded-md border border-white/15 bg-white/5 px-2"
            >
              {[7, 14, 30].map((d) => (
                <option key={d} value={d} className="bg-slate-900">
                  {d} days
                </option>
              ))}
            </select>
            <a href={downloads.calendar(days, hour)}>
              <Button size="sm">Download .ics</Button>
            </a>
            <span className="text-muted-foreground">Opens in Google Calendar, Outlook or Apple Calendar.</span>
          </div>
        )}
        {plan.tasks.map((t, i) => (
          <motion.div
            key={t.id}
            initial={{ opacity: 0, x: -6 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.03 }}
            className="flex items-center gap-3 rounded-lg bg-white/5 px-3 py-2"
          >
            <button onClick={() => toggle(t.id)} aria-label={t.done ? "Mark not done" : "Mark done"}>
              {t.done ? <CheckCircle2 className="h-5 w-5 text-emerald-400" /> : <Circle className="h-5 w-5 text-muted-foreground" />}
            </button>
            <Link href={t.link} className="min-w-0 flex-1">
              <p className={`text-sm ${t.done ? "text-muted-foreground line-through" : ""}`}>{t.title}</p>
              <p className="truncate text-xs text-muted-foreground">{t.detail}</p>
            </Link>
            <span className="shrink-0 text-xs text-muted-foreground">{t.minutes} min</span>
          </motion.div>
        ))}
        {plan.complete && <p className="pt-1 text-sm text-emerald-400">Plan complete — great work today! 🎉</p>}
      </CardContent>
    </Card>
  );
}
