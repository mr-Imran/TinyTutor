"use client";

import { motion } from "framer-motion";
import { Cpu, Database, Server } from "lucide-react";
import { PageHeader } from "@/components/PageHeader";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  return (
    <div>
      <PageHeader
        title="Settings"
        description="Local-first configuration — everything runs on your machine."
      />

      <div className="grid gap-6 md:grid-cols-2">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Server className="h-5 w-5 text-violet-400" /> Backend API
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>
                URL: <code className="text-foreground">{apiUrl}</code>
              </p>
              <p>FastAPI + SQLite — no cloud required.</p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }}>
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Cpu className="h-5 w-5 text-cyan-400" /> AI Model (Ollama)
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm text-muted-foreground">
              <p>
                Default model: <code className="text-foreground">qwen2.5:0.5b</code>
              </p>
              <p>Install: <code className="text-foreground">ollama pull qwen2.5:0.5b</code></p>
              <p>Alternative: <code className="text-foreground">gemma3:270m</code> (edit backend/config.py)</p>
            </CardContent>
          </Card>
        </motion.div>

        <motion.div
          className="md:col-span-2"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5 text-emerald-400" /> Storage
              </CardTitle>
            </CardHeader>
            <CardContent className="text-sm text-muted-foreground">
              <ul className="list-inside list-disc space-y-1">
                <li>SQLite database: backend/data/tutor.db</li>
                <li>Uploads: backend/data/uploads/</li>
                <li>Keyword search on chunks — no vector database</li>
                <li>APScheduler sends a practice question every 30 minutes for weak topics</li>
              </ul>
            </CardContent>
          </Card>
        </motion.div>
      </div>
    </div>
  );
}
