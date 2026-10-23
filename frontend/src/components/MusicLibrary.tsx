import { useCallback, useEffect, useRef, useState } from "react";
import { api, uploadMusic, type Track } from "../api";
import { Button, ErrorNote, Icon, ProgressBar } from "./ui";
import { formatBytes, t } from "../i18n";

interface Pending {
  name: string;
  progress: number;
}

/** The music library: upload, listen to and delete tracks. */
export function MusicLibrary() {
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
    <div className="space-y-3">
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
        <div key={p.name} className="space-y-2 rounded-2xl bg-cream-100 p-3 dark:bg-cocoa-900">
          <p className="truncate text-sm">{p.name}</p>
          <ProgressBar value={Math.max(p.progress, 0.02)} active={p.progress >= 1} />
        </div>
      ))}
      {tracks === null ? (
        <p className="text-sm text-cocoa-400">{t.loading}</p>
      ) : tracks.length === 0 && pending.length === 0 ? (
        <p className="rounded-2xl bg-cream-100 py-6 text-center text-sm text-cocoa-400 dark:bg-cocoa-900">{t.noMusic}</p>
      ) : (
        <ul className="space-y-2">
          {tracks.map((track) => (
            <li key={track.name} className="space-y-2 rounded-2xl bg-cream-100 p-3 dark:bg-cocoa-900">
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium">{track.title}</p>
                  <p className="text-xs text-cocoa-400">
                    {formatDuration(track.duration)}
                    {track.tempo ? ` · ${t.bpm(track.tempo)}` : ""} · {formatBytes(track.size_bytes)}
                  </p>
                </div>
                <button
                  onClick={() => remove(track)}
                  aria-label={t.remove}
                  className="flex size-9 shrink-0 items-center justify-center rounded-full text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950"
                >
                  <Icon name="trash" className="size-4" />
                </button>
              </div>
              <audio src={track.url} controls preload="none" className="h-9 w-full" />
            </li>
          ))}
        </ul>
      )}
      <Button variant="secondary" onClick={() => input.current?.click()} className="w-full" disabled={pending.length > 0}>
        <Icon name="plus" className="size-4" />
        {t.uploadMusic}
      </Button>
    </div>
  );
}

function formatDuration(seconds: number): string {
  const s = Math.round(seconds);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}
