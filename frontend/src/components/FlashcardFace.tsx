"use client";

import { Markdown } from "@/components/Markdown";
import { cardImageUrl, Flashcard } from "@/lib/api";
import { renderCloze } from "@/lib/cards";

/** An image with occlusion boxes: the asked box is solid orange until revealed, then outlined. */
export function OcclusionImage({ card, reveal, small = false }: { card: Flashcard; reveal: boolean; small?: boolean }) {
  if (!card.image_name || !card.masks) return null;
  return (
    <div className={`relative inline-block ${small ? "max-w-[10rem]" : "max-w-full"}`}>
      {/* eslint-disable-next-line @next/next/no-img-element -- served by the backend, not optimisable */}
      <img src={cardImageUrl(card.image_name)} alt="" className="block max-h-[22rem] max-w-full rounded-md" />
      {card.masks.map((m, i) => {
        const target = i === card.cloze_index;
        const style = { left: `${m.x * 100}%`, top: `${m.y * 100}%`, width: `${m.w * 100}%`, height: `${m.h * 100}%` };
        if (!target) return null;
        return (
          <div
            key={i}
            style={style}
            className={`absolute rounded-sm ${reveal ? "border-2 border-red-500" : "border border-orange-700 bg-orange-500"}`}
          />
        );
      })}
    </div>
  );
}

export function FlashcardFront({ card }: { card: Flashcard }) {
  if (card.card_type === "cloze" && card.cloze_index != null) {
    return <Markdown text={renderCloze(card.front, card.cloze_index, false)} className="text-xl font-medium" />;
  }
  if (card.card_type === "occlusion") {
    return (
      <div className="space-y-3">
        <p className="text-lg font-medium">{card.front}</p>
        <OcclusionImage card={card} reveal={false} />
      </div>
    );
  }
  return <Markdown text={card.front} className="text-xl font-medium" />;
}

export function FlashcardBack({ card }: { card: Flashcard }) {
  if (card.card_type === "cloze" && card.cloze_index != null) {
    return (
      <div className="space-y-2">
        <Markdown text={renderCloze(card.front, card.cloze_index, true)} className="text-lg" />
        {card.back && <Markdown text={card.back} className="text-muted-foreground" />}
      </div>
    );
  }
  if (card.card_type === "occlusion") {
    return (
      <div className="space-y-2">
        <OcclusionImage card={card} reveal />
        <p className="text-lg font-medium text-emerald-300">{card.back}</p>
      </div>
    );
  }
  return <Markdown text={card.back} className="text-muted-foreground" />;
}

/** One-line summary for the card list. */
export function FlashcardSummary({ card }: { card: Flashcard }) {
  if (card.card_type === "cloze" && card.cloze_index != null) {
    return <Markdown text={renderCloze(card.front, card.cloze_index, true)} className="font-medium" />;
  }
  if (card.card_type === "occlusion") {
    return (
      <div className="flex items-center gap-3">
        <OcclusionImage card={card} reveal small />
        <span className="font-medium">{card.back}</span>
      </div>
    );
  }
  return (
    <>
      <Markdown text={card.front} className="font-medium" />
      <Markdown text={card.back} className="text-muted-foreground" />
    </>
  );
}
