import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, ApiError, type Output, type Step, type Workflow } from "../api";
import { ClipPicker } from "../components/ClipPicker";
import { optionsSummary } from "../components/OptionsForm";
import { Button, buttonClass, Card, ErrorNote, Icon, ProgressRing, Spinner, StatusBadge } from "../components/ui";
import { useUploader } from "../components/useUploader";
import { formatTime, stepLabel, stepStatusLabel, t, ui } from "../i18n";
import { useLive } from "../live";

interface LogLine {
  id: number;
  level: string;
  message: string;
}

export function Project() {
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
      setLogs((l) => [...l.slice(-199), { id: event.id, level: String(p.level), message: String(p.message) }]);
      return;
    }
    if (event.type === "step" && !p.status) {
      // Plain progress update: patch locally instead of refetching.
      setWf(
        (w) =>
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
        <Link to="/" className="text-sm font-medium underline">
          {t.back}
        </Link>
      </Card>
    );
  }
  if (!wf) {
    return error ? (
      <ErrorNote>{error}</ErrorNote>
    ) : (
      <div className="flex justify-center py-20 text-cocoa-400">
        <Spinner className="size-7" />
      </div>
    );
  }

  const remove = () => {
    if (!confirm(ui.project.confirmRemove)) return;
    act(async () => {
      await api.remove(wf.id);
      navigate("/");
    });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pt-1">
        <Link
          to="/"
          aria-label={t.back}
          className="-ms-2 flex size-10 shrink-0 items-center justify-center rounded-full hover:bg-cream-200 dark:hover:bg-cocoa-800"
        >
          <Icon name="back" className="size-6" />
        </Link>
        <div className="min-w-0">
          <h1 className="truncate text-xl font-bold tracking-tight" dir="auto">
            {wf.title || "…"}
          </h1>
          <p className="text-xs text-cocoa-400">{formatTime(wf.created_at)}</p>
        </div>
      </div>

      {error && <ErrorNote>{error}</ErrorNote>}

      {(wf.status === "queued" || wf.status === "running") && (
        <Working wf={wf} acting={acting} onStop={() => act(() => api.cancel(wf.id))} />
      )}

      {(wf.status === "failed" || wf.status === "cancelled") && (
        <Card className="space-y-4 text-center">
          <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-rose-50 text-rose-600 dark:bg-rose-950/40 dark:text-rose-300">
            <Icon name="alert" className="size-7" />
          </div>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold">{wf.status === "failed" ? ui.project.failed : ui.home.cancelled}</h2>
            {wf.error && (
              <p className="text-sm text-cocoa-500 dark:text-cream-300" dir="auto">
                {wf.error}
              </p>
            )}
          </div>
          <Button disabled={acting} onClick={() => act(() => api.retry(wf.id))} className="w-full">
            <Icon name="refresh" />
            {ui.project.tryAgain}
          </Button>
        </Card>
      )}

      {wf.status === "draft" && (
        <Card className="space-y-4">
          <p className="text-sm text-cocoa-500 dark:text-cream-300">{ui.project.draftHint}</p>
          <ClipPicker files={uploader.files} onAdd={uploader.add} onRemove={uploader.remove} disabled={uploader.busy} />
          <Button
            className="w-full"
            disabled={acting || uploader.busy || (wf.clips.length === 0 && uploader.files.length === 0)}
            onClick={() =>
              act(async () => {
                if (uploader.files.length && !(await uploader.uploadAll(wf.id))) return;
                uploader.reset();
                await api.submit(wf.id);
              })
            }
          >
            {uploader.busy ? <Spinner /> : <Icon name="sparkle" />}
            {ui.project.start}
          </Button>
        </Card>
      )}

      {wf.outputs.length > 0 && (
        <section className="space-y-3">
          {wf.status === "done" && (
            <div className="px-1">
              <h2 className="text-2xl font-bold tracking-tight">{ui.project.ready}</h2>
              <p className="text-sm text-cocoa-400">{ui.project.readyHint}</p>
            </div>
          )}
          <div className="-mx-5 flex snap-x snap-mandatory gap-3 overflow-x-auto px-5 pb-2 sm:mx-0 sm:grid sm:grid-cols-3 sm:overflow-visible sm:px-0">
            {wf.outputs.map((o) => (
              <OutputCard key={`${o.index}-${wf.finished_at}`} output={o} />
            ))}
          </div>
        </section>
      )}

      {wf.status === "done" && (
        <Card className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="font-medium">{ui.project.remakeTitle}</p>
          <Button variant="secondary" disabled={acting} onClick={() => act(() => api.rerun(wf.id, "product"))}>
            <Icon name="refresh" className="size-4" />
            {ui.project.remake}
          </Button>
        </Card>
      )}

      <Details wf={wf} logs={logs} />

      {wf.status !== "running" && (
        <div className="flex justify-center">
          <Button variant="ghost" disabled={acting} onClick={remove} className="text-sm text-rose-700 dark:text-rose-300">
            <Icon name="trash" className="size-4" />
            {ui.project.remove}
          </Button>
        </div>
      )}
    </div>
  );
}

function Working({ wf, acting, onStop }: { wf: Workflow; acting: boolean; onStop: () => void }) {
  const running = wf.status === "running";
  const step = wf.steps.find((s) => s.status === "running");
  const cover = wf.clips.find((c) => c.thumbnail_url)?.thumbnail_url;
  return (
    <div className="relative overflow-hidden rounded-3xl bg-cocoa-900 text-white shadow-soft">
      {cover && <img src={cover} alt="" className="absolute inset-0 size-full scale-110 object-cover opacity-50 blur-xl" />}
      <div className="relative flex flex-col items-center gap-4 px-6 py-10 text-center">
        <div className="relative">
          <ProgressRing value={running ? wf.progress : null} size={96} />
          {running && (
            <span className="absolute inset-0 flex items-center justify-center text-lg font-bold">
              {Math.round(wf.progress * 100)}%
            </span>
          )}
        </div>
        <div className="space-y-1">
          <h2 className="text-xl font-bold">
            {running ? (ui.project.stages[step?.name ?? ""] ?? ui.project.working) : ui.project.queued(wf.queue_position)}
          </h2>
          <p className="text-sm text-white/75">{ui.project.workingHint}</p>
        </div>
        <button
          onClick={onStop}
          disabled={acting}
          className="rounded-full bg-white/15 px-5 py-2 text-sm font-medium backdrop-blur transition hover:bg-white/25 disabled:opacity-50"
        >
          {ui.project.stop}
        </button>
      </div>
    </div>
  );
}

/** iOS saves a video to Photos only through the share sheet, so share the file where possible. */
function canShareFiles(): boolean {
  try {
    const probe = new File([""], "probe.mp4", { type: "video/mp4" });
    return typeof navigator.canShare === "function" && navigator.canShare({ files: [probe] });
  } catch {
    return false;
  }
}

function OutputCard({ output }: { output: Output }) {
  const [state, setState] = useState<"idle" | "loading" | "ready">("idle");
  const [copied, setCopied] = useState(false);
  const file = useRef<File | null>(null);
  const download = `${output.video_url}?download=1`;

  const save = async () => {
    try {
      if (!file.current) {
        setState("loading");
        const blob = await (await fetch(output.video_url)).blob();
        file.current = new File([blob], `${output.label.replace(/\W+/g, "-").toLowerCase()}.mp4`, {
          type: "video/mp4",
        });
      }
      await navigator.share({ files: [file.current] });
      setState("idle");
    } catch (e) {
      // A slow download can use up the tap's permission to open the share sheet;
      // the file is kept, so the next tap opens it at once.
      setState(file.current && (e as Error).name === "NotAllowedError" ? "ready" : "idle");
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(output.caption);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard needs https or localhost; the caption is shown in the details instead
    }
  };

  return (
    <div className="w-[78%] shrink-0 snap-center space-y-3 sm:w-auto">
      <video
        src={output.video_url}
        poster={output.cover_url}
        controls
        playsInline
        preload="none"
        className="aspect-[9/16] w-full rounded-3xl bg-black object-cover shadow-soft"
      />
      <div className="flex items-baseline justify-between gap-2 px-1">
        <p className="font-semibold">{output.label}</p>
        <p className="text-xs text-cocoa-400">{t.seconds(output.duration)}</p>
      </div>
      {canShareFiles() ? (
        <Button onClick={save} disabled={state === "loading"} className="w-full">
          {state === "loading" ? <Spinner /> : <Icon name="download" />}
          {state === "loading" ? ui.project.saving : ui.project.save}
        </Button>
      ) : (
        <a href={download} className={buttonClass("primary", "w-full")}>
          <Icon name="download" />
          {ui.project.save}
        </a>
      )}
      <div className="flex gap-2">
        <Button variant="secondary" onClick={copy} className="min-h-10 min-w-0 flex-1 whitespace-nowrap px-2 text-[13px]">
          <Icon name={copied ? "check" : "copy"} className="size-4" />
          {copied ? ui.project.copied : ui.project.copyCaption}
        </Button>
        {output.silent_url && (
          <a href={`${output.silent_url}?download=1`} className={buttonClass("secondary", "min-h-10 min-w-0 flex-1 whitespace-nowrap px-2 text-[13px]")}>
            {ui.project.withoutMusic}
          </a>
        )}
      </div>
    </div>
  );
}

function Details({ wf, logs }: { wf: Workflow; logs: LogLine[] }) {
  const plan = wf.steps.find((s) => s.name === "plan" && s.status === "done");
  const notes = (plan?.result?.notes as string[] | undefined) ?? [];
  return (
    <Card className="!p-0">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
          <span className="font-semibold">{ui.project.details}</span>
          <span className="flex items-center gap-2 text-xs text-cocoa-400">
            {ui.project.clips(wf.clips.length)}
            {wf.ai_cost > 0 && ` · ${ui.project.aiCost(wf.ai_cost)}`}
            <Icon name="chevron" className="size-4 transition group-open:rotate-180" />
          </span>
        </summary>
        <div className="space-y-5 border-t border-cream-200 px-5 py-4 text-sm dark:border-cocoa-700">
          <ol className="space-y-2.5">
            {wf.steps.map((s) => (
              <StepRow key={s.name} step={s} />
            ))}
          </ol>
          {notes.length > 0 && (
            <ul className="space-y-1 text-xs text-amber-700 dark:text-amber-300">
              {notes.map((n) => (
                <li key={n}>⚠ {n}</li>
              ))}
            </ul>
          )}
          <dl className="space-y-3">
            {wf.product_url && (
              <Info label={t.productUrl}>
                <a href={wf.product_url} target="_blank" rel="noreferrer" className="block truncate underline" dir="ltr">
                  {wf.product_url}
                </a>
              </Info>
            )}
            {wf.product_text && <Info label={t.product}>{wf.product_text}</Info>}
            {wf.prompt && <Info label={t.idea}>{wf.prompt}</Info>}
            <Info label={t.options}>{optionsSummary(wf.options).join(" · ")}</Info>
            {plan?.result?.planner != null && <Info label={ui.project.editor}>{String(plan.result.planner)}</Info>}
          </dl>
          {wf.outputs.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs font-medium text-cocoa-400">{t.caption}</p>
              {wf.outputs.map((o) => (
                <p key={o.index} className="select-all whitespace-pre-wrap rounded-2xl bg-cream-100 p-3 text-xs dark:bg-cocoa-900">
                  {o.caption}
                </p>
              ))}
            </div>
          )}
          {logs.length > 0 && (
            <ul className="max-h-48 space-y-1 overflow-y-auto rounded-2xl bg-cream-100 p-3 font-mono text-[11px] dark:bg-cocoa-900" dir="ltr">
              {logs.map((l) => (
                <li key={l.id} className={l.level === "error" ? "text-rose-700 dark:text-rose-300" : "text-cocoa-500 dark:text-cream-300"}>
                  {l.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>
    </Card>
  );
}

function StepRow({ step }: { step: Step }) {
  return (
    <li className="space-y-1">
      <div className="flex items-center justify-between gap-2">
        <span>{stepLabel[step.name] ?? step.name}</span>
        <StatusBadge
          status={step.status}
          label={step.status === "running" ? `${Math.round(step.progress * 100)}%` : stepStatusLabel[step.status]}
        />
      </div>
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

function Info({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-0.5">
      <dt className="text-xs font-medium text-cocoa-400">{label}</dt>
      <dd className="whitespace-pre-wrap text-cocoa-700 dark:text-cream-200" dir="auto">
        {children}
      </dd>
    </div>
  );
}
