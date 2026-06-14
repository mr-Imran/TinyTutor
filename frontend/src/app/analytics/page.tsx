"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, AnalyticsData } from "@/lib/api";

export default function AnalyticsPage() {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.analytics().then(setData).catch(console.error).finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-12 w-48" />
        <Skeleton className="h-64" />
        <Skeleton className="h-64" />
      </div>
    );
  }

  const masteryData =
    data?.topic_scores.map((t) => ({
      topic: t.topic.length > 12 ? t.topic.slice(0, 12) + "…" : t.topic,
      mastery: t.mastery_percentage,
      correct: t.correct_answers,
      wrong: t.wrong_answers,
    })) ?? [];

  const activityData =
    data?.activity.map((a) => ({
      date: a.date.slice(5),
      quizzes: a.count,
    })) ?? [];

  const historyByDay: Record<string, { correct: number; wrong: number }> = {};
  data?.quiz_history.forEach((q) => {
    const day = q.created_at.slice(5, 10);
    if (!historyByDay[day]) historyByDay[day] = { correct: 0, wrong: 0 };
    if (q.is_correct) historyByDay[day].correct++;
    else historyByDay[day].wrong++;
  });
  const trendData = Object.entries(historyByDay)
    .slice(0, 14)
    .map(([date, v]) => ({ date, ...v }));

  return (
    <div>
      <PageHeader
        title="Analytics"
        description="Topic mastery, quiz history, and study activity."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
          <Card>
            <CardHeader>
              <CardTitle>Topic Mastery</CardTitle>
            </CardHeader>
            <CardContent className="h-72">
              {masteryData.length === 0 ? (
                <p className="text-sm text-muted-foreground">No quiz data yet.</p>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={masteryData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff15" />
                    <XAxis dataKey="topic" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                    <YAxis tick={{ fill: "#94a3b8" }} domain={[0, 100]} />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(222 40% 10%)",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: 8,
                      }}
                    />
                    <Bar dataKey="mastery" fill="url(#masteryGrad)" radius={[6, 6, 0, 0]} />
                    <defs>
                      <linearGradient id="masteryGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#8b5cf6" />
                        <stop offset="100%" stopColor="#22d3ee" />
                      </linearGradient>
                    </defs>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}>
          <Card>
            <CardHeader>
              <CardTitle>Study Activity</CardTitle>
            </CardHeader>
            <CardContent className="h-72">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={activityData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#ffffff15" />
                  <XAxis dataKey="date" tick={{ fill: "#94a3b8", fontSize: 11 }} />
                  <YAxis tick={{ fill: "#94a3b8" }} allowDecimals={false} />
                  <Tooltip
                    contentStyle={{
                      background: "hsl(222 40% 10%)",
                      border: "1px solid rgba(255,255,255,0.1)",
                      borderRadius: 8,
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="quizzes"
                    stroke="#22d3ee"
                    strokeWidth={2}
                    dot={{ fill: "#8b5cf6" }}
                  />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          className="lg:col-span-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.15 }}
        >
          <Card>
            <CardHeader>
              <CardTitle>Quiz Performance Trend</CardTitle>
            </CardHeader>
            <CardContent className="h-64">
              {trendData.length === 0 ? (
                <p className="text-sm text-muted-foreground">Take quizzes to see trends.</p>
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={trendData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#ffffff15" />
                    <XAxis dataKey="date" tick={{ fill: "#94a3b8" }} />
                    <YAxis tick={{ fill: "#94a3b8" }} allowDecimals={false} />
                    <Tooltip
                      contentStyle={{
                        background: "hsl(222 40% 10%)",
                        border: "1px solid rgba(255,255,255,0.1)",
                        borderRadius: 8,
                      }}
                    />
                    <Bar dataKey="correct" stackId="a" fill="#34d399" radius={[0, 0, 0, 0]} />
                    <Bar dataKey="wrong" stackId="a" fill="#f87171" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          className="lg:col-span-2"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
        >
          <Card>
            <CardHeader>
              <CardTitle>Weak Topics</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="flex flex-wrap gap-2">
                {data?.weak_topics.length ? (
                  data.weak_topics.map((t) => (
                    <span
                      key={t.topic}
                      className="rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-sm"
                    >
                      {t.topic} — {t.mastery_percentage}%
                    </span>
                  ))
                ) : (
                  <p className="text-sm text-muted-foreground">No weak topics identified yet.</p>
                )}
              </div>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
