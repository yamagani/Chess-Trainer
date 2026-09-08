import io
import json
from pathlib import Path

import chess.pgn

from chesslab.book import (
    Book,
    build_book,
    fen_key,
    iter_games,
    opening_name_from_headers,
    preview_san,
    slugify_opening,
)

REPO = Path(__file__).resolve().parents[2]
STARTER = REPO / "book" / "starter-repertoire.pgn"

TWO_GAMES = """\
[Event "A"]
[Opening "Ruy Lopez"]
[ECO "C60"]

1. e4 e5 2. Nf3 Nc6 3. Bb5 *

[Event "B"]
[ECO "C50"]

1. e4 e5 2. Nf3 Nc6 3. Bc4 *
"""


def test_fen_key_drops_clocks():
    assert fen_key("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1") == (
        "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"
    )


def test_slugify_matches_ts():
    assert slugify_opening("Sicilian Defense, Najdorf") == "sicilian-defense-najdorf"
    assert slugify_opening("---") == "opening"


def test_preview_san_black_first():
    assert preview_san([("e4", "w"), ("e5", "b"), ("Nf3", "w")]) == "1. e4 e5 2. Nf3"
    assert preview_san([("e5", "b"), ("Nf3", "w")]) == "1... e5 2. Nf3"


def test_opening_name_fallbacks():
    g = chess.pgn.read_game(io.StringIO('[ECO "B12"]\n[Event "Advance"]\n\n1. e4 *'))
    assert opening_name_from_headers(g) == "B12: Advance"
    g = chess.pgn.read_game(io.StringIO('[Event "Casual game"]\n\n1. e4 *'))
    assert opening_name_from_headers(g) == "Unnamed opening"


def test_multi_game_file_is_split_correctly(tmp_path):
    assert len(list(iter_games(TWO_GAMES))) == 2
    path = tmp_path / "two.pgn"
    path.write_text(TWO_GAMES)
    book = build_book([path])
    assert len(book.sources) == 2
    start = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"
    # e4 is shared: stored once, attributed to the first opening seen
    assert [m["uci"] for m in book.positions[start]] == ["e2e4"]
    after_nc6 = "r1bqkbnr/pppp1ppp/2n5/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R w KQkq -"
    assert sorted(m["uci"] for m in book.positions[after_nc6]) == ["f1b5", "f1c4"]
    assert book.sources[0]["eco"] == "C50" and book.sources[0]["openingName"] == "C50: B"


def test_book_move_shape_matches_frontend():
    book = build_book([STARTER])
    move = book.positions["rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq -"][0]
    assert set(move) == {"uci", "san", "from", "to", "openingName"}
    src = book.sources[0]
    assert {"id", "openingName", "preview", "plyCount", "uploadedAt"} <= set(src)
    assert src["plyCount"] <= 24


def test_build_is_deterministic():
    a, b = build_book([STARTER]).to_json(), build_book([STARTER]).to_json()
    assert a == b
    assert json.loads(a)["sources"]


def test_shipped_book_is_up_to_date():
    shipped = (REPO / "frontend" / "public" / "book.json").read_text("utf-8")
    assert shipped == build_book(sorted((REPO / "book").rglob("*.pgn"))).to_json(), (
        "frontend/public/book.json is stale — run: python -m chesslab.cli build-book"
    )


def test_lookup_and_load(tmp_path):
    book = build_book([STARTER])
    start = chess.Board().fen()
    assert book.lookup(start, "e2e4")["san"] == "e4"
    assert book.lookup(start, "a2a3") is None
    path = tmp_path / "book.json"
    path.write_text(book.to_json())
    assert Book.load(path).to_dict() == book.to_dict()
    assert Book.load(tmp_path / "missing.json").is_empty()
