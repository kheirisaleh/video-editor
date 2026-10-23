import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import "@fontsource/inter/700.css";
import "@fontsource/vazirmatn/400.css";
import "./index.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Link, Navigate, NavLink, Route, Routes } from "react-router-dom";
import { Icon, type IconName } from "./components/ui";
import { t, ui } from "./i18n";
import { LiveProvider, useLiveConnected } from "./live";
import { Create } from "./pages/Create";
import { Home } from "./pages/Home";
import { Project } from "./pages/Project";
import { SettingsPage } from "./pages/SettingsPage";

const tabs: { to: string; label: string; icon: IconName }[] = [
  { to: "/", label: ui.tabs.videos, icon: "home" },
  { to: "/new", label: ui.tabs.create, icon: "plus" },
  { to: "/settings", label: ui.tabs.settings, icon: "settings" },
];

function TopBar() {
  const connected = useLiveConnected();
  return (
    <header className="sticky top-0 z-20 bg-cream-100/80 backdrop-blur-xl dark:bg-cocoa-900/80">
      <div className="mx-auto flex max-w-3xl items-center gap-3 px-5 pb-3 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <Link to="/" className="flex items-center gap-2.5 text-lg font-bold tracking-tight">
          <img src="/icon.svg" alt="" className="size-8 rounded-xl" />
          {ui.brand}
        </Link>
        <nav className="ms-6 hidden gap-1 sm:flex">
          {tabs.map((tab) => (
            <NavLink
              key={tab.to}
              to={tab.to}
              end
              className={({ isActive }) =>
                `rounded-full px-4 py-2 text-sm font-medium transition ${
                  isActive
                    ? "bg-cocoa-900 text-cream-50 dark:bg-cream-100 dark:text-cocoa-900"
                    : "text-cocoa-500 hover:bg-cream-200 dark:text-cream-300 dark:hover:bg-cocoa-800"
                }`
              }
            >
              {tab.label}
            </NavLink>
          ))}
        </nav>
        <span
          className={`ms-auto size-2.5 rounded-full ${connected ? "bg-emerald-500" : "bg-stone-400"}`}
          title={connected ? t.live : t.offline}
          aria-label={connected ? t.live : t.offline}
        />
      </div>
    </header>
  );
}

function TabBar() {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-20 border-t border-cocoa-900/5 bg-white/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-xl sm:hidden dark:border-white/5 dark:bg-cocoa-900/85">
      <div className="mx-auto grid max-w-md grid-cols-3">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end
            className={({ isActive }) =>
              `flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium transition ${
                isActive ? "text-cocoa-900 dark:text-cream-50" : "text-cocoa-400"
              }`
            }
          >
            {({ isActive }) =>
              tab.icon === "plus" ? (
                <>
                  <span className="-mt-1 flex size-9 items-center justify-center rounded-full bg-cocoa-900 text-cream-50 shadow-soft dark:bg-cream-100 dark:text-cocoa-900">
                    <Icon name="plus" className="size-5" />
                  </span>
                  {tab.label}
                </>
              ) : (
                <>
                  <Icon name={tab.icon} className={`size-6 ${isActive ? "stroke-[2.2]" : ""}`} />
                  {tab.label}
                </>
              )
            }
          </NavLink>
        ))}
      </div>
    </nav>
  );
}

function App() {
  return (
    <LiveProvider>
      <TopBar />
      <main className="mx-auto max-w-3xl px-5 pb-32 pt-2 sm:pb-12">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/new" element={<Create />} />
          <Route path="/w/:id" element={<Project />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/music" element={<Navigate to="/settings#music" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <TabBar />
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
