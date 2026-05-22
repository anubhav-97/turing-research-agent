import type { AgentTraceStep } from "../types";

interface Props {
  trace: AgentTraceStep[];
}

/**
 * Shows the validator's feedback string when it routed back to Research.
 * Surfaces the "informed loop" behaviour: the feedback is fed verbatim
 * into the next research attempt's prompt.
 */
export function ValidatorFeedback({ trace }: Props) {
  // Find the most recent validator step that routed back to research.
  const step = [...trace]
    .reverse()
    .find(
      (t) =>
        t.node === "validator" &&
        t.status === "done" &&
        t.nextNode === "research" &&
        t.delta?.validation_feedback,
    );

  if (!step) return null;

  return (
    <div className="rounded-md border border-amber-300 bg-amber-50 dark:bg-amber-950/30 dark:border-amber-800/60 px-3 py-2 text-xs flex items-start gap-2">
      <span className="text-amber-600 dark:text-amber-300 font-semibold shrink-0">
        Validator → Research:
      </span>
      <span className="text-amber-900 dark:text-amber-100 italic">
        “{step.delta?.validation_feedback}”
      </span>
    </div>
  );
}
