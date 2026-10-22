import { useEffect, useState } from "react";
import { api, type AppSettings, type RenderOptions } from "../api";
import { OptionsForm, optionsValid } from "../components/OptionsForm";
import { Button, Card, ErrorNote } from "../components/ui";
import { t } from "../i18n";

export function SettingsPage() {
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [draft, setDraft] = useState<RenderOptions | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [state, setState] = useState<"idle" | "saving" | "saved">("idle");

  useEffect(() => {
    api
      .settings()
      .then((s) => {
        setSettings(s);
        setDraft(s.defaults);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const save = async () => {
    if (!draft) return;
    if (!optionsValid(draft)) return setError(t.opt.lengthError);
    setState("saving");
    setError(null);
    try {
      setDraft(await api.saveDefaults(draft));
      setState("saved");
      window.setTimeout(() => setState("idle"), 1500);
    } catch (e) {
      setError((e as Error).message);
      setState("idle");
    }
  };

  if (!draft || !settings) return error ? <ErrorNote>{error}</ErrorNote> : <p className="text-cocoa-400">{t.loading}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">{t.settings}</h1>
      <Card className="space-y-4">
        <div>
          <h2 className="font-medium">{t.defaults}</h2>
          <p className="text-xs text-cocoa-400">{t.defaultsHint}</p>
        </div>
        <OptionsForm value={draft} onChange={setDraft} disabled={state === "saving"} />
      </Card>
      {error && <ErrorNote>{error}</ErrorNote>}
      <Button onClick={save} disabled={state === "saving"} className="w-full">
        {state === "saved" ? t.saved : t.save}
      </Button>
      <Card className="space-y-2 text-sm">
        <h2 className="font-medium">{t.system}</h2>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1">
          <dt className="text-cocoa-400">{t.emojiSource}</dt>
          <dd>{settings.emoji}</dd>
          <dt className="text-cocoa-400">{t.fonts}</dt>
          <dd>{Object.values(settings.fonts).join(", ")}</dd>
        </dl>
      </Card>
    </div>
  );
}
