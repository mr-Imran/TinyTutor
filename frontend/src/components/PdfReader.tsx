"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/TextLayer.css";
import "react-pdf/dist/Page/AnnotationLayer.css";
import { Highlighter, ChevronLeft, ChevronRight, Save, Trash2, Sparkles } from "lucide-react";
import { HumanText } from "@/components/HumanText";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { api, pdfFileUrl, ReaderChunk, ReaderDoc, ReaderMarker } from "@/lib/api";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

export function PdfReader() {
  const [docs, setDocs] = useState<ReaderDoc[]>([]);
  const [docId, setDocId] = useState<number | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(1);
  const [slides, setSlides] = useState<ReaderChunk[]>([]);
  const [markers, setMarkers] = useState<ReaderMarker[]>([]);
  const [selection, setSelection] = useState("");
  const [markerType, setMarkerType] = useState<"highlight" | "underline" | "note">("highlight");
  const [markerColor, setMarkerColor] = useState("yellow");
  const [markerNote, setMarkerNote] = useState("");
  const [askQ, setAskQ] = useState("");
  const [explanation, setExplanation] = useState("");
  const [saveTitle, setSaveTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [savingMarker, setSavingMarker] = useState(false);
  const [savingDoc, setSavingDoc] = useState(false);

  useEffect(() => {
    api.listReaderDocuments().then((list) => {
      setDocs(list);
      if (list[0]) setDocId(list[0].id);
    });
  }, []);

  const activeDoc = useMemo(() => docs.find((d) => d.id === docId) ?? null, [docs, docId]);
  const isPdf = activeDoc?.file_type === "pdf";

  const loadMeta = useCallback(async (id: number) => {
    const [chunks, ann] = await Promise.all([api.getDocumentChunks(id), api.getDocumentMarkers(id)]);
    setSlides(chunks);
    setMarkers(ann);
  }, []);

  useEffect(() => {
    if (!docId) return;
    loadMeta(docId).catch(() => {});
  }, [docId, loadMeta]);

  const captureSelection = useCallback(() => {
    const text = window.getSelection()?.toString().trim() || "";
    setSelection(text);
  }, []);

  const explain = async () => {
    if (!selection) return;
    setLoading(true);
    setExplanation("");
    try {
      const res = await api.explainSelection(selection, askQ || undefined, "bn");
      setExplanation(res.explanation);
    } catch (e) {
      setExplanation(e instanceof Error ? e.message : "Could not explain.");
    } finally {
      setLoading(false);
    }
  };

  const saveMarker = async () => {
    if (!selection || !docId) return;
    setSavingMarker(true);
    try {
      await api.saveMarker({
        document_id: docId,
        page_number: isPdf ? page : undefined,
        marker_type: markerType,
        color: markerColor,
        selected_text: selection,
        note: markerNote || undefined,
      });
      setMarkerNote("");
      const ann = await api.getDocumentMarkers(docId);
      setMarkers(ann);
    } finally {
      setSavingMarker(false);
    }
  };

  const saveAsDocument = async () => {
    if (!selection) return;
    setSavingDoc(true);
    try {
      await api.saveReaderDocument({
        title: saveTitle || `Saved note ${new Date().toLocaleString()}`,
        topic: activeDoc?.topic || "Saved Notes",
        content: selection + (markerNote ? `\n\nNote: ${markerNote}` : ""),
        source: activeDoc?.filename || "Reader Save",
      });
      setSaveTitle("");
    } finally {
      setSavingDoc(false);
    }
  };

  const deleteMarker = async (id: number) => {
    await api.deleteMarker(id);
    if (docId) setMarkers(await api.getDocumentMarkers(docId));
  };

  const fileUrl = docId ? pdfFileUrl(docId) : "";

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3">
        <select
          className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm"
          value={docId ?? ""}
          onChange={(e) => {
            setDocId(Number(e.target.value));
            setPage(1);
            setExplanation("");
            setSelection("");
          }}
        >
          {docs.length === 0 && <option value="">No PDF/PPTX uploaded</option>}
          {docs.map((p) => (
            <option key={p.id} value={p.id}>
              [{p.file_type.toUpperCase()}] {p.title || p.filename}
            </option>
          ))}
        </select>
        {isPdf ? (
          <div className="flex items-center gap-2">
            <Button variant="outline" size="icon" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm text-muted-foreground">
              Page {page} / {numPages || "?"}
            </span>
            <Button
              variant="outline"
              size="icon"
              disabled={page >= numPages}
              onClick={() => setPage((p) => p + 1)}
            >
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        ) : null}
      </div>

      <p className="flex items-center gap-2 text-xs text-muted-foreground">
        <Highlighter className="h-3.5 w-3.5" />
        Highlight any text in the PDF, then click &quot;Use selection&quot; and ask your question.
      </p>

      {docId && isPdf && fileUrl ? (
        <div
          className="max-h-[480px] overflow-auto rounded-xl border border-white/10 bg-black/30 p-2"
          onMouseUp={captureSelection}
        >
          <Document
            file={fileUrl}
            onLoadSuccess={({ numPages: n }) => setNumPages(n)}
            loading={<p className="p-8 text-sm text-muted-foreground">Loading PDF…</p>}
          >
            <Page pageNumber={page} width={560} renderTextLayer renderAnnotationLayer />
          </Document>
        </div>
      ) : docId && !isPdf ? (
        <div className="max-h-[480px] space-y-3 overflow-auto rounded-xl border border-white/10 bg-black/20 p-3">
          {slides.length === 0 ? (
            <p className="text-sm text-muted-foreground">No extracted slide content found.</p>
          ) : (
            slides.map((s) => (
              <div key={s.id} className="rounded-lg border border-white/10 bg-white/5 p-3" onMouseUp={captureSelection}>
                <p className="mb-1 text-xs text-cyan-300">{s.title || "Slide"}</p>
                <HumanText text={s.content} className="text-muted-foreground" />
              </div>
            ))
          )}
        </div>
      ) : (
        <Card>
          <CardContent className="py-12 text-center text-muted-foreground">
            Upload a PDF or PPTX from the Upload page to use the reader.
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={captureSelection}>
          Use selection
        </Button>
        {selection && (
          <span className="max-w-md truncate rounded-lg bg-amber-500/10 px-3 py-1.5 text-xs text-amber-200">
            {selection.slice(0, 120)}
            {selection.length > 120 ? "…" : ""}
          </span>
        )}
      </div>

      <div className="grid gap-2 sm:grid-cols-3">
        <select
          className="rounded-lg border border-white/15 bg-white/5 px-3 py-2 text-sm"
          value={markerType}
          onChange={(e) => setMarkerType(e.target.value as "highlight" | "underline" | "note")}
        >
          <option value="highlight">Highlight</option>
          <option value="underline">Underline</option>
          <option value="note">Note</option>
        </select>
        <Input placeholder="Marker color (yellow, blue...)" value={markerColor} onChange={(e) => setMarkerColor(e.target.value)} />
        <Input placeholder="Optional note for marker" value={markerNote} onChange={(e) => setMarkerNote(e.target.value)} />
      </div>
      <div className="flex flex-wrap gap-2">
        <Button onClick={saveMarker} disabled={!selection || !docId || savingMarker}>
          <Highlighter className="mr-2 h-4 w-4" />
          {savingMarker ? "Saving marker..." : "Save marker"}
        </Button>
        <Button variant="outline" onClick={explain} disabled={!selection || loading}>
          <Sparkles className="mr-2 h-4 w-4" />
          {loading ? "Explaining..." : "AI explain (Bangla)"}
        </Button>
      </div>

      <Input
        placeholder="Optional: What do you want to know about this part?"
        value={askQ}
        onChange={(e) => setAskQ(e.target.value)}
      />

      <div className="flex flex-wrap gap-2">
        <Input
          placeholder="Title to save selected text as a document"
          value={saveTitle}
          onChange={(e) => setSaveTitle(e.target.value)}
        />
        <Button onClick={saveAsDocument} disabled={!selection || savingDoc}>
          <Save className="mr-2 h-4 w-4" />
          {savingDoc ? "Saving..." : "Save document"}
        </Button>
      </div>

      {explanation && (
        <Card className="border-cyan-500/20">
          <CardContent className="pt-4">
            <HumanText text={explanation} />
          </CardContent>
        </Card>
      )}

      {markers.length > 0 && (
        <Card>
          <CardContent className="space-y-2 pt-4">
            <p className="text-sm font-medium">Saved markers</p>
            {markers.map((m) => (
              <div key={m.id} className="flex items-start justify-between gap-3 rounded-lg bg-white/5 p-3">
                <div>
                  <p className="text-xs text-cyan-300">
                    {m.marker_type.toUpperCase()} {m.page_number ? `· page ${m.page_number}` : ""}
                  </p>
                  <p className="text-sm">{m.selected_text}</p>
                  {m.note ? <p className="mt-1 text-xs text-muted-foreground">Note: {m.note}</p> : null}
                </div>
                <Button variant="ghost" size="icon" onClick={() => deleteMarker(m.id)}>
                  <Trash2 className="h-4 w-4 text-red-400" />
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
