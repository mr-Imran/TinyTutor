"use client";

import { useState } from "react";
import { Layers, Loader2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, Concept, Document } from "@/lib/api";

/** Concept map as term chips; hovering a term highlights the terms it connects to. */
function ConceptMap({ concepts }: { concepts: Concept[] }) {
  const [active, setActive] = useState<string | null>(null);
  const activeConcept = concepts.find((c) => c.term === active);
  const linked = new Set(
    activeConcept
      ? [
          ...activeConcept.related,
          ...concepts.filter((c) => c.related.includes(activeConcept.term)).map((c) => c.term),
        ]
      : []
  );

  return (
    <div>
      <div className="flex flex-wrap gap-2">
        {concepts.map((c) => (
          <button
            key={c.term}
            onMouseEnter={() => setActive(c.term)}
            onFocus={() => setActive(c.term)}
            onClick={() => setActive(c.term)}
            className={`rounded-full border px-3 py-1 text-xs transition-colors ${
              c.term === active
                ? "border-violet-400 bg-violet-500/30 text-white"
                : linked.has(c.term)
                  ? "border-cyan-400/60 bg-cyan-500/15"
                  : "border-white/15 bg-white/5 text-muted-foreground"
            }`}
          >
            {c.term}
          </button>
        ))}
      </div>
      {activeConcept && (
        <p className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium text-foreground">{activeConcept.term}:</span> {activeConcept.definition}
          {linked.size > 0 && <> Connects to {Array.from(linked).join(", ")}.</>}
        </p>
      )}
    </div>
  );
}

export function DocumentInsights({ doc, onChange }: { doc: Document; onChange: (doc: Document) => void }) {
  const [busy, setBusy] = useState(false);
  const [cardsMsg, setCardsMsg] = useState("");

  const regenerate = async () => {
    setBusy(true);
    try {
      onChange(await api.resummarize(doc.id));
    } finally {
      setBusy(false);
    }
  };

  const makeCards = async () => {
    setCardsMsg("Writing flashcards…");
    try {
      const { created } = await api.generateFlashcards({ document_id: doc.id, count: 10 });
      setCardsMsg(`${created.length} flashcards added — review them on the Flashcards page.`);
    } catch (e) {
      setCardsMsg(e instanceof Error ? e.message : "Could not make flashcards");
    }
  };

  const status = doc.summary_status;
  const working = status === "pending" || status === "running" || busy;

  return (
    <div className="space-y-3 border-t border-white/10 px-6 pb-4 pt-3 text-sm">
      {working ? (
        <p className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Writing a summary and concept map…
        </p>
      ) : doc.summary ? (
        <>
          <p className="leading-relaxed text-muted-foreground">{doc.summary}</p>
          {doc.concepts && doc.concepts.length > 0 && <ConceptMap concepts={doc.concepts} />}
        </>
      ) : (
        <p className="text-muted-foreground">
          {status === "failed"
            ? "The summary could not be generated. Check the AI model in Settings."
            : status === "empty"
              ? "No text was found in this file (scanned PDFs need Tesseract OCR installed)."
              : "No summary yet."}
        </p>
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={regenerate} disabled={working}>
          <RefreshCw className="h-3.5 w-3.5" /> {doc.summary ? "Regenerate" : "Summarise"}
        </Button>
        <Button variant="outline" size="sm" onClick={makeCards} disabled={doc.chunk_count === 0}>
          <Layers className="h-3.5 w-3.5" /> Make flashcards
        </Button>
        {cardsMsg && <span className="text-xs text-cyan-400">{cardsMsg}</span>}
      </div>
    </div>
  );
}
