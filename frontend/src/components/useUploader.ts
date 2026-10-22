import { useState } from "react";
import { uploadClip } from "../api";
import { t } from "../i18n";
import type { PendingFile } from "./ClipPicker";

/** Holds picked files and uploads them one after another with per file progress. */
export function useUploader() {
  const [files, setFiles] = useState<PendingFile[]>([]);
  const [busy, setBusy] = useState(false);

  const patch = (key: string, change: Partial<PendingFile>) =>
    setFiles((list) => list.map((f) => (f.key === key ? { ...f, ...change } : f)));

  const add = (picked: PendingFile[]) =>
    setFiles((list) => [...list, ...picked.filter((p) => !list.some((f) => f.key === p.key))]);

  const remove = (key: string) => setFiles((list) => list.filter((f) => f.key !== key));

  /** Returns true when every file is on the server. */
  const uploadAll = async (workflowId: string): Promise<boolean> => {
    setBusy(true);
    let ok = true;
    try {
      for (const f of files) {
        if (f.done) continue;
        patch(f.key, { error: undefined, progress: 0.001 });
        try {
          await uploadClip(workflowId, f.file, (p) => patch(f.key, { progress: p }));
          patch(f.key, { done: true, progress: 1 });
        } catch (e) {
          ok = false;
          patch(f.key, { error: `${t.uploadFailed}: ${(e as Error).message}`, progress: 0 });
        }
      }
    } finally {
      setBusy(false);
    }
    return ok;
  };

  return { files, busy, add, remove, uploadAll, reset: () => setFiles([]) };
}
