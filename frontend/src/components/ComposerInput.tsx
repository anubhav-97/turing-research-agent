import { useState, KeyboardEvent } from "react";

interface Props {
  onSend: (text: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ComposerInput({ onSend, disabled, placeholder }: Props) {
  const [text, setText] = useState("");

  const submit = () => {
    if (!text.trim() || disabled) return;
    onSend(text);
    setText("");
  };

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  return (
    <div className="flex items-end gap-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-2 shadow-sm focus-within:ring-2 focus-within:ring-blue-500">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
        disabled={disabled}
        placeholder={placeholder ?? "Ask about a company… (Enter to send, Shift+Enter for newline)"}
        rows={1}
        className="flex-1 resize-none bg-transparent text-sm outline-none placeholder:text-slate-400 max-h-32"
      />
      <button
        onClick={submit}
        disabled={!text.trim() || disabled}
        className="rounded-md bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-medium px-4 py-1.5"
      >
        Send
      </button>
    </div>
  );
}
