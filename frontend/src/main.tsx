import "@fontsource/vazirmatn/400.css";
import "@fontsource/vazirmatn/500.css";
import "@fontsource/vazirmatn/600.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, NavLink, Route, Routes } from "react-router-dom";
import { t } from "./i18n";
import { LiveProvider, useLiveConnected } from "./live";
import { NewWorkflow } from "./pages/NewWorkflow";
import { WorkflowDetail } from "./pages/WorkflowDetail";
import { WorkflowList } from "./pages/WorkflowList";

function Header() {
  const connected = useLiveConnected();
  const tab = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-1.5 text-sm transition ${
      isActive ? "bg-cream-200 font-medium dark:bg-cocoa-700" : "text-cocoa-500 hover:text-cocoa-700 dark:text-cream-300"
    }`;
  return (
    <header className="sticky top-0 z-10 border-b border-cream-200 bg-cream-100/90 backdrop-blur dark:border-cocoa-700 dark:bg-cocoa-900/90">
      <div className="mx-auto flex max-w-2xl items-center gap-2 px-4 py-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <Link to="/" className="me-2 flex items-center gap-2 font-semibold">
          <img src="/icon.svg" alt="" className="size-7" />
          {t.appName}
        </Link>
        <nav className="flex gap-1">
          <NavLink to="/" end className={tab}>
            {t.workflows}
          </NavLink>
          <NavLink to="/new" className={tab}>
            {t.newWorkflow}
          </NavLink>
        </nav>
        <span
          className="ms-auto flex items-center gap-1.5 text-xs text-cocoa-400"
          title={connected ? t.live : t.offline}
        >
          <span className={`size-2 rounded-full ${connected ? "bg-emerald-500" : "bg-stone-400"}`} />
          {connected ? t.live : t.offline}
        </span>
      </div>
    </header>
  );
}

function App() {
  return (
    <LiveProvider>
      <Header />
      <main className="mx-auto max-w-2xl px-4 py-5 pb-[max(1.25rem,env(safe-area-inset-bottom))]">
        <Routes>
          <Route path="/" element={<WorkflowList />} />
          <Route path="/new" element={<NewWorkflow />} />
          <Route path="/w/:id" element={<WorkflowDetail />} />
        </Routes>
      </main>
    </LiveProvider>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
