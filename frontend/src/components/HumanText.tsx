"use client";

/** Plain human-readable text — line breaks preserved, no markdown rendering. */
export function HumanText({ text, className = "" }: { text: string; className?: string }) {
  return (
    <p className={`whitespace-pre-wrap text-sm leading-relaxed ${className}`}>{text}</p>
  );
}
