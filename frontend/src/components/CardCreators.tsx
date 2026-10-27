"use client";

import { PointerEvent, useEffect, useRef, useState } from "react";
import { ImagePlus, Sparkles, SquareDashed, Trash2 } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { api, OcclusionMask } from "@/lib/api";
import { addBlank, clozeCount, renderCloze } from "@/lib/cards";

const field = "w-full rounded-lg border border-white/15 bg-white/5 px-3 text-sm";

function TopicField({ value, onChange, topics }: { value: string; onChange: (v: string) => void; topics: string[] }) {
  return (
    <>
      <input
        list="card-topics"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Topic"
        className={`${field} h-9`}
      />
      <datalist id="card-topics">
        {topics.map((t) => (
          <option key={t} value={t} />
        ))}
      </datalist>
    </>
  );
}

/** Fill-in-the-blank cards: select words and press "Make blank", or let the AI pick. */
export function ClozeCreator({ topics, onCreated }: { topics: string[]; onCreated: (message: string) => void }) {
  const [topic, setTopic] = useState(topics[0] ?? "");
  const [text, setText] = useState("");
  const [extra, setExtra] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);
  const blanks = clozeCount(text);

  useEffect(() => {
    if (!topic && topics[0]) setTopic(topics[0]);
  }, [topics, topic]);

  const blank = () => {
    const el = ref.current;
    if (!el) return;
    const result = addBlank(text, el.selectionStart, el.selectionEnd);
    if (!result.added) setError("Select the word(s) to hide first.");
    else {
      setError("");
      setText(result.text);
    }
  };

  const suggest = async () => {
    setBusy(true);
    setError("");
    try {
      const r = await api.suggestCloze(text);
      if (!r.used_ai) setError("The AI could not pick blanks; select words and use Make blank.");
      setText(r.text);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not suggest blanks");
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    setBusy(true);
    setError("");
    try {
      const cards = await api.createCloze({ topic: topic.trim(), text, extra });
      onCreated(cards.length ? `Added ${cards.length} fill-in-the-blank card${cards.length === 1 ? "" : "s"}.` : "Those cards already exist.");
      setText("");
      setExtra("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create cards");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 text-sm">
      <TopicField value={topic} onChange={setTopic} topics={topics} />
      <textarea
        ref={ref}
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={4}
        placeholder="Paste a sentence, select a key word, then press Make blank. Or type {{c1::answer}}."
        className={`${field} py-2`}
      />
      <div className="flex gap-2">
        <Button variant="outline" size="sm" className="flex-1" onClick={blank} type="button">
          <SquareDashed className="h-3.5 w-3.5" /> Make blank
        </Button>
        <Button variant="outline" size="sm" className="flex-1" onClick={suggest} disabled={busy || text.trim().length < 5}>
          <Sparkles className="h-3.5 w-3.5" /> AI picks
        </Button>
      </div>
      <input value={extra} onChange={(e) => setExtra(e.target.value)} placeholder="Extra info on the back (optional)" className={`${field} h-9`} />
      {blanks > 0 && (
        <div className="rounded-md bg-white/5 p-2 text-xs text-muted-foreground">
          <p className="mb-1">Preview of card 1 of {blanks}:</p>
          <Markdown text={renderCloze(text, Number(text.match(/\{\{c(\d+)::/)?.[1] ?? 1), false)} />
        </div>
      )}
      <Button className="w-full" size="sm" onClick={create} disabled={busy || !blanks || !topic.trim()}>
        Create {blanks || ""} card{blanks === 1 ? "" : "s"}
      </Button>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}

/** Image-hiding cards: drag boxes over a diagram; each box becomes one card. */
export function OcclusionEditor({ topics, onCreated }: { topics: string[]; onCreated: (message: string) => void }) {
  const [topic, setTopic] = useState(topics[0] ?? "");
  const [header, setHeader] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [masks, setMasks] = useState<OcclusionMask[]>([]);
  const [draft, setDraft] = useState<OcclusionMask | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const start = useRef<{ x: number; y: number } | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!topic && topics[0]) setTopic(topics[0]);
  }, [topics, topic]);

  useEffect(() => {
    if (!file) return setUrl(null);
    const u = URL.createObjectURL(file);
    setUrl(u);
    return () => URL.revokeObjectURL(u);
  }, [file]);

  const point = (e: PointerEvent) => {
    const r = box.current!.getBoundingClientRect();
    return {
      x: Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1),
      y: Math.min(Math.max((e.clientY - r.top) / r.height, 0), 1),
    };
  };

  const down = (e: PointerEvent) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    start.current = point(e);
  };
  const move = (e: PointerEvent) => {
    if (!start.current) return;
    const p = point(e);
    const s = start.current;
    setDraft({ x: Math.min(s.x, p.x), y: Math.min(s.y, p.y), w: Math.abs(p.x - s.x), h: Math.abs(p.y - s.y) });
  };
  const up = () => {
    if (draft && draft.w > 0.01 && draft.h > 0.01) setMasks((m) => [...m, { ...draft, label: "" }]);
    start.current = null;
    setDraft(null);
  };

  const create = async () => {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const cards = await api.createOcclusion(file, topic.trim(), masks, header);
      onCreated(`Added ${cards.length} image card${cards.length === 1 ? "" : "s"}.`);
      setFile(null);
      setMasks([]);
      setHeader("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not create cards");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-2 text-sm">
      <TopicField value={topic} onChange={setTopic} topics={topics} />
      <label className="block cursor-pointer">
        <input
          type="file"
          accept=".png,.jpg,.jpeg,.webp"
          className="hidden"
          onChange={(e) => {
            setFile(e.target.files?.[0] ?? null);
            setMasks([]);
            e.target.value = "";
          }}
        />
        <span className="inline-flex h-9 w-full items-center justify-center gap-2 rounded-md border border-white/20 bg-white/5 text-xs hover:bg-white/10">
          <ImagePlus className="h-3.5 w-3.5" /> {file ? file.name : "Choose a diagram"}
        </span>
      </label>
      {url && (
        <>
          <p className="text-xs text-muted-foreground">Drag over each label you want to hide.</p>
          <div
            ref={box}
            className="relative touch-none select-none overflow-hidden rounded-md"
            onPointerDown={down}
            onPointerMove={move}
            onPointerUp={up}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- local preview of the chosen file */}
            <img src={url} alt="" draggable={false} className="block w-full" />
            {[...masks, ...(draft ? [draft] : [])].map((m, i) => (
              <div
                key={i}
                className="absolute flex items-center justify-center border border-orange-700 bg-orange-500/80 text-[10px] font-bold text-white"
                style={{ left: `${m.x * 100}%`, top: `${m.y * 100}%`, width: `${m.w * 100}%`, height: `${m.h * 100}%` }}
              >
                {i < masks.length ? i + 1 : ""}
              </div>
            ))}
          </div>
          {masks.map((m, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="w-5 text-xs text-muted-foreground">{i + 1}.</span>
              <input
                value={m.label ?? ""}
                onChange={(e) => setMasks((all) => all.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))}
                placeholder="Answer (what is under the box)"
                className={`${field} h-8 text-xs`}
              />
              <button aria-label="Remove box" onClick={() => setMasks((all) => all.filter((_, j) => j !== i))}>
                <Trash2 className="h-3.5 w-3.5 text-red-400" />
              </button>
            </div>
          ))}
          <input value={header} onChange={(e) => setHeader(e.target.value)} placeholder="Question, e.g. Label the cell" className={`${field} h-9`} />
        </>
      )}
      <Button className="w-full" size="sm" onClick={create} disabled={busy || !file || !masks.length || !topic.trim()}>
        Create {masks.length || ""} card{masks.length === 1 ? "" : "s"}
      </Button>
      {error && <p className="text-xs text-red-400">{error}</p>}
    </div>
  );
}
