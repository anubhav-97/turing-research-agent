// Curated suggestion chips, split into two groups so reviewers can demo
// both graph paths from the empty state.
//
// VALIDATOR_CHIPS — engineered to:
//   1. Trigger the Validator loop. The mock dataset only stores three
//      coarse fields per company (recent_news / stock_info / key_developments).
//      Queries asking for facts *outside* those fields score low confidence
//      on the first Research pass → routes to Validator → "insufficient" →
//      loop back to Research → validator feedback drives a Tavily search →
//      high-confidence answer → Synthesis.
//   2. Have a stable, verifiable answer. We avoid queries like "current CEO"
//      or "Q3 earnings" — those drift over time and can produce stale-looking
//      answers. Historical/biographical facts won't change.
//
// CLARITY_CHIPS — vague or ambiguous queries that have NO obvious single
// company. Clarity Agent flags them, the graph interrupts, and the user
// is asked to clarify. Resuming with a specific company name continues
// the graph through Research → Synthesis.
const VALIDATOR_CHIPS: { label: string; query: string }[] = [
  {
    label: "Apple HQ location",
    query: "Where is Apple's corporate headquarters located?",
  },
  {
    label: "NVIDIA founded year",
    query: "In what year was NVIDIA founded and by whom?",
  },
  {
    label: "Microsoft + LinkedIn",
    query: "When did Microsoft acquire LinkedIn and for how much?",
  },
  {
    label: "Google's parent",
    query: "What is Google's parent company called and when was it formed?",
  },
  {
    label: "Amazon's founder",
    query: "Who founded Amazon and in what year?",
  },
  {
    label: "Tesla first car",
    query: "What was Tesla's first production vehicle and when was it launched?",
  },
];

const CLARITY_CHIPS: { label: string; query: string }[] = [
  {
    label: "That EV company",
    query: "Tell me about that EV company everyone is talking about.",
  },
  {
    label: "The big chip maker",
    query: "How is the big chip maker doing recently?",
  },
  {
    label: "That cloud giant",
    query: "What's the latest on that cloud computing giant?",
  },
];

interface Props {
  onPick: (text: string) => void;
  disabled?: boolean;
}

export function SuggestedQueries({ onPick, disabled }: Props) {
  return (
    <div className="space-y-3">
      <div>
        <p className="text-[10px] uppercase tracking-wide text-slate-400 dark:text-slate-500 mb-1.5">
          ↻ Validator loop · stable-fact queries
        </p>
        <div className="flex flex-wrap gap-2">
          {VALIDATOR_CHIPS.map((s) => (
            <button
              key={s.label}
              onClick={() => onPick(s.query)}
              disabled={disabled}
              title={s.query}
              className="text-xs px-3 py-1.5 rounded-full border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50 transition-colors"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="text-[10px] uppercase tracking-wide text-amber-600 dark:text-amber-400 mb-1.5">
          ❓ Clarify / interrupt · vague queries
        </p>
        <div className="flex flex-wrap gap-2">
          {CLARITY_CHIPS.map((s) => (
            <button
              key={s.label}
              onClick={() => onPick(s.query)}
              disabled={disabled}
              title={s.query}
              className="text-xs px-3 py-1.5 rounded-full border border-amber-300 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/30 hover:bg-amber-100 dark:hover:bg-amber-900/50 text-amber-900 dark:text-amber-200 disabled:opacity-50 transition-colors"
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
