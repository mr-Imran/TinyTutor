"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Database, Plus, Pencil, Trash2, ChevronLeft, ChevronRight, Search } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, AddContextBody, DbOverview } from "@/lib/api";

const PAGE_SIZE = 25;

const TABLE_LABELS: Record<string, string> = {
  users: "Users",
  documents: "Documents",
  knowledge_chunks: "Knowledge Chunks",
  quiz_attempts: "Quiz Attempts",
  topic_scores: "Topic Scores",
  scheduled_questions: "Scheduled Questions",
};

function truncate(val: unknown, max = 80): string {
  const s = val === null || val === undefined ? "" : String(val);
  return s.length > max ? s.slice(0, max) + "…" : s;
}

export default function DatabasePage() {
  const [overview, setOverview] = useState<DbOverview | null>(null);
  const [activeTable, setActiveTable] = useState("knowledge_chunks");
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [search, setSearch] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedRow, setSelectedRow] = useState<Record<string, unknown> | null>(null);

  const [showAdd, setShowAdd] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<AddContextBody>({
    title: "",
    topic: "General",
    content: "",
    source: "Manual entry",
  });
  const [message, setMessage] = useState("");

  const loadOverview = useCallback(() => {
    api.dbOverview().then(setOverview).catch(console.error);
  }, []);

  const loadTable = useCallback(() => {
    setLoading(true);
    api
      .dbTable(activeTable, PAGE_SIZE, offset, activeTable === "knowledge_chunks" ? search : "")
      .then((res) => {
        setRows(res.rows);
        setTotal(res.total);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [activeTable, offset, search]);

  useEffect(() => {
    loadOverview();
  }, [loadOverview]);

  useEffect(() => {
    loadTable();
  }, [loadTable]);

  useEffect(() => {
    setOffset(0);
    setSelectedRow(null);
  }, [activeTable]);

  const saveContext = async () => {
    if (!form.content.trim()) return;
    try {
      if (editId) {
        await api.updateChunk(editId, form);
        setMessage("Chunk updated — AI tutor will use the new text.");
      } else {
        await api.addContext(form);
        setMessage("Context added — available in AI Tutor and quizzes.");
      }
      setShowAdd(false);
      setEditId(null);
      setForm({ title: "", topic: "General", content: "", source: "Manual entry" });
      loadOverview();
      loadTable();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Save failed");
    }
  };

  const startEdit = (row: Record<string, unknown>) => {
    setEditId(row.id as number);
    setForm({
      title: String(row.title || ""),
      topic: String(row.topic || "General"),
      content: String(row.content || ""),
      source: String(row.source || "Manual entry"),
    });
    setShowAdd(true);
  };

  const deleteChunk = async (id: number) => {
    if (!confirm("Delete this knowledge chunk?")) return;
    await api.deleteChunk(id);
    setMessage("Chunk deleted.");
    setSelectedRow(null);
    loadOverview();
    loadTable();
  };

  const columns =
    rows.length > 0
      ? Object.keys(rows[0]).filter((k) => k !== "content" || activeTable !== "knowledge_chunks")
      : [];

  const displayColumns =
    activeTable === "knowledge_chunks"
      ? ["id", "title", "topic", "source", "created_at"]
      : columns.slice(0, 6);

  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  return (
    <div>
      <PageHeader
        title="Local Database"
        description="Browse SQLite tables and add study context manually for the AI tutor."
      />

      {overview && (
        <p className="mb-4 text-xs text-muted-foreground font-mono">{overview.db_path}</p>
      )}

      {/* Quick add context */}
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-6">
        <Card className="border-violet-500/30">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Plus className="h-4 w-4 text-violet-400" />
              Add study context
            </CardTitle>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setEditId(null);
                setForm({ title: "", topic: "General", content: "", source: "Manual entry" });
                setShowAdd(!showAdd);
              }}
            >
              {showAdd ? "Close" : "New chunk"}
            </Button>
          </CardHeader>
          <AnimatePresence>
            {showAdd && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
              >
                <CardContent className="space-y-3 border-t border-white/10 pt-4">
                  <div className="grid gap-3 sm:grid-cols-2">
                    <Input
                      placeholder="Title"
                      value={form.title}
                      onChange={(e) => setForm({ ...form, title: e.target.value })}
                    />
                    <Input
                      placeholder="Topic"
                      value={form.topic}
                      onChange={(e) => setForm({ ...form, topic: e.target.value })}
                    />
                  </div>
                  <Input
                    placeholder="Source (e.g. Lecture notes)"
                    value={form.source}
                    onChange={(e) => setForm({ ...form, source: e.target.value })}
                  />
                  <textarea
                    className="min-h-[120px] w-full rounded-lg border border-white/15 bg-white/5 p-3 text-sm backdrop-blur focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    placeholder="Paste definitions, formulas, or notes the AI should use…"
                    value={form.content}
                    onChange={(e) => setForm({ ...form, content: e.target.value })}
                  />
                  <Button onClick={saveContext}>
                    {editId ? "Update chunk" : "Save to database"}
                  </Button>
                </CardContent>
              </motion.div>
            )}
          </AnimatePresence>
        </Card>
      </motion.div>

      {message && (
        <p className="mb-4 text-sm text-cyan-400">{message}</p>
      )}

      <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
        {/* Table list */}
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-sm">
              <Database className="h-4 w-4" /> Tables
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 p-2">
            {overview?.tables.map((t) => (
              <button
                key={t.name}
                onClick={() => setActiveTable(t.name)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition-colors ${
                  activeTable === t.name
                    ? "bg-primary/25 text-white"
                    : "hover:bg-white/5 text-muted-foreground"
                }`}
              >
                <span>{TABLE_LABELS[t.name] || t.name}</span>
                <span className="text-xs opacity-70">{t.row_count}</span>
              </button>
            ))}
          </CardContent>
        </Card>

        {/* Data grid */}
        <div className="space-y-4">
          {activeTable === "knowledge_chunks" && (
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                className="pl-9"
                placeholder="Search chunks…"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setOffset(0);
                }}
              />
            </div>
          )}

          <Card className="overflow-hidden">
            {loading ? (
              <CardContent className="space-y-2 p-4">
                {[1, 2, 3, 4, 5].map((i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </CardContent>
            ) : rows.length === 0 ? (
              <CardContent className="py-12 text-center text-muted-foreground">
                No rows in this table.
              </CardContent>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-white/10 bg-white/5">
                      {displayColumns.map((col) => (
                        <th key={col} className="px-4 py-3 text-left font-medium text-muted-foreground">
                          {col}
                        </th>
                      ))}
                      {activeTable === "knowledge_chunks" && (
                        <th className="px-4 py-3 text-right">Actions</th>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={String(row.id)}
                        className="cursor-pointer border-b border-white/5 hover:bg-white/5"
                        onClick={() => setSelectedRow(row)}
                      >
                        {displayColumns.map((col) => (
                          <td key={col} className="px-4 py-3 font-mono text-xs">
                            {truncate(row[col])}
                          </td>
                        ))}
                        {activeTable === "knowledge_chunks" && (
                          <td className="px-4 py-3 text-right" onClick={(e) => e.stopPropagation()}>
                            <Button variant="ghost" size="icon" onClick={() => startEdit(row)}>
                              <Pencil className="h-3.5 w-3.5" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => deleteChunk(row.id as number)}
                            >
                              <Trash2 className="h-3.5 w-3.5 text-red-400" />
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex items-center justify-between border-t border-white/10 px-4 py-3">
              <span className="text-xs text-muted-foreground">
                {total} rows · page {currentPage} / {pageCount}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  <ChevronLeft className="h-4 w-4" />
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset + PAGE_SIZE >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  <ChevronRight className="h-4 w-4" />
                </Button>
              </div>
            </div>
          </Card>

          {/* Row detail */}
          <AnimatePresence>
            {selectedRow && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
              >
                <Card>
                  <CardHeader className="flex flex-row items-center justify-between">
                    <CardTitle className="text-sm">Row #{String(selectedRow.id)}</CardTitle>
                    <Button variant="ghost" size="sm" onClick={() => setSelectedRow(null)}>
                      Close
                    </Button>
                  </CardHeader>
                  <CardContent className="max-h-96 space-y-3 overflow-y-auto">
                    {Object.entries(selectedRow).map(([key, val]) => (
                      <div key={key}>
                        <p className="text-xs font-medium text-violet-400">{key}</p>
                        <pre className="mt-1 whitespace-pre-wrap break-words rounded-lg bg-black/20 p-2 text-xs text-muted-foreground">
                          {val === null ? "null" : String(val)}
                        </pre>
                      </div>
                    ))}
                  </CardContent>
                </Card>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}
