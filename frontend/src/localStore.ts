// Personal data lives in this browser only (localStorage). Nothing is sent
// anywhere. Export/import lets people move it between browsers.

import type { OpeningProgress, Study, StudyListItem } from "./types";

const PROGRESS_KEY = "opening-lab.progress.v1";
const STUDIES_KEY = "opening-lab.studies.v1";
const LEGACY_SESSION_KEY = "cta_session_progress";

export const STORAGE_NOTE =
  "Progress, notes, and studies are stored in this browser only. Use Export to back them up.";

function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) {
      return fallback;
    }
    const parsed = JSON.parse(raw) as T;
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch {
    return fallback;
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* quota or private mode — data stays in memory for this session */
  }
}

function emptyProgress(): OpeningProgress {
  return { learnedLineIds: [], notes: "", updatedAt: new Date().toISOString() };
}

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

// ---- progress ---------------------------------------------------------------

export function loadProgress(): Record<string, OpeningProgress> {
  const stored = readJson<Record<string, OpeningProgress>>(PROGRESS_KEY, {});
  // One-time migration from the old per-tab guest storage.
  try {
    const legacy = sessionStorage.getItem(LEGACY_SESSION_KEY);
    if (legacy) {
      const parsed = JSON.parse(legacy) as Record<string, OpeningProgress>;
      for (const [id, item] of Object.entries(parsed)) {
        stored[id] = mergeOne(stored[id], item);
      }
      sessionStorage.removeItem(LEGACY_SESSION_KEY);
      writeJson(PROGRESS_KEY, stored);
    }
  } catch {
    /* ignore */
  }
  return stored;
}

export function readOpeningProgress(openingId: string): OpeningProgress {
  return loadProgress()[openingId] ?? emptyProgress();
}

export function writeOpeningProgress(
  openingId: string,
  patch: { learnedLineIds?: string[]; notes?: string },
): OpeningProgress {
  const all = loadProgress();
  const current = all[openingId] ?? emptyProgress();
  const next: OpeningProgress = {
    learnedLineIds: patch.learnedLineIds
      ? [...new Set(patch.learnedLineIds.filter((id) => id.length > 0))]
      : current.learnedLineIds,
    notes: typeof patch.notes === "string" ? patch.notes.slice(0, 20_000) : current.notes,
    updatedAt: new Date().toISOString(),
  };
  all[openingId] = next;
  writeJson(PROGRESS_KEY, all);
  return next;
}

function mergeOne(
  a: OpeningProgress | undefined,
  b: OpeningProgress | undefined,
): OpeningProgress {
  return {
    learnedLineIds: [
      ...new Set([...(a?.learnedLineIds ?? []), ...(b?.learnedLineIds ?? [])]),
    ],
    notes: (a?.notes && a.notes.length > 0 ? a.notes : b?.notes) ?? "",
    updatedAt: new Date().toISOString(),
  };
}

// ---- studies ----------------------------------------------------------------

function previewPgn(pgn: string): string {
  const body = pgn
    .split("\n")
    .filter((line) => !line.startsWith("["))
    .join(" ")
    .replace(/\s+/g, " ")
    .trim();
  return body.length > 90 ? `${body.slice(0, 87)}…` : body;
}

function loadStudies(): Study[] {
  const stored = readJson<Study[]>(STUDIES_KEY, []);
  return Array.isArray(stored) ? stored : [];
}

export function listStudies(): StudyListItem[] {
  return loadStudies()
    .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
    .map((study) => ({
      id: study.id,
      title: study.title,
      preview: previewPgn(study.pgn),
      createdAt: study.createdAt,
    }));
}

export function createStudy(title: string, pgn: string): Study {
  const trimmedTitle = title.trim();
  const trimmedPgn = pgn.trim();
  if (trimmedTitle.length < 1 || trimmedTitle.length > 80) {
    throw new Error("Title must be 1–80 characters");
  }
  if (trimmedPgn.length < 10) {
    throw new Error("Paste or upload a PGN");
  }
  if (trimmedPgn.length > 200_000) {
    throw new Error("PGN is too large");
  }
  const study: Study = {
    id: newId(),
    title: trimmedTitle,
    pgn: trimmedPgn,
    createdAt: new Date().toISOString(),
  };
  writeJson(STUDIES_KEY, [...loadStudies(), study]);
  return study;
}

export function getStudy(id: string): Study {
  const study = loadStudies().find((item) => item.id === id);
  if (!study) {
    throw new Error("Study not found");
  }
  return study;
}

export function deleteStudy(id: string): void {
  writeJson(
    STUDIES_KEY,
    loadStudies().filter((item) => item.id !== id),
  );
}

// ---- export / import --------------------------------------------------------

type Backup = {
  app: "opening-lab";
  version: 1;
  exportedAt: string;
  progress: Record<string, OpeningProgress>;
  studies: Study[];
};

export function exportBackup(): string {
  const backup: Backup = {
    app: "opening-lab",
    version: 1,
    exportedAt: new Date().toISOString(),
    progress: loadProgress(),
    studies: loadStudies(),
  };
  return JSON.stringify(backup, null, 2);
}

export function importBackup(text: string): { openings: number; studies: number } {
  const parsed = JSON.parse(text) as Partial<Backup>;
  if (parsed?.app !== "opening-lab" || !parsed.progress || !Array.isArray(parsed.studies)) {
    throw new Error("That file is not an Opening Lab backup");
  }
  const progress = loadProgress();
  for (const [id, item] of Object.entries(parsed.progress)) {
    progress[id] = mergeOne(progress[id], item);
  }
  writeJson(PROGRESS_KEY, progress);

  const existing = loadStudies();
  const known = new Set(existing.map((study) => study.id));
  const added = parsed.studies.filter(
    (study): study is Study =>
      Boolean(study) &&
      typeof study.id === "string" &&
      typeof study.title === "string" &&
      typeof study.pgn === "string" &&
      !known.has(study.id),
  );
  writeJson(STUDIES_KEY, [...existing, ...added]);
  return { openings: Object.keys(parsed.progress).length, studies: added.length };
}

export function downloadText(filename: string, text: string): void {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
