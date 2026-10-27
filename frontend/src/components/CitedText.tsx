"use client";

import { FileText } from "lucide-react";
import { ChatSource, formatTimestamp, sourceLink } from "@/lib/api";

function sourceLabel(s: ChatSource) {
  const name = s.source || s.title || "Notes";
  if (s.page_number) return `${name} · p.${s.page_number}`;
  if (s.start_seconds != null) return `${name} · ${formatTimestamp(s.start_seconds)}`;
  return name;
}

const sourceHref = sourceLink;

function CitationChip({ source, n }: { source?: ChatSource; n: number }) {
  const className =
    "mx-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded bg-violet-500/25 px-1 align-text-top text-[10px] font-semibold text-violet-200";
  if (!source) return <span className={className}>{n}</span>;
  const href = sourceHref(source);
  const title = `${sourceLabel(source)}\n\n${source.preview ?? ""}`;
  return href ? (
    <a href={href} target="_blank" rel="noreferrer" title={title} className={`${className} hover:bg-violet-500/50`}>
      {n}
    </a>
  ) : (
    <span title={title} className={className}>
      {n}
    </span>
  );
}

/** Plain text where [1]-style markers become clickable citations, plus a source list. */
export function CitedText({ text, sources = [] }: { text: string; sources?: ChatSource[] }) {
  const byN = new Map(sources.map((s) => [s.n, s]));
  const parts = text.split(/(\[\d+\])/g);
  const cited = new Set<number>();
  for (const p of parts) {
    const m = p.match(/^\[(\d+)\]$/);
    if (m) cited.add(Number(m[1]));
  }
  const shown = sources.filter((s) => cited.has(s.n));

  return (
    <div>
      <p className="whitespace-pre-wrap text-sm leading-relaxed">
        {parts.map((p, i) => {
          const m = p.match(/^\[(\d+)\]$/);
          return m ? <CitationChip key={i} n={Number(m[1])} source={byN.get(Number(m[1]))} /> : p;
        })}
      </p>
      {shown.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2 border-t border-white/10 pt-2">
          {shown.map((s) => {
            const href = sourceHref(s);
            const body = (
              <>
                <span className="font-semibold text-violet-300">[{s.n}]</span>
                <FileText className="h-3 w-3" />
                {sourceLabel(s)}
              </>
            );
            return href ? (
              <a
                key={s.n}
                href={href}
                target="_blank"
                rel="noreferrer"
                title={s.preview}
                className="inline-flex items-center gap-1 rounded-md bg-white/5 px-2 py-1 text-xs text-muted-foreground hover:bg-white/10 hover:text-foreground"
              >
                {body}
              </a>
            ) : (
              <span
                key={s.n}
                title={s.preview}
                className="inline-flex items-center gap-1 rounded-md bg-white/5 px-2 py-1 text-xs text-muted-foreground"
              >
                {body}
              </span>
            );
          })}
        </div>
      )}
    </div>
  );
}
