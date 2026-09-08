"""Command-line entry points used by the GitHub Actions workflows.

    python -m chesslab.cli build-book   [--pgn-dir book] [--out frontend/public/book.json]
    python -m chesslab.cli review-game  (--pgn-file F | --issue-body-file F | --stdin)
                                        [--id ID] [--out-dir frontend/public/reviews]
                                        [--book frontend/public/book.json] [--depth N]
                                        [--summary-file F]

Nothing here reads credentials: the workflows commit with the job's own
GITHUB_TOKEN, and the scripts only touch files inside the repo.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from .book import Book, build_book
from .engine import Engine
from .review import ReviewError, list_item, review_pgn
from .schema import ANALYZE_DEPTH

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PGN_DIR = REPO_ROOT / "book"
DEFAULT_BOOK_OUT = REPO_ROOT / "frontend" / "public" / "book.json"
DEFAULT_REVIEWS_DIR = REPO_ROOT / "frontend" / "public" / "reviews"
MAX_INDEX_ITEMS = 200


# --- build-book --------------------------------------------------------------


def build_book_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="build-book", description="PGN files -> book.json")
    parser.add_argument("--pgn-dir", type=Path, default=DEFAULT_PGN_DIR)
    parser.add_argument("--out", type=Path, default=DEFAULT_BOOK_OUT)
    parser.add_argument("--check", action="store_true", help="exit 1 if the output would change")
    args = parser.parse_args(argv)

    pgn_files = sorted(args.pgn_dir.rglob("*.pgn"))
    if not pgn_files:
        print(f"No .pgn files under {args.pgn_dir}", file=sys.stderr)
        return 1
    book = build_book(pgn_files)
    text = book.to_json()
    print(
        f"{len(pgn_files)} file(s) -> {len(book.sources)} line(s), "
        f"{len(book.positions)} position(s), "
        f"{len({s['openingName'] for s in book.sources})} opening(s)"
    )
    if args.check:
        current = args.out.read_text("utf-8") if args.out.exists() else ""
        if current != text:
            print(f"{args.out} is out of date; run build-book", file=sys.stderr)
            return 1
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, "utf-8")
    print(f"wrote {args.out}")
    return 0


# --- review-game -------------------------------------------------------------

_FENCE = re.compile(r"```(?:pgn|text)?\s*\n(.*?)\n```", re.DOTALL | re.IGNORECASE)
_PGN_SECTION = re.compile(r"^###\s*PGN\s*$\n(.*?)(?=^###\s|\Z)", re.DOTALL | re.MULTILINE | re.IGNORECASE)


def pgn_from_issue_body(body: str) -> str:
    """Pull the PGN out of a GitHub issue-form body (fenced block, `### PGN` section, or whole body)."""
    fence = _FENCE.search(body)
    if fence:
        return fence.group(1).strip()
    section = _PGN_SECTION.search(body)
    if section:
        return section.group(1).strip()
    return body.strip()


def _load_index(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", "utf-8")
    tmp.replace(path)  # atomic on POSIX


def _safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise SystemExit(f"invalid review id: {value!r}")
    return value


def summary_markdown(review: dict, base_url: str | None) -> str:
    s = review["summary"]
    lines = [
        f"**{review['white']}** vs **{review['black']}** — {review['result']}",
        "",
        f"| Inaccuracies | Mistakes | Blunders |",
        f"|---|---|---|",
        f"| {s['inaccuracies']} | {s['mistakes']} | {s['blunders']} |",
        "",
        f"Analyzed {review['progress']['analyzed']} plies at depth {review['engine']['depth']}.",
    ]
    if s["worst"]:
        lines += ["", "Worst moves:", ""]
        for w in s["worst"][:5]:
            move_no = (w["ply"] + 1) // 2
            dots = "." if w["color"] == "w" else "..."
            lines.append(f"- {move_no}{dots} {w['san']} — {w['kind']} (−{w['lossCp']} cp)")
    if base_url:
        lines += ["", f"Open the review: {base_url.rstrip('/')}/#/review/{review['id']}"]
    return "\n".join(lines) + "\n"


def review_game_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="review-game", description="PGN -> reviews/<id>.json")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--pgn-file", type=Path)
    src.add_argument("--issue-body-file", type=Path, help="raw GitHub issue body; PGN is extracted")
    src.add_argument("--stdin", action="store_true")
    parser.add_argument("--id", help="review id (default: hash of the PGN)")
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_REVIEWS_DIR)
    parser.add_argument("--book", type=Path, default=DEFAULT_BOOK_OUT)
    parser.add_argument("--depth", type=int, default=ANALYZE_DEPTH)
    parser.add_argument("--summary-file", type=Path, help="write a markdown summary here (for the issue comment)")
    parser.add_argument("--site-url", help="public site URL used in the summary link")
    args = parser.parse_args(argv)

    if args.pgn_file:
        pgn = args.pgn_file.read_text("utf-8", errors="replace")
    elif args.issue_body_file:
        pgn = pgn_from_issue_body(args.issue_body_file.read_text("utf-8", errors="replace"))
    else:
        pgn = sys.stdin.read()

    book = Book.load(args.book)
    override = _safe_id(args.id) if args.id else None

    def progress(done: int, total: int) -> None:
        if done == total or done % 10 == 0:
            print(f"  {done}/{total}", flush=True)

    try:
        with Engine() as engine:
            review = review_pgn(pgn, engine, book, depth=args.depth, review_id_override=override, on_progress=progress)
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        if args.summary_file:
            args.summary_file.write_text(f"Could not review this game: {exc}\n", "utf-8")
        return 2

    out = args.out_dir / f"{review['id']}.json"
    _write_json(out, review)

    index_path = args.out_dir / "index.json"
    index = [item for item in _load_index(index_path) if item.get("id") != review["id"]]
    index.insert(0, list_item(review))
    _write_json(index_path, index[:MAX_INDEX_ITEMS])

    if args.summary_file:
        args.summary_file.write_text(summary_markdown(review, args.site_url), "utf-8")
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("build-book", "review-game"):
        print(__doc__, file=sys.stderr)
        return 1
    command, rest = argv[0], argv[1:]
    return build_book_main(rest) if command == "build-book" else review_game_main(rest)


if __name__ == "__main__":
    sys.exit(main())
