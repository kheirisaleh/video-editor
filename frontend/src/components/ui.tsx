import type { ReactNode } from "react";
import type { StepStatus, WorkflowStatus } from "../api";
import { workflowStatusLabel } from "../i18n";

const statusStyle: Record<WorkflowStatus | StepStatus, string> = {
  draft: "bg-cream-200 text-cocoa-600 dark:bg-cocoa-700 dark:text-cream-200",
  pending: "bg-cream-200 text-cocoa-500 dark:bg-cocoa-700 dark:text-cream-300",
  queued: "bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200",
  running: "bg-sky-100 text-sky-800 dark:bg-sky-900/50 dark:text-sky-200",
  done: "bg-emerald-100 text-emerald-800 dark:bg-emerald-900/50 dark:text-emerald-200",
  failed: "bg-rose-100 text-rose-800 dark:bg-rose-900/50 dark:text-rose-200",
  cancelled: "bg-stone-200 text-stone-600 dark:bg-stone-700 dark:text-stone-200",
  skipped: "bg-stone-200 text-stone-600 dark:bg-stone-700 dark:text-stone-200",
};

export function StatusBadge({ status, label }: { status: WorkflowStatus | StepStatus; label?: string }) {
  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ${statusStyle[status]}`}
    >
      {status === "running" && <span className="size-1.5 animate-pulse rounded-full bg-current" />}
      {label ?? workflowStatusLabel[status as WorkflowStatus]}
    </span>
  );
}

export function ProgressBar({ value, active = false }: { value: number; active?: boolean }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-cream-200 dark:bg-cocoa-700">
      <div
        className={`h-full rounded-full bg-cocoa-500 transition-[width] duration-500 dark:bg-cream-300 ${active ? "animate-pulse" : ""}`}
        style={{ width: `${Math.round(Math.max(0, Math.min(value, 1)) * 100)}%` }}
      />
    </div>
  );
}

/** Circular progress; `value` null shows a spinning arc for work without a known progress. */
export function ProgressRing({ value, size = 56 }: { value: number | null; size?: number }) {
  const r = 22;
  const length = 2 * Math.PI * r;
  const shown = value === null ? 0.25 : Math.max(0.02, Math.min(value, 1));
  return (
    <svg viewBox="0 0 48 48" width={size} height={size} className={value === null ? "animate-spin" : ""}>
      <circle cx="24" cy="24" r={r} fill="none" strokeWidth="4" className="stroke-white/30" />
      <circle
        cx="24"
        cy="24"
        r={r}
        fill="none"
        strokeWidth="4"
        strokeLinecap="round"
        className="stroke-white transition-[stroke-dashoffset] duration-700"
        strokeDasharray={length}
        strokeDashoffset={length * (1 - shown)}
        transform="rotate(-90 24 24)"
      />
    </svg>
  );
}

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-3xl bg-white p-5 shadow-soft ring-1 ring-cocoa-900/5 dark:bg-cocoa-800 dark:ring-white/5 ${className}`}
    >
      {children}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger" | "ghost";

const buttonStyle: Record<ButtonVariant, string> = {
  primary:
    "bg-cocoa-900 text-cream-50 shadow-soft hover:bg-cocoa-700 dark:bg-cream-100 dark:text-cocoa-900 dark:hover:bg-white",
  secondary:
    "bg-cream-200 text-cocoa-900 hover:bg-cream-300 dark:bg-cocoa-700 dark:text-cream-100 dark:hover:bg-cocoa-600",
  danger: "bg-rose-50 text-rose-700 hover:bg-rose-100 dark:bg-rose-950/40 dark:text-rose-300",
  ghost: "text-cocoa-600 hover:bg-cream-200 dark:text-cream-200 dark:hover:bg-cocoa-700",
};

export function buttonClass(variant: ButtonVariant = "primary", className = ""): string {
  return `inline-flex min-h-12 items-center justify-center gap-2 rounded-2xl px-5 text-[15px] font-semibold transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 ${buttonStyle[variant]} ${className}`;
}

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return <button {...props} className={buttonClass(variant, className)} />;
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-2xl bg-rose-50 px-4 py-3 text-sm text-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
      {children}
    </div>
  );
}

export function Spinner({ className = "size-5" }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={`animate-spin ${className}`} fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

const iconPaths = {
  home: "M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6h-6v6H4a1 1 0 0 1-1-1z",
  plus: "M12 5v14M5 12h14",
  settings:
    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  download: "M12 4v11m0 0-4-4m4 4 4-4M5 19h14",
  copy: "M9 9h10v10H9zM5 15V5h10",
  check: "m5 12 5 5 9-10",
  back: "m15 18-6-6 6-6",
  close: "M6 6l12 12M18 6 6 18",
  film: "M4 5h16v14H4zM8 5v14M16 5v14M4 9h4M4 15h4M16 9h4M16 15h4",
  sparkle: "M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM19 16l.8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8z",
  music: "M9 18V5l11-2v13M9 18a3 3 0 1 1-6 0 3 3 0 0 1 6 0zm11-2a3 3 0 1 1-6 0 3 3 0 0 1 6 0z",
  refresh: "M20 11a8 8 0 1 0-2.3 5.7M20 4v7h-7",
  trash: "M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3",
  chevron: "m6 9 6 6 6-6",
  link: "M10 14a4 4 0 0 0 5.7 0l3-3a4 4 0 0 0-5.7-5.7l-1 1M14 10a4 4 0 0 0-5.7 0l-3 3a4 4 0 0 0 5.7 5.7l1-1",
  alert: "M12 8v5m0 3h.01M10.3 3.9 2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z",
} as const;

export type IconName = keyof typeof iconPaths;

export function Icon({ name, className = "size-5" }: { name: IconName; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`shrink-0 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={iconPaths[name]} />
    </svg>
  );
}

/** Wrap left to right content (file names, URLs, English text) so it does not break the RTL flow. */
export function Ltr({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <bdi dir="ltr" className={className}>
      {children}
    </bdi>
  );
}
