import type { ReactNode } from "react";

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-surface border border-line rounded-card ${className}`}>{children}</div>
  );
}

export function CardHeader({ title, action }: { title: string; action?: ReactNode }) {
  return (
    <div className="flex items-center justify-between px-5 py-3 border-b border-line">
      <h2 className="eyebrow">{title}</h2>
      {action}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({
  children, onClick, disabled, variant = "secondary", type = "button", className = "",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  variant?: ButtonVariant;
  type?: "button" | "submit";
  className?: string;
}) {
  const base =
    "inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded transition-colors disabled:opacity-40 disabled:cursor-not-allowed";
  const variants: Record<ButtonVariant, string> = {
    primary: "bg-accent text-white hover:bg-[#24405e]",
    secondary: "bg-surface border border-line text-ink hover:bg-surface-sunk",
    ghost: "text-ink-soft hover:text-ink hover:bg-surface-sunk",
  };
  return (
    <button type={type} onClick={onClick} disabled={disabled}
      className={`${base} ${variants[variant]} ${className}`}>
      {children}
    </button>
  );
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-ink-soft">
      <span
        className="w-3.5 h-3.5 border-2 border-line border-t-accent rounded-full animate-spin"
        aria-hidden="true"
      />
      {label && <span>{label}</span>}
      <span className="sr-only">Loading</span>
    </span>
  );
}

/** Renders both thrown errors and the backend's handled failures.
 *  The backend returns 200 with {success:false, reasoning} for things it
 *  handled deliberately — a UI that only rendered thrown errors would
 *  show a failed parse as a success. */
export function ErrorBanner({
  message, tone = "error", onDismiss,
}: {
  message: string;
  tone?: "error" | "warning";
  onDismiss?: () => void;
}) {
  const tones = {
    error: "border-l-negative bg-[#fdf4f3] text-[#7a2a24]",
    warning: "border-l-signal bg-signal-soft text-[#7a4d0a]",
  };
  return (
    <div className={`border border-line border-l-[3px] rounded-card px-4 py-3 text-sm ${tones[tone]}`}
      role="alert">
      <div className="flex items-start justify-between gap-4">
        <p className="leading-relaxed">{message}</p>
        {onDismiss && (
          <button onClick={onDismiss} className="text-xs opacity-60 hover:opacity-100 shrink-0"
            aria-label="Dismiss">
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}

export function EmptyState({ title, hint, action }: { title: string; hint: string; action?: ReactNode }) {
  return (
    <div className="text-center py-14 px-6">
      <p className="text-ink font-medium">{title}</p>
      <p className="text-sm text-ink-soft mt-1.5 max-w-md mx-auto leading-relaxed">{hint}</p>
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block">
      <span className="eyebrow block mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-xs text-ink-faint mt-1">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full px-3 py-2 text-sm bg-surface border border-line rounded focus:border-accent outline-none";
