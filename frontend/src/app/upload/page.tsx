"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import Link from "next/link";
import {
  ChevronDown,
  FileUp,
  Trash2,
  FileText,
  Film,
  Globe,
  Image as ImageIcon,
  Link2,
  Mic,
  Play,
  Presentation,
  RotateCcw,
  X,
  Youtube,
} from "lucide-react";
import { DocumentInsights } from "@/components/DocumentInsights";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, Document, UploadResult } from "@/lib/api";

const MEDIA = [".mp3", ".m4a", ".wav", ".ogg", ".flac", ".mp4", ".webm", ".mov", ".mkv"];
const ACCEPTED = [".pdf", ".pptx", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg", ".webp", ...MEDIA];
const MAX_DOCUMENT_BYTES = 25 * 1024 * 1024;

function DocIcon({ type }: { type: string }) {
  if (type === "pdf") return <FileText className="h-8 w-8 text-red-400" />;
  if (type === "pptx") return <Presentation className="h-8 w-8 text-orange-400" />;
  if (type === "youtube") return <Youtube className="h-8 w-8 text-red-500" />;
  if (type === "web") return <Globe className="h-8 w-8 text-cyan-400" />;
  if (type === "image") return <ImageIcon className="h-8 w-8 text-emerald-400" />;
  if (type === "audio") return <Mic className="h-8 w-8 text-violet-400" />;
  if (type === "video") return <Film className="h-8 w-8 text-violet-400" />;
  return <FileText className="h-8 w-8 text-sky-400" />;
}

function describeResult(result: UploadResult) {
  if (result.media_status) return `Added "${result.title}". Transcribing on this computer; progress is shown below.`;
  const base = result.empty
    ? `Added "${result.title}" but found no readable text.`
    : `Added "${result.title}" — ${result.chunk_count} chunks stored. Writing a summary…`;
  return result.warnings?.length ? `${base} ${result.warnings.join(" ")}` : base;
}

export default function UploadPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [url, setUrl] = useState("");
  const [importing, setImporting] = useState(false);

  const load = useCallback(() => {
    api.documents().then(setDocs).catch(console.error).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Summaries are written in the background after upload; poll until they finish.
  const summarizing = docs.some(
    (d) =>
      d.summary_status === "pending" ||
      d.summary_status === "running" ||
      d.media_status === "pending" ||
      d.media_status === "running"
  );
  useEffect(() => {
    if (!summarizing) return;
    const id = setInterval(load, 3000);
    return () => clearInterval(id);
  }, [summarizing, load]);

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    setMessage("");
    try {
      for (const file of Array.from(files)) {
        const name = file.name.toLowerCase();
        if (!ACCEPTED.some((ext) => name.endsWith(ext))) {
          setMessage(`Supported files: ${ACCEPTED.join(", ")}`);
          continue;
        }
        const isMedia = MEDIA.some((ext) => name.endsWith(ext));
        if (!isMedia && file.size > MAX_DOCUMENT_BYTES) {
          setMessage(`"${file.name}" is over 25MB.`);
          continue;
        }
        const isImage = /\.(png|jpe?g|webp)$/.test(name);
        if (isImage) setMessage(`Reading "${file.name}" with the vision model…`);
        if (isMedia) setMessage(`Uploading "${file.name}"…`);
        const result = await api.upload(file);
        setMessage(describeResult(result));
      }
      load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const importLink = async () => {
    if (!url.trim()) return;
    setImporting(true);
    setMessage("Importing…");
    try {
      const result = await api.importUrl(url.trim());
      setMessage(describeResult(result));
      setUrl("");
      load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Import failed");
    } finally {
      setImporting(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const remove = async (id: number) => {
    await api.deleteDocument(id);
    load();
  };

  // Notes written in the app live on the Notes page.
  const library = docs.filter((d) => d.file_type !== "note");

  return (
    <div>
      <PageHeader
        title="Upload Materials"
        description="Add PDF books, Word notes, slides, photos of handwritten notes, web articles or YouTube videos. Scanned pages and photos are read by your AI model's vision."
      />

      <motion.div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        animate={{ scale: dragOver ? 1.02 : 1 }}
        className={`glass-card mb-8 flex flex-col items-center justify-center border-2 border-dashed p-12 transition-colors ${
          dragOver ? "border-primary bg-primary/10" : "border-white/20"
        }`}
      >
        <FileUp className="mb-4 h-12 w-12 text-violet-400" />
        <p className="mb-2 text-lg font-medium">Drag & drop files here</p>
        <p className="mb-4 text-sm text-muted-foreground">
          PDF, DOCX, PPTX, TXT, MD or images (max 25MB) · lecture recordings: MP3, M4A, WAV, MP4, WEBM (max 1GB)
        </p>
        <label className="cursor-pointer">
          <input
            type="file"
            accept={ACCEPTED.join(",")}
            multiple
            className="hidden"
            disabled={uploading}
            onChange={(e) => handleFiles(e.target.files)}
          />
          <span className="inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-lg">
            {uploading ? "Processing…" : "Browse files"}
          </span>
        </label>
      </motion.div>

      <div className="glass-card mb-8 flex flex-col gap-2 p-4 sm:flex-row sm:items-center">
        <Link2 className="hidden h-5 w-5 shrink-0 text-violet-400 sm:block" />
        <Input
          placeholder="Paste a web article, YouTube video, or link to a PDF"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && importLink()}
          disabled={importing}
        />
        <Button onClick={importLink} disabled={importing || !url.trim()}>
          {importing ? "Importing…" : "Import link"}
        </Button>
      </div>

      <AnimatePresence>
        {message && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mb-4 text-sm text-cyan-400"
          >
            {message}
          </motion.p>
        )}
      </AnimatePresence>

      <h2 className="mb-4 text-lg font-semibold">Your Library</h2>
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : library.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No documents yet. Upload your first study material above.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {library.map((doc, i) => (
            <motion.div
              key={doc.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Card>
                <div className="flex flex-row items-center justify-between gap-4">
                  <button
                    className="flex flex-1 items-center gap-4 px-6 py-4 text-left"
                    onClick={() => setExpanded(expanded === doc.id ? null : doc.id)}
                  >
                    <DocIcon type={doc.file_type} />
                    <div>
                      <p className="font-medium">{doc.title || doc.filename}</p>
                      <p className="text-sm text-muted-foreground">
                        {doc.topic} · {doc.file_type.toUpperCase()} · {doc.chunk_count} chunks
                      </p>
                      <MediaStatus doc={doc} />
                    </div>
                    <ChevronDown
                      className={`ml-auto h-4 w-4 text-muted-foreground transition-transform ${
                        expanded === doc.id ? "rotate-180" : ""
                      }`}
                    />
                  </button>
                  <MediaActions doc={doc} onChange={load} />
                  <Button variant="ghost" size="icon" className="mr-4" onClick={() => remove(doc.id)}>
                    <Trash2 className="h-4 w-4 text-red-400" />
                  </Button>
                </div>
                {expanded === doc.id && (
                  <DocumentInsights
                    doc={doc}
                    onChange={(updated) => setDocs((all) => all.map((d) => (d.id === updated.id ? updated : d)))}
                  />
                )}
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}

function MediaStatus({ doc }: { doc: Document }) {
  if (!doc.media_status || doc.media_status === "done") return null;
  if (doc.media_status === "pending") return <p className="text-xs text-violet-300">Waiting to transcribe…</p>;
  if (doc.media_status === "running") {
    const pct = Math.round((doc.media_progress ?? 0) * 100);
    return (
      <div className="mt-1 w-48">
        <p className="text-xs text-violet-300">
          Transcribing… {pct}%{pct === 0 ? " (the first run downloads the speech model)" : ""}
        </p>
        <div className="mt-1 h-1 rounded-full bg-white/10">
          <div className="h-1 rounded-full bg-violet-400 transition-all" style={{ width: `${Math.max(2, pct)}%` }} />
        </div>
      </div>
    );
  }
  if (doc.media_status === "cancelled") return <p className="text-xs text-muted-foreground">Transcription cancelled.</p>;
  return <p className="text-xs text-red-400">Transcription failed: {doc.media_error}</p>;
}

function MediaActions({ doc, onChange }: { doc: Document; onChange: () => void }) {
  if (doc.file_type !== "audio" && doc.file_type !== "video") return null;
  const run = (action: Promise<unknown>) => action.then(onChange).catch(onChange);
  if (doc.media_status === "pending" || doc.media_status === "running") {
    return (
      <Button variant="ghost" size="sm" onClick={() => run(api.cancelTranscription(doc.id))}>
        <X className="h-4 w-4" /> Cancel
      </Button>
    );
  }
  if (doc.media_status === "failed" || doc.media_status === "cancelled") {
    return (
      <Button variant="ghost" size="sm" onClick={() => run(api.retryTranscription(doc.id))}>
        <RotateCcw className="h-4 w-4" /> Retry
      </Button>
    );
  }
  return (
    <Link href={`/media?doc=${doc.id}`}>
      <Button variant="ghost" size="sm">
        <Play className="h-4 w-4" /> Play
      </Button>
    </Link>
  );
}
