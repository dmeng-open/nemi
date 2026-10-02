import { Menu, X } from "lucide-react";
import { useState } from "react";
import { Outlet } from "react-router-dom";

import { Sidebar } from "@/components/layout/Sidebar";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/hooks/useTheme";

export function AppShell() {
  const [open, setOpen] = useState(false);
  useTheme();

  return (
    <div className="min-h-screen bg-bg text-ink md:grid md:grid-cols-[240px_1fr]">
      <aside className="hidden border-r border-line md:block">
        <Sidebar />
      </aside>
      {open ? (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            className="absolute inset-0 bg-black/40"
            aria-label="Close menu"
            onClick={() => setOpen(false)}
          />
          <div className="relative h-full w-72 bg-bg shadow-[var(--shadow)]">
            <Button
              variant="ghost"
              size="icon"
              className="absolute top-4 right-3"
              aria-label="Close menu"
              onClick={() => setOpen(false)}
            >
              <X className="h-4 w-4" />
            </Button>
            <Sidebar onNavigate={() => setOpen(false)} />
          </div>
        </div>
      ) : null}
      <div className="min-w-0">
        <header className="flex items-center justify-between px-4 py-3 md:hidden">
          <p className="font-serif text-xl">Nemi</p>
          <Button variant="quiet" size="icon" aria-label="Open menu" onClick={() => setOpen(true)}>
            <Menu className="h-4 w-4" />
          </Button>
        </header>
        <main className="mx-auto w-full max-w-5xl px-4 py-6 md:px-10 md:py-10">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
