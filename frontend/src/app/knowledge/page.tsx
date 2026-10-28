"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { ArrowLeftRight, ArrowRight, Network, Plus, RefreshCw, Route, Trash2 } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api, ConceptNode, KnowledgeGraph, LearningPath } from "@/lib/api";

// The graph draws on a canvas and touches window, so it only renders in the browser.
const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), { ssr: false });

const LEVEL_COLORS: Record<ConceptNode["level"], string> = {
  mastered: "#34d399",
  learning: "#fbbf24",
  weak: "#f87171",
  unknown: "#94a3b8",
};
const LEVEL_LABELS: Record<ConceptNode["level"], string> = {
  mastered: "Mastered (80%+)",
  learning: "Learning",
  weak: "Weak (under 50%)",
  unknown: "Not practised",
};

type GraphNode = ConceptNode & { id: string; x?: number; y?: number };
type GraphLink = { id: number; source: string | GraphNode; target: string | GraphNode; kind: string };

function endKey(end: string | GraphNode) {
  return typeof end === "string" ? end : end.id;
}

export default function KnowledgePage() {
  const [graph, setGraph] = useState<KnowledgeGraph | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [showRelated, setShowRelated] = useState(true);
  const [addTarget, setAddTarget] = useState("");
  const wrap = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(800);

  useEffect(() => {
    api.knowledgeGraph().then(setGraph).catch(() => setGraph({ nodes: [], edges: [] }));
  }, []);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    setWidth(el.clientWidth);
    return () => observer.disconnect();
  }, [graph]);

  const rebuild = async (forceAi = false) => {
    setBusy(true);
    setMessage("");
    try {
      const g = await api.rebuildKnowledge(forceAi);
      setGraph(g);
      setMessage(g.warning ?? `${g.nodes.length} concepts, ${g.edges.filter((e) => e.kind === "prereq").length} prerequisite links.`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not build the map");
    } finally {
      setBusy(false);
    }
  };

  const nodesByKey = useMemo(() => new Map((graph?.nodes ?? []).map((n) => [n.key, n])), [graph]);
  const node = selected ? nodesByKey.get(selected) : undefined;

  // react-force-graph mutates the objects it is given, so it gets fresh copies per graph.
  const data = useMemo(() => {
    if (!graph) return { nodes: [] as GraphNode[], links: [] as GraphLink[] };
    return {
      nodes: graph.nodes.map((n) => ({ ...n, id: n.key })),
      links: graph.edges
        .filter((e) => showRelated || e.kind === "prereq")
        .map((e) => ({ id: e.id, source: e.source, target: e.target, kind: e.kind })),
    };
  }, [graph, showRelated]);

  const pathKeys = useMemo(() => new Set(path?.steps.map((s) => s.key) ?? []), [path]);

  const select = useCallback((key: string | null) => {
    setSelected(key);
    setPath(null);
  }, []);

  const showPath = async () => {
    if (!selected) return;
    setPath(await api.learningPath(selected).catch(() => null));
  };

  const prereqsOf = (key: string) => graph?.edges.filter((e) => e.kind === "prereq" && e.target === key) ?? [];
  const unlocks = (key: string) => graph?.edges.filter((e) => e.kind === "prereq" && e.source === key) ?? [];

  const edit = async (action: Promise<KnowledgeGraph>) => {
    try {
      setGraph(await action);
      setPath(null);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not change the link");
    }
  };

  return (
    <div>
      <PageHeader
        title="Knowledge Map"
        description="Every key concept across your materials, coloured by mastery. Arrows point from what you need first to what it unlocks."
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Button onClick={() => rebuild(false)} disabled={busy}>
          <RefreshCw className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} /> {graph?.nodes.length ? "Update map" : "Build map"}
        </Button>
        <Button variant="outline" onClick={() => rebuild(true)} disabled={busy || !graph?.nodes.length}>
          Re-ask AI for prerequisites
        </Button>
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input type="checkbox" checked={showRelated} onChange={(e) => setShowRelated(e.target.checked)} />
          Show “related” links
        </label>
        <div className="ml-auto flex flex-wrap gap-3 text-xs">
          {(Object.keys(LEVEL_COLORS) as ConceptNode["level"][]).map((l) => (
            <span key={l} className="flex items-center gap-1">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: LEVEL_COLORS[l] }} /> {LEVEL_LABELS[l]}
            </span>
          ))}
        </div>
        {message && <p className="w-full text-xs text-cyan-300">{message}</p>}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <Card className="overflow-hidden lg:col-span-2">
          <div ref={wrap} className="h-[34rem] w-full">
            {graph && graph.nodes.length === 0 ? (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center text-sm text-muted-foreground">
                <Network className="h-8 w-8" />
                Concepts come from the summaries of your uploads. Upload material, wait for its summary, then build the map.
              </div>
            ) : (
              <ForceGraph2D
                graphData={data}
                width={width}
                height={544}
                backgroundColor="rgba(0,0,0,0)"
                nodeId="id"
                nodeLabel={(n) => `${(n as GraphNode).name}: ${(n as GraphNode).definition}`}
                linkDirectionalArrowLength={(l) => ((l as GraphLink).kind === "prereq" ? 5 : 0)}
                linkDirectionalArrowRelPos={0.9}
                linkColor={(l) => {
                  const link = l as GraphLink;
                  const onPath = pathKeys.has(endKey(link.source)) && pathKeys.has(endKey(link.target));
                  if (onPath && link.kind === "prereq") return "#a78bfa";
                  return link.kind === "prereq" ? "rgba(203,213,225,0.55)" : "rgba(148,163,184,0.18)";
                }}
                linkLineDash={(l) => ((l as GraphLink).kind === "related" ? [2, 3] : null)}
                linkWidth={(l) => ((l as GraphLink).kind === "prereq" ? 1.5 : 1)}
                onNodeClick={(n) => select((n as GraphNode).id)}
                onBackgroundClick={() => select(null)}
                nodeCanvasObject={(n, ctx, scale) => {
                  const g = n as GraphNode;
                  const r = g.id === selected ? 7 : 5;
                  ctx.beginPath();
                  ctx.arc(g.x ?? 0, g.y ?? 0, r, 0, 2 * Math.PI);
                  ctx.fillStyle = LEVEL_COLORS[g.level];
                  ctx.globalAlpha = path && !pathKeys.has(g.id) ? 0.25 : 1;
                  ctx.fill();
                  if (g.id === selected || pathKeys.has(g.id)) {
                    ctx.lineWidth = 2 / scale;
                    ctx.strokeStyle = "#a78bfa";
                    ctx.stroke();
                  }
                  const size = Math.max(10 / scale, 3);
                  ctx.font = `${size}px sans-serif`;
                  ctx.textAlign = "center";
                  ctx.fillStyle = "#e2e8f0";
                  ctx.fillText(g.name, g.x ?? 0, (g.y ?? 0) + r + size);
                  ctx.globalAlpha = 1;
                }}
                nodePointerAreaPaint={(n, color, ctx) => {
                  const g = n as GraphNode;
                  ctx.fillStyle = color;
                  ctx.beginPath();
                  ctx.arc(g.x ?? 0, g.y ?? 0, 8, 0, 2 * Math.PI);
                  ctx.fill();
                }}
              />
            )}
          </div>
        </Card>

        <div className="space-y-4">
          {!node ? (
            <Card>
              <CardContent className="p-5 text-sm text-muted-foreground">
                Click a concept to see what it needs, what it unlocks, and a learning path to it.
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">{node.name}</CardTitle>
                <p className="text-xs text-muted-foreground">
                  {node.topic} · {node.mastery == null ? "not practised yet" : `${Math.round(node.mastery)}% topic mastery`}
                </p>
              </CardHeader>
              <CardContent className="space-y-4 text-sm">
                {node.definition && <p>{node.definition}</p>}
                {node.documents.length > 0 && (
                  <p className="text-xs text-muted-foreground">From: {node.documents.map((d) => d.title).join(", ")}</p>
                )}
                <Button size="sm" onClick={showPath}>
                  <Route className="h-3.5 w-3.5" /> Learning path to here
                </Button>

                <div>
                  <p className="mb-1 text-xs font-medium">Needs first</p>
                  {prereqsOf(node.key).length === 0 && <p className="text-xs text-muted-foreground">Nothing recorded.</p>}
                  {prereqsOf(node.key).map((e) => (
                    <LinkRow
                      key={e.id}
                      label={nodesByKey.get(e.source)?.name ?? e.source}
                      origin={e.origin}
                      onOpen={() => select(e.source)}
                      onFlip={() => edit(api.flipConceptLink(e.id))}
                      onRemove={() => edit(api.removeConceptLink(e.id))}
                    />
                  ))}
                </div>
                <div>
                  <p className="mb-1 text-xs font-medium">Unlocks</p>
                  {unlocks(node.key).length === 0 && <p className="text-xs text-muted-foreground">Nothing recorded.</p>}
                  {unlocks(node.key).map((e) => (
                    <LinkRow
                      key={e.id}
                      label={nodesByKey.get(e.target)?.name ?? e.target}
                      origin={e.origin}
                      onOpen={() => select(e.target)}
                      onFlip={() => edit(api.flipConceptLink(e.id))}
                      onRemove={() => edit(api.removeConceptLink(e.id))}
                    />
                  ))}
                </div>
                <div className="flex gap-2">
                  <select
                    value={addTarget}
                    onChange={(e) => setAddTarget(e.target.value)}
                    className="h-8 flex-1 rounded-md border border-white/15 bg-white/5 px-2 text-xs"
                  >
                    <option value="" className="bg-slate-900">
                      Add something it needs first…
                    </option>
                    {graph?.nodes
                      .filter((n) => n.key !== node.key)
                      .map((n) => (
                        <option key={n.key} value={n.key} className="bg-slate-900">
                          {n.name}
                        </option>
                      ))}
                  </select>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={!addTarget}
                    onClick={() => {
                      edit(api.addConceptLink(addTarget, node.key));
                      setAddTarget("");
                    }}
                    aria-label="Add prerequisite"
                  >
                    <Plus className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          )}

          {path && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Learning path to {path.target.name}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <ol className="space-y-2">
                  {path.steps.map((s, i) => (
                    <li key={s.key} className="flex items-start gap-2">
                      <span
                        className="mt-1 h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ background: LEVEL_COLORS[s.level] }}
                        title={LEVEL_LABELS[s.level]}
                      />
                      <div>
                        <p className="font-medium">
                          {i + 1}. {s.name}
                        </p>
                        {s.definition && <p className="text-xs text-muted-foreground">{s.definition}</p>}
                      </div>
                    </li>
                  ))}
                </ol>
                {path.skipped.length > 0 && (
                  <p className="text-xs text-muted-foreground">Skipped (already mastered): {path.skipped.join(", ")}</p>
                )}
                <Link href="/tutor" className="inline-flex items-center gap-1 text-xs text-cyan-300 hover:underline">
                  Study step 1 with the AI Tutor <ArrowRight className="h-3 w-3" />
                </Link>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

function LinkRow({
  label,
  origin,
  onOpen,
  onFlip,
  onRemove,
}: {
  label: string;
  origin: string;
  onOpen: () => void;
  onFlip: () => void;
  onRemove: () => void;
}) {
  return (
    <div className="flex items-center gap-2 py-0.5 text-xs">
      <button className="flex-1 truncate text-left hover:text-cyan-300" onClick={onOpen}>
        {label}
      </button>
      <span className="text-[10px] text-muted-foreground">{origin === "user" ? "you" : origin === "ai" ? "AI" : "doc"}</span>
      <button aria-label="Flip direction" title="Wrong way round: flip it" onClick={onFlip}>
        <ArrowLeftRight className="h-3.5 w-3.5 text-muted-foreground hover:text-foreground" />
      </button>
      <button aria-label="Remove link" title="Not a real prerequisite: remove" onClick={onRemove}>
        <Trash2 className="h-3.5 w-3.5 text-red-400" />
      </button>
    </div>
  );
}
