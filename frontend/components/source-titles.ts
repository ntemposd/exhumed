// Formats vector source labels for bubble footers. Mirrors backend/utils/source_titles.py.

const DISPLAY_TITLE_MAX_LEN = 48;
const TRAILING_PUNCTUATION_RE = /[.;:\s]+$/;
const STORED_ELLIPSIS_RE = /\.{2,}/;

export type VectorSourceCitation = {
  title: string;
  volume?: string | null;
  chapter?: string | null;
};

export function normalizeStoredCitationField(value: string): string {
  let cleaned = value.trim();
  if (!cleaned) {
    return "";
  }

  cleaned = cleaned.replace(STORED_ELLIPSIS_RE, "").trim();
  return cleaned.replace(TRAILING_PUNCTUATION_RE, "").trim();
}

export function composeSourceCitation(
  title: string,
  volume?: string | null,
  chapter?: string | null,
): string {
  const parts: string[] = [];
  const normalizedTitle = normalizeStoredCitationField(title);
  if (normalizedTitle) {
    parts.push(normalizedTitle);
  }

  const normalizedVolume = normalizeStoredCitationField(volume ?? "");
  if (normalizedVolume) {
    parts.push(normalizedVolume);
  }

  const normalizedChapter = normalizeStoredCitationField(chapter ?? "");
  if (normalizedChapter) {
    parts.push(normalizedChapter);
  }

  return parts.join(" - ");
}

export function formatSourceTitle(title: string, maxLen = DISPLAY_TITLE_MAX_LEN): string {
  let cleaned = title.trim();
  if (!cleaned) {
    return "";
  }

  if (!cleaned.endsWith("...")) {
    cleaned = cleaned.replace(TRAILING_PUNCTUATION_RE, "").trim();
  }

  if (cleaned.length <= maxLen) {
    return cleaned;
  }

  if (maxLen <= 3) {
    return "...";
  }

  return `${cleaned.slice(0, maxLen - 3).trimEnd()}...`;
}

export function formatSourceCitation(
  citation: VectorSourceCitation | string,
  maxLen = DISPLAY_TITLE_MAX_LEN,
): string {
  if (typeof citation === "string") {
    return formatSourceTitle(citation, maxLen);
  }

  const normalizedTitle = normalizeStoredCitationField(citation.title);
  const suffixParts: string[] = [];

  const normalizedVolume = normalizeStoredCitationField(citation.volume ?? "");
  if (normalizedVolume) {
    suffixParts.push(normalizedVolume);
  }

  const normalizedChapter = normalizeStoredCitationField(citation.chapter ?? "");
  if (normalizedChapter) {
    suffixParts.push(normalizedChapter);
  }

  if (suffixParts.length === 0) {
    return formatSourceTitle(normalizedTitle, maxLen);
  }

  const suffix = ` - ${suffixParts.join(" - ")}`;
  if (!normalizedTitle) {
    return formatSourceTitle(suffix.slice(3), maxLen);
  }

  const composed = normalizedTitle + suffix;
  if (composed.length <= maxLen) {
    return composed;
  }

  const titleBudget = maxLen - suffix.length;
  if (titleBudget <= 3) {
    return formatSourceTitle(composed, maxLen);
  }

  return formatSourceTitle(normalizedTitle, titleBudget) + suffix;
}

function citationKey(citation: VectorSourceCitation | string): string {
  if (typeof citation === "string") {
    return formatSourceTitle(citation);
  }

  return [
    normalizeStoredCitationField(citation.title),
    normalizeStoredCitationField(citation.volume ?? ""),
    normalizeStoredCitationField(citation.chapter ?? ""),
  ].join("\0");
}

export function normalizeSourceTitles(
  sources: Array<string | VectorSourceCitation> | undefined | null,
): string[] {
  const seen = new Set<string>();
  const normalized: string[] = [];

  for (const source of sources ?? []) {
    const formatted = formatSourceCitation(source);
    const key = citationKey(source);
    if (!formatted || seen.has(key)) {
      continue;
    }

    seen.add(key);
    normalized.push(formatted);
  }

  return normalized;
}
