"""Game review — port of backend1/src/reviews.ts.

`review_pgn` turns a PGN string into the `GameReview` JSON the frontend
renders (same keys as before, minus `userId`). It runs synchronously in a
batch job, so `status` is always "ready" (or "error") when written.
"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from typing import Callable

import chess
import chess.pgn

from .book import Book
from .engine import Engine, classify_loss, eval_loss, flip, to_white_pov
from .schema import (
    ANALYZE_DEPTH,
    ANALYZE_MULTI_PV,
    MAX_PGN_CHARS,
    MAX_REVIEW_PLIES,
    Evaluation,
    ReviewSummary,
)


class ReviewError(ValueError):
    """User-facing problem with the submitted PGN."""


def _header(game: chess.pgn.Game, key: str, fallback: str) -> str:
    """Header value, or `fallback` when missing or a PGN placeholder ("?", "????.??.??")."""
    value = game.headers.get(key, "").strip()
    return value if value and set(value) - set("?.") else fallback


def parse_pgn(pgn: str) -> tuple[str, chess.pgn.Game]:
    trimmed = pgn.strip()
    if len(trimmed) < 10:
        raise ReviewError("Paste or upload a PGN game")
    if len(trimmed) > MAX_PGN_CHARS:
        raise ReviewError("PGN is too large")
    try:
        game = chess.pgn.read_game(io.StringIO(trimmed))
    except ValueError as exc:  # pragma: no cover - python-chess is lenient
        raise ReviewError("Could not parse that PGN") from exc
    if game is None:
        raise ReviewError("Could not parse that PGN")
    if game.errors and not list(game.mainline_moves()):
        raise ReviewError("Could not parse that PGN")
    if not list(game.mainline_moves()):
        raise ReviewError("That PGN has no moves")
    return trimmed, game


def review_id(pgn: str) -> str:
    """Stable id for a PGN so re-submitting the same game overwrites, not duplicates."""
    return hashlib.sha1(pgn.strip().encode("utf-8")).hexdigest()[:12]


def summarize(moves: list[dict]) -> ReviewSummary:
    flagged = [
        m for m in moves
        if m.get("annotation") and m["annotation"]["kind"] in ("inaccuracy", "mistake", "blunder")
    ]
    worst = sorted(flagged, key=lambda m: m["lossCp"], reverse=True)[:8]
    return {
        "inaccuracies": sum(1 for m in flagged if m["annotation"]["kind"] == "inaccuracy"),
        "mistakes": sum(1 for m in flagged if m["annotation"]["kind"] == "mistake"),
        "blunders": sum(1 for m in flagged if m["annotation"]["kind"] == "blunder"),
        "worst": [
            {
                "ply": m["ply"],
                "san": m["san"],
                "color": m["color"],
                "lossCp": m["lossCp"],
                "kind": m["annotation"]["kind"],
            }
            for m in worst
        ],
    }


def review_pgn(
    pgn: str,
    engine: Engine,
    book: Book | None = None,
    *,
    depth: int = ANALYZE_DEPTH,
    multipv: int = ANALYZE_MULTI_PV,
    max_plies: int = MAX_REVIEW_PLIES,
    review_id_override: str | None = None,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict:
    trimmed, game = parse_pgn(pgn)
    book = book or Book()
    played = list(game.mainline_moves())[:max_plies]
    board = game.board()
    starting_fen = board.fen()
    moves: list[dict] = []

    for index, move in enumerate(played):
        fen_before = board.fen()
        color = "w" if board.turn == chess.WHITE else "b"
        san = board.san(move)
        played_uci = move.uci()

        analysis = engine.analyze(board, depth, multipv)
        best_line = analysis.lines[0] if analysis.lines else None
        played_eval: Evaluation | None = next(
            (line.evaluation for line in analysis.lines if line.uci == played_uci), None
        )
        if played_eval is None:
            probe = board.copy()
            probe.push(move)
            if probe.is_checkmate():
                played_eval = {"type": "mate", "value": 1}
            elif probe.is_game_over():
                played_eval = {"type": "cp", "value": 0}
            else:
                played_eval = engine.analyze_move(board, move, depth) or {"type": "cp", "value": 0}

        best_eval = best_line.evaluation if best_line else played_eval
        loss_cp = eval_loss(best_eval, played_eval)
        book_hit = book.lookup(fen_before, played_uci)
        annotation = classify_loss(loss_cp, book_hit is not None)

        board.push(move)
        reviewed = {
            "ply": index + 1,
            "san": san,
            "from": chess.square_name(move.from_square),
            "to": chess.square_name(move.to_square),
            "color": color,
            "fen": board.fen(),
            "evaluation": to_white_pov(played_eval, color),
            "bestEvaluation": to_white_pov(best_eval, color),
            "lossCp": loss_cp,
        }
        if move.promotion:
            reviewed["promotion"] = chess.piece_symbol(move.promotion)
        if annotation:
            reviewed["annotation"] = annotation
        if analysis.bestmove and analysis.bestmove != played_uci:
            reviewed["bestMove"] = analysis.bestmove
        if book_hit:
            reviewed["openingName"] = book_hit["openingName"]
        moves.append(reviewed)
        if on_progress:
            on_progress(index + 1, len(played))

    result = {
        "id": review_id_override or review_id(trimmed),
        "pgn": trimmed,
        "white": _header(game, "White", "White"),
        "black": _header(game, "Black", "Black"),
        "result": _header(game, "Result", "*"),
        "event": _header(game, "Event", "Casual game"),
        "date": _header(game, "Date", ""),
        "status": "ready",
        "progress": {"analyzed": len(moves), "total": len(played)},
        "startingFen": starting_fen,
        "moves": moves,
        "summary": summarize(moves),
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "engine": {"depth": depth, "multipv": multipv},
    }
    if game.errors:
        # python-chess keeps the legal prefix and records what it could not parse
        result["warning"] = f"Stopped at ply {len(played)}: {game.errors[0]}"
    return result


def list_item(review: dict) -> dict:
    """ReviewListItem — what reviews/index.json holds."""
    keys = ("id", "white", "black", "result", "event", "date", "status", "progress", "summary", "createdAt")
    return {k: review[k] for k in keys if k in review}


# `flip` is re-exported for callers that only import review.py
__all__ = ["ReviewError", "review_pgn", "review_id", "summarize", "list_item", "parse_pgn", "flip"]
