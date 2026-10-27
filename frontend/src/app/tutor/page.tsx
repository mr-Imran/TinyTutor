"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { Send, Bot, User, Plus, MessageSquare, Trash2, Mic, Square, Volume2, VolumeX } from "lucide-react";
import { CitedText } from "@/components/CitedText";
import { HumanText } from "@/components/HumanText";
import { PageHeader } from "@/components/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { api, ChatSession, ChatSource, streamChat } from "@/lib/api";
import { canSpeak, speak, stopSpeaking, useSpeechRecognition } from "@/lib/speech";

type Message = { role: "user" | "assistant"; content: string; sources?: ChatSource[] };

const GREETING: Message = {
  role: "assistant",
  content: "Hi! Ask me anything from your uploaded study materials. I explain concepts simply and show where each answer came from.",
};

export default function TutorPage() {
  const [messages, setMessages] = useState<Message[]>([GREETING]);
  const [input, setInput] = useState("");
  const [topics, setTopics] = useState<string[]>([]);
  const [topic, setTopic] = useState("");
  const [loading, setLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [readAloud, setReadAloud] = useState(false);
  const [ttsAvailable, setTtsAvailable] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const loadSessions = useCallback(() => {
    api.chatSessions("tutor").then(setSessions).catch(() => {});
  }, []);

  useEffect(() => {
    api.topics().then((r) => setTopics(r.topics)).catch(() => {});
    loadSessions();
  }, [loadSessions]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    return () => abortRef.current?.abort();
  }, []);

  // Speaking a question sends it as soon as the speaker pauses.
  const voice = useSpeechRecognition((text) => send(text));

  useEffect(() => {
    setTtsAvailable(canSpeak());
    return stopSpeaking;
  }, []);

  const openSession = async (id: number) => {
    if (loading) return;
    const detail = await api.chatSession(id);
    setSessionId(id);
    setMessages(
      detail.messages.length
        ? detail.messages.map((m) => ({ role: m.role, content: m.content, sources: m.sources }))
        : [GREETING]
    );
  };

  const newChat = () => {
    if (loading) return;
    setSessionId(null);
    setMessages([GREETING]);
  };

  const removeSession = async (id: number) => {
    await api.deleteChatSession(id);
    if (id === sessionId) newChat();
    loadSessions();
  };

  const send = async (spoken?: string) => {
    const userMsg = (spoken ?? input).trim();
    if (!userMsg || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", content: userMsg }, { role: "assistant", content: "" }]);
    setLoading(true);

    const setLast = (msg: Message) =>
      setMessages((m) => {
        const copy = [...m];
        copy[copy.length - 1] = msg;
        return copy;
      });

    try {
      const controller = new AbortController();
      abortRef.current = controller;
      const result = await streamChat(
        "tutor",
        { message: userMsg, topic: topic || undefined, session_id: sessionId },
        (full, meta) => setLast({ role: "assistant", content: full, sources: meta.sources }),
        controller.signal
      );
      if (result.sessionId && result.sessionId !== sessionId) setSessionId(result.sessionId);
      if (readAloud) speak(result.text);
      loadSessions();
    } catch {
      setLast({ role: "assistant", content: "Could not reach the AI. Is the backend running and an AI provider set up in Settings?" });
    } finally {
      abortRef.current = null;
      setLoading(false);
    }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      <PageHeader title="AI Tutor" description="Chat with your study materials — answers cite the exact page they came from." />

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

      <div className="flex min-h-0 flex-1 gap-4">
        <Card className="hidden w-60 shrink-0 flex-col overflow-hidden lg:flex">
          <div className="border-b border-white/10 p-3">
            <Button variant="outline" size="sm" className="w-full" onClick={newChat}>
              <Plus className="h-4 w-4" /> New chat
            </Button>
          </div>
          <div className="flex-1 space-y-1 overflow-y-auto p-2">
            {sessions.length === 0 && <p className="p-2 text-xs text-muted-foreground">Past chats appear here.</p>}
            {sessions.map((s) => (
              <div
                key={s.id}
                className={`group flex items-center gap-2 rounded-md px-2 py-2 text-xs ${
                  s.id === sessionId ? "bg-primary/20 text-white" : "text-muted-foreground hover:bg-white/5"
                }`}
              >
                <button className="flex min-w-0 flex-1 items-center gap-2 text-left" onClick={() => openSession(s.id)}>
                  <MessageSquare className="h-3.5 w-3.5 shrink-0" />
                  <span className="truncate">{s.title}</span>
                </button>
                <button
                  aria-label="Delete chat"
                  className="opacity-0 transition-opacity group-hover:opacity-100"
                  onClick={() => removeSession(s.id)}
                >
                  <Trash2 className="h-3.5 w-3.5 text-red-400" />
                </button>
              </div>
            ))}
          </div>
        </Card>

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
                    msg.role === "user" ? "bg-primary/30 text-white" : "bg-white/5 text-foreground"
                  }`}
                >
                  {msg.role === "assistant" ? (
                    <CitedText text={msg.content} sources={msg.sources} />
                  ) : (
                    <HumanText text={msg.content} />
                  )}
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
              placeholder={
                voice.listening ? "Listening…" : sessionId ? "Ask a follow-up…" : "Ask about your textbooks…"
              }
              value={voice.listening ? voice.interim : input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && send()}
              readOnly={voice.listening}
            />
            {voice.supported && (
              <Button
                variant={voice.listening ? "default" : "outline"}
                size="icon"
                onClick={voice.listening ? voice.stop : voice.start}
                disabled={loading}
                aria-label={voice.listening ? "Stop listening" : "Ask by voice"}
                title={voice.error ?? (voice.listening ? "Stop listening" : "Ask by voice")}
              >
                {voice.listening ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
              </Button>
            )}
            {ttsAvailable && (
              <Button
                variant={readAloud ? "default" : "outline"}
                size="icon"
                onClick={() => {
                  if (readAloud) stopSpeaking();
                  setReadAloud(!readAloud);
                }}
                aria-label={readAloud ? "Stop reading answers aloud" : "Read answers aloud"}
                title={readAloud ? "Reading answers aloud" : "Read answers aloud"}
              >
                {readAloud ? <Volume2 className="h-4 w-4" /> : <VolumeX className="h-4 w-4" />}
              </Button>
            )}
            <Button onClick={() => send()} disabled={loading} size="icon" aria-label="Send">
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
}
