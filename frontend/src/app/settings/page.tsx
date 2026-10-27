"use client";

import { useCallback, useEffect, useState } from "react";
import { motion } from "framer-motion";
import { CheckCircle2, Cpu, Database, KeyRound, RefreshCw, Server, XCircle } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { DataCard, EmbeddingsCard, VisionModelField } from "@/components/SettingsExtras";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, LlmHealth, LlmProvider, LlmSettings, LlmSettingsUpdate } from "@/lib/api";

const PROVIDERS: { id: LlmProvider; label: string; hint: string }[] = [
  { id: "ollama", label: "Ollama (local)", hint: "Private and free. Runs on your computer." },
  { id: "anthropic", label: "Anthropic Claude", hint: "Needs an Anthropic API key." },
  { id: "openai", label: "OpenAI-compatible", hint: "OpenAI, Groq, OpenRouter, LM Studio, vLLM…" },
  { id: "gemini", label: "Google Gemini", hint: "Needs a Google AI Studio API key." },
];

const KEY_FIELD: Partial<Record<LlmProvider, keyof LlmSettings["keys"]>> = {
  anthropic: "anthropic_api_key",
  openai: "openai_api_key",
  gemini: "gemini_api_key",
};

export default function SettingsPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const [settings, setSettings] = useState<LlmSettings | null>(null);
  const [provider, setProvider] = useState<LlmProvider>("ollama");
  const [model, setModel] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [loadingModels, setLoadingModels] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [health, setHealth] = useState<LlmHealth | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  const applySettings = useCallback((s: LlmSettings, p: LlmProvider) => {
    setSettings(s);
    setProvider(p);
    setModel(s.providers[p].model);
    setBaseUrl(p === "ollama" ? s.ollama_url : p === "openai" ? s.openai_base_url : "");
    setApiKey("");
  }, []);

  const checkHealth = useCallback(() => {
    setHealth(null);
    api.llmHealth().then(setHealth).catch(() => setHealth({ ok: false, provider, model, error: "Backend unreachable" }));
  }, [provider, model]);

  const loadModels = useCallback((p: LlmProvider) => {
    setLoadingModels(true);
    setModelsError(null);
    api
      .llmModels(p)
      .then((r) => {
        setModels(r.models);
        setModelsError(r.error);
      })
      .catch((e) => setModelsError(e instanceof Error ? e.message : "Could not list models"))
      .finally(() => setLoadingModels(false));
  }, []);

  useEffect(() => {
    api
      .llmSettings()
      .then((s) => {
        applySettings(s, s.provider);
        loadModels(s.provider);
      })
      .catch(() => setMessage("Could not load settings — is the backend running?"));
    api.llmHealth().then(setHealth).catch(() => {});
  }, [applySettings, loadModels]);

  const pickProvider = (p: LlmProvider) => {
    if (!settings) return;
    applySettings(settings, p);
    setModels([]);
    loadModels(p);
  };

  const save = async () => {
    setSaving(true);
    setMessage("");
    const body: LlmSettingsUpdate = { provider, model };
    if (provider === "ollama") body.ollama_url = baseUrl;
    if (provider === "openai") body.openai_base_url = baseUrl;
    const keyField = KEY_FIELD[provider];
    if (keyField && apiKey) body[keyField] = apiKey;
    try {
      const s = await api.saveLlmSettings(body);
      applySettings(s, s.provider);
      setMessage(`Saved. TinyTutor now uses ${s.model || "no model"} via ${s.provider}.`);
      loadModels(s.provider);
      api.llmHealth().then(setHealth).catch(() => {});
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  };

  const clearKey = async () => {
    const keyField = KEY_FIELD[provider];
    if (!keyField) return;
    const s = await api.saveLlmSettings({ [keyField]: "" });
    applySettings(s, provider);
  };

  const keyField = KEY_FIELD[provider];
  const savedKey = keyField && settings ? settings.keys[keyField] : "";

  return (
    <div>
      <PageHeader title="Settings" description="Choose which AI powers TinyTutor. Your notes stay in the local database either way." />

      <div className="grid gap-6 md:grid-cols-2">
        <motion.div className="md:col-span-2" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2">
                  <Cpu className="h-5 w-5 text-cyan-400" /> AI Model
                </span>
                <button onClick={checkHealth} className="flex items-center gap-2 text-xs font-normal" title="Re-check connection">
                  {health === null ? (
                    <span className="text-muted-foreground">Checking…</span>
                  ) : health.ok ? (
                    <span className="flex items-center gap-1 text-emerald-400">
                      <CheckCircle2 className="h-4 w-4" /> Connected · {health.model}
                    </span>
                  ) : (
                    <span className="flex items-center gap-1 text-red-400" title={health.error ?? ""}>
                      <XCircle className="h-4 w-4" /> Not reachable
                    </span>
                  )}
                </button>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5 text-sm">
              <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
                {PROVIDERS.map((p) => (
                  <button
                    key={p.id}
                    onClick={() => pickProvider(p.id)}
                    className={`rounded-lg border p-3 text-left transition-colors ${
                      provider === p.id ? "border-primary bg-primary/15" : "border-white/10 bg-white/5 hover:bg-white/10"
                    }`}
                  >
                    <p className="font-medium">{p.label}</p>
                    <p className="mt-1 text-xs text-muted-foreground">{p.hint}</p>
                  </button>
                ))}
              </div>

              {(provider === "ollama" || provider === "openai") && (
                <label className="block space-y-1">
                  <span className="text-xs text-muted-foreground">{provider === "ollama" ? "Ollama URL" : "Base URL"}</span>
                  <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} />
                </label>
              )}

              {keyField && (
                <label className="block space-y-1">
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <KeyRound className="h-3 w-3" /> API key
                    {savedKey ? ` — saved (${savedKey})` : provider === "anthropic" ? " — or set ANTHROPIC_API_KEY" : ""}
                  </span>
                  <div className="flex gap-2">
                    <Input
                      type="password"
                      placeholder={savedKey ? "Leave blank to keep the saved key" : "Paste your key"}
                      value={apiKey}
                      onChange={(e) => setApiKey(e.target.value)}
                    />
                    {savedKey && (
                      <Button variant="outline" onClick={clearKey}>
                        Remove
                      </Button>
                    )}
                  </div>
                  <span className="text-xs text-muted-foreground">Stored in your local SQLite database.</span>
                </label>
              )}

              <label className="block space-y-1">
                <span className="flex items-center justify-between text-xs text-muted-foreground">
                  Model
                  <button className="flex items-center gap-1 hover:text-foreground" onClick={() => loadModels(provider)}>
                    <RefreshCw className={`h-3 w-3 ${loadingModels ? "animate-spin" : ""}`} /> Refresh list
                  </button>
                </span>
                <Input
                  list="model-options"
                  value={model}
                  placeholder={settings?.providers[provider].default_model || "Model name"}
                  onChange={(e) => setModel(e.target.value)}
                />
                <datalist id="model-options">
                  {models.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <span className="text-xs text-muted-foreground">
                  {modelsError
                    ? `Could not list models: ${modelsError}`
                    : models.length
                      ? `${models.length} models available — start typing to pick one.`
                      : loadingModels
                        ? "Loading models…"
                        : provider === "ollama"
                          ? "No models installed. Try: ollama pull qwen2.5:0.5b"
                          : ""}
                </span>
              </label>

              <VisionModelField provider={provider} />

              <div className="flex items-center gap-3">
                <Button onClick={save} disabled={saving || !model}>
                  {saving ? "Saving…" : "Save & use this model"}
                </Button>
                {message && <span className="text-xs text-cyan-400">{message}</span>}
              </div>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.03 }}>
          <EmbeddingsCard />
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 }}>
          <DataCard />
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5 text-violet-400" /> Backend API
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>
                URL: <code className="text-foreground">{apiUrl}</code>
              </p>
              <p>FastAPI + SQLite on your machine.</p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5 text-emerald-400" /> Storage
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <ul className="list-inside list-disc space-y-1">
                <li>SQLite database: backend/data/tutor.db</li>
                <li>Uploads: backend/data/uploads/</li>
                <li>Hybrid search: SQLite FTS5 keywords + embeddings stored in SQLite</li>
                <li>A practice question for your weakest topic every 30 minutes</li>
              </ul>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
