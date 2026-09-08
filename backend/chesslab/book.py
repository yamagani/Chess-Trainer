"""Opening book builder — port of backend1/src/openingBook.ts.

Input:  one or more PGN files (any number of games per file).
Output: the `StoredBook` JSON the frontend already understands:

    {"positions": {"<fen key>": [BookMove, ...]}, "sources": [BookSource, ...]}

The build is deterministic: source ids are content hashes, and nothing
depends on wall-clock time, so re-running on unchanged PGNs produces a
byte-identical book.json (no noisy commits from CI).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

import chess
import chess.pgn

from .schema import MAX_BOOK_PLIES

UNNAMED_OPENING = "Unnamed opening"


# --- helpers mirrored from openingBook.ts / bookEngine.ts -------------------


def fen_key(fen: str) -> str:
    """First four FEN fields: placement, side, castling, en passant."""
    return " ".join(fen.split(" ")[:4])


def to_uci(move: chess.Move) -> str:
    return move.uci()


def slugify_opening(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower())
    slug = re.sub(r"^-+|-+$", "", slug)
    return slug or "opening"


def _header(game: chess.pgn.Game, key: str) -> str:
    value = game.headers.get(key, "")
    return value if value and value != "?" else ""


def opening_name_from_headers(game: chess.pgn.Game) -> str:
    opening = _header(game, "Opening")
    if opening:
        return opening
    eco = _header(game, "ECO")
    event = _header(game, "Event")
    if eco and event:
        return f"{eco}: {event}"
    if eco:
        return eco
    if event and event != "Casual game":
        return event
    return UNNAMED_OPENING


def preview_san(moves: list[tuple[str, str]]) -> str:
    """`moves` is a list of (san, color) — first 8 plies rendered like `1. e4 e5 2. Nf3`."""
    parts: list[str] = []
    number = 1
    for san, color in moves[:8]:
        if color == "w":
            parts.append(f"{number}. {san}")
            number += 1
        elif not parts:
            parts.append(f"{number}... {san}")
            number += 1
        else:
            parts.append(san)
    return " ".join(parts)


# --- book model --------------------------------------------------------------


def serialize_move(move: chess.Move, board: chess.Board, opening_name: str) -> dict:
    """BookMove dict for `move` played from `board` (board must be *before* the move)."""
    out = {
        "uci": move.uci(),
        "san": board.san(move),
        "from": chess.square_name(move.from_square),
        "to": chess.square_name(move.to_square),
        "openingName": opening_name,
    }
    if move.promotion:
        out["promotion"] = chess.piece_symbol(move.promotion)
    return out


@dataclass
class Book:
    positions: dict[str, list[dict]] = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)

    # -- mutation
    def add_move(self, fen_before: str, move: dict) -> bool:
        key = fen_key(fen_before)
        existing = self.positions.setdefault(key, [])
        if any(item["uci"] == move["uci"] for item in existing):
            return False
        existing.append(move)
        return True

    def add_game(self, game: chess.pgn.Game, *, max_plies: int = MAX_BOOK_PLIES) -> dict | None:
        """Add one PGN game's first `max_plies` moves. Returns the BookSource or None if empty."""
        board = game.board()
        opening_name = opening_name_from_headers(game)
        eco = _header(game, "ECO")
        sans: list[tuple[str, str]] = []
        ucis: list[str] = []
        for move in list(game.mainline_moves())[:max_plies]:
            if move not in board.legal_moves:
                break
            sans.append((board.san(move), "w" if board.turn == chess.WHITE else "b"))
            ucis.append(move.uci())
            self.add_move(board.fen(), serialize_move(move, board, opening_name))
            board.push(move)
        if not ucis:
            return None
        source = {
            "id": source_id(opening_name, ucis),
            "openingName": opening_name,
            "preview": preview_san(sans),
            "plyCount": len(ucis),
            "uploadedAt": _uploaded_at(game),
        }
        if eco:
            source["eco"] = eco
        # identical line already present (same opening + same moves) -> skip duplicate source
        if any(s["id"] == source["id"] for s in self.sources):
            return None
        self.sources.append(source)
        return source

    # -- lookup
    def moves_for(self, fen: str) -> list[dict]:
        return self.positions.get(fen_key(fen), [])

    def lookup(self, fen: str, uci: str) -> dict | None:
        return next((m for m in self.moves_for(fen) if m["uci"] == uci), None)

    def is_empty(self) -> bool:
        return not self.positions and not self.sources

    # -- (de)serialisation
    def to_dict(self) -> dict:
        return {"positions": self.positions, "sources": self.sources}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False) + "\n"

    @classmethod
    def from_dict(cls, data: dict) -> "Book":
        return cls(positions=dict(data.get("positions") or {}), sources=list(data.get("sources") or []))

    @classmethod
    def load(cls, path: Path) -> "Book":
        try:
            return cls.from_dict(json.loads(Path(path).read_text("utf-8")))
        except (OSError, ValueError):
            return cls()


def source_id(opening_name: str, ucis: Iterable[str]) -> str:
    digest = hashlib.sha1(f"{opening_name}\n{' '.join(ucis)}".encode("utf-8")).hexdigest()
    # UUID-shaped so it stays a valid, stable line id for the frontend
    return f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}"


def _uploaded_at(game: chess.pgn.Game) -> str:
    """Deterministic stand-in for the old upload timestamp: the PGN Date header if usable."""
    date = _header(game, "Date").replace(".", "-")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date):
        return f"{date}T00:00:00.000Z"
    return "1970-01-01T00:00:00.000Z"


# --- parsing -----------------------------------------------------------------


def iter_games(pgn_text: str) -> Iterable[chess.pgn.Game]:
    """Yield every parseable game in a PGN string (fixes the old `\\n[Event` splitting)."""
    stream = io.StringIO(pgn_text)
    while True:
        try:
            game = chess.pgn.read_game(stream)
        except ValueError:
            continue
        if game is None:
            return
        if game.errors:
            # python-chess records illegal-move errors but still returns the parsed prefix;
            # that prefix is legal, so we keep it (matches chess.js leniency for opening lines).
            pass
        yield game


def build_book(pgn_paths: Iterable[Path], *, max_plies: int = MAX_BOOK_PLIES) -> Book:
    book = Book()
    # sorted for determinism regardless of filesystem order
    for path in sorted(Path(p) for p in pgn_paths):
        for game in iter_games(path.read_text("utf-8", errors="replace")):
            book.add_game(game, max_plies=max_plies)
    book.sources.sort(key=lambda s: (s["openingName"], s["id"]))
    return book
