import { useState } from "react";

interface Props {
  question: string;
  onResume: (answer: string) => void;
  disabled?: boolean;
}

export function ClarificationBanner({ question, onResume, disabled }: Props) {
  const [text, setText] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!text.trim() || disabled) return;
    onResume(text);
    setText("");
  };

  return (
    <div className="rounded-lg border border-amber-400 bg-amber-50 dark:bg-amber-950/30 px-4 py-3 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="text-amber-600 dark:text-amber-300 font-bold text-lg leading-none">?</div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-amber-800 dark:text-amber-200 mb-1">
            Clarification needed
          </div>
          <p className="text-sm text-amber-900 dark:text-amber-100 mb-3">{question}</p>
          <form className="flex gap-2" onSubmit={handleSubmit}>
            <input
              type="text"
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Type your clarification…"
              disabled={disabled}
              className="flex-1 rounded-md border border-amber-300 dark:border-amber-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
            />
            <button
              type="submit"
              disabled={!text.trim() || disabled}
              className="rounded-md bg-amber-600 hover:bg-amber-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-1.5"
            >
              Resume
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
