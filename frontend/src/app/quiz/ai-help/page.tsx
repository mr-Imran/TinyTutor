"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { motion } from "framer-motion";
import { ArrowLeft, BookOpen, Sparkles } from "lucide-react";
import Link from "next/link";
import { ExplanationView } from "@/components/ExplanationView";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, AiHelpResult } from "@/lib/api";

function AiHelpContent() {
  const router = useRouter();
  const params = useSearchParams();
  const question = params.get("q") || "";
  const userAnswer = params.get("answer") || "";
  const topic = params.get("topic") || undefined;

  const [data, setData] = useState<AiHelpResult | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!question.trim()) {
      setError("No question provided.");
      setLoading(false);
      return;
    }
    api
      .aiHelp({
        question: question.trim(),
        user_answer: userAnswer.trim() || undefined,
        topic,
      })
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load help"))
      .finally(() => setLoading(false));
  }, [question, userAnswer, topic]);

  return (
    <div className="mx-auto max-w-3xl">
      <Button variant="ghost" className="mb-4" onClick={() => router.back()}>
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Quiz
      </Button>

      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}>
        <div className="mb-6 flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-gradient-to-br from-violet-500 to-cyan-500">
            <Sparkles className="h-6 w-6 text-white" />
          </div>
          <div>
            <h1 className="text-2xl font-bold">AI Help</h1>
            <p className="text-sm text-muted-foreground">Simple explanation in easy words</p>
          </div>
        </div>

        <Card className="mb-6 border-violet-500/20">
          <CardHeader>
            <CardTitle className="text-sm text-muted-foreground">Your question</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-lg font-medium">{question}</p>
            {userAnswer && (
              <p className="mt-3 rounded-lg bg-white/5 p-3 text-sm text-muted-foreground">
                <span className="text-xs uppercase text-violet-400">Your answer: </span>
                {userAnswer}
              </p>
            )}
          </CardContent>
        </Card>

        {loading && (
          <Card>
            <CardContent className="space-y-3 py-8">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-3/4" />
            </CardContent>
          </Card>
        )}

        {error && (
          <Card className="border-red-500/30">
            <CardContent className="py-8 text-center text-red-400">{error}</CardContent>
          </Card>
        )}

        {data && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
            <div
              className={`mb-4 rounded-lg px-4 py-2 text-sm ${
                data.matched
                  ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                  : "border border-amber-500/30 bg-amber-500/10 text-amber-200"
              }`}
            >
              {data.matched
                ? "Found related content in your study materials."
                : "Not in your uploaded notes — general explanation below."}
            </div>

            {data.chunks.length > 0 && (
              <Card className="mb-4">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <BookOpen className="h-4 w-4" /> Related materials
                  </CardTitle>
                </CardHeader>
                <CardContent className="flex flex-wrap gap-2">
                  {data.chunks.map((c, i) => (
                    <span key={i} className="rounded-full bg-white/10 px-3 py-1 text-xs">
                      {c.title || c.source || c.topic}
                    </span>
                  ))}
                </CardContent>
              </Card>
            )}

            <Card>
              <CardContent className="py-6">
                <ExplanationView text={data.explanation} />
              </CardContent>
            </Card>

            <div className="mt-6 flex flex-wrap gap-3">
              <Link href="/quiz">
                <Button>Try another question</Button>
              </Link>
              <Link href="/database">
                <Button variant="outline">Add study context</Button>
              </Link>
            </div>
          </motion.div>
        )}
      </motion.div>
    </div>
  );
}

export default function AiHelpPage() {
  return (
    <Suspense
      fallback={
        <div className="space-y-4">
          <Skeleton className="h-10 w-32" />
          <Skeleton className="h-48" />
        </div>
      }
    >
      <AiHelpContent />
    </Suspense>
  );
}
