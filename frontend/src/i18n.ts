import type { StepStatus, WorkflowStatus } from "./api";

export const t = {
  appName: "Studio",
  workflows: "Workflows",
  newWorkflow: "New workflow",
  noWorkflows: "No workflows yet.",
  startFirst: "Create your first workflow",
  live: "Live",
  offline: "Offline",
  clips: "Footage",
  clipCount: (n: number) => `${n} ${n === 1 ? "clip" : "clips"}`,
  queuePosition: (n: number) => `#${n} in queue`,
  title: "Title (optional)",
  titlePlaceholder: "e.g. Teddy office chair",
  productUrl: "Product link",
  productText: "Product description",
  productTextPlaceholder: "Name, features, price, anything that matters. English or Persian.",
  productHint: "A link or a description is required.",
  prompt: "Your idea (optional)",
  promptPlaceholder: "Describe the video you want, in English or Persian",
  pickClips: "Choose footage",
  dropHint: "Drop videos here or tap to choose",
  start: "Start and add to queue",
  uploading: "Uploading",
  uploadFailed: "Upload failed",
  needClips: "Choose at least one clip.",
  needProduct: "Enter a product link or description.",
  submitDraft: "Add to queue",
  cancel: "Cancel",
  retry: "Retry",
  remove: "Delete",
  confirmRemove: "Delete this workflow and all its files?",
  steps: "Steps",
  log: "Log",
  product: "Product",
  idea: "Idea",
  back: "Back",
  notFound: "Workflow not found.",
  loading: "Loading…",
  outputs: "Videos",
  variant: (n: number) => `Variant ${n}`,
  download: "Download",
  downloadSilent: "Without music",
  caption: "Post caption",
  copy: "Copy",
  copied: "Copied",
  seconds: (s: number) => `${s.toFixed(1)}s`,
  options: "Video options",
  optionsHint: "Starts from your defaults in Settings.",
  settings: "Settings",
  music: "Music",
  save: "Save",
  saved: "Saved",
  defaults: "Default video options",
  defaultsHint: "Used for every new workflow. You can still change them per workflow.",
  system: "System",
  emojiSource: "Emoji",
  fonts: "Fonts",
  musicHint:
    "Royalty free tracks for your videos. Each variant gets a different track; cuts follow the beat.",
  uploadMusic: "Add tracks",
  noMusic: "No tracks yet.",
  bpm: (n: number) => `${Math.round(n)} BPM`,
  confirmRemoveTrack: (n: string) => `Delete ${n}?`,
  nav: { new: "New" },
  opt: {
    length: "Length",
    min: "Minimum",
    max: "Maximum",
    lengthError: "The minimum must not be longer than the maximum.",
    variants: "Variants",
    music: "Music",
    withMusic: "Add music",
    autoTrack: "Automatic (a different track per variant)",
    noTracks: "The music library is empty. Add tracks on the Music page.",
    beatSync: "Cut on the beat",
    silentCopy: "Also export without music",
    text: "Text",
    withText: "Text on video",
    emoji: "Emoji",
    cta: "“Link below the video”",
    styleAuto: "Auto",
    styleSans: "Sans",
    styleSerif: "Serif",
    caption: "Post caption",
    hashtags: "Hashtags",
    disclosure: "Disclosure",
    quality: "Quality",
    qualityHigh: "Best",
    qualityStandard: "Faster",
  },
};

export const workflowStatusLabel: Record<WorkflowStatus, string> = {
  draft: "Draft",
  queued: "Queued",
  running: "Running",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
};

export const stepStatusLabel: Record<StepStatus, string> = {
  pending: "Waiting",
  running: "Running",
  done: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

export const stepLabel: Record<string, string> = {
  ingest: "Prepare footage",
  analyze: "Analyze footage",
  plan: "Plan edits",
  render: "Render videos",
};

export function formatBytes(bytes: number): string {
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = bytes;
  while (v >= 1024 && i < units.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}

export function formatTime(iso: string | null): string {
  if (!iso) return "";
  const date = new Date(iso.endsWith("Z") || iso.includes("+") ? iso : `${iso}Z`);
  return new Intl.DateTimeFormat("en-GB", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
