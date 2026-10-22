import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type WorkflowSummary } from "../api";
import { Card, ErrorNote, ProgressBar, StatusBadge } from "../components/ui";
import { fa, formatTime, stepLabel, t } from "../i18n";
import { useLive } from "../live";

export function WorkflowList() {
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
  if (!items) return <p className="text-cocoa-400">{t.loading}</p>;

  if (items.length === 0) {
    return (
      <Card className="flex flex-col items-center gap-4 py-12 text-center">
        <p className="text-cocoa-500 dark:text-cream-300">{t.noWorkflows}</p>
        <Link
          to="/new"
          className="rounded-xl bg-cocoa-600 px-4 py-2.5 text-sm font-medium text-cream-50 dark:bg-cream-200 dark:text-cocoa-900"
        >
          {t.startFirst}
        </Link>
      </Card>
    );
  }

  return (
    <ul className="space-y-3">
      {items.map((w) => (
        <li key={w.id}>
          <Link to={`/w/${w.id}`} className="block">
            <Card className="flex gap-3 transition hover:border-cream-300 dark:hover:border-cocoa-600">
              <div className="aspect-[9/16] w-14 shrink-0 overflow-hidden rounded-lg bg-cream-200 dark:bg-cocoa-700">
                {w.thumbnail_url && <img src={w.thumbnail_url} alt="" className="size-full object-cover" />}
              </div>
              <div className="min-w-0 flex-1 space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <h2 className="truncate font-medium" dir="auto">
                    {w.title || "…"}
                  </h2>
                  <StatusBadge status={w.status} />
                </div>
                <p className="text-xs text-cocoa-400">
                  {t.clipCount(w.clip_count)} · {formatTime(w.created_at)}
                  {w.queue_position ? ` · ${t.queuePosition(w.queue_position)}` : ""}
                </p>
                {w.status === "running" && (
                  <div className="space-y-1">
                    <ProgressBar value={w.progress} />
                    <p className="text-xs text-cocoa-500 dark:text-cream-300">
                      {stepLabel[w.current_step ?? ""] ?? w.current_step} · {fa(Math.round(w.progress * 100))}٪
                    </p>
                  </div>
                )}
                {w.status === "failed" && w.error && (
                  <p className="line-clamp-2 text-xs text-rose-700 dark:text-rose-300" dir="auto">
                    {w.error}
                  </p>
                )}
              </div>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}
