"use client";

import { Markdown } from "@/components/Markdown";

export function ExplanationView({ text }: { text: string }) {
  return <Markdown text={text} className="text-muted-foreground" />;
}
