import { useEffect, useRef, useState } from "react";
import { t, ui } from "../i18n";
import { Icon } from "./ui";

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

/** Picked clips as 9:16 tiles with a preview frame, upload progress and a remove button. */
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

  const dropProps = {
    onDragOver: (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(true);
    },
    onDragLeave: () => setDragging(false),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      if (!disabled) onAdd(toPending(e.dataTransfer.files));
    },
  };

  return (
    <div {...dropProps}>
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
      {files.length === 0 ? (
        <button
          type="button"
          disabled={disabled}
          onClick={() => input.current?.click()}
          className={`flex w-full flex-col items-center gap-3 rounded-3xl border-2 border-dashed px-4 py-10 text-center transition disabled:opacity-50 ${
            dragging
              ? "border-cocoa-500 bg-cream-100 dark:bg-cocoa-700"
              : "border-cream-300 hover:border-cocoa-400 hover:bg-cream-50 dark:border-cocoa-600 dark:hover:bg-cocoa-700/40"
          }`}
        >
          <span className="flex size-14 items-center justify-center rounded-2xl bg-cocoa-900 text-cream-50 dark:bg-cream-100 dark:text-cocoa-900">
            <Icon name="plus" className="size-7" />
          </span>
          <span className="text-base font-semibold">{ui.create.addClips}</span>
          <span className="text-sm text-cocoa-400">{t.dropHint}</span>
        </button>
      ) : (
        <ul className={`grid grid-cols-3 gap-2 sm:grid-cols-4 ${dragging ? "opacity-70" : ""}`}>
          {files.map((f) => (
            <ClipTile key={f.key} item={f} onRemove={disabled || f.done ? undefined : () => onRemove(f.key)} />
          ))}
          {!disabled && (
            <li>
              <button
                type="button"
                onClick={() => input.current?.click()}
                className="flex aspect-[9/16] w-full flex-col items-center justify-center gap-1.5 rounded-2xl border-2 border-dashed border-cream-300 text-sm font-medium text-cocoa-500 transition hover:border-cocoa-400 dark:border-cocoa-600 dark:text-cream-300"
              >
                <Icon name="plus" className="size-6" />
                {ui.create.addMore}
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

function ClipTile({ item, onRemove }: { item: PendingFile; onRemove?: () => void }) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    const objectUrl = URL.createObjectURL(item.file);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [item.file]);

  const uploading = item.progress > 0 && !item.done;
  return (
    <li className="relative aspect-[9/16] overflow-hidden rounded-2xl bg-cocoa-900">
      {url && (
        // The #t fragment makes iOS Safari show a frame instead of a black tile.
        <video src={`${url}#t=0.1`} muted playsInline preload="metadata" className="size-full object-cover" />
      )}
      {uploading && (
        <div className="absolute inset-x-2 bottom-2 h-1.5 overflow-hidden rounded-full bg-white/30">
          <div
            className="h-full rounded-full bg-white transition-[width] duration-300"
            style={{ width: `${Math.round(item.progress * 100)}%` }}
          />
        </div>
      )}
      {item.done && (
        <span className="absolute bottom-2 right-2 flex size-6 items-center justify-center rounded-full bg-emerald-500 text-white">
          <Icon name="check" className="size-4" />
        </span>
      )}
      {item.error && (
        <span className="absolute inset-0 flex items-center justify-center bg-rose-900/70 p-2 text-center text-xs text-white">
          {t.uploadFailed}
        </span>
      )}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={t.remove}
          className="absolute right-1.5 top-1.5 flex size-7 items-center justify-center rounded-full bg-black/50 text-white backdrop-blur"
        >
          <Icon name="close" className="size-4" />
        </button>
      )}
    </li>
  );
}
