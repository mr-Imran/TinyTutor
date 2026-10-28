"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Download, Image as ImageIcon, Layers, Mic, Sparkles, SquareDashed, Trash2, Upload } from "lucide-react";
import { ClozeCreator, OcclusionEditor } from "@/components/CardCreators";
import { FlashcardBack, FlashcardFront, FlashcardSummary } from "@/components/FlashcardFace";
import { PageHeader } from "@/components/PageHeader";
import { StatCard } from "@/components/StatCard";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, downloads, Flashcard, FlashcardStats } from "@/lib/api";
import { spokenCard } from "@/lib/cards";
import { canSpeak, speak, stopSpeaking, useSpeechRecognition } from "@/lib/speech";

// SM-2 grades behind each answer button.
const GRADES = [
  { grade: 1, label: "Again", hint: "Forgot", className: "bg-red-500/20 hover:bg-red-500/35" },
  { grade: 3, label: "Hard", hint: "Barely", className: "bg-orange-500/20 hover:bg-orange-500/35" },
  { grade: 4, label: "Good", hint: "Recalled", className: "bg-emerald-500/20 hover:bg-emerald-500/35" },
  { grade: 5, label: "Easy", hint: "Instant", className: "bg-cyan-500/20 hover:bg-cyan-500/35" },
];

function gradeFromSpeech(text: string): number | null {
  const t = text.toLowerCase();
  if (/\b(again|forgot|wrong|no idea)\b/.test(t)) return 1;
  if (/\bhard\b/.test(t)) return 3;
  if (/\b(good|right|correct)\b/.test(t)) return 4;
  if (/\beasy\b/.test(t)) return 5;
  return null;
}

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
  const [oral, setOral] = useState(false);
  const [oralSupported, setOralSupported] = useState(false);
  const [spokenAnswer, setSpokenAnswer] = useState("");
  const [importTopic, setImportTopic] = useState("Imported");
  const [maker, setMaker] = useState<"ai" | "cloze" | "image">("ai");
  const oralPhase = useRef<"answer" | "grade">("answer");

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

  // Oral mode: the card is read aloud, the spoken answer flips it, then a spoken grade moves on.
  const voice = useSpeechRecognition((text) => {
    if (oralPhase.current === "answer") {
      setSpokenAnswer(text);
      setFlipped(true);
    } else {
      const grade = gradeFromSpeech(text);
      if (grade) review(grade);
      else speak("Say again, hard, good, or easy.", voice.start);
    }
  });

  useEffect(() => {
    setOralSupported(canSpeak() && voice.supported);
  }, [voice.supported]);

  useEffect(() => {
    if (!oral || !current) return;
    if (!flipped) {
      oralPhase.current = "answer";
      setSpokenAnswer("");
      speak(spokenCard(current, "front"), voice.start);
    } else {
      oralPhase.current = "grade";
      speak(`The answer is: ${spokenCard(current, "back")}. How did you do? Say again, hard, good, or easy.`, voice.start);
    }
    return () => {
      stopSpeaking();
      voice.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-run per card/side, not per render
  }, [oral, current?.id, flipped]);

  const importDeck = async (file: File | undefined) => {
    if (!file) return;
    setMessage("Importing…");
    try {
      const r = await api.importFlashcards(file, importTopic);
      setMessage(`Imported ${r.imported} cards${r.skipped ? ` (${r.skipped} skipped as duplicates or empty)` : ""}.`);
      load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Import failed");
    }
  };

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
                    <p className="mb-4 flex items-center justify-between text-xs text-muted-foreground">
                      <span>
                        {current.topic} · {queue.length} left
                      </span>
                      {oral && (
                        <span className={`flex items-center gap-1 ${voice.listening ? "text-red-400" : ""}`}>
                          <Mic className="h-3 w-3" />
                          {voice.listening ? voice.interim || "Listening…" : "Speaking…"}
                        </span>
                      )}
                    </p>
                    <div
                      role="button"
                      tabIndex={-1}
                      className="flex flex-1 cursor-pointer flex-col items-center justify-center text-center"
                      onClick={() => setFlipped(true)}
                    >
                      {/* Image cards show the revealed picture in place of the question picture. */}
                      {!(flipped && current.card_type === "occlusion") && <FlashcardFront card={current} />}
                      {flipped ? (
                        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-6 border-t border-white/10 pt-6">
                          {spokenAnswer && <p className="mb-2 text-xs text-cyan-300">You said: “{spokenAnswer}”</p>}
                          <FlashcardBack card={current} />
                        </motion.div>
                      ) : (
                        <p className="mt-6 text-xs text-muted-foreground">Click or press space to show the answer</p>
                      )}
                    </div>
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
          <KeyboardShortcuts enabled={!!current && !oral} flipped={flipped} onFlip={() => setFlipped(true)} onGrade={review} />
          {oralSupported && (
            <div className="mt-3 flex justify-center">
              <Button
                variant={oral ? "default" : "outline"}
                size="sm"
                onClick={() => {
                  setFlipped(false);
                  setOral(!oral);
                }}
                disabled={!current}
              >
                <Mic className="h-3.5 w-3.5" /> {oral ? "Stop oral practice" : "Oral practice (hands-free)"}
              </Button>
            </div>
          )}
          {voice.error && <p className="mt-2 text-center text-xs text-red-400">{voice.error}</p>}
        </div>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Make cards</CardTitle>
            <div className="mt-2 grid grid-cols-3 gap-1 rounded-lg bg-white/5 p-1 text-xs">
              {([
                ["ai", "AI", Sparkles],
                ["cloze", "Blanks", SquareDashed],
                ["image", "Image", ImageIcon],
              ] as const).map(([key, label, Icon]) => (
                <button
                  key={key}
                  onClick={() => setMaker(key)}
                  className={`flex items-center justify-center gap-1 rounded-md py-1.5 ${maker === key ? "bg-primary text-white" : "hover:bg-white/10"}`}
                >
                  <Icon className="h-3.5 w-3.5" /> {label}
                </button>
              ))}
            </div>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            {maker === "cloze" ? (
              <ClozeCreator topics={topics} onCreated={(m) => { setMessage(m); load(); }} />
            ) : maker === "image" ? (
              <OcclusionEditor topics={topics} onCreated={(m) => { setMessage(m); load(); }} />
            ) : topics.length === 0 ? (
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
            <div className="space-y-2 border-t border-white/10 pt-3">
              <p className="text-xs font-medium">Export</p>
              <div className="flex gap-2">
                <a href={downloads.flashcardsApkg()} className="flex-1">
                  <Button variant="outline" size="sm" className="w-full" disabled={!stats?.total}>
                    <Download className="h-3.5 w-3.5" /> Anki
                  </Button>
                </a>
                <a href={downloads.flashcardsCsv()} className="flex-1">
                  <Button variant="outline" size="sm" className="w-full" disabled={!stats?.total}>
                    <Download className="h-3.5 w-3.5" /> CSV
                  </Button>
                </a>
              </div>
              <p className="pt-1 text-xs font-medium">Import (.apkg, .csv, Anki .txt)</p>
              <input
                className="h-8 w-full rounded-md border border-white/15 bg-white/5 px-2 text-xs"
                value={importTopic}
                onChange={(e) => setImportTopic(e.target.value)}
                placeholder="Topic for cards without a deck"
              />
              <label className="block cursor-pointer">
                <input
                  type="file"
                  accept=".apkg,.csv,.txt,.tsv"
                  className="hidden"
                  onChange={(e) => {
                    importDeck(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
                <span className="inline-flex h-8 w-full items-center justify-center gap-2 rounded-md border border-white/20 bg-white/5 text-xs hover:bg-white/10">
                  <Upload className="h-3.5 w-3.5" /> Choose file
                </span>
              </label>
            </div>
          </CardContent>
        </Card>
      </div>

      {showAll && (
        <div className="mt-6 space-y-2">
          {allCards.map((c) => (
            <Card key={c.id}>
              <CardContent className="flex items-start justify-between gap-4 p-4 text-sm">
                <div className="min-w-0">
                  <FlashcardSummary card={c} />
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
      const t = e.target;
      if (t instanceof HTMLInputElement || t instanceof HTMLSelectElement || t instanceof HTMLTextAreaElement) return;
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
