import { useEffect, useState, type ReactNode } from "react";
import { api, type AiSettings, type AiTestResult, type AiUsage } from "../api";
import { t, ui } from "../i18n";
import { Segmented, Toggle } from "./OptionsForm";
import { Button, ErrorNote, Icon } from "./ui";

const input =
  "w-full rounded-2xl border-0 bg-cream-100 px-4 py-3 text-base outline-none ring-1 ring-transparent transition focus:bg-white focus:ring-cocoa-400 dark:bg-cocoa-900 dark:focus:ring-cream-300";

/** AI connection, spending limits and this month's usage. */
export function AiSettingsCard() {
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [usage, setUsage] = useState<AiUsage | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "testing">("idle");
  const [test, setTest] = useState<AiTestResult | null>(null);

  useEffect(() => {
    api
      .ai()
      .then(setAi)
      .catch((e) => setError((e as Error).message));
    api
      .aiUsage()
      .then(setUsage)
      .catch(() => setUsage(null));
  }, []);

  if (!ai) return error ? <ErrorNote>{error}</ErrorNote> : null;

  const set = <K extends keyof AiSettings>(key: K, value: AiSettings[K]) => {
    setAi({ ...ai, [key]: value });
    setTest(null);
  };

  const save = async (): Promise<boolean> => {
    setError(null);
    setState("saving");
    try {
      const { api_key_set: _ignored, ...rest } = ai;
      setAi(await api.saveAi({ ...rest, api_key: apiKey ? apiKey : null }));
      setApiKey("");
      setUsage(await api.aiUsage());
      setState("saved");
      window.setTimeout(() => setState("idle"), 1500);
      return true;
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
      return false;
    }
  };

  const runTest = async () => {
    if (!(await save())) return;
    setState("testing");
    try {
      setTest(await api.testAi());
      setUsage(await api.aiUsage());
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setState("idle");
    }
  };

  const busy = state === "saving" || state === "testing";
  const providerName = ai.provider === "anthropic" ? "Claude" : ai.text_model || t.ai.openai;

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <span
          className={`flex size-11 shrink-0 items-center justify-center rounded-2xl ${
            ai.provider === "none"
              ? "bg-cream-200 text-cocoa-400 dark:bg-cocoa-700"
              : "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-300"
          }`}
        >
          <Icon name="sparkle" className="size-6" />
        </span>
        <div className="min-w-0">
          <p className="font-medium">{ai.provider === "none" ? ui.settings.off : ui.settings.on(providerName)}</p>
          <p className="text-xs text-cocoa-400">{ui.settings.aiHint}</p>
        </div>
      </div>

      {ai.provider === "anthropic" && usage && <UsageMeter usage={usage} />}

      <Segmented
        value={ai.provider}
        options={[
          ["none", t.ai.none],
          ["anthropic", "Claude"],
          ["openai", ui.settings.local],
        ]}
        onChange={(v) => set("provider", v as AiSettings["provider"])}
      />

      {ai.provider !== "none" && (
        <div className="space-y-4">
          {ai.provider === "openai" && (
            <Field label={t.ai.baseUrl} hint={t.ai.openaiHint}>
              <input
                className={input}
                dir="ltr"
                inputMode="url"
                placeholder="http://192.168.1.20:11434/v1"
                value={ai.base_url}
                onChange={(e) => set("base_url", e.target.value)}
              />
            </Field>
          )}
          <Field
            label={t.ai.apiKey}
            hint={ai.api_key_set ? t.ai.apiKeySet : ai.provider === "anthropic" ? t.ai.claudeHint : undefined}
          >
            <input
              className={input}
              type="password"
              autoComplete="off"
              dir="ltr"
              placeholder={ai.api_key_set ? "••••••••" : ai.provider === "openai" ? t.ai.apiKeyOptional : "sk-ant-…"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </Field>

          {ai.provider === "anthropic" && (
            <div className="space-y-2">
              <p className="text-sm font-medium">{t.ai.budget}</p>
              <div className="grid grid-cols-2 gap-3">
                <Money label={t.ai.monthly} value={ai.monthly_budget_usd} max={10_000} onChange={(v) => set("monthly_budget_usd", v)} />
                <Money label={t.ai.perVideo} value={ai.workflow_budget_usd} max={1_000} onChange={(v) => set("workflow_budget_usd", v)} />
              </div>
              <p className="text-xs text-cocoa-400">
                {t.ai.budgetHint} {t.ai.noLimit}.
              </p>
            </div>
          )}

          <details className="group rounded-2xl bg-cream-100 px-4 dark:bg-cocoa-900">
            <summary className="flex cursor-pointer list-none items-center justify-between py-3 text-sm font-medium">
              {ui.settings.advanced}
              <Icon name="chevron" className="size-4 transition group-open:rotate-180" />
            </summary>
            <div className="space-y-4 pb-4">
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label={t.ai.textModel}>
                  <input
                    className={`${input} bg-white`}
                    dir="ltr"
                    placeholder={ai.provider === "anthropic" ? "claude-opus-5-5" : "qwen3:14b"}
                    value={ai.text_model}
                    onChange={(e) => set("text_model", e.target.value)}
                  />
                </Field>
                <Field label={t.ai.visionModel} hint={t.ai.visionHint}>
                  <input
                    className={`${input} bg-white`}
                    dir="ltr"
                    placeholder={ai.provider === "anthropic" ? "claude-opus-5-5" : "qwen2.5vl:7b"}
                    value={ai.vision_model}
                    onChange={(e) => set("vision_model", e.target.value)}
                  />
                </Field>
              </div>
              {ai.provider === "anthropic" && (
                <Field label={t.ai.effort}>
                  <Segmented
                    value={ai.effort}
                    options={[
                      ["low", "Low"],
                      ["medium", "Medium"],
                      ["high", "High"],
                      ["xhigh", "Max"],
                    ]}
                    onChange={(v) => set("effort", v as AiSettings["effort"])}
                  />
                </Field>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Field label={t.ai.batch} hint={t.ai.batchHint}>
                  <input
                    className={`${input} bg-white`}
                    type="number"
                    min={1}
                    max={12}
                    value={ai.shots_per_request}
                    onChange={(e) => set("shots_per_request", Math.min(12, Math.max(1, Number(e.target.value) || 1)))}
                  />
                </Field>
                <Field label={t.ai.timeout}>
                  <input
                    className={`${input} bg-white`}
                    type="number"
                    min={10}
                    max={3600}
                    value={ai.timeout}
                    onChange={(e) => set("timeout", Math.min(3600, Math.max(10, Number(e.target.value) || 10)))}
                  />
                </Field>
              </div>
              <Toggle label={t.ai.required} checked={ai.required} onChange={(v) => set("required", v)} />
            </div>
          </details>
        </div>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}
      {test && (
        <div
          className={`rounded-2xl px-4 py-3 text-sm ${
            test.ok
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
              : "bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
          }`}
        >
          <p className="font-medium">
            {test.ok ? "✓" : "✕"} {test.detail}
          </p>
          <p className="text-xs opacity-80">
            text {test.text_ok ? "✓" : "✕"} · vision {test.vision_ok ? "✓" : "✕"} · {test.seconds}s
          </p>
        </div>
      )}
      <div className="flex gap-2">
        <Button onClick={save} disabled={busy} className="flex-1">
          {state === "saved" ? t.saved : t.save}
        </Button>
        {ai.provider !== "none" && (
          <Button variant="secondary" onClick={runTest} disabled={busy} className="flex-1 whitespace-nowrap px-3">
            {state === "testing" ? t.ai.testing : t.ai.test}
          </Button>
        )}
      </div>
    </div>
  );
}

function UsageMeter({ usage }: { usage: AiUsage }) {
  const share = usage.month_budget > 0 ? Math.min(usage.month_spent / usage.month_budget, 1) : 0;
  const color = share > 0.9 ? "bg-rose-500" : share > 0.7 ? "bg-amber-500" : "bg-emerald-500";
  return (
    <div className="space-y-2 rounded-2xl bg-cream-100 p-4 dark:bg-cocoa-900">
      <p className="text-sm font-medium">{ui.settings.usage(usage.month_spent, usage.month_budget)}</p>
      {usage.month_budget > 0 && (
        <div className="h-2 overflow-hidden rounded-full bg-cream-300 dark:bg-cocoa-700">
          <div className={`h-full rounded-full ${color} transition-[width]`} style={{ width: `${Math.max(share * 100, 1)}%` }} />
        </div>
      )}
      <p className="text-xs text-cocoa-400">{ui.settings.calls(usage.month_calls)}</p>
    </div>
  );
}

function Money({
  label,
  value,
  max,
  onChange,
}: {
  label: string;
  value: number;
  max: number;
  onChange: (v: number) => void;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-cocoa-400">{label}</span>
      <div className="relative">
        <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-cocoa-400">$</span>
        <input
          className={`${input} pl-8`}
          type="number"
          inputMode="decimal"
          min={0}
          max={max}
          step={0.5}
          value={value}
          onChange={(e) => onChange(Math.min(max, Math.max(0, Number(e.target.value) || 0)))}
        />
      </div>
    </label>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs font-medium text-cocoa-400">{label}</span>
      {children}
      {hint && <span className="block text-xs text-cocoa-400">{hint}</span>}
    </label>
  );
}
