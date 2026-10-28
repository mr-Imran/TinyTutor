"use client";

import { useState } from "react";
import { ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { Grounding } from "@/lib/api";

const LABELS: Record<Grounding["label"], { text: string; className: string; icon: typeof ShieldCheck }> = {
  fully: { text: "Supported by your notes", className: "bg-emerald-500/15 text-emerald-300", icon: ShieldCheck },
  partly: { text: "Partly supported by your notes", className: "bg-amber-500/15 text-amber-300", icon: ShieldQuestion },
  unsupported: { text: "Mostly not found in your notes", className: "bg-red-500/15 text-red-300", icon: ShieldAlert },
  not_in_notes: { text: "Not from your notes (general knowledge)", className: "bg-slate-500/20 text-slate-300", icon: ShieldAlert },
};

/** How well an answer is backed by the student's notes, with the unsupported sentences on demand. */
export function GroundingBadge({ grounding, checking }: { grounding?: Grounding | null; checking?: boolean }) {
  const [open, setOpen] = useState(false);
  if (checking) return <p className="mt-2 text-[11px] text-muted-foreground">Checking against your notes…</p>;
  if (!grounding) return null;
  const { text, className, icon: Icon } = LABELS[grounding.label];
  const unsupported = grounding.sentences.filter((s) => !s.supported);
  return (
    <div className="mt-2">
      <button
        onClick={() => setOpen(!open)}
        disabled={!unsupported.length}
        className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${className}`}
        title={`Checked ${grounding.checked} sentence(s) by ${grounding.method}`}
      >
        <Icon className="h-3 w-3" />
        {text}
        {grounding.checked > 0 && ` · ${grounding.supported}/${grounding.checked}`}
        {unsupported.length > 0 && (open ? " ▴" : " ▾")}
      </button>
      {open && unsupported.length > 0 && (
        <div className="mt-2 space-y-1 border-l-2 border-amber-400/40 pl-2 text-xs text-muted-foreground">
          <p className="text-amber-300/80">Could not find these in your notes, so double-check them:</p>
          {unsupported.map((s, i) => (
            <p key={i} className="italic">“{s.text}”</p>
          ))}
        </div>
      )}
    </div>
  );
}
