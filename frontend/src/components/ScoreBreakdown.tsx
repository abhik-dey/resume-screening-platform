import type { ScoreComponent } from "../api/types";

/* ---------------------------------------------------------------------
   THE SIGNATURE ELEMENT.

   A score in this system is never just a number — it's the sum of three
   weighted components, and the whole product is built around being able
   to answer "why that number?". So the score is drawn as a stacked bar
   whose segment widths ARE the weighted contributions. The bar is the
   arithmetic, not a decoration of it.

   The empty remainder is shown too: the gap between what a candidate
   earned and the full width is as informative as what they earned.
   --------------------------------------------------------------------- */

const COMPONENT_COLORS: Record<string, string> = {
  skills: "var(--signal)",
  experience: "var(--accent)",
  education: "#7a8fa6",
};

export function ScoreBar({
  components, score, compact = false,
}: {
  components?: ScoreComponent[];
  score: number;
  compact?: boolean;
}) {
  const height = compact ? "h-1.5" : "h-2.5";

  // Without a breakdown (list views read from the stored score only), fall
  // back to a single bar rather than inventing a decomposition.
  if (!components || components.length === 0) {
    return (
      <div className={`w-full ${height} bg-line rounded-full overflow-hidden`}>
        <div className="h-full bg-signal rounded-full" style={{ width: `${score * 100}%` }} />
      </div>
    );
  }

  return (
    <div className={`w-full ${height} bg-line rounded-full overflow-hidden flex`}
      role="img"
      aria-label={`Match score ${(score * 100).toFixed(0)} percent, composed of ${components
        .map((c) => `${c.name} ${(c.weighted_score * 100).toFixed(0)}`)
        .join(", ")}`}>
      {components.map((component) => (
        <div key={component.name}
          style={{
            width: `${component.weighted_score * 100}%`,
            background: COMPONENT_COLORS[component.name] ?? "var(--ink-faint)",
          }}
          title={`${component.name}: ${(component.weighted_score * 100).toFixed(1)} of ${(
            component.weight * 100
          ).toFixed(0)} available`}
        />
      ))}
    </div>
  );
}

export function ScoreBreakdown({ components, score }: { components: ScoreComponent[]; score: number }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <span className="eyebrow">Match score</span>
        <span className="numeric text-2xl font-semibold text-ink">{score.toFixed(2)}</span>
      </div>

      <ScoreBar components={components} score={score} />

      <dl className="mt-4 space-y-3">
        {components.map((component) => (
          <div key={component.name}>
            <div className="flex items-baseline justify-between gap-3">
              <dt className="flex items-center gap-2 text-sm text-ink">
                <span className="w-2 h-2 rounded-sm shrink-0"
                  style={{ background: COMPONENT_COLORS[component.name] ?? "var(--ink-faint)" }} />
                <span className="capitalize">{component.name}</span>
              </dt>
              <dd className="numeric text-sm text-ink-soft whitespace-nowrap">
                {component.raw_score.toFixed(2)}
                <span className="text-ink-faint"> × {component.weight.toFixed(2)} = </span>
                <span className="text-ink font-medium">{component.weighted_score.toFixed(3)}</span>
              </dd>
            </div>
            <p className="text-xs text-ink-soft mt-1 ml-4 leading-relaxed">{component.detail}</p>
          </div>
        ))}
      </dl>
    </div>
  );
}
