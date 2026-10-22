import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type Output, type Step, type Workflow } from "../api";
import { ClipPicker } from "../components/ClipPicker";
import { optionsSummary } from "../components/OptionsForm";
import { Button, Card, ErrorNote, Ltr, ProgressBar, StatusBadge } from "../components/ui";
import { useUploader } from "../components/useUploader";
import { formatBytes, formatTime, stepLabel, stepStatusLabel, t } from "../i18n";
import { useLive } from "../live";

interface LogLine {
  id: number;
  at: string | null;
  level: string;
  message: string;
}

export function WorkflowDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const [wf, setWf] = useState<Workflow | null>(null);
  const [missing, setMissing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [acting, setActing] = useState(false);
  const [logs, setLogs] = useState<LogLine[]>([]);
  const uploader = useUploader();
  const refetch = useRef<number | undefined>(undefined);

  const load = useCallback(async () => {
    try {
      setWf(await api.get(id));
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) setMissing(true);
      else setError((e as Error).message);
    }
  }, [id]);

  useEffect(() => {
    load();
    return () => window.clearTimeout(refetch.current);
  }, [load]);

  useLive((event) => {
    if (event.workflow_id !== id) return;
    const p = event.payload;
    if (event.type === "log") {
      setLogs((l) => [
        ...l.slice(-199),
        { id: event.id, at: event.at, level: String(p.level), message: String(p.message) },
      ]);
      return;
    }
    if (event.type === "step" && !p.status) {
      // Plain progress update: patch locally instead of refetching.
      setWf((w) =>
        w && {
          ...w,
          steps: w.steps.map((s) =>
            s.name === p.name
              ? { ...s, progress: Number(p.progress), message: (p.message as string) ?? s.message }
              : s,
          ),
        },
      );
      return;
    }
    window.clearTimeout(refetch.current);
    refetch.current = window.setTimeout(load, 150);
  });

  const act = async (fn: () => Promise<unknown>) => {
    setActing(true);
    setError(null);
    try {
      await fn();
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setActing(false);
    }
  };

  if (missing) {
    return (
      <Card className="space-y-3 text-center">
        <p>{t.notFound}</p>
        <Link to="/" className="text-sm underline">
          {t.back}
        </Link>
      </Card>
    );
  }
  if (!wf) return error ? <ErrorNote>{error}</ErrorNote> : <p className="text-cocoa-400">{t.loading}</p>;

  const canRemove = wf.status !== "running";

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h1 className="truncate text-xl font-semibold" dir="auto">
            {wf.title || "…"}
          </h1>
          <p className="text-xs text-cocoa-400">
            {formatTime(wf.created_at)}
            {wf.queue_position ? ` · ${t.queuePosition(wf.queue_position)}` : ""}
          </p>
          <p className="text-xs text-cocoa-400">{optionsSummary(wf.options).join(" · ")}</p>
        </div>
        <StatusBadge status={wf.status} />
      </div>

      {wf.error && (
        <ErrorNote>
          <span dir="auto">{wf.error}</span>
        </ErrorNote>
      )}
      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="flex flex-wrap gap-2">
        {wf.status === "draft" && (
          <Button
            disabled={acting || uploader.busy}
            onClick={() =>
              act(async () => {
                if (uploader.files.length && !(await uploader.uploadAll(wf.id))) return;
                uploader.reset();
                await api.submit(wf.id);
              })
            }
          >
            {t.submitDraft}
          </Button>
        )}
        {(wf.status === "queued" || wf.status === "running") && (
          <Button variant="secondary" disabled={acting} onClick={() => act(() => api.cancel(wf.id))}>
            {t.cancel}
          </Button>
        )}
        {(wf.status === "failed" || wf.status === "cancelled") && (
          <Button disabled={acting} onClick={() => act(() => api.retry(wf.id))}>
            {t.retry}
          </Button>
        )}
        {canRemove && (
          <Button
            variant="danger"
            disabled={acting}
            onClick={() => {
              if (!confirm(t.confirmRemove)) return;
              act(async () => {
                await api.remove(wf.id);
                navigate("/");
              });
            }}
          >
            {t.remove}
          </Button>
        )}
      </div>

      <Card className="space-y-3">
        <h2 className="font-medium">{t.steps}</h2>
        <ol className="space-y-3">
          {wf.steps.map((s) => (
            <StepRow key={s.name} step={s} />
          ))}
        </ol>
      </Card>

      {wf.outputs.length > 0 && (
        <Card className="space-y-3">
          <h2 className="font-medium">{t.outputs}</h2>
          <div className="grid gap-4 sm:grid-cols-3">
            {wf.outputs.map((o) => (
              <OutputCard key={`${o.index}-${wf.finished_at}`} output={o} />
            ))}
          </div>
        </Card>
      )}

      <Card className="space-y-3">
        <h2 className="font-medium">
          {t.clips} <span className="text-sm font-normal text-cocoa-400">({wf.clips.length})</span>
        </h2>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
          {wf.clips.map((c) => (
            <figure key={c.id} className="space-y-1">
              <div className="relative aspect-[9/16] overflow-hidden rounded-lg bg-cream-200 dark:bg-cocoa-700">
                {c.thumbnail_url ? (
                  <img src={c.thumbnail_url} alt="" className="size-full object-cover" loading="lazy" />
                ) : (
                  <div className="flex size-full items-center justify-center text-xs text-cocoa-400">
                    {c.position + 1}
                  </div>
                )}
                {c.probe && (
                  <span className="absolute bottom-1 left-1 rounded bg-black/55 px-1.5 py-0.5 text-[10px] text-white">
                    {c.probe.duration.toFixed(1)}s
                  </span>
                )}
                {wf.status === "draft" && (
                  <button
                    onClick={() => act(() => api.removeClip(wf.id, c.id))}
                    className="absolute right-1 top-1 rounded-full bg-black/55 px-1.5 text-xs text-white"
                    aria-label={t.remove}
                  >
                    ✕
                  </button>
                )}
              </div>
              <figcaption className="truncate text-[11px] text-cocoa-400">
                <Ltr>{c.original_name}</Ltr>
                {c.probe ? (
                  <Ltr className="block">
                    {c.probe.width}×{c.probe.height}
                  </Ltr>
                ) : (
                  <Ltr className="block">{formatBytes(c.size_bytes)}</Ltr>
                )}
              </figcaption>
            </figure>
          ))}
        </div>
        {wf.status === "draft" && (
          <ClipPicker files={uploader.files} onAdd={uploader.add} onRemove={uploader.remove} disabled={uploader.busy} />
        )}
      </Card>

      <Card className="space-y-3 text-sm">
        {wf.product_url && (
          <div className="space-y-1">
            <h3 className="font-medium">{t.productUrl}</h3>
            <a href={wf.product_url} target="_blank" rel="noreferrer" className="block truncate underline" dir="ltr">
              {wf.product_url}
            </a>
          </div>
        )}
        {wf.product_text && (
          <div className="space-y-1">
            <h3 className="font-medium">{t.product}</h3>
            <p className="whitespace-pre-wrap text-cocoa-600 dark:text-cream-200" dir="auto">
              {wf.product_text}
            </p>
          </div>
        )}
        {wf.prompt && (
          <div className="space-y-1">
            <h3 className="font-medium">{t.idea}</h3>
            <p className="whitespace-pre-wrap text-cocoa-600 dark:text-cream-200" dir="auto">
              {wf.prompt}
            </p>
          </div>
        )}
      </Card>

      {logs.length > 0 && (
        <Card className="space-y-2">
          <h2 className="font-medium">{t.log}</h2>
          <ul className="max-h-60 space-y-1 overflow-y-auto font-mono text-xs" dir="ltr">
            {logs.map((l) => (
              <li key={l.id} className={l.level === "error" ? "text-rose-700 dark:text-rose-300" : "text-cocoa-500 dark:text-cream-300"}>
                {l.message}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

function StepRow({ step }: { step: Step }) {
  return (
    <li className="space-y-1.5">
      <div className="flex items-center justify-between gap-2 text-sm">
        <span>{stepLabel[step.name] ?? step.name}</span>
        <div className="flex items-center gap-2">
          {step.status === "running" && (
            <span className="text-xs text-cocoa-400">{Math.round(step.progress * 100)}%</span>
          )}
          <StatusBadge status={step.status} label={stepStatusLabel[step.status]} />
        </div>
      </div>
      {step.status === "running" && <ProgressBar value={step.progress} />}
      {step.status === "running" && step.message && (
        <p className="truncate text-xs text-cocoa-400" dir="auto">
          {step.message}
        </p>
      )}
      {step.error && (
        <p className="text-xs text-rose-700 dark:text-rose-300" dir="auto">
          {step.error}
        </p>
      )}
    </li>
  );
}

function OutputCard({ output }: { output: Output }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(output.caption);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard needs https or localhost; the caption stays selectable below
    }
  };
  const link =
    "inline-flex min-h-9 flex-1 items-center justify-center rounded-lg border border-cream-300 px-2 text-xs font-medium hover:bg-cream-100 dark:border-cocoa-600 dark:hover:bg-cocoa-700";
  return (
    <div className="space-y-2">
      <video
        src={output.video_url}
        poster={output.cover_url}
        controls
        playsInline
        preload="none"
        className="aspect-[9/16] w-full rounded-xl bg-black object-cover"
      />
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="font-medium">
          {t.variant(output.index)} · {output.label}
        </span>
        <span className="shrink-0 text-xs text-cocoa-400">
          {t.seconds(output.duration)} · {formatBytes(output.size_bytes)}
        </span>
      </div>
      {output.music && <p className="truncate text-xs text-cocoa-400">♪ {output.music}</p>}
      <div className="flex gap-2">
        <a href={`${output.video_url}?download=1`} className={link}>
          {t.download}
        </a>
        {output.silent_url && (
          <a href={`${output.silent_url}?download=1`} className={link}>
            {t.downloadSilent}
          </a>
        )}
      </div>
      <details className="rounded-lg bg-cream-100 px-3 py-2 text-xs dark:bg-cocoa-700/60">
        <summary className="cursor-pointer font-medium">{t.caption}</summary>
        <p className="mt-2 select-all whitespace-pre-wrap">{output.caption}</p>
        <button onClick={copy} className="mt-2 underline">
          {copied ? t.copied : t.copy}
        </button>
      </details>
    </div>
  );
}
