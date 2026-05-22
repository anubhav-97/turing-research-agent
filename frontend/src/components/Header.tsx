import { useChat } from "../store/chat";

function exportMarkdown(messages: { role: string; content: string }[], threadId: string) {
  const lines = [
    `# Conversation — ${threadId}`,
    `_Exported ${new Date().toLocaleString()}_`,
    "",
  ];
  for (const m of messages) {
    const speaker = m.role === "user" ? "**You**" : "**Assistant**";
    lines.push(`${speaker}:`, "", m.content, "");
  }
  const blob = new Blob([lines.join("\n")], { type: "text/markdown" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `conversation-${threadId}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export function Header() {
  const { theme, toggleTheme, resetThread, messages, threadId } = useChat();
  const hasContent = messages.length > 0;

  return (
    <header className="flex items-center justify-between border-b border-slate-200 dark:border-slate-800 px-4 py-3 bg-white/70 dark:bg-slate-900/70 backdrop-blur">
      <div className="flex items-center gap-3 min-w-0">
        <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-blue-500 via-violet-500 to-emerald-500 flex items-center justify-center text-white font-bold text-sm shadow">
          TR
        </div>
        <div className="min-w-0">
          <h1 className="text-sm sm:text-base font-semibold">Turing Research Agent</h1>
          <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
            LangGraph · DeepAgents · Groq · thread {threadId.slice(0, 12)}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-1.5">
        <button
          onClick={() => exportMarkdown(messages, threadId)}
          disabled={!hasContent}
          title="Export conversation to Markdown"
          className="text-xs px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
        >
          Export
        </button>
        <button
          onClick={resetThread}
          title="Start a fresh conversation"
          className="text-xs px-2.5 py-1.5 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          New thread
        </button>
        <button
          onClick={toggleTheme}
          title="Toggle dark mode"
          className="text-xs w-8 h-8 rounded-md border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"
        >
          {theme === "dark" ? "☀" : "☾"}
        </button>
      </div>
    </header>
  );
}
