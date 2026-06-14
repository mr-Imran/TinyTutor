"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { FileText, Flame, Target, Trophy, Zap } from "lucide-react";
import Link from "next/link";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Skeleton } from "@/components/ui/skeleton";
import { api, DashboardData, ScheduledQuestion } from "@/lib/api";

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [notifications, setNotifications] = useState<ScheduledQuestion[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.dashboard(), api.notifications()])
      .then(([d, n]) => {
        setData(d);
        setNotifications(n);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-32" />
          ))}
        </div>
      </div>
    );
  }

  const d = data!;

  return (
    <div>
      <PageHeader
        title={`Welcome back${d.user?.display_name ? `, ${d.user.display_name}` : ""}`}
        description="Your personal AI study tutor — track progress, fix weak topics, ace exams."
      />

      <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard title="Study Streak" value={`${d.study_streak} days`} icon={Flame} delay={0} />
        <StatCard title="Documents" value={d.total_documents} icon={FileText} delay={0.05} />
        <StatCard title="Quizzes Taken" value={d.total_quizzes} icon={Zap} delay={0.1} />
        <StatCard
          title="Readiness Score"
          value={`${d.readiness_score}%`}
          subtitle="Exam readiness"
          icon={Target}
          delay={0.15}
        />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.2 }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-amber-400">
                <Target className="h-5 w-5" /> Weak Topics
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {d.weak_topics.length === 0 ? (
                <p className="text-sm text-muted-foreground">No data yet — take a quiz or upload materials.</p>
              ) : (
                d.weak_topics.map((t) => (
                  <div key={t.topic}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span>{t.topic}</span>
                      <span className="text-muted-foreground">{t.mastery_percentage}%</span>
                    </div>
                    <Progress value={t.mastery_percentage} />
                  </div>
                ))
              )}
              <Link href="/quiz">
                <Button variant="outline" className="w-full">Practice weak topics</Button>
              </Link>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.25 }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-emerald-400">
                <Trophy className="h-5 w-5" /> Strong Topics
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {d.strong_topics.length === 0 ? (
                <p className="text-sm text-muted-foreground">Keep studying to build mastery.</p>
              ) : (
                d.strong_topics.map((t) => (
                  <div key={t.topic}>
                    <div className="mb-1 flex justify-between text-sm">
                      <span>{t.topic}</span>
                      <span className="text-emerald-400">{t.mastery_percentage}%</span>
                    </div>
                    <Progress value={t.mastery_percentage} />
                  </div>
                ))
              )}
            </CardContent>
          </Card>
        </motion.div>
      </div>

      {d.study_targets?.has_plan && (
        <motion.div className="mt-6" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <Card className="border-violet-500/25">
            <CardHeader>
              <CardTitle className="text-base">Exam study plan</CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              {d.study_targets.in_exam_window ? (
                <p>
                  Exam period is active. Study about <strong className="text-foreground">{d.study_targets.hours_per_day}h</strong> today
                  toward CGPA <strong className="text-foreground">{d.study_targets.expected_cgpa}</strong>.
                  Logged: {d.study_targets.hours_logged}h · Remaining: {d.study_targets.hours_remaining}h
                </p>
              ) : (
                <p>
                  {d.study_targets.days_left} days in plan · Goal {d.study_targets.total_hours_needed}h total ·{" "}
                  {d.study_targets.hours_per_day}h/day suggested
                </p>
              )}
              <Link href="/study" className="mt-3 inline-block text-cyan-400 hover:underline">
                Open What to Study →
              </Link>
            </CardContent>
          </Card>
        </motion.div>
      )}

      {notifications.length > 0 && (
        <motion.div
          className="mt-6"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <Card className="border-cyan-500/30">
            <CardHeader>
              <CardTitle>Reminders</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {notifications.slice(0, 3).map((n) => (
                <div key={n.id} className="rounded-lg bg-white/5 p-3 text-sm">
                  <span className="text-xs text-cyan-400">
                    {n.notification_type === "study" ? "Study reminder" : "Quiz"} · {n.topic}
                  </span>
                  <p className="mt-1 whitespace-pre-wrap">{n.question}</p>
                </div>
              ))}
            </CardContent>
          </Card>
        </motion.div>
      )}

      <div className="mt-8 flex flex-wrap gap-3">
        <Link href="/exam-hub"><Button>Exam Hub</Button></Link>
        <Link href="/study"><Button variant="outline">What to Study</Button></Link>
        <Link href="/upload"><Button variant="outline">Upload Materials</Button></Link>
        <Link href="/quiz"><Button variant="accent">Start Quiz</Button></Link>
      </div>
    </div>
  );
}
