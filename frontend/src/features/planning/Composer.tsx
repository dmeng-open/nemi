import { useState } from "react";

import { Button } from "@/components/ui/button";
import { EXAMPLES } from "@/features/planning/examples";

export function Composer({
  onSubmit,
  pending = false,
}: {
  onSubmit: (message: string) => void;
  pending?: boolean;
}) {
  const [message, setMessage] = useState("");
  const trimmed = message.trim();

  return (
    <form
      className="mx-auto flex max-w-2xl flex-col gap-6"
      onSubmit={(event) => {
        event.preventDefault();
        if (!trimmed || pending) return;
        onSubmit(trimmed);
      }}
    >
      <div>
        <h1 className="font-serif text-4xl leading-tight md:text-6xl">What would you like to do?</h1>
        <p className="mt-4 max-w-xl text-base leading-7 text-muted">
          Tell Nemi the day, the mood, and the limits. It will check your schedule before it asks to add anything.
        </p>
      </div>
      <label className="block">
        <span className="sr-only">Planning request</span>
        <textarea
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={5}
          placeholder="Saturday afternoon, something with food or music, under $50."
          className="w-full resize-none rounded-3xl border border-line bg-surface px-5 py-4 text-base leading-7 shadow-[var(--shadow)] outline-none"
        />
      </label>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example.label}
            type="button"
            className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm text-muted hover:text-ink"
            onClick={() => setMessage(example.message)}
          >
            {example.label}
          </button>
        ))}
      </div>
      <div>
        <Button type="submit" disabled={!trimmed || pending}>
          {pending ? "Starting…" : "Plan this"}
        </Button>
      </div>
    </form>
  );
}
