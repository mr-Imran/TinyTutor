"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { api, Document, formatTimestamp, mediaUrl } from "@/lib/api";

type Line = { id: number; content: string; start_seconds: number | null };

function Player() {
  const params = useSearchParams();
  const docId = Number(params.get("doc"));
  const start = Number(params.get("t") ?? 0);
  const [doc, setDoc] = useState<Document | null>(null);
  const [lines, setLines] = useState<Line[]>([]);
  const [now, setNow] = useState(0);
  const [error, setError] = useState("");
  const media = useRef<HTMLMediaElement | null>(null);
  const active = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!docId) return;
    api.document(docId).then(setDoc).catch(() => setError("Recording not found."));
    api.transcript(docId).then(setLines).catch(() => {});
  }, [docId]);

  const seek = (seconds: number) => {
    const el = media.current;
    if (!el) return;
    el.currentTime = seconds;
    el.play().catch(() => {}); // autoplay may be blocked until the user interacts
  };

  // Jump to the cited moment once the media knows its duration.
  const onLoaded = () => {
    if (start && media.current) media.current.currentTime = start;
  };

  const current = lines.reduce<Line | null>(
    (best, l) => (l.start_seconds != null && l.start_seconds <= now + 0.5 ? l : best),
    null
  );

  useEffect(() => {
    active.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [current?.id]);

  if (!docId) return <p className="text-sm text-muted-foreground">No recording selected.</p>;
  if (error) return <p className="text-sm text-red-400">{error}</p>;

  const props = {
    src: mediaUrl(docId),
    controls: true,
    onLoadedMetadata: onLoaded,
    onTimeUpdate: (e: React.SyntheticEvent<HTMLMediaElement>) => setNow(e.currentTarget.currentTime),
    className: "w-full rounded-lg",
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="h-fit">
        <CardContent className="space-y-3 p-4">
          <p className="font-medium">{doc?.title ?? "Loading…"}</p>
          {doc?.file_type === "video" ? (
            <video ref={(el) => { media.current = el; }} {...props} />
          ) : (
            <audio ref={(el) => { media.current = el; }} {...props} />
          )}
          <p className="text-xs text-muted-foreground">
            {doc?.topic}
            {doc?.duration_seconds ? ` · ${formatTimestamp(Math.round(doc.duration_seconds))}` : ""} · transcribed on
            this computer
          </p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="max-h-[70vh] space-y-1 overflow-y-auto p-4 text-sm">
          {lines.length === 0 && <p className="text-muted-foreground">No transcript yet.</p>}
          {lines.map((l) => {
            const isCurrent = l.id === current?.id;
            return (
              <button
                key={l.id}
                ref={isCurrent ? active : undefined}
                onClick={() => l.start_seconds != null && seek(l.start_seconds)}
                className={`flex w-full gap-3 rounded-md p-2 text-left ${isCurrent ? "bg-violet-500/20" : "hover:bg-white/5"}`}
              >
                <span className="w-12 shrink-0 font-mono text-xs text-violet-300">
                  {l.start_seconds != null ? formatTimestamp(l.start_seconds) : ""}
                </span>
                <span className="leading-relaxed">{l.content}</span>
              </button>
            );
          })}
        </CardContent>
      </Card>
    </div>
  );
}

export default function MediaPage() {
  return (
    <div>
      <PageHeader title="Lecture" description="Click any line of the transcript to jump to that moment." />
      <Link href="/upload" className="mb-4 inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
        <ArrowLeft className="h-3 w-3" /> Back to your materials
      </Link>
      <Suspense fallback={null}>
        <Player />
      </Suspense>
    </div>
  );
}
