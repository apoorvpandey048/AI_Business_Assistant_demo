// Shared draft-state logic for the two user prompts (Analysis mode + Case rules).
// Both the PromptBar editor and the Settings summary read the same three states so
// there is one source of truth and no drift:
//   - "active"    saved, non-empty, draft matches what is applied
//   - "inactive"  nothing saved, nothing typed
//   - "unsaved"   the draft differs from what is currently applied

export type PromptState = "active" | "inactive" | "unsaved";

export function promptState(saved: string, draft: string): PromptState {
  if (draft.trim() !== saved.trim()) return "unsaved";
  return saved.trim() ? "active" : "inactive";
}

// Char cap shared with the backend (_CASE_MAX_CHARS / role cap).
export const PROMPT_MAX_CHARS = 1500;

// Which prompt the bar should open to when navigated from elsewhere (Settings link).
export type PromptKind = "role" | "cases";
