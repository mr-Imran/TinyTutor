"use client";

import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Award,
  BookOpen,
  Brain,
  Check,
  Flame,
  Layers,
  Library,
  LucideIcon,
  Medal,
  Sparkles,
  Star,
  Target,
  Timer,
  Trophy,
  X,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress as ProgressBar } from "@/components/ui/progress";
import { api, Progress } from "@/lib/api";

const BADGE_ICONS: Record<string, LucideIcon> = {
  book: BookOpen,
  library: Library,
  sparkles: Sparkles,
  target: Target,
  layers: Layers,
  brain: Brain,
  flame: Flame,
  trophy: Trophy,
  timer: Timer,
  medal: Medal,
  check: Check,
  star: Star,
};

const GOALS = [50, 100, 150, 250];

export function ProgressPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [p, setP] = useState<Progress | null>(null);
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    api.progress().then(setP).catch(() => {});
  }, [refreshKey]);

  if (!p) return null;

  const fresh = p.badges.filter((b) => b.new);
  const earned = p.badges.filter((b) => b.earned_at);
  const goalPct = Math.min(100, (p.today_xp / p.daily_goal) * 100);
  const maxWeek = Math.max(p.daily_goal, ...p.week.map((d) => d.xp));

  const dismiss = async () => {
    await api.markBadgesSeen();
    setP({ ...p, badges: p.badges.map((b) => ({ ...b, new: false })) });
  };

  const changeGoal = async (goal: number) => setP(await api.setDailyGoal(goal));

  return (
    <>
      <AnimatePresence>
        {fresh.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            className="mb-6 flex items-center justify-between gap-3 rounded-xl border border-amber-400/40 bg-amber-500/10 px-4 py-3"
          >
            <span className="flex items-center gap-2 text-sm">
              <Award className="h-5 w-5 text-amber-300" />
              New badge{fresh.length > 1 ? "s" : ""}: {fresh.map((b) => b.name).join(", ")}
            </span>
            <button onClick={dismiss} aria-label="Dismiss">
              <X className="h-4 w-4 text-muted-foreground" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <Card className="mb-8">
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Trophy className="h-5 w-5 text-amber-300" /> Level {p.level}
            </span>
            <span className="text-sm font-normal text-muted-foreground">{p.xp.toLocaleString()} XP</span>
          </CardTitle>
          <div>
            <ProgressBar value={(p.level_xp / p.level_size) * 100} />
            <p className="mt-1 text-xs text-muted-foreground">
              {p.level_size - p.level_xp} XP to level {p.level + 1}
            </p>
          </div>
        </CardHeader>
        <CardContent className="grid gap-6 md:grid-cols-3">
          <div>
            <p className="mb-2 flex items-center justify-between text-sm">
              <span>Today</span>
              <span className="text-muted-foreground">
                {p.today_xp} / {p.daily_goal} XP
              </span>
            </p>
            <ProgressBar value={goalPct} />
            <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
              Daily goal:
              {GOALS.map((g) => (
                <button
                  key={g}
                  onClick={() => changeGoal(g)}
                  className={`rounded px-1.5 py-0.5 ${p.daily_goal === g ? "bg-primary/30 text-white" : "hover:bg-white/10"}`}
                >
                  {g}
                </button>
              ))}
            </div>
            <p className="mt-3 flex items-center gap-1 text-xs text-muted-foreground">
              <Flame className="h-3.5 w-3.5 text-orange-400" /> {p.current_streak}-day streak · best {p.longest_streak}
            </p>
          </div>

          <div>
            <p className="mb-2 text-sm">This week</p>
            <div className="flex h-20 items-end gap-1.5">
              {p.week.map((d) => (
                <div key={d.date} className="flex flex-1 flex-col items-center gap-1" title={`${d.date}: ${d.xp} XP`}>
                  <div
                    className={`w-full rounded-t ${d.xp >= p.daily_goal ? "bg-emerald-400/70" : "bg-violet-500/50"}`}
                    style={{ height: `${Math.max(4, (d.xp / maxWeek) * 64)}px` }}
                  />
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(`${d.date}T00:00:00`).toLocaleDateString(undefined, { weekday: "narrow" })}
                  </span>
                </div>
              ))}
            </div>
          </div>

          <div>
            <p className="mb-2 flex items-center justify-between text-sm">
              <span>Badges</span>
              <button className="text-xs text-muted-foreground hover:text-foreground" onClick={() => setShowAll((s) => !s)}>
                {earned.length}/{p.badges.length} · {showAll ? "hide" : "see all"}
              </button>
            </p>
            <div className="flex flex-wrap gap-2">
              {(showAll ? p.badges : earned.slice(-6)).map((b) => {
                const Icon = BADGE_ICONS[b.icon] ?? Award;
                return (
                  <div
                    key={b.id}
                    title={`${b.name}: ${b.description}`}
                    className={`flex h-10 w-10 items-center justify-center rounded-full border ${
                      b.earned_at ? "border-amber-400/50 bg-amber-500/15 text-amber-300" : "border-white/10 bg-white/5 text-white/20"
                    }`}
                  >
                    <Icon className="h-5 w-5" />
                  </div>
                );
              })}
              {!showAll && earned.length === 0 && <p className="text-xs text-muted-foreground">Study to earn your first badge.</p>}
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
}
