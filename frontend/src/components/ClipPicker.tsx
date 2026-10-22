import { useRef, useState } from "react";
import { fa, formatBytes, t } from "../i18n";
import { Ltr, ProgressBar } from "./ui";

export interface PendingFile {
  key: string;
  file: File;
  progress: number;
  error?: string;
  done?: boolean;
}

export function toPending(files: FileList | File[]): PendingFile[] {
  return Array.from(files)
    .filter((f) => f.type.startsWith("video/") || /\.(mp4|mov|m4v|webm|mkv|avi|3gp)$/i.test(f.name))
    .map((file) => ({ key: `${file.name}-${file.size}-${file.lastModified}`, file, progress: 0 }));
}

export function ClipPicker({
  files,
  onAdd,
  onRemove,
  disabled,
}: {
  files: PendingFile[];
  onAdd: (files: PendingFile[]) => void;
  onRemove: (key: string) => void;
  disabled?: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);

  return (
    <div className="space-y-3">
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          if (!disabled) onAdd(toPending(e.dataTransfer.files));
        }}
        className={`flex w-full flex-col items-center gap-2 rounded-2xl border-2 border-dashed px-4 py-8 text-center text-sm transition disabled:opacity-50 ${
          dragging
            ? "border-cocoa-500 bg-cream-100 dark:bg-cocoa-700"
            : "border-cream-300 hover:border-cocoa-400 dark:border-cocoa-600"
        }`}
      >
        <svg viewBox="0 0 24 24" className="size-8 text-cocoa-400" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="font-medium text-cocoa-700 dark:text-cream-100">{t.pickClips}</span>
        <span className="text-cocoa-400">{t.dropHint}</span>
      </button>
      <input
        ref={input}
        type="file"
        accept="video/*"
        multiple
        hidden
        onChange={(e) => {
          if (e.target.files) onAdd(toPending(e.target.files));
          e.target.value = "";
        }}
      />
      {files.length > 0 && (
        <ul className="space-y-2">
          {files.map((f, i) => (
            <li key={f.key} className="rounded-xl bg-cream-100 px-3 py-2 dark:bg-cocoa-700/60">
              <div className="flex items-center gap-3 text-sm">
                <span className="w-5 shrink-0 text-cocoa-400">{fa(i + 1)}</span>
                <Ltr className="min-w-0 flex-1 truncate">{f.file.name}</Ltr>
                <Ltr className="shrink-0 text-xs text-cocoa-400">{formatBytes(f.file.size)}</Ltr>
                {!disabled && !f.done && (
                  <button
                    type="button"
                    onClick={() => onRemove(f.key)}
                    className="shrink-0 rounded-lg px-2 py-1 text-xs text-rose-700 hover:bg-rose-50 dark:text-rose-300 dark:hover:bg-rose-950"
                    aria-label={t.remove}
                  >
                    ✕
                  </button>
                )}
                {f.done && <span className="shrink-0 text-emerald-600">✓</span>}
              </div>
              {f.progress > 0 && !f.done && (
                <div className="mt-2">
                  <ProgressBar value={f.progress} />
                </div>
              )}
              {f.error && <p className="mt-1 text-xs text-rose-700 dark:text-rose-300">{f.error}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
