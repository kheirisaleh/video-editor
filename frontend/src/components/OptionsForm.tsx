import { useEffect, useState, type ReactNode } from "react";
import { api, type RenderOptions, type Track } from "../api";
import { t } from "../i18n";

const LENGTH_PRESETS: [number, number][] = [
  [10, 15],
  [15, 25],
  [20, 35],
  [30, 60],
];

export function OptionsForm({
  value,
  onChange,
  disabled,
}: {
  value: RenderOptions;
  onChange: (next: RenderOptions) => void;
  disabled?: boolean;
}) {
  const [tracks, setTracks] = useState<Track[]>([]);
  useEffect(() => {
    api.music().then(setTracks).catch(() => setTracks([]));
  }, []);

  const set = <K extends keyof RenderOptions>(key: K, v: RenderOptions[K]) => onChange({ ...value, [key]: v });
  const lengthError = value.min_duration > value.max_duration;

  return (
    <fieldset disabled={disabled} className="space-y-5">
      <Section title={t.opt.length}>
        <div className="flex flex-wrap gap-2">
          {LENGTH_PRESETS.map(([lo, hi]) => (
            <Chip
              key={`${lo}-${hi}`}
              active={value.min_duration === lo && value.max_duration === hi}
              onClick={() => onChange({ ...value, min_duration: lo, max_duration: hi })}
            >
              {lo}–{hi}s
            </Chip>
          ))}
        </div>
        <div className="flex items-center gap-3">
          <NumberField label={t.opt.min} value={value.min_duration} onChange={(v) => set("min_duration", v)} />
          <span className="pt-5 text-cocoa-400">–</span>
          <NumberField label={t.opt.max} value={value.max_duration} onChange={(v) => set("max_duration", v)} />
        </div>
        {lengthError && <p className="text-xs text-rose-700 dark:text-rose-300">{t.opt.lengthError}</p>}
      </Section>

      <Section title={t.opt.variants}>
        <Segmented
          value={String(value.variants)}
          options={[
            ["1", "1"],
            ["2", "2"],
            ["3", "3"],
          ]}
          onChange={(v) => set("variants", Number(v))}
        />
      </Section>

      <Section title={t.opt.music}>
        <Toggle label={t.opt.withMusic} checked={value.music} onChange={(v) => set("music", v)} />
        {value.music && (
          <>
            <select
              className="w-full rounded-xl border border-cream-300 bg-white px-3 py-2.5 text-sm dark:border-cocoa-600 dark:bg-cocoa-900"
              value={value.music_track ?? ""}
              onChange={(e) => set("music_track", e.target.value || null)}
            >
              <option value="">{t.opt.autoTrack}</option>
              {tracks.map((tr) => (
                <option key={tr.name} value={tr.name}>
                  {tr.title}
                  {tr.tempo ? ` · ${Math.round(tr.tempo)} BPM` : ""}
                </option>
              ))}
            </select>
            {tracks.length === 0 && <p className="text-xs text-cocoa-400">{t.opt.noTracks}</p>}
            <Toggle label={t.opt.beatSync} checked={value.beat_sync} onChange={(v) => set("beat_sync", v)} />
            <Toggle label={t.opt.silentCopy} checked={value.silent_copy} onChange={(v) => set("silent_copy", v)} />
          </>
        )}
      </Section>

      <Section title={t.opt.text}>
        <Toggle label={t.opt.withText} checked={value.texts} onChange={(v) => set("texts", v)} />
        {value.texts && (
          <>
            <Toggle label={t.opt.emoji} checked={value.emoji} onChange={(v) => set("emoji", v)} />
            <Toggle label={t.opt.cta} checked={value.call_to_action} onChange={(v) => set("call_to_action", v)} />
            <Segmented
              value={value.text_style}
              options={[
                ["auto", t.opt.styleAuto],
                ["sans", t.opt.styleSans],
                ["serif", t.opt.styleSerif],
              ]}
              onChange={(v) => set("text_style", v as RenderOptions["text_style"])}
            />
            <div className="grid grid-cols-2 gap-2 text-center text-sm">
              <div className="rounded-lg bg-cocoa-500 px-2 py-3 text-white" style={{ fontFamily: "TikTok Sans, Inter" }}>
                so cozy 🤍
                <div className="text-[10px] opacity-70">TikTok Sans</div>
              </div>
              <div className="rounded-lg bg-cocoa-500 px-2 py-3 font-semibold text-white" style={{ fontFamily: "Source Serif 4, Georgia, serif" }}>
                so cozy 🤍
                <div className="font-sans text-[10px] font-normal opacity-70">Source Serif</div>
              </div>
            </div>
          </>
        )}
      </Section>

      <Section title={t.opt.caption}>
        <label className="block space-y-1">
          <span className="text-xs text-cocoa-400">{t.opt.hashtags}</span>
          <input
            className="w-full rounded-xl border border-cream-300 bg-white px-3 py-2.5 text-sm dark:border-cocoa-600 dark:bg-cocoa-900"
            value={value.hashtags.join(" ")}
            onChange={(e) => set("hashtags", e.target.value.split(/[\s,]+/).filter(Boolean))}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-xs text-cocoa-400">{t.opt.disclosure}</span>
          <input
            className="w-full rounded-xl border border-cream-300 bg-white px-3 py-2.5 text-sm dark:border-cocoa-600 dark:bg-cocoa-900"
            value={value.disclosure}
            onChange={(e) => set("disclosure", e.target.value)}
          />
        </label>
      </Section>

      <Section title={t.opt.quality}>
        <Segmented
          value={value.quality}
          options={[
            ["high", t.opt.qualityHigh],
            ["standard", t.opt.qualityStandard],
          ]}
          onChange={(v) => set("quality", v as RenderOptions["quality"])}
        />
      </Section>
    </fieldset>
  );
}

export function optionsValid(o: RenderOptions): boolean {
  return o.min_duration >= 5 && o.max_duration <= 180 && o.min_duration <= o.max_duration;
}

export function optionsSummary(o: RenderOptions): string[] {
  const parts = [
    `${o.min_duration}–${o.max_duration}s`,
    `${o.variants} ${o.variants === 1 ? "variant" : "variants"}`,
    o.music ? (o.music_track ? `♪ ${o.music_track.replace(/\.[^.]+$/, "")}` : "♪ auto") : "no music",
    o.texts ? (o.emoji ? "text + emoji" : "text") : "no text",
  ];
  if (o.texts && o.text_style !== "auto") parts.push(o.text_style);
  return parts;
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="space-y-2.5">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-cocoa-400">{title}</h3>
      {children}
    </div>
  );
}

export function Toggle({ label, checked, onChange }: { label: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex min-h-10 cursor-pointer items-center justify-between gap-3 text-sm">
      <span>{label}</span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition ${checked ? "bg-cocoa-600 dark:bg-cream-200" : "bg-cream-300 dark:bg-cocoa-700"}`}
      >
        <span
          className={`absolute top-0.5 size-5 rounded-full bg-white shadow transition-all dark:bg-cocoa-900 ${checked ? "left-[22px]" : "left-0.5"}`}
        />
      </button>
    </label>
  );
}

export function Segmented({
  value,
  options,
  onChange,
}: {
  value: string;
  options: [string, string][];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex rounded-xl bg-cream-200 p-1 dark:bg-cocoa-700">
      {options.map(([key, label]) => (
        <button
          key={key}
          type="button"
          onClick={() => onChange(key)}
          className={`min-h-9 flex-1 rounded-lg px-2 text-sm transition ${
            value === key ? "bg-white font-medium shadow-sm dark:bg-cocoa-900" : "text-cocoa-500 dark:text-cream-300"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full border px-3 py-1.5 text-sm transition ${
        active
          ? "border-cocoa-600 bg-cocoa-600 text-cream-50 dark:border-cream-200 dark:bg-cream-200 dark:text-cocoa-900"
          : "border-cream-300 hover:bg-cream-100 dark:border-cocoa-600 dark:hover:bg-cocoa-700"
      }`}
    >
      {children}
    </button>
  );
}

function NumberField({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label className="block flex-1 space-y-1">
      <span className="text-xs text-cocoa-400">{label}</span>
      <div className="flex items-center rounded-xl border border-cream-300 bg-white pe-3 dark:border-cocoa-600 dark:bg-cocoa-900">
        <input
          type="number"
          inputMode="numeric"
          min={5}
          max={180}
          className="w-full rounded-xl bg-transparent px-3 py-2.5 text-base outline-none"
          value={Number.isFinite(value) ? value : ""}
          onChange={(e) => onChange(e.target.value === "" ? NaN : Number(e.target.value))}
        />
        <span className="text-sm text-cocoa-400">s</span>
      </div>
    </label>
  );
}
