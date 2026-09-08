// Data access for the static site. There is no server: the opening book and
// finished reviews are JSON files produced by GitHub Actions (backend/), and
// personal data (progress, notes, studies) lives in this browser (localStore).

import {
  offlineGetOpening,
  offlineListBookSources,
  offlineListOpenings,
  offlineTryTrainerMove,
} from "./offlineBook";
import type {
  BookSource,
  GameReview,
  OpeningCourse,
  ReviewListItem,
  TrainerTryResult,
} from "./types";

const DEFAULT_REPO_URL = "https://github.com/yamagani/Chess-Trainer";

/** Repository that runs the review workflow (set VITE_REPO_URL at build time to override). */
export function repoUrl(): string {
  const raw = import.meta.env.VITE_REPO_URL;
  return (typeof raw === "string" && raw.trim() ? raw.trim() : DEFAULT_REPO_URL).replace(/\/$/, "");
}

function siteUrl(path: string): string {
  return `${import.meta.env.BASE_URL}${path.replace(/^\//, "")}`;
}

// ---- opening book (client-side) -------------------------------------------

export function listOpenings(): Promise<OpeningCourse[]> {
  return offlineListOpenings();
}

export function getOpening(slug: string): Promise<OpeningCourse> {
  return offlineGetOpening(slug);
}

export function listBookSources(): Promise<BookSource[]> {
  return offlineListBookSources();
}

export function tryTrainerMove(input: {
  fen: string;
  from: string;
  to: string;
  promotion?: string;
  preferredOpening?: string;
}): Promise<TrainerTryResult> {
  return offlineTryTrainerMove(input);
}

// ---- reviews (JSON published by the "Review game" workflow) ---------------

async function fetchJson<T>(path: string): Promise<T | null> {
  const response = await fetch(siteUrl(path), { cache: "no-cache" });
  if (response.status === 404) {
    return null;
  }
  if (!response.ok) {
    throw new Error(`Could not load ${path} (${response.status})`);
  }
  const text = await response.text();
  if (!text.trim()) {
    return null;
  }
  return JSON.parse(text) as T;
}

export async function listReviews(): Promise<ReviewListItem[]> {
  const items = await fetchJson<ReviewListItem[]>("reviews/index.json");
  return Array.isArray(items) ? items : [];
}

export const REVIEW_ID_PATTERN = /^[A-Za-z0-9_-]{1,64}$/;

export async function getReview(id: string): Promise<GameReview> {
  if (!REVIEW_ID_PATTERN.test(id)) {
    throw new Error("Invalid review id");
  }
  const review = await fetchJson<GameReview>(`reviews/${id}.json`);
  if (!review) {
    throw new Error(
      "Review not found. If you just requested it, wait for the site to redeploy and reload.",
    );
  }
  return review;
}

/** Parse a review JSON produced by `python -m chesslab.cli review-game` (for local runs). */
export function parseReviewJson(text: string): GameReview {
  const parsed = JSON.parse(text) as Partial<GameReview>;
  if (
    !parsed ||
    typeof parsed.id !== "string" ||
    !Array.isArray(parsed.moves) ||
    typeof parsed.startingFen !== "string"
  ) {
    throw new Error("That file is not an Opening Lab review");
  }
  return parsed as GameReview;
}

// GitHub's issue-form prefill works through query parameters named after the
// form field ids (see .github/ISSUE_TEMPLATE/review.yml). Browsers cap URLs
// around 8k chars, so very long PGNs are pasted manually instead.
const MAX_PREFILL_CHARS = 6000;

export function reviewRequestUrl(pgn: string): { url: string; prefilled: boolean } {
  const trimmed = pgn.trim();
  const params = new URLSearchParams({ template: "review.yml" });
  const title = titleFromPgn(trimmed);
  if (title) {
    params.set("title", `Review: ${title}`);
  }
  const prefilled = trimmed.length > 0 && trimmed.length <= MAX_PREFILL_CHARS;
  if (prefilled) {
    params.set("pgn", trimmed);
  }
  return { url: `${repoUrl()}/issues/new?${params.toString()}`, prefilled };
}

function header(pgn: string, key: string): string {
  const match = pgn.match(new RegExp(`^\\[${key}\\s+"([^"]*)"\\]`, "m"));
  const value = match?.[1]?.trim() ?? "";
  return value && value !== "?" ? value : "";
}

export function titleFromPgn(pgn: string): string {
  const white = header(pgn, "White");
  const black = header(pgn, "Black");
  if (white || black) {
    return `${white || "White"} vs ${black || "Black"}`;
  }
  return "";
}
