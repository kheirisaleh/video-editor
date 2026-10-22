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

export function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`rounded-2xl border border-cream-200 bg-white/80 p-4 shadow-sm dark:border-cocoa-700 dark:bg-cocoa-900/60 ${className}`}
    >
      {children}
    </div>
  );
}

type ButtonVariant = "primary" | "secondary" | "danger";

const buttonStyle: Record<ButtonVariant, string> = {
  primary:
    "bg-cocoa-600 text-cream-50 hover:bg-cocoa-700 dark:bg-cream-200 dark:text-cocoa-900 dark:hover:bg-cream-100",
  secondary:
    "border border-cream-300 bg-white text-cocoa-700 hover:bg-cream-100 dark:border-cocoa-600 dark:bg-cocoa-900 dark:text-cream-100 dark:hover:bg-cocoa-700",
  danger:
    "border border-rose-200 bg-white text-rose-700 hover:bg-rose-50 dark:border-rose-900 dark:bg-transparent dark:text-rose-300",
};

export function Button({
  variant = "primary",
  className = "",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  return (
    <button
      {...props}
      className={`inline-flex min-h-11 items-center justify-center gap-2 rounded-xl px-4 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50 ${buttonStyle[variant]} ${className}`}
    />
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200">
      {children}
    </div>
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
