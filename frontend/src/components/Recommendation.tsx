import type { Recommendation } from "../api/types";

const LABELS: Record<Recommendation, { text: string; tone: string }> = {
  strong_recommend: { text: "Strong match", tone: "text-positive bg-[#eef5f1] border-[#c6dcd0]" },
  recommend: { text: "Recommended", tone: "text-accent bg-accent-soft border-[#c9d6e4]" },
  consider: { text: "Consider", tone: "text-caution bg-signal-soft border-signal-line" },
  not_recommended: { text: "Not recommended", tone: "text-negative bg-[#fdf4f3] border-[#e8cbc8]" },
};

export function RecommendationBadge({ value }: { value: Recommendation }) {
  const { text, tone } = LABELS[value];
  return (
    <span className={`inline-block px-2.5 py-1 text-xs font-medium rounded border ${tone}`}>
      {text}
    </span>
  );
}

/* The Phase 12 advisory notice.
 *
 * The backend made `advisory_notice` a REQUIRED response field precisely
 * so that consuming clients couldn't quietly drop it. Rendering it as a
 * component — placed adjacent to every recommendation rather than in a
 * footer — is what honors that decision on this side of the wire. */
export function AdvisoryNotice({ notice }: { notice: string }) {
  return (
    <div className="border border-signal-line bg-signal-soft rounded-card px-4 py-3">
      <p className="eyebrow mb-1 text-[#8a6412]">Advisory only</p>
      <p className="text-xs text-[#6d4f10] leading-relaxed">{notice}</p>
    </div>
  );
}

export function StatusPill({ status }: { status: string }) {
  const tones: Record<string, string> = {
    parsed: "text-positive bg-[#eef5f1] border-[#c6dcd0]",
    uploaded: "text-ink-soft bg-surface-sunk border-line",
    parsing: "text-caution bg-signal-soft border-signal-line",
    failed: "text-negative bg-[#fdf4f3] border-[#e8cbc8]",
    open: "text-positive bg-[#eef5f1] border-[#c6dcd0]",
    closed: "text-ink-soft bg-surface-sunk border-line",
    draft: "text-caution bg-signal-soft border-signal-line",
  };
  return (
    <span className={`inline-block px-2 py-0.5 text-xs rounded border ${tones[status] ?? tones.uploaded}`}>
      {status}
    </span>
  );
}

export function SkillChip({ name, missing = false }: { name: string; missing?: boolean }) {
  return (
    <span className={`inline-block px-2 py-0.5 text-xs rounded border ${
      missing
        ? "text-negative bg-[#fdf4f3] border-[#e8cbc8] line-through decoration-1"
        : "text-ink-soft bg-surface-sunk border-line"
    }`}>
      {name}
    </span>
  );
}
