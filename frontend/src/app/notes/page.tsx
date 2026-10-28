"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { BookOpenText, Eye, FileText, Layers, Link2, PenLine, Plus, Sigma, Sparkles, Trash2 } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, Note, NoteAction, NoteSummary } from "@/lib/api";

const SAVE_DELAY_MS = 1500;
const NOTE_LINK = "#note:";

const ACTIONS: { action: NoteAction; label: string }[] = [
  { action: "continue", label: "Continue writing" },
  { action: "simplify", label: "Simplify selection" },
  { action: "explain", label: "Explain selection" },
  { action: "summarize", label: "Summarise selection" },
  { action: "flashcards", label: "Flashcards from selection" },
];

/** [[Title]] and [[Title|label]] become in-app links for the preview. */
function withNoteLinks(body: string) {
  return body.replace(/\[\[([^[\]|]+?)(?:\|([^[\]]+))?\]\]/g, (_, title: string, label?: string) =>
    `[${label ?? title}](${NOTE_LINK}${encodeURIComponent(title.trim())})`
  );
}

function NotesEditor() {
  const router = useRouter();
  const params = useSearchParams();
  const [notes, setNotes] = useState<NoteSummary[]>([]);
  const [note, setNote] = useState<Note | null>(null);
  const [title, setTitle] = useState("");
  const [topic, setTopic] = useState("");
  const [body, setBody] = useState("");
  const [mode, setMode] = useState<"write" | "preview" | "split">("split");
  const [status, setStatus] = useState("");
  const [assist, setAssist] = useState<{ action: NoteAction; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const dirty = useRef(false);

  const loadList = useCallback(() => api.notes().then(setNotes).catch(() => {}), []);

  const open = useCallback((n: Note) => {
    setNote(n);
    setTitle(n.title);
    setTopic(n.topic);
    setBody(n.body);
    setAssist(null);
    dirty.current = false;
    setStatus("");
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  // Open from the URL: ?id=12 (citations, search) or ?title=Cells ([[links]]).
  useEffect(() => {
    const id = Number(params.get("id"));
    const byTitle = params.get("title");
    if (id && id !== note?.id) api.note(id).then(open).catch(() => setStatus("That note no longer exists."));
    else if (byTitle && byTitle.toLowerCase() !== note?.title.toLowerCase()) {
      api.noteByTitle(byTitle).then(open).catch(async () => {
        // A link to a note that does not exist yet creates it, as in other wiki-style editors.
        const created = await api.createNote({ title: byTitle, body: `# ${byTitle}\n\n` });
        open(created);
        loadList();
        router.replace(`/notes?id=${created.id}`);
      });
    }
  }, [params, note?.id, note?.title, open, loadList, router]);

  const save = useCallback(async () => {
    if (!note || !dirty.current || !title.trim()) return;
    dirty.current = false;
    setStatus("Saving…");
    try {
      const saved = await api.updateNote(note.id, { title, topic, body });
      setNote((n) => (n && n.id === saved.id ? { ...saved, body: n.body } : n));
      setStatus(`Saved · searchable${saved.sync?.added ? ` · ${saved.sync.added} part(s) re-indexed` : ""}`);
      loadList();
    } catch (e) {
      dirty.current = true;
      setStatus(e instanceof Error ? e.message : "Could not save");
    }
  }, [note, title, topic, body, loadList]);

  // Autosave after a pause in typing.
  useEffect(() => {
    if (!dirty.current) return;
    const timer = setTimeout(save, SAVE_DELAY_MS);
    return () => clearTimeout(timer);
  }, [title, topic, body, save]);

  const edit = (setter: (v: string) => void) => (value: string) => {
    dirty.current = true;
    setStatus("Unsaved changes");
    setter(value);
  };

  const create = async () => {
    const created = await api.createNote({ title: `Untitled ${new Date().toLocaleDateString()}`, body: "" });
    open(created);
    loadList();
    router.replace(`/notes?id=${created.id}`);
  };

  const remove = async () => {
    if (!note || !confirm(`Delete "${note.title}"? This cannot be undone.`)) return;
    await api.deleteDocument(note.id);
    setNote(null);
    setBody("");
    setTitle("");
    loadList();
    router.replace("/notes");
  };

  const insert = (before: string, after = "", placeholder = "") => {
    const el = editor.current;
    if (!el) return;
    const { selectionStart: s, selectionEnd: e } = el;
    const selected = body.slice(s, e) || placeholder;
    edit(setBody)(body.slice(0, s) + before + selected + after + body.slice(e));
    requestAnimationFrame(() => {
      el.focus();
      el.setSelectionRange(s + before.length, s + before.length + selected.length);
    });
  };

  const runAssist = async (action: NoteAction) => {
    const el = editor.current;
    const selection = el ? body.slice(el.selectionStart, el.selectionEnd) : "";
    const text = action === "continue" ? body.slice(-4000) : selection;
    if (!text.trim()) {
      setStatus(action === "continue" ? "Write something first." : "Select some text in the editor first.");
      return;
    }
    setBusy(true);
    try {
      const r = await api.noteAssist(action, text, note?.id);
      if (action === "flashcards") setStatus(`Created ${r.created ?? 0} flashcard(s) from the selection.`);
      else setAssist({ action, text: r.text ?? "" });
    } catch (e) {
      setStatus(e instanceof Error ? e.message : "AI unavailable");
    } finally {
      setBusy(false);
    }
  };

  const applyAssist = (how: "append" | "replace") => {
    if (!assist) return;
    const el = editor.current;
    if (how === "replace" && el && el.selectionStart !== el.selectionEnd) {
      edit(setBody)(body.slice(0, el.selectionStart) + assist.text + body.slice(el.selectionEnd));
    } else {
      edit(setBody)(`${body.trimEnd()}\n\n${assist.text}\n`);
    }
    setAssist(null);
  };

  const preview = (
    <Markdown
      text={withNoteLinks(body) || "_Nothing written yet._"}
      renderLink={(href, children) =>
        href.startsWith(NOTE_LINK) ? (
          <button
            className="text-violet-300 underline decoration-dotted underline-offset-2"
            onClick={() => router.push(`/notes?title=${href.slice(NOTE_LINK.length)}`)}
          >
            {children}
          </button>
        ) : undefined
      }
    />
  );

  return (
    <div className="grid gap-6 lg:grid-cols-[16rem_1fr]">
      <Card className="h-fit">
        <CardContent className="space-y-1 p-3">
          <Button className="mb-2 w-full" size="sm" onClick={create}>
            <Plus className="h-4 w-4" /> New note
          </Button>
          {notes.length === 0 && <p className="p-2 text-xs text-muted-foreground">Your notes appear here.</p>}
          {notes.map((n) => (
            <button
              key={n.id}
              onClick={() => {
                save();
                router.replace(`/notes?id=${n.id}`);
              }}
              className={`block w-full rounded-md px-2 py-2 text-left text-xs ${
                n.id === note?.id ? "bg-primary/20 text-white" : "text-muted-foreground hover:bg-white/5"
              }`}
            >
              <span className="flex items-center gap-1.5 font-medium">
                <FileText className="h-3.5 w-3.5 shrink-0" /> <span className="truncate">{n.title}</span>
              </span>
              <span className="mt-0.5 block truncate opacity-70">{n.preview || "Empty"}</span>
            </button>
          ))}
        </CardContent>
      </Card>

      {!note ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-16 text-center text-sm text-muted-foreground">
            <BookOpenText className="h-8 w-8" />
            Write notes in Markdown. Link notes with [[Note title]], write math as $x^2$. Notes are searchable and the AI
            tutor can cite them.
            <Button size="sm" onClick={create}>
              <Plus className="h-4 w-4" /> New note
            </Button>
          </CardContent>
        </Card>
      ) : (
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Input value={title} onChange={(e) => edit(setTitle)(e.target.value)} className="max-w-md text-base font-medium" placeholder="Title" />
            <Input value={topic} onChange={(e) => edit(setTopic)(e.target.value)} className="max-w-[12rem]" placeholder="Topic" />
            <span className="text-xs text-muted-foreground">{status}</span>
            <Button variant="ghost" size="icon" className="ml-auto" onClick={remove} aria-label="Delete note">
              <Trash2 className="h-4 w-4 text-red-400" />
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-1">
            {([
              ["write", PenLine],
              ["split", Layers],
              ["preview", Eye],
            ] as const).map(([m, Icon]) => (
              <Button key={m} variant={mode === m ? "default" : "outline"} size="sm" onClick={() => setMode(m)} className="capitalize">
                <Icon className="h-3.5 w-3.5" /> {m}
              </Button>
            ))}
            <span className="mx-2 h-5 w-px bg-white/10" />
            <Button variant="ghost" size="sm" onClick={() => insert("## ", "", "Heading")}>
              H
            </Button>
            <Button variant="ghost" size="sm" onClick={() => insert("**", "**", "bold")}>
              <b>B</b>
            </Button>
            <Button variant="ghost" size="sm" onClick={() => insert("[[", "]]", "Note title")} title="Link to another note">
              <Link2 className="h-3.5 w-3.5" />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => insert("$", "$", "x^2")} title="Math">
              <Sigma className="h-3.5 w-3.5" />
            </Button>
            <span className="mx-2 h-5 w-px bg-white/10" />
            <select
              disabled={busy}
              value=""
              onChange={(e) => e.target.value && runAssist(e.target.value as NoteAction)}
              className="h-8 rounded-md border border-white/15 bg-white/5 px-2 text-xs"
            >
              <option value="" className="bg-slate-900">
                {busy ? "AI is working…" : "✦ AI assist"}
              </option>
              {ACTIONS.map((a) => (
                <option key={a.action} value={a.action} className="bg-slate-900">
                  {a.label}
                </option>
              ))}
            </select>
          </div>

          {assist && (
            <Card className="border-violet-500/30">
              <CardContent className="space-y-2 p-4 text-sm">
                <p className="flex items-center gap-1 text-xs text-violet-300">
                  <Sparkles className="h-3.5 w-3.5" /> {ACTIONS.find((a) => a.action === assist.action)?.label}
                </p>
                <Markdown text={assist.text} />
                <div className="flex gap-2">
                  {assist.action !== "continue" && (
                    <Button size="sm" onClick={() => applyAssist("replace")}>
                      Replace selection
                    </Button>
                  )}
                  <Button size="sm" variant="outline" onClick={() => applyAssist("append")}>
                    Add to the end
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => setAssist(null)}>
                    Discard
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          <div className={`grid gap-4 ${mode === "split" ? "lg:grid-cols-2" : ""}`}>
            {mode !== "preview" && (
              <textarea
                ref={editor}
                value={body}
                onChange={(e) => edit(setBody)(e.target.value)}
                onBlur={save}
                spellCheck
                placeholder={"# Heading\n\nWrite here. Link other notes with [[Note title]]. Math: $E = mc^2$"}
                className="min-h-[28rem] w-full rounded-xl border border-white/15 bg-white/5 p-4 font-mono text-sm leading-relaxed"
              />
            )}
            {mode !== "write" && <Card className="min-h-[28rem] overflow-auto p-5">{preview}</Card>}
          </div>

          {(note.backlinks.length > 0 || note.links.length > 0) && (
            <Card>
              <CardContent className="grid gap-4 p-4 text-xs sm:grid-cols-2">
                <div>
                  <p className="mb-1 font-medium">Linked from</p>
                  {note.backlinks.length === 0 && <p className="text-muted-foreground">No other note links here yet.</p>}
                  {note.backlinks.map((b) => (
                    <button key={b.id} className="block text-violet-300 hover:underline" onClick={() => router.push(`/notes?id=${b.id}`)}>
                      {b.title}
                    </button>
                  ))}
                </div>
                <div>
                  <p className="mb-1 font-medium">Links to</p>
                  {note.links.map((l) => (
                    <button
                      key={l.title}
                      className={`block hover:underline ${l.id ? "text-violet-300" : "text-muted-foreground"}`}
                      onClick={() => router.push(l.id ? `/notes?id=${l.id}` : `/notes?title=${encodeURIComponent(l.title)}`)}
                      title={l.id ? "" : "Not written yet: click to create it"}
                    >
                      {l.title}
                      {!l.id && " (new)"}
                    </button>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

export default function NotesPage() {
  return (
    <div>
      <PageHeader title="Notes" description="Your own notes in Markdown, with [[links]] between them. Saved automatically, searchable, and citable by the tutor." />
      <Suspense fallback={null}>
        <NotesEditor />
      </Suspense>
    </div>
  );
}
