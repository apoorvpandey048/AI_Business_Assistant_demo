// The Cases prompt is a user-defined triage ruleset — free text describing how
// answers are sorted into the three colour panels (red / green / blue). Unlike the
// role label we don't try to extract a noun phrase; a simple presence label is enough
// for the always-visible status next to the chat input.

export function caseLabel(cases: string): string {
  return cases.trim() ? "Case rules active" : "No case rules";
}
