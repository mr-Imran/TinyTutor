import { Flashcard } from "@/lib/api";

const CLOZE = /\{\{c(\d+)::([\s\S]*?)(?:::([\s\S]*?))?\}\}/g;

/** Cloze text for one card: the asked blank hidden (or shown, bold), other blanks filled in. */
export function renderCloze(text: string, index: number, reveal: boolean, markdown = true) {
  return text.replace(CLOZE, (_, n: string, answer: string, hint?: string) => {
    if (Number(n) !== index) return answer;
    const shown = reveal ? answer : hint ? `[${hint}]` : "[...]";
    return markdown ? `**${shown}**` : shown;
  });
}

export function clozeCount(text: string) {
  return new Set(Array.from(text.matchAll(CLOZE), (m) => m[1])).size;
}

/** Wrap the selected range of a textarea's text in the next {{cN::...}}. */
export function addBlank(text: string, start: number, end: number) {
  if (start === end) return { text, added: false };
  const used = Array.from(text.matchAll(CLOZE), (m) => Number(m[1]));
  const next = used.length ? Math.max(...used) + 1 : 1;
  return {
    text: `${text.slice(0, start)}{{c${next}::${text.slice(start, end)}}}${text.slice(end)}`,
    added: true,
  };
}

/** What oral mode reads out for each side of a card. */
export function spokenCard(card: Flashcard, side: "front" | "back") {
  if (card.card_type === "cloze" && card.cloze_index != null) {
    const text = renderCloze(card.front, card.cloze_index, side === "back", false).replace(/\[\.\.\.\]/g, "blank");
    return side === "back" && card.back ? `${text}. ${card.back}` : text;
  }
  if (card.card_type === "occlusion") {
    return side === "front" ? `${card.front}. Look at the highlighted box on screen.` : card.back;
  }
  return side === "front" ? card.front : card.back;
}
