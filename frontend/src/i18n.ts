import type { StepStatus, WorkflowStatus } from "./api";

export const t = {
  appName: "استودیو",
  workflows: "ورک‌فلوها",
  newWorkflow: "ورک‌فلوی جدید",
  noWorkflows: "هنوز ورک‌فلویی نساختی.",
  startFirst: "اولین ورک‌فلو رو بساز",
  live: "زنده",
  offline: "قطع",
  clips: "فوتیج‌ها",
  clipCount: (n: number) => `${fa(n)} فوتیج`,
  queuePosition: (n: number) => `نفر ${fa(n)} در صف`,
  title: "عنوان (اختیاری)",
  titlePlaceholder: "مثلا صندلی تدی",
  productUrl: "لینک محصول",
  productText: "توضیح محصول",
  productTextPlaceholder: "اسم محصول، ویژگی‌ها، قیمت یا هر چیزی که مهمه",
  productHint: "لینک یا توضیح، حداقل یکی لازمه.",
  prompt: "ایده‌ات (اختیاری)",
  promptPlaceholder: "مثلا: اول جعبه رو باز کنم، حس آرام و دنج داشته باشه، روی نرمی پارچه تاکید کن",
  pickClips: "انتخاب فوتیج‌ها",
  dropHint: "ویدیوها رو اینجا بکش یا بزن تا انتخاب کنی",
  start: "شروع و رفتن به صف",
  uploading: "در حال آپلود",
  uploadFailed: "آپلود ناموفق بود",
  needClips: "حداقل یه فوتیج انتخاب کن.",
  needProduct: "لینک یا توضیح محصول رو وارد کن.",
  submitDraft: "ارسال به صف",
  addClips: "افزودن فوتیج",
  cancel: "لغو",
  retry: "تلاش دوباره",
  remove: "حذف",
  confirmRemove: "این ورک‌فلو و همه فایل‌هاش حذف بشه؟",
  steps: "مراحل",
  log: "گزارش",
  product: "محصول",
  idea: "ایده",
  back: "بازگشت",
  notFound: "این ورک‌فلو پیدا نشد.",
  loading: "در حال بارگذاری…",
  error: "خطا",
  seconds: (s: number) => `${fa(s.toFixed(1))} ثانیه`,
  outputsSoon: "ساخت خروجی‌ها در فازهای بعدی اضافه میشه. فعلا فوتیج‌ها آماده‌سازی میشن.",
};

export const workflowStatusLabel: Record<WorkflowStatus, string> = {
  draft: "پیش‌نویس",
  queued: "در صف",
  running: "در حال اجرا",
  done: "تمام شد",
  failed: "ناموفق",
  cancelled: "لغو شد",
};

export const stepStatusLabel: Record<StepStatus, string> = {
  pending: "در انتظار",
  running: "در حال اجرا",
  done: "انجام شد",
  failed: "ناموفق",
  skipped: "رد شد",
};

export const stepLabel: Record<string, string> = {
  ingest: "آماده‌سازی فوتیج‌ها",
  product: "شناخت محصول",
  analyze: "تحلیل فوتیج‌ها",
  music: "انتخاب موزیک",
  plan: "طراحی ادیت",
  render: "رندر",
  review: "بازبینی کیفیت",
};

const faDigits = "۰۱۲۳۴۵۶۷۸۹";

export function fa(value: number | string): string {
  return String(value).replace(/\d/g, (d) => faDigits[Number(d)]);
}

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
  return new Intl.DateTimeFormat("fa-IR", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}
