"use client";

import { useCallback, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { FileUp, Trash2, FileText, Presentation } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, Document } from "@/lib/api";

export default function UploadPage() {
  const [docs, setDocs] = useState<Document[]>([]);
  const [uploading, setUploading] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");

  const load = useCallback(() => {
    api.documents().then(setDocs).catch(console.error).finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    setMessage("");
    try {
      for (const file of Array.from(files)) {
        const ext = file.name.toLowerCase();
        if (!ext.endsWith(".pdf") && !ext.endsWith(".pptx")) {
          setMessage("Only PDF and PPTX files are supported.");
          continue;
        }
        const result = await api.upload(file);
        setMessage(`Uploaded "${result.title}" — ${result.chunk_count} chunks stored.`);
      }
      load();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const remove = async (id: number) => {
    await api.deleteDocument(id);
    load();
  };

  return (
    <div>
      <PageHeader
        title="Upload Materials"
        description="Add PDF books, class notes, PPTX slides, or previous year papers."
      />

      <motion.div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        animate={{ scale: dragOver ? 1.02 : 1 }}
        className={`glass-card mb-8 flex flex-col items-center justify-center border-2 border-dashed p-12 transition-colors ${
          dragOver ? "border-primary bg-primary/10" : "border-white/20"
        }`}
      >
        <FileUp className="mb-4 h-12 w-12 text-violet-400" />
        <p className="mb-2 text-lg font-medium">Drag & drop files here</p>
        <p className="mb-4 text-sm text-muted-foreground">PDF or PPTX · Max 25MB</p>
        <label className="cursor-pointer">
          <input
            type="file"
            accept=".pdf,.pptx"
            multiple
            className="hidden"
            disabled={uploading}
            onChange={(e) => handleFiles(e.target.files)}
          />
          <span className="inline-flex h-10 items-center justify-center rounded-lg bg-primary px-4 text-sm font-medium text-primary-foreground shadow-lg">
            {uploading ? "Processing…" : "Browse files"}
          </span>
        </label>
      </motion.div>

      <AnimatePresence>
        {message && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="mb-4 text-sm text-cyan-400"
          >
            {message}
          </motion.p>
        )}
      </AnimatePresence>

      <h2 className="mb-4 text-lg font-semibold">Your Library</h2>
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-20" />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No documents yet. Upload your first study material above.
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {docs.map((doc, i) => (
            <motion.div
              key={doc.id}
              initial={{ opacity: 0, x: -10 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.05 }}
            >
              <Card className="flex flex-row items-center justify-between gap-4">
                <CardContent className="flex items-center gap-4 py-4">
                  {doc.file_type === "pdf" ? (
                    <FileText className="h-8 w-8 text-red-400" />
                  ) : (
                    <Presentation className="h-8 w-8 text-orange-400" />
                  )}
                  <div>
                    <p className="font-medium">{doc.title || doc.filename}</p>
                    <p className="text-sm text-muted-foreground">
                      {doc.topic} · {doc.chunk_count} chunks
                    </p>
                  </div>
                </CardContent>
                <Button variant="ghost" size="icon" onClick={() => remove(doc.id)}>
                  <Trash2 className="h-4 w-4 text-red-400" />
                </Button>
              </Card>
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}
