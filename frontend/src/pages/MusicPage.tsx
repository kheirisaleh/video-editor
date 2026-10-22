import { useCallback, useEffect, useRef, useState } from "react";
import { api, uploadMusic, type Track } from "../api";
import { Button, Card, ErrorNote, ProgressBar } from "../components/ui";
import { formatBytes, t } from "../i18n";

interface Pending {
  name: string;
  progress: number;
}

export function MusicPage() {
  const [tracks, setTracks] = useState<Track[] | null>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  const [error, setError] = useState<string | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    try {
      setTracks(await api.music());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const upload = async (files: FileList) => {
    setError(null);
    const list = Array.from(files);
    setPending(list.map((f) => ({ name: f.name, progress: 0 })));
    for (const file of list) {
      try {
        await uploadMusic(file, (p) =>
          setPending((ps) => ps.map((x) => (x.name === file.name ? { ...x, progress: p } : x))),
        );
      } catch (e) {
        setError(`${file.name}: ${(e as Error).message}`);
      }
      setPending((ps) => ps.filter((x) => x.name !== file.name));
      await load();
    }
  };

  const remove = async (track: Track) => {
    if (!confirm(t.confirmRemoveTrack(track.title))) return;
    try {
      await api.removeMusic(track.name);
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="space-y-4">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">{t.music}</h1>
        <p className="text-sm text-cocoa-400">{t.musicHint}</p>
      </div>
      <Button onClick={() => input.current?.click()} className="w-full" disabled={pending.length > 0}>
        {t.uploadMusic}
      </Button>
      <input
        ref={input}
        type="file"
        accept="audio/*,.mp3,.m4a,.wav,.ogg,.flac,.aac"
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files?.length) upload(e.target.files);
          e.target.value = "";
        }}
      />
      {error && <ErrorNote>{error}</ErrorNote>}
      {pending.map((p) => (
        <Card key={p.name} className="space-y-2">
          <p className="truncate text-sm">{p.name}</p>
          <ProgressBar value={Math.max(p.progress, 0.02)} active={p.progress >= 1} />
        </Card>
      ))}
      {tracks === null ? (
        <p className="text-cocoa-400">{t.loading}</p>
      ) : tracks.length === 0 && pending.length === 0 ? (
        <Card className="py-8 text-center text-cocoa-400">{t.noMusic}</Card>
      ) : (
        <ul className="space-y-3">
          {tracks.map((track) => (
            <li key={track.name}>
              <Card className="space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium">{track.title}</p>
                    <p className="text-xs text-cocoa-400">
                      {formatDuration(track.duration)}
                      {track.tempo ? ` · ${t.bpm(track.tempo)}` : ""} · {formatBytes(track.size_bytes)}
                    </p>
                  </div>
                  <button
                    onClick={() => remove(track)}
                    className="shrink-0 rounded-lg px-2 py-1 text-xs text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950"
                  >
                    {t.remove}
                  </button>
                </div>
                <audio src={track.url} controls preload="none" className="h-9 w-full" />
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
