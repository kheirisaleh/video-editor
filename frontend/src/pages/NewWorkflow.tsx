import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { ClipPicker } from "../components/ClipPicker";
import { Button, Card, ErrorNote } from "../components/ui";
import { useUploader } from "../components/useUploader";
import { t } from "../i18n";

const field =
  "w-full rounded-xl border border-cream-300 bg-white px-3 py-2.5 text-base outline-none transition focus:border-cocoa-400 focus:ring-2 focus:ring-cream-200 dark:border-cocoa-600 dark:bg-cocoa-900 dark:focus:ring-cocoa-700";

export function NewWorkflow() {
  const navigate = useNavigate();
  const uploader = useUploader();
  const [title, setTitle] = useState("");
  const [productUrl, setProductUrl] = useState("");
  const [productText, setProductText] = useState("");
  const [prompt, setPrompt] = useState("");
  const [workflowId, setWorkflowId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (uploader.files.length === 0) return setError(t.needClips);
    if (!productUrl.trim() && !productText.trim()) return setError(t.needProduct);

    setSubmitting(true);
    try {
      const input = {
        title,
        product_text: productText,
        product_url: productUrl.trim() || null,
        prompt,
      };
      // Reuse the draft when a previous attempt failed half way through the uploads.
      const id = workflowId ?? (await api.create(input)).id;
      if (workflowId) await api.update(id, input);
      setWorkflowId(id);
      if (!(await uploader.uploadAll(id))) return;
      await api.submit(id);
      navigate(`/w/${id}`);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const busy = submitting || uploader.busy;

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <h1 className="text-xl font-semibold">{t.newWorkflow}</h1>

      <Card className="space-y-4">
        <ClipPicker files={uploader.files} onAdd={uploader.add} onRemove={uploader.remove} disabled={busy} />
      </Card>

      <Card className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">{t.productUrl}</span>
          <input
            type="url"
            dir="ltr"
            inputMode="url"
            className={field}
            placeholder="https://"
            value={productUrl}
            onChange={(e) => setProductUrl(e.target.value)}
            disabled={busy}
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">{t.productText}</span>
          <textarea
            dir="auto"
            rows={3}
            className={field}
            placeholder={t.productTextPlaceholder}
            value={productText}
            onChange={(e) => setProductText(e.target.value)}
            disabled={busy}
          />
          <span className="text-xs text-cocoa-400">{t.productHint}</span>
        </label>
      </Card>

      <Card className="space-y-4">
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">{t.prompt}</span>
          <textarea
            dir="auto"
            rows={3}
            className={field}
            placeholder={t.promptPlaceholder}
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            disabled={busy}
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-sm font-medium">{t.title}</span>
          <input
            dir="auto"
            className={field}
            placeholder={t.titlePlaceholder}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={busy}
          />
        </label>
      </Card>

      {error && <ErrorNote>{error}</ErrorNote>}

      <Button type="submit" disabled={busy} className="w-full">
        {uploader.busy ? `${t.uploading}…` : t.start}
      </Button>
    </form>
  );
}
