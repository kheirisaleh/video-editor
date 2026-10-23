import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { api, type RenderOptions } from "../api";
import { ClipPicker } from "../components/ClipPicker";
import { OptionsForm, optionsValid, Toggle } from "../components/OptionsForm";
import { Button, Card, ErrorNote, Icon, Spinner } from "../components/ui";
import { useUploader } from "../components/useUploader";
import { t, ui } from "../i18n";

const field =
  "w-full rounded-2xl border-0 bg-cream-100 px-4 py-3.5 text-base outline-none ring-1 ring-transparent transition placeholder:text-cocoa-400 focus:bg-white focus:ring-cocoa-400 dark:bg-cocoa-900 dark:focus:ring-cream-300";

export function Create() {
  const navigate = useNavigate();
  const uploader = useUploader();
  const [productUrl, setProductUrl] = useState("");
  const [productText, setProductText] = useState("");
  const [prompt, setPrompt] = useState("");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [options, setOptions] = useState<RenderOptions | null>(null);

  useEffect(() => {
    api
      .settings()
      .then((s) => setOptions(s.defaults))
      .catch((e) => setError((e as Error).message));
  }, []);

  const set = (change: Partial<RenderOptions>) => setOptions((o) => o && { ...o, ...change });

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (uploader.files.length === 0) return setError(ui.create.needClips);
    if (!productUrl.trim() && !productText.trim()) return setError(ui.create.needProduct);
    if (options && !optionsValid(options)) return setError(t.opt.lengthError);

    setSubmitting(true);
    try {
      const input = {
        product_text: productText,
        product_url: productUrl.trim() || null,
        prompt,
        options: options ?? undefined,
      };
      // Reuse the draft when a previous attempt failed half way through the uploads.
      const id = workflowId ?? (await api.create(input)).id;
      if (workflowId) await api.update(id, input);
      setWorkflowId(id);
      if (!(await uploader.uploadAll(id))) return;
      await api.submit(id);
      navigate(`/w/${id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const busy = submitting || uploader.busy;
  const total = uploader.files.reduce((sum, f) => sum + f.file.size, 0);
  const sent = uploader.files.reduce((sum, f) => sum + f.file.size * (f.done ? 1 : f.progress), 0);
  const done = uploader.files.filter((f) => f.done).length;

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <h1 className="pt-2 text-3xl font-bold tracking-tight">{ui.create.title}</h1>

      <Step number={1} title={ui.create.clips} hint={ui.create.clipsHint}>
        <ClipPicker files={uploader.files} onAdd={uploader.add} onRemove={uploader.remove} disabled={busy} />
      </Step>

      <Step number={2} title={ui.create.product}>
        <div className="relative">
          <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-cocoa-400">
            <Icon name="link" className="size-[18px]" />
          </span>
          <input
            type="url"
            dir="ltr"
            inputMode="url"
            className={`${field} pl-11`}
            placeholder={ui.create.productLink}
            value={productUrl}
            onChange={(e) => setProductUrl(e.target.value)}
            disabled={busy}
          />
        </div>
        <textarea
          dir="auto"
          rows={3}
          className={field}
          placeholder={ui.create.productTextPlaceholder}
          value={productText}
          onChange={(e) => setProductText(e.target.value)}
          disabled={busy}
        />
      </Step>

      <Step number={3} title={ui.create.idea} badge={ui.create.ideaOptional}>
        <textarea
          dir="auto"
          rows={2}
          className={field}
          placeholder={ui.create.ideaPlaceholder}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          disabled={busy}
        />
      </Step>

      {options && (
        <Step number={4} title={ui.create.style}>
          <ChoiceGroup label={ui.create.look}>
            {ui.create.styles.map((s) => (
              <Choice
                key={s.key}
                active={options.text_style === s.key}
                title={s.label}
                hint={s.hint}
                disabled={busy || !options.texts}
                onClick={() => set({ text_style: s.key as RenderOptions["text_style"] })}
                preview={<StylePreview style={s.key} />}
              />
            ))}
          </ChoiceGroup>
          <ChoiceGroup label={ui.create.length}>
            {ui.create.lengths.map((l) => (
              <Choice
                key={l.key}
                active={options.min_duration === l.min && options.max_duration === l.max}
                title={l.label}
                hint={l.hint}
                disabled={busy}
                onClick={() => set({ min_duration: l.min, max_duration: l.max })}
              />
            ))}
          </ChoiceGroup>
          <div className="divide-y divide-cream-200 rounded-2xl bg-cream-100 px-4 dark:divide-cocoa-700 dark:bg-cocoa-900">
            <Toggle label={ui.create.music} checked={options.music} onChange={(v) => set({ music: v })} />
            <Toggle label={ui.create.text} checked={options.texts} onChange={(v) => set({ texts: v })} />
          </div>
          <details className="group">
            <summary className="flex cursor-pointer list-none items-center justify-center gap-1.5 py-1 text-sm font-medium text-cocoa-500 dark:text-cream-300">
              {ui.create.more}
              <Icon name="chevron" className="size-4 transition group-open:rotate-180" />
            </summary>
            <div className="mt-4">
              <OptionsForm value={options} onChange={setOptions} disabled={busy} />
            </div>
          </details>
        </Step>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}

      <div className="sticky bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-10 pt-2 sm:bottom-4">
        <Button type="submit" disabled={busy} className="relative w-full overflow-hidden text-base">
          {uploader.busy && (
            <span
              className="absolute inset-y-0 left-0 bg-white/15 transition-[width] duration-300 dark:bg-cocoa-900/15"
              style={{ width: `${total ? (sent / total) * 100 : 0}%` }}
            />
          )}
          <span className="relative flex items-center gap-2">
            {busy ? <Spinner /> : <Icon name="sparkle" />}
            {uploader.busy
              ? ui.create.uploading(done, uploader.files.length, total ? Math.round((sent / total) * 100) : 0)
              : submitting
                ? ui.create.starting
                : ui.create.submit}
          </span>
        </Button>
      </div>
    </form>
  );
}

function Step({
  number,
  title,
  hint,
  badge,
  children,
}: {
  number: number;
  title: string;
  hint?: string;
  badge?: string;
  children: ReactNode;
}) {
  return (
    <Card className="space-y-4">
      <div className="flex items-start gap-3">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-full bg-cocoa-900 text-sm font-bold text-cream-50 dark:bg-cream-100 dark:text-cocoa-900">
          {number}
        </span>
        <div className="min-w-0 pt-0.5">
          <h2 className="flex items-center gap-2 text-lg font-semibold leading-tight">
            {title}
            {badge && <span className="text-xs font-normal text-cocoa-400">{badge}</span>}
          </h2>
          {hint && <p className="mt-1 text-sm text-cocoa-400">{hint}</p>}
        </div>
      </div>
      {children}
    </Card>
  );
}

function ChoiceGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium text-cocoa-500 dark:text-cream-300">{label}</p>
      <div className="grid grid-cols-3 gap-2">{children}</div>
    </div>
  );
}

function Choice({
  active,
  title,
  hint,
  preview,
  disabled,
  onClick,
}: {
  active: boolean;
  title: string;
  hint: string;
  preview?: ReactNode;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={active}
      className={`flex flex-col items-center gap-1 rounded-2xl px-2 py-3 text-center transition disabled:opacity-40 ${
        active
          ? "bg-cocoa-900 text-cream-50 shadow-soft dark:bg-cream-100 dark:text-cocoa-900"
          : "bg-cream-100 hover:bg-cream-200 dark:bg-cocoa-900 dark:hover:bg-cocoa-700"
      }`}
    >
      {preview}
      <span className="text-sm font-semibold">{title}</span>
      <span className={`text-[11px] leading-tight ${active ? "opacity-75" : "text-cocoa-400"}`}>{hint}</span>
    </button>
  );
}

/** A tiny sample of the overlay font, so the choice is visual instead of a word. */
function StylePreview({ style }: { style: string }) {
  if (style === "serif") return <span className="font-['Source_Serif_4'] text-2xl italic leading-8">Aa</span>;
  if (style === "sans") return <span className="font-['TikTok_Sans'] text-2xl font-bold leading-8">Aa</span>;
  return (
    <span className="text-2xl leading-8">
      <span className="font-['TikTok_Sans'] font-bold">A</span>
      <span className="font-['Source_Serif_4'] italic">a</span>
    </span>
  );
}
