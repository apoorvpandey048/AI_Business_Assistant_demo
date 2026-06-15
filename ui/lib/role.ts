// The analysis mode (persona) is free text. For the always-visible label next to the
// chat input we derive a short human name from it: "Act as a lawyer reviewing…" →
// "Lawyer". When no pattern matches and the text is long, degrade to "Custom role" —
// never truncate mid-thought into something misleading.

const LEAD_INS = /^(?:act|answer|respond|analy[sz]e|review|think|write|speak)\s+as\s+(?:an?\s+|the\s+)?/i;
const YOU_ARE = /^you\s+are\s+(?:an?\s+|the\s+)?/i;

export function roleLabel(role: string): string {
  const r = role.trim().replace(/\s+/g, " ");
  if (!r) return "General";
  let rest: string | null = null;
  if (LEAD_INS.test(r)) rest = r.replace(LEAD_INS, "");
  else if (YOU_ARE.test(r)) rest = r.replace(YOU_ARE, "");
  if (rest) {
    // keep the role noun phrase, stop at the first clause boundary
    const phrase = rest.split(/[,.;:\n]| who | that | reviewing | analyzing | for /i)[0].trim();
    if (phrase && phrase.length <= 32) {
      return phrase.charAt(0).toUpperCase() + phrase.slice(1);
    }
  }
  if (r.length <= 32) return r.charAt(0).toUpperCase() + r.slice(1);
  return "Custom role";
}
