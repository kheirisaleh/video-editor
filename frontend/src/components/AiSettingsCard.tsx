import { useEffect, useState, type ReactNode } from "react";
import { api, type AiSettings, type AiTestResult } from "../api";
import { t } from "../i18n";
import { Button, Card, ErrorNote } from "./ui";

const input =
  "w-full rounded-xl border border-cream-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-cocoa-400 dark:border-cocoa-600 dark:bg-cocoa-900";

export function AiSettingsCard() {
  const [ai, setAi] = useState<AiSettings | null>(null);
  const [apiKey, setApiKey] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "testing">("idle");
  const [test, setTest] = useState<AiTestResult | null>(null);

  useEffect(() => {
    api
      .ai()
      .then(setAi)
      .catch((e) => setError((e as Error).message));
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
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setState("idle");
    }
  };

  const busy = state === "saving" || state === "testing";

  return (
    <Card className="space-y-4">
      <div>
        <h2 className="font-medium">{t.ai.title}</h2>
        <p className="text-xs text-cocoa-400">{t.ai.hint}</p>
      </div>

      <Field label={t.ai.provider}>
        <select className={input} value={ai.provider} onChange={(e) => set("provider", e.target.value as AiSettings["provider"])}>
          <option value="none">{t.ai.none}</option>
          <option value="anthropic">{t.ai.claude}</option>
          <option value="openai">{t.ai.openai}</option>
        </select>
        {ai.provider === "anthropic" && <Hint>{t.ai.claudeHint}</Hint>}
        {ai.provider === "openai" && <Hint>{t.ai.openaiHint}</Hint>}
      </Field>

      {ai.provider !== "none" && (
        <>
          {ai.provider === "openai" && (
            <Field label={t.ai.baseUrl}>
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
          <Field label={t.ai.apiKey}>
            <input
              className={input}
              type="password"
              autoComplete="off"
              dir="ltr"
              placeholder={ai.api_key_set ? "••••••••" : ai.provider === "openai" ? t.ai.apiKeyOptional : "sk-ant-…"}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
            {ai.api_key_set && <Hint>{t.ai.apiKeySet}</Hint>}
          </Field>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label={t.ai.textModel}>
              <input
                className={input}
                dir="ltr"
                placeholder={ai.provider === "anthropic" ? "claude-opus-5-5" : "qwen3:14b"}
                value={ai.text_model}
                onChange={(e) => set("text_model", e.target.value)}
              />
            </Field>
            <Field label={t.ai.visionModel}>
              <input
                className={input}
                dir="ltr"
                placeholder={ai.provider === "anthropic" ? "claude-opus-5-5" : "qwen2.5vl:7b"}
                value={ai.vision_model}
                onChange={(e) => set("vision_model", e.target.value)}
              />
              <Hint>{t.ai.visionHint}</Hint>
            </Field>
          </div>
          {ai.provider === "anthropic" && (
            <Field label={t.ai.effort}>
              <select className={input} value={ai.effort} onChange={(e) => set("effort", e.target.value as AiSettings["effort"])}>
                {["low", "medium", "high", "xhigh"].map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label={t.ai.batch}>
              <input
                className={input}
                type="number"
                min={1}
                max={12}
                value={ai.shots_per_request}
                onChange={(e) => set("shots_per_request", Math.min(12, Math.max(1, Number(e.target.value) || 1)))}
              />
              <Hint>{t.ai.batchHint}</Hint>
            </Field>
            <Field label={t.ai.timeout}>
              <input
                className={input}
                type="number"
                min={10}
                max={3600}
                value={ai.timeout}
                onChange={(e) => set("timeout", Math.min(3600, Math.max(10, Number(e.target.value) || 10)))}
              />
            </Field>
          </div>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span>{t.ai.required}</span>
            <input
              type="checkbox"
              className="size-5 accent-cocoa-600"
              checked={ai.required}
              onChange={(e) => set("required", e.target.checked)}
            />
          </label>
        </>
      )}

      {error && <ErrorNote>{error}</ErrorNote>}
      {test && (
        <div
          className={`rounded-xl px-3 py-2 text-sm ${
            test.ok
              ? "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
              : "bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-200"
          }`}
        >
          <p className="font-medium">{test.ok ? "✓" : "✕"} {test.detail}</p>
          <p className="text-xs opacity-80">
            text {test.text_ok ? "✓" : "✕"} · vision {test.vision_ok ? "✓" : "✕"} · {test.seconds}s
          </p>
        </div>
      )}
      <div className="flex gap-2">
        <Button onClick={save} disabled={busy} className="flex-1">
          {state === "saved" ? t.saved : t.ai.save}
        </Button>
        {ai.provider !== "none" && (
          <Button variant="secondary" onClick={runTest} disabled={busy} className="flex-1">
            {state === "testing" ? t.ai.testing : t.ai.test}
          </Button>
        )}
      </div>
    </Card>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="text-xs text-cocoa-400">{label}</span>
      {children}
    </label>
  );
}

function Hint({ children }: { children: ReactNode }) {
  return <span className="block text-xs text-cocoa-400">{children}</span>;
}
