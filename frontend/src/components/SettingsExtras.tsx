"use client";

import { useEffect, useState } from "react";
import { Archive, Download, Eye, RefreshCw, Sparkles, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { api, downloads, EmbeddingSettings, LlmProvider } from "@/lib/api";

const EMBED_LABELS: Record<string, string> = {
  auto: "Automatic",
  ollama: "Ollama (local)",
  openai: "OpenAI-compatible",
  gemini: "Google Gemini",
  off: "Off (keywords only)",
};

export function EmbeddingsCard() {
  const [s, setS] = useState<EmbeddingSettings | null>(null);
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const apply = (next: EmbeddingSettings) => {
    setS(next);
    setModel(next.model ?? "");
  };

  useEffect(() => {
    api.embeddingSettings().then(apply).catch(() => {});
  }, []);

  if (!s) return null;

  const save = async (body: { provider?: string; model?: string }) => {
    setMessage("");
    try {
      apply(await api.saveEmbeddingSettings(body));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    }
  };

  const reindex = async () => {
    setBusy(true);
    setMessage("Building the index — this can take a while for big libraries…");
    try {
      const r = await api.reindexEmbeddings();
      apply(r);
      setMessage(r.error ? `Could not embed: ${r.error}` : `Indexed ${r.embedded} new chunks.`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Indexing failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-violet-400" /> Search by meaning
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          Embeddings let the tutor and Search find notes that mean the same thing in different words. Claude has
          no embeddings API, so Automatic uses a local Ollama model (<code>ollama pull nomic-embed-text</code>)
          unless your chat provider is OpenAI-compatible or Gemini.
        </p>
        <select
          value={s.choice}
          onChange={(e) => save({ provider: e.target.value })}
          className="h-10 w-full rounded-lg border border-white/15 bg-white/5 px-3 text-sm"
        >
          {s.choices.map((c) => (
            <option key={c} value={c} className="bg-slate-900">
              {EMBED_LABELS[c] ?? c}
              {c === "auto" && s.choice === "auto" && s.provider ? ` → ${EMBED_LABELS[s.provider]}` : ""}
            </option>
          ))}
        </select>
        {s.provider && (
          <>
            <div className="flex gap-2">
              <Input value={model} onChange={(e) => setModel(e.target.value)} placeholder={s.defaults[s.provider]} />
              <Button variant="outline" onClick={() => save({ model })} disabled={model === s.model}>
                Save
              </Button>
            </div>
            <div>
              <p className="mb-1 flex justify-between text-xs text-muted-foreground">
                <span>Indexed chunks</span>
                <span>
                  {s.indexed} / {s.total}
                </span>
              </p>
              <Progress value={s.total ? (s.indexed / s.total) * 100 : 0} />
            </div>
            <Button variant="outline" size="sm" onClick={reindex} disabled={busy || s.indexed >= s.total}>
              <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} />
              {s.indexed >= s.total ? "Index up to date" : "Build index"}
            </Button>
          </>
        )}
        {message && <p className="text-xs text-cyan-400">{message}</p>}
      </CardContent>
    </Card>
  );
}

/** Optional separate model for reading images (useful with Ollama text-only models). */
export function VisionModelField({ provider }: { provider: LlmProvider }) {
  const [models, setModels] = useState<Record<LlmProvider, string> | null>(null);
  const [value, setValue] = useState("");
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    api.visionSettings().then((m) => {
      setModels(m);
      setValue(m[provider] ?? "");
    }).catch(() => {});
  }, [provider]);

  if (!models) return null;

  const save = async () => {
    const m = await api.saveVisionSettings(provider, value);
    setModels(m);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <label className="block space-y-1">
      <span className="flex items-center gap-1 text-xs text-muted-foreground">
        <Eye className="h-3 w-3" /> Vision model for photos and scanned pages (optional)
      </span>
      <div className="flex gap-2">
        <Input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={provider === "ollama" ? "e.g. qwen2.5vl or llava — blank uses the chat model" : "Blank uses the chat model"}
        />
        <Button variant="outline" onClick={save} disabled={value === (models[provider] ?? "")}>
          {saved ? "Saved" : "Save"}
        </Button>
      </div>
    </label>
  );
}

export function DataCard() {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  const restore = async (file: File | undefined) => {
    if (!file) return;
    const ok = window.confirm(
      "Restoring replaces ALL current documents, flashcards, chats and progress with the backup. " +
        "A safety copy of the current database is kept in backend/data. Continue?"
    );
    if (!ok) return;
    setBusy(true);
    setMessage("Restoring…");
    try {
      const r = await api.restoreBackup(file);
      setMessage(
        `Restored ${r.documents} documents, ${r.flashcards} flashcards and ${r.files} files. ` +
          `Previous data saved as ${r.safety_copy}.`
      );
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Restore failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Archive className="h-5 w-5 text-amber-300" /> Backup &amp; export
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <p className="text-xs text-muted-foreground">
          A backup is one .zip with your database and every uploaded file. Keep it somewhere safe, or use it to move
          TinyTutor to another computer.
        </p>
        <div className="flex flex-wrap gap-2">
          <a href={downloads.backup()}>
            <Button size="sm">
              <Download className="h-3.5 w-3.5" /> Download backup
            </Button>
          </a>
          <label className="cursor-pointer">
            <input
              type="file"
              accept=".zip"
              className="hidden"
              disabled={busy}
              onChange={(e) => {
                restore(e.target.files?.[0]);
                e.target.value = "";
              }}
            />
            <span className="inline-flex h-8 items-center gap-2 rounded-md border border-white/20 bg-white/5 px-3 text-xs hover:bg-white/10">
              <Upload className="h-3.5 w-3.5" /> Restore from backup
            </span>
          </label>
        </div>
        <div className="flex flex-wrap gap-2 border-t border-white/10 pt-3">
          <a href={downloads.flashcardsApkg()}>
            <Button variant="outline" size="sm">Flashcards → Anki</Button>
          </a>
          <a href={downloads.flashcardsCsv()}>
            <Button variant="outline" size="sm">Flashcards → CSV</Button>
          </a>
          <a href={downloads.quizHistoryCsv()}>
            <Button variant="outline" size="sm">Quiz history → CSV</Button>
          </a>
        </div>
        {message && <p className="text-xs text-cyan-400">{message}</p>}
      </CardContent>
    </Card>
  );
}
