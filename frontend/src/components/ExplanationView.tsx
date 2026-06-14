"use client";

import { HumanText } from "@/components/HumanText";

export function ExplanationView({ text }: { text: string }) {
  return <HumanText text={text} className="text-muted-foreground" />;
}
