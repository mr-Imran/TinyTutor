"use client";

import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Layers, Sparkles, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, Flashcard, FlashcardStats } from "@/lib/api";

// SM-2 grades behind each answer button.
const GRADES = [
  { grade: 1, label: "Again", hint: "Forgot", className: "bg-red-500/20 hover:bg-red-500/35" },
  { grade: 3, label: "Hard", hint: "Barely", className: "bg-orange-500/20 hover:bg-orange-500/35" },
  { grade: 4, label: "Good", hint: "Recalled", className: "bg-emerald-500/20 hover:bg-emerald-500/35" },
  { grade: 5, label: "Easy", hint: "Instant", className: "bg-cyan-500/20 hover:bg-cyan-500/35" },
];

export default function FlashcardsPage() {
  const [stats, setStats] = useState<FlashcardStats | null>(null);
  const [queue, setQueue] = useState<Flashcard[]>([]);
  const [flipped, setFlipped] = useState(false);
  const [topics, setTopics] = useState<string[]>([]);
  const [genTopic, setGenTopic] = useState("");
  const [generating, setGenerating] = useState(false);
  const [message, setMessage] = useState("");
  const [allCards, setAllCards] = useState<Flashcard[]>([]);
  const [showAll, setShowAll] = useState(false);

  const load = useCallback(() => {
    api.flashcardStats().then(setStats).catch(() => {});
    api.dueFlashcards(50).then(setQueue).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    api.topics().then((r) => {
      setTopics(r.topics);
      setGenTopic((t) => t || r.topics[0] || "");
    }).catch(() => {});
  }, [load]);

  useEffect(() => {
    if (showAll) api.flashcards().then(setAllCards).catch(() => {});
  }, [showAll, stats]);

  const generate = async () => {
    if (!genTopic) return;
    setGenerating(true);
    setMessage("");
    try {
      const { created } = await api.generateFlashcards({ topic: genTopic, count: 10 });
      setMessage(created.length ? `Added ${created.length} new cards for ${genTopic}.` : "No new cards — they may already exist.");
      load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not generate cards");
    } finally {
      setGenerating(false);
    }
  };

  const review = async (grade: number) => {
    const card = queue[0];
    if (!card) return;
    setFlipped(false);
    setQueue((q) => q.slice(1));
    await api.reviewFlashcard(card.id, grade).catch(() => {});
    api.flashcardStats().then(setStats).catch(() => {});
  };

  const remove = async (id: number) => {
    await api.deleteFlashcard(id);
    setAllCards((c) => c.filter((x) => x.id !== id));
    load();
  };

  const current = queue[0];

  return (
    <div>
      <PageHeader
        title="Flashcards"
        description="Spaced repetition: cards you find hard come back sooner, easy ones later. Reviews count toward topic mastery."
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard title="Due now" value={stats?.due ?? 0} icon={Layers} />
        <StatCard title="Total cards" value={stats?.total ?? 0} icon={Layers} />
        <StatCard title="Learned" value={stats?.learned ?? 0} icon={Sparkles} />
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <AnimatePresence mode="wait">
            {current ? (
              <motion.div key={current.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, x: -30 }}>
                <Card className="flex min-h-[18rem] flex-col">
                  <CardContent className="flex flex-1 flex-col p-6">
                    <p className="mb-4 text-xs text-muted-foreground">
                      {current.topic} · {queue.length} left
                    </p>
                    <button className="flex flex-1 flex-col items-center justify-center text-center" onClick={() => setFlipped(true)}>
                      <p className="text-xl font-medium">{current.front}</p>
                      {flipped ? (
                        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6 border-t border-white/10 pt-6 text-muted-foreground">
                          {current.back}
                        </motion.p>
                      ) : (
                        <p className="mt-6 text-xs text-muted-foreground">Click or press space to show the answer</p>
                      )}
                    </button>
                    {flipped ? (
                      <div className="mt-6 grid grid-cols-4 gap-2">
                        {GRADES.map((g) => (
                          <button key={g.grade} onClick={() => review(g.grade)} className={`rounded-lg px-2 py-2 text-sm ${g.className}`}>
                            <span className="block font-medium">{g.label}</span>
                            <span className="block text-xs text-muted-foreground">{g.hint}</span>
                          </button>
                        ))}
                      </div>
                    ) : (
                      <Button className="mt-6" onClick={() => setFlipped(true)}>
                        Show answer
                      </Button>
                    )}
                  </CardContent>
                </Card>
              </motion.div>
            ) : (
              <Card>
                <CardContent className="py-16 text-center text-muted-foreground">
                  {stats?.total ? "All caught up! Come back later for the next review." : "No cards yet — generate some from a topic."}
                </CardContent>
              </Card>
            )}
          </AnimatePresence>
          <KeyboardShortcuts enabled={!!current} flipped={flipped} onFlip={() => setFlipped(true)} onGrade={review} />
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-violet-400" /> Make cards with AI
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {topics.length === 0 ? (
              <p className="text-muted-foreground">Upload study material first.</p>
            ) : (
              <>
                <select
                  value={genTopic}
                  onChange={(e) => setGenTopic(e.target.value)}
                  className="h-10 w-full rounded-lg border border-white/15 bg-white/5 px-3 text-sm"
                >
                  {topics.map((t) => (
                    <option key={t} value={t} className="bg-slate-900">
                      {t}
                    </option>
                  ))}
                </select>
                <Button className="w-full" onClick={generate} disabled={generating}>
                  {generating ? "Writing cards…" : "Generate 10 cards"}
                </Button>
              </>
            )}
            {message && <p className="text-xs text-cyan-400">{message}</p>}
            {stats && stats.topics.length > 0 && (
              <div className="space-y-1 border-t border-white/10 pt-3">
                {stats.topics.map((t) => (
                  <p key={t.topic} className="flex justify-between text-xs text-muted-foreground">
                    <span className="truncate">{t.topic}</span>
                    <span>
                      {t.due} due / {t.total}
                    </span>
                  </p>
                ))}
              </div>
            )}
            <Button variant="ghost" size="sm" className="w-full" onClick={() => setShowAll((s) => !s)}>
              {showAll ? "Hide all cards" : "Manage all cards"}
            </Button>
          </CardContent>
        </Card>
      </div>

      {showAll && (
        <div className="mt-6 space-y-2">
          {allCards.map((c) => (
            <Card key={c.id}>
              <CardContent className="flex items-start justify-between gap-4 p-4 text-sm">
                <div>
                  <p className="font-medium">{c.front}</p>
                  <p className="text-muted-foreground">{c.back}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {c.topic} · next review {new Date(c.due_at + "Z").toLocaleDateString()}
                  </p>
                </div>
                <Button variant="ghost" size="icon" onClick={() => remove(c.id)} aria-label="Delete card">
                  <Trash2 className="h-4 w-4 text-red-400" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

function KeyboardShortcuts({
  enabled,
  flipped,
  onFlip,
  onGrade,
}: {
  enabled: boolean;
  flipped: boolean;
  onFlip: () => void;
  onGrade: (grade: number) => void;
}) {
  useEffect(() => {
    if (!enabled) return;
    const handler = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return;
      if (!flipped && (e.key === " " || e.key === "Enter")) {
        e.preventDefault();
        onFlip();
      } else if (flipped && ["1", "2", "3", "4"].includes(e.key)) {
        onGrade(GRADES[Number(e.key) - 1].grade);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [enabled, flipped, onFlip, onGrade]);
  return enabled ? <p className="mt-2 text-center text-xs text-muted-foreground">Keys: space to flip · 1-4 to grade</p> : null;
}
