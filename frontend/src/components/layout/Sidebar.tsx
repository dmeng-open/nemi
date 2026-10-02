import { CalendarDays, Plus, Settings, SlidersHorizontal, Sparkles } from "lucide-react";
import { NavLink } from "react-router-dom";

import { NemiMark } from "@/components/NemiMark";
import { cn } from "@/lib/utils";

const links = [
  { to: "/", label: "New plan", icon: Plus, end: true },
  { to: "/plans", label: "Recent plans", icon: Sparkles, end: true },
  { to: "/preferences", label: "Preferences", icon: SlidersHorizontal, end: false },
  { to: "/integrations", label: "Integrations", icon: CalendarDays, end: false },
  { to: "/settings", label: "Settings", icon: Settings, end: false },
];

export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <div className="flex h-full flex-col px-4 py-6">
      <div className="flex items-center gap-3 px-2">
        <NemiMark />
        <div>
          <p className="font-serif text-2xl leading-none">Nemi</p>
          <p className="mt-1 text-xs text-muted">Your planning agent</p>
        </div>
      </div>
      <nav className="mt-8 flex flex-col gap-1" aria-label="Primary">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm",
                isActive ? "bg-surface text-ink shadow-[var(--shadow)]" : "text-muted hover:text-ink",
              )
            }
          >
            <link.icon className="h-4 w-4" aria-hidden="true" />
            {link.label}
          </NavLink>
        ))}
      </nav>
      <p className="mt-auto px-3 text-xs leading-5 text-muted">
        Local demo. OpenAI reasons. The city around you is mocked.
      </p>
    </div>
  );
}
