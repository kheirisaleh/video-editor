import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type WorkflowSummary } from "../api";
import { buttonClass, ErrorNote, Icon, ProgressRing, Spinner } from "../components/ui";
import { formatTime, ui } from "../i18n";
import { useLive } from "../live";

export function Home() {
  const [items, setItems] = useState<WorkflowSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setItems(await api.list());
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Overall progress is computed on the server, so refetch, but at most about once a second.
  useLive((event) => {
    if (event.type === "log" || pending.current !== undefined) return;
    const progressOnly = event.type === "step" && !event.payload.status;
    pending.current = window.setTimeout(
      () => {
        pending.current = undefined;
        load();
      },
      progressOnly ? 1000 : 200,
    );
  });

  useEffect(() => () => window.clearTimeout(pending.current), []);

  if (error) return <ErrorNote>{error}</ErrorNote>;
  if (!items) {
    return (
      <div className="flex justify-center py-20 text-cocoa-400">
        <Spinner className="size-7" />
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-5 px-4 py-16 text-center">
        <div className="flex size-20 items-center justify-center rounded-[28px] bg-white text-cocoa-600 shadow-soft dark:bg-cocoa-800 dark:text-cream-200">
          <Icon name="film" className="size-9" />
        </div>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">{ui.home.emptyTitle}</h1>
          <p className="mx-auto max-w-xs text-cocoa-500 dark:text-cream-300">{ui.home.emptyText}</p>
        </div>
        <Link to="/new" className={buttonClass("primary", "px-7")}>
          <Icon name="plus" />
          {ui.home.create}
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3 pt-2">
        <h1 className="text-3xl font-bold tracking-tight">{ui.home.title}</h1>
        <Link to="/new" className={buttonClass("primary", "hidden min-h-10 px-4 text-sm sm:inline-flex")}>
          <Icon name="plus" className="size-4" />
          {ui.home.create}
        </Link>
      </div>
      <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4">
        {items.map((w) => (
          <li key={w.id}>
            <ProjectTile item={w} />
          </li>
        ))}
      </ul>
    </div>
  );
}

function ProjectTile({ item: w }: { item: WorkflowSummary }) {
  const image = w.cover_url ?? w.thumbnail_url;
  const working = w.status === "running" || w.status === "queued";
  return (
    <Link to={`/w/${w.id}`} className="group block space-y-2">
      <div className="relative aspect-[9/16] overflow-hidden rounded-3xl bg-cream-200 shadow-soft dark:bg-cocoa-800">
        {image && (
          <img
            src={image}
            alt=""
            loading="lazy"
            className={`size-full object-cover transition duration-300 group-hover:scale-[1.03] ${working ? "scale-105 blur-[2px]" : ""}`}
          />
        )}
        {working && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-cocoa-900/45 text-white">
            <ProgressRing value={w.status === "running" ? w.progress : null} />
            <span className="text-xs font-semibold">
              {w.status === "running" ? `${Math.round(w.progress * 100)}%` : ui.home.waiting}
            </span>
          </div>
        )}
        <div className="absolute inset-x-2 bottom-2 flex">
          <StatusPill item={w} />
        </div>
      </div>
      <div className="px-1">
        <p className="truncate text-sm font-semibold" dir="auto">
          {w.title || "…"}
        </p>
        <p className="text-xs text-cocoa-400">{formatTime(w.created_at)}</p>
      </div>
    </Link>
  );
}

function StatusPill({ item: w }: { item: WorkflowSummary }) {
  const base = "inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold backdrop-blur-md";
  switch (w.status) {
    case "done":
      return (
        <span className={`${base} bg-white/85 text-cocoa-900`}>
          <Icon name="check" className="size-3.5 text-emerald-600" />
          {ui.home.ready(w.output_count)}
        </span>
      );
    case "running":
      return <span className={`${base} bg-white/85 text-cocoa-900`}>{ui.home.editing}</span>;
    case "queued":
      return <span className={`${base} bg-white/85 text-cocoa-900`}>{ui.home.waiting}</span>;
    case "failed":
      return <span className={`${base} bg-rose-600/90 text-white`}>{ui.home.failed}</span>;
    case "cancelled":
      return <span className={`${base} bg-black/55 text-white`}>{ui.home.cancelled}</span>;
    default:
      return <span className={`${base} bg-black/55 text-white`}>{ui.home.draft}</span>;
  }
}
