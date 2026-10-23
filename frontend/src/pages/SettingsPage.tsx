import { useEffect, useState, type ReactNode } from "react";
import { api, type AppSettings, type RenderOptions } from "../api";
import { AiSettingsCard } from "../components/AiSettingsCard";
import { MusicLibrary } from "../components/MusicLibrary";
import { OptionsForm, optionsValid } from "../components/OptionsForm";
import { Button, Card, ErrorNote, Icon, type IconName } from "../components/ui";
import { formatBytes, t, ui } from "../i18n";

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

  useEffect(() => {
    if (settings && location.hash) document.querySelector(location.hash)?.scrollIntoView();
  }, [settings]);

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

  if (!draft || !settings) return error ? <ErrorNote>{error}</ErrorNote> : null;

  const used = settings.storage.uploads + settings.storage.work + settings.storage.exports + settings.storage.music;

  return (
    <div className="space-y-4">
      <h1 className="pt-2 text-3xl font-bold tracking-tight">{ui.settings.title}</h1>

      <Section id="ai" icon="sparkle" title={ui.settings.ai}>
        <AiSettingsCard />
      </Section>

      <Section id="music" icon="music" title={ui.settings.music} hint={ui.settings.musicHint}>
        <MusicLibrary />
      </Section>

      <Section id="defaults" icon="film" title={ui.settings.defaults} hint={ui.settings.defaultsHint}>
        <OptionsForm value={draft} onChange={setDraft} disabled={state === "saving"} />
        {error && <ErrorNote>{error}</ErrorNote>}
        <Button onClick={save} disabled={state === "saving"} className="w-full">
          {state === "saved" ? t.saved : t.save}
        </Button>
      </Section>

      <Section id="system" icon="settings" title={ui.settings.system}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
          <dt className="text-cocoa-400">{t.storage}</dt>
          <dd>{t.storageLine(formatBytes(used), formatBytes(settings.storage.free))}</dd>
          <dt className="text-cocoa-400">{t.fonts}</dt>
          <dd>{Object.values(settings.fonts).join(", ")}</dd>
          <dt className="text-cocoa-400">{t.emojiSource}</dt>
          <dd>{settings.emoji}</dd>
        </dl>
      </Section>
    </div>
  );
}

function Section({
  id,
  icon,
  title,
  hint,
  children,
}: {
  id: string;
  icon: IconName;
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <Card className="scroll-mt-20 space-y-4">
      <div id={id} className="flex items-start gap-3">
        <Icon name={icon} className="mt-0.5 size-5 shrink-0 text-cocoa-400" />
        <div>
          <h2 className="text-lg font-semibold leading-tight">{title}</h2>
          {hint && <p className="mt-1 text-sm text-cocoa-400">{hint}</p>}
        </div>
      </div>
      {children}
    </Card>
  );
}
