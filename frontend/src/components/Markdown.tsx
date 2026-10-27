"use client";

import { ReactNode } from "react";
import ReactMarkdown, { Components, defaultUrlTransform } from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import "katex/dist/katex.min.css";
import "highlight.js/styles/github-dark.css";
import { cn } from "@/lib/utils";

// [3] citation markers become links to "#cite-3", which renderCitation turns into a chip.
const CITE_PREFIX = "#cite-";

function withCitationLinks(text: string) {
  // Leave code untouched: only replace markers outside ``` fences and `inline code`.
  return text
    .split(/(```[\s\S]*?```|`[^`\n]*`)/g)
    .map((part, i) => (i % 2 ? part : part.replace(/\[(\d+)\](?!\()/g, `[$1](${CITE_PREFIX}$1)`)))
    .join("");
}

/** LLMs often write \( \) and \[ \] for math; remark-math only reads $ delimiters. */
function normalizeMath(text: string) {
  return text
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => `$$${m}$$`)
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => `$${m}$`);
}

const baseComponents: Components = {
  p: ({ children }) => <p className="mb-2 whitespace-pre-wrap leading-relaxed last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="mb-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="mb-2 list-decimal space-y-1 pl-5">{children}</ol>,
  h1: ({ children }) => <h3 className="mb-2 mt-3 text-base font-semibold">{children}</h3>,
  h2: ({ children }) => <h3 className="mb-2 mt-3 text-base font-semibold">{children}</h3>,
  h3: ({ children }) => <h4 className="mb-1 mt-2 font-semibold">{children}</h4>,
  blockquote: ({ children }) => (
    <blockquote className="mb-2 border-l-2 border-violet-400/50 pl-3 text-muted-foreground">{children}</blockquote>
  ),
  pre: ({ children }) => (
    <pre className="mb-2 overflow-x-auto rounded-lg bg-black/40 p-3 text-xs leading-relaxed">{children}</pre>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="rounded bg-white/10 px-1 py-0.5 text-[0.9em]">{children}</code>
    ),
  table: ({ children }) => (
    <div className="mb-2 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border border-white/15 px-2 py-1 text-left">{children}</th>,
  td: ({ children }) => <td className="border border-white/15 px-2 py-1">{children}</td>,
};

/**
 * Markdown with LaTeX math ($x^2$, $$...$$), highlighted code blocks and tables.
 * Pass renderCitation to turn [n] markers into citation chips.
 */
export function Markdown({
  text,
  className,
  renderCitation,
  renderLink,
  inline = false,
}: {
  text: string;
  className?: string;
  renderCitation?: (n: number) => ReactNode;
  /** Custom rendering for some links (return undefined for the default). */
  renderLink?: (href: string, children: ReactNode) => ReactNode | undefined;
  inline?: boolean;
}) {
  const components: Components = {
    ...baseComponents,
    ...(inline ? { p: ({ children }) => <span className="whitespace-pre-wrap">{children}</span> } : {}),
    a: ({ href, children }) => {
      if (href?.startsWith(CITE_PREFIX) && renderCitation) return <>{renderCitation(Number(href.slice(CITE_PREFIX.length)))}</>;
      if (href?.startsWith(CITE_PREFIX)) return <span>{children}</span>;
      const custom = href && renderLink ? renderLink(href, children) : undefined;
      if (custom !== undefined) return <>{custom}</>;
      return (
        <a href={href} target="_blank" rel="noreferrer" className="text-cyan-300 underline underline-offset-2">
          {children}
        </a>
      );
    },
  };
  const source = normalizeMath(renderCitation ? withCitationLinks(text) : text);
  const Tag = inline ? "span" : "div";
  return (
    <Tag className={cn("markdown text-sm", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, [remarkMath, { singleDollarTextMath: true }]]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: false }], [rehypeHighlight, { detect: true, ignoreMissing: true }]]}
        components={components}
        urlTransform={(url) => (url.startsWith(CITE_PREFIX) || url.startsWith("#") ? url : defaultUrlTransform(url))}
      >
        {source}
      </ReactMarkdown>
    </Tag>
  );
}
