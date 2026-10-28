"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { BarChart3, Cpu, Download, HardDrive, Mic, ShieldCheck, Star, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, CatalogModel, GroundingSettings, OllamaOverview, pullOllamaModel, TranscriptionSettings } from "@/lib/api";

const PURPOSE: Record<CatalogModel["purpose"], string> = {
  chat: "Chat & tutoring",
  vision: "Vision (photos, scans)",
  embedding: "Search by meaning",
};

/** Download, remove and choose local Ollama models, with suggestions for this computer. */
export function ModelManagerCard() {
  const [data, setData] = useState<OllamaOverview | null>(null);
  const [pulling, setPulling] = useState<Record<string, { status: string; percent?: number | null; error?: string }>>({});
  const [custom, setCustom] = useState("");

  const load = useCallback(() => {
    api.ollamaOverview().then(setData).catch(() => {});
  }, []);
  useEffect(load, [load]);

  const pull = async (name: string) => {
    setPulling((p) => ({ ...p, [name]: { status: "starting" } }));
    try {
      await pullOllamaModel(name, (e) =>
        setPulling((p) => ({ ...p, [name]: { status: e.status, percent: e.percent ?? p[name]?.percent, error: e.error } }))
      );
    } catch (e) {
      setPulling((p) => ({ ...p, [name]: { status: "error", error: e instanceof Error ? e.message : "failed" } }));
    }
    load();
  };

  const remove = async (name: string) => {
    if (!confirm(`Delete ${name} from this computer?`)) return;
    await api.deleteOllamaModel(name).catch(() => {});
    load();
  };

  if (!data) return null;
  const { system } = data;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <HardDrive className="h-5 w-5 text-violet-400" /> Local models (Ollama)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <p className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span className="flex items-center gap-1">
            <Cpu className="h-3.5 w-3.5" /> {system.cpu_count} CPU threads
          </span>
          <span>
            RAM {system.ram_available_gb} GB free of {system.ram_total_gb} GB
          </span>
          <span>{system.gpu ? `GPU: ${system.gpu.name} (${system.gpu.memory_gb ?? "?"} GB)` : "No NVIDIA GPU found"}</span>
          <span>Models up to about {Math.max(0, system.model_budget_gb - 1.5).toFixed(1)} GB should run smoothly</span>
        </p>
        {data.error && <p className="text-xs text-amber-300">{data.error}. Install it from ollama.com, then reload.</p>}

        {data.installed.length > 0 && (
          <div>
            <p className="mb-1 text-xs font-medium">Installed</p>
            {data.installed.map((m) => (
              <div key={m.name} className="flex items-center gap-2 border-t border-white/5 py-1.5 text-xs">
                <span className="font-medium">{m.name}</span>
                <span className="text-muted-foreground">
                  {m.size_gb} GB{m.parameters ? ` · ${m.parameters}` : ""}
                  {m.running ? " · loaded now" : ""}
                </span>
                <button className="ml-auto" aria-label={`Delete ${m.name}`} onClick={() => remove(m.name)}>
                  <Trash2 className="h-3.5 w-3.5 text-red-400" />
                </button>
              </div>
            ))}
          </div>
        )}

        {(["chat", "vision", "embedding"] as const).map((purpose) => (
          <div key={purpose}>
            <p className="mb-1 text-xs font-medium">{PURPOSE[purpose]}</p>
            {data.catalog
              .filter((m) => m.purpose === purpose)
              .map((m) => {
                const p = pulling[m.name];
                const busy = p && !["success", "error"].includes(p.status);
                return (
                  <div key={m.name} className={`flex items-center gap-2 py-1 text-xs ${m.fits ? "" : "opacity-50"}`}>
                    {m.recommended && <Star className="h-3 w-3 shrink-0 fill-amber-300 text-amber-300" aria-label="Recommended" />}
                    <span className="w-36 shrink-0 font-medium">{m.name}</span>
                    <span className="w-14 shrink-0 text-muted-foreground">≈{m.size_gb} GB</span>
                    <span className="min-w-0 flex-1 truncate text-muted-foreground" title={m.note}>
                      {m.fits ? m.note : "Probably too big for this computer"}
                    </span>
                    {m.installed ? (
                      <span className="text-emerald-300">Installed</span>
                    ) : busy ? (
                      <span className="w-28 text-right text-violet-300">
                        {p.percent != null ? `${Math.round(p.percent)}%` : p.status}
                      </span>
                    ) : (
                      <Button size="sm" variant="outline" className="h-7" onClick={() => pull(m.name)} disabled={!!data.error}>
                        <Download className="h-3 w-3" /> Get
                      </Button>
                    )}
                    {p?.error && <span className="text-red-400">{p.error}</span>}
                  </div>
                );
              })}
          </div>
        ))}

        <div className="flex gap-2 border-t border-white/10 pt-3">
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="Any other model, e.g. phi4-mini"
            className="h-8 flex-1 rounded-md border border-white/15 bg-white/5 px-2 text-xs"
          />
          <Button size="sm" variant="outline" disabled={!custom.trim() || !!data.error} onClick={() => pull(custom.trim())}>
            <Download className="h-3 w-3" /> Download
          </Button>
        </div>
        {custom.trim() && pulling[custom.trim()] && (
          <p className="text-xs text-violet-300">
            {pulling[custom.trim()].error ??
              `${pulling[custom.trim()].status}${pulling[custom.trim()].percent != null ? ` ${Math.round(pulling[custom.trim()].percent!)}%` : ""}`}
          </p>
        )}
        <p className="text-xs text-muted-foreground">
          After downloading, pick the model under AI Model above (chat), as the vision model, or under Search by meaning.
        </p>
      </CardContent>
    </Card>
  );
}

function Toggle({ checked, onChange, label, hint }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <input type="checkbox" className="mt-1" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span>
        <span className="block">{label}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
    </label>
  );
}

export function GroundingCard() {
  const [s, setS] = useState<GroundingSettings | null>(null);
  useEffect(() => {
    api.groundingSettings().then(setS).catch(() => {});
  }, []);
  if (!s) return null;
  const save = async (body: Partial<GroundingSettings>) => setS(await api.saveGroundingSettings(body));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-emerald-400" /> Answer checking
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <Toggle
          checked={s.enabled}
          onChange={(enabled) => save({ enabled })}
          label="Check tutor answers against your notes"
          hint="Shows how much of each answer your notes support, and says plainly when your notes do not cover a question."
        />
        <Toggle
          checked={s.ai_check}
          onChange={(ai_check) => save({ ai_check })}
          label="Double-check unclear sentences with the AI"
          hint="More accurate, but one extra AI call per answer (slower, and costs tokens on paid APIs)."
        />
      </CardContent>
    </Card>
  );
}

export function TranscriptionCard() {
  const [s, setS] = useState<TranscriptionSettings | null>(null);
  useEffect(() => {
    api.transcriptionSettings().then(setS).catch(() => {});
  }, []);
  if (!s) return null;
  const save = async (body: { model?: string; language?: string }) => setS(await api.saveTranscriptionSettings(body));
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mic className="h-5 w-5 text-violet-400" /> Lecture transcription
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        {!s.installed && (
          <p className="text-xs text-amber-300">
            faster-whisper is not installed. Run pip install -r requirements.txt in the backend folder.
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-xs text-muted-foreground">Speech model</label>
          <select
            value={s.model}
            onChange={(e) => save({ model: e.target.value })}
            className="h-9 rounded-md border border-white/15 bg-white/5 px-2 text-sm"
          >
            {s.models.map((m) => (
              <option key={m} value={m} className="bg-slate-900">
                {m}
              </option>
            ))}
          </select>
          <label className="text-xs text-muted-foreground">Language</label>
          <input
            defaultValue={s.language}
            onBlur={(e) => e.target.value !== s.language && save({ language: e.target.value })}
            placeholder="auto"
            className="h-9 w-20 rounded-md border border-white/15 bg-white/5 px-2 text-sm"
          />
        </div>
        <p className="text-xs text-muted-foreground">
          Runs on this computer; audio never leaves it. tiny ≈ 75 MB (fastest), base ≈ 145 MB, small ≈ 480 MB, medium ≈
          1.5 GB (most accurate). The model downloads the first time it is used. Language is a code like en or bn; leave
          empty to detect it.
        </p>
      </CardContent>
    </Card>
  );
}

export function UsageLinkCard() {
  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-3 p-5 text-sm">
        <span className="flex items-center gap-2">
          <BarChart3 className="h-5 w-5 text-cyan-400" /> Tokens and cost per feature, with a monthly budget
        </span>
        <Link href="/usage">
          <Button variant="outline" size="sm">
            Open usage
          </Button>
        </Link>
      </CardContent>
    </Card>
  );
}
