"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { ExternalLink, FileText, Search, Sparkles } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, formatTimestamp, SearchHit, sourceLink } from "@/lib/api";

/** Renders FTS snippet markers [[term]] as highlights. */
function Snippet({ text }: { text: string }) {
  return (
    <p className="text-sm leading-relaxed text-muted-foreground">
      {text.split(/(\[\[.*?\]\])/g).map((part, i) =>
        part.startsWith("[[") ? (
          <mark key={i} className="rounded bg-violet-500/30 px-0.5 text-foreground">
            {part.slice(2, -2)}
          </mark>
        ) : (
          part
        )
      )}
    </p>
  );
}

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [searched, setSearched] = useState("");

  useEffect(() => {
    const q = query.trim();
    if (q.length < 3) {
      setResults([]);
      setSearched("");
      return;
    }
    const timer = setTimeout(() => {
      setLoading(true);
      api
        .search(q, 30)
        .then((r) => {
          setResults(r.results);
          setSearched(q);
        })
        .catch(() => setResults([]))
        .finally(() => setLoading(false));
    }, 250);
    return () => clearTimeout(timer);
  }, [query]);

  return (
    <div>
      <PageHeader title="Search" description="Find any idea across all your materials — by exact words or by meaning." />

      <div className="relative mb-6">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          autoFocus
          className="h-12 pl-10 text-base"
          placeholder="e.g. photosynthesis light reaction"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : searched && results.length === 0 ? (
        <p className="text-sm text-muted-foreground">No matches for “{searched}”.</p>
      ) : (
        <div className="space-y-3">
          {results.map((hit, i) => {
            const href = sourceLink(hit);
            return (
              <motion.div key={hit.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.02 }}>
                <Card>
                  <CardContent className="space-y-2 p-4">
                    <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <FileText className="h-3.5 w-3.5" />
                        {hit.source}
                        {hit.page_number ? ` · page ${hit.page_number}` : ""}
                        {hit.start_seconds != null ? ` · ${formatTimestamp(hit.start_seconds)}` : ""} · {hit.topic}
                        {hit.semantic_score != null && !hit.snippet.includes("[[") && (
                          <span className="ml-2 inline-flex items-center gap-1 rounded bg-violet-500/20 px-1.5 py-0.5 text-[10px] text-violet-200">
                            <Sparkles className="h-3 w-3" /> related meaning
                          </span>
                        )}
                      </span>
                      {href && (
                        <a href={href} target="_blank" rel="noreferrer" className="flex items-center gap-1 hover:text-foreground">
                          Open <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                    <Snippet text={hit.snippet} />
                  </CardContent>
                </Card>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}
