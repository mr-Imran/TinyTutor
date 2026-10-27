"use client";

import { useState } from "react";
import { CheckCircle2, CircleHelp, Sigma, XCircle } from "lucide-react";
import { Markdown } from "@/components/Markdown";
import { Button } from "@/components/ui/button";
import { api, MathSolution } from "@/lib/api";

/** True for questions that look like algebra or arithmetic, where step checking helps. */
export function looksMathematical(text: string) {
  return /\$|\\frac|\\sqrt|[0-9]\s*[-+*/^=]\s*[0-9a-z(]|\b(solve|simplify|expand|factor|derivative|integral|equation)\b/i.test(
    text
  );
}

const STATUS = {
  verified: { icon: CheckCircle2, className: "text-emerald-400", title: "Checked with algebra: follows from the step before" },
  mismatch: { icon: XCircle, className: "text-red-400", title: "Does not follow from the step before. Check this step carefully" },
  unchecked: { icon: CircleHelp, className: "text-muted-foreground", title: "Not checked automatically" },
};

function asMath(expression: string) {
  return expression.includes("$") ? expression : `$${expression}$`;
}

/** "Show steps": a worked solution where each algebra step is verified with sympy. */
export function MathSteps({ problem }: { problem: string }) {
  const [solution, setSolution] = useState<MathSolution | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const solve = async () => {
    setBusy(true);
    setError("");
    try {
      setSolution(await api.solveMath(problem));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not solve this");
    } finally {
      setBusy(false);
    }
  };

  if (!solution) {
    return (
      <div>
        <Button variant="outline" size="sm" onClick={solve} disabled={busy}>
          <Sigma className="h-3.5 w-3.5" /> {busy ? "Working it out…" : "Show steps"}
        </Button>
        {error && <p className="mt-1 text-xs text-red-400">{error}</p>}
      </div>
    );
  }
  return (
    <div className="rounded-lg border border-white/10 bg-black/20 p-3 text-sm">
      <p className="mb-2 text-xs text-muted-foreground">
        Worked solution · {solution.verified} step{solution.verified === 1 ? "" : "s"} verified with algebra
        {solution.mismatches > 0 && (
          <span className="text-red-300"> · {solution.mismatches} step(s) look wrong, so be careful</span>
        )}
      </p>
      <ol className="space-y-2">
        {solution.steps.map((s, i) => {
          const { icon: Icon, className, title } = STATUS[s.status];
          return (
            <li key={i} className="flex gap-2">
              <span title={title}>
                <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${className}`} />
              </span>
              <div className="min-w-0">
                {s.explanation && <Markdown text={s.explanation} className="text-muted-foreground" />}
                {s.expression && <Markdown text={asMath(s.expression)} />}
              </div>
            </li>
          );
        })}
      </ol>
      {solution.final_answer && (
        <div className="mt-2 border-t border-white/10 pt-2">
          <span className="text-xs text-muted-foreground">Answer: </span>
          <Markdown text={asMath(solution.final_answer)} inline />
        </div>
      )}
    </div>
  );
}
