"use client";

import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Send, Bot, User } from "lucide-react";
import { HumanText } from "@/components/HumanText";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

type Message = { role: "user" | "assistant"; content: string };

export default function TutorPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "Hi! Ask me anything from your uploaded study materials. I explain concepts simply.",
    },
  ]);
  const [input, setInput] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    import("@/lib/api").then(({ api }) =>
      api.topics().then((r) => setTopics(r.topics)).catch(() => {})
    );
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = async () => {
    if (!input.trim() || loading) return;
    const userMsg = input.trim();
    setInput("");
    setMessages((m) => [...m, { role: "user", content: userMsg }]);
    setLoading(true);
    setMessages((m) => [...m, { role: "assistant", content: "" }]);
    try {
      const { default: API_BASE } = await import("@/lib/api-base");
      const controller = new AbortController();
      abortRef.current = controller;
      const res = await fetch(`${API_BASE}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: userMsg, topic: topic || undefined }),
        signal: controller.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(await res.text());
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let full = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value, { stream: true });
        setMessages((m) => {
          const copy = [...m];
          copy[copy.length - 1] = { role: "assistant", content: full };
          return copy;
        });
      }
    } catch {
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = {
          role: "assistant",
          content: "Could not reach the AI. Is the backend and Ollama running?",
        };
        return copy;
      });
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <PageHeader
        title="AI Tutor"
        description="Chat with your study materials — concepts explained simply."
      />

      {topics.length > 0 && (
        <div className="mb-4 flex flex-wrap gap-2">
          <button
            onClick={() => setTopic("")}
            className={`rounded-full px-3 py-1 text-xs ${!topic ? "bg-primary text-white" : "bg-white/10"}`}
          >
            All topics
          </button>
          {topics.map((t) => (
            <button
              key={t}
              onClick={() => setTopic(t)}
              className={`rounded-full px-3 py-1 text-xs ${topic === t ? "bg-primary text-white" : "bg-white/10"}`}
            >
              {t}
            </button>
          ))}
        </div>
      )}

      <Card className="flex flex-1 flex-col overflow-hidden">
        <CardContent className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
          {messages.map((msg, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={`flex gap-3 ${msg.role === "user" ? "justify-end" : ""}`}
            >
              {msg.role === "assistant" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-violet-500/20">
                  <Bot className="h-4 w-4 text-violet-400" />
                </div>
              )}
              <div
                className={`max-w-[85%] rounded-xl px-4 py-3 text-sm ${
                  msg.role === "user"
                    ? "bg-primary/30 text-white"
                    : "bg-white/5 text-foreground"
                }`}
              >
                <HumanText text={msg.content} />
              </div>
              {msg.role === "user" && (
                <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-cyan-500/20">
                  <User className="h-4 w-4 text-cyan-400" />
                </div>
              )}
            </motion.div>
          ))}
          {loading && <Skeleton className="h-3 w-24" />}
          <div ref={bottomRef} />
        </CardContent>

        <div className="flex gap-2 border-t border-white/10 p-4">
          <Input
            placeholder="Ask about your textbooks…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && send()}
          />
          <Button onClick={send} disabled={loading} size="icon">
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </Card>
    </div>
  );
}
