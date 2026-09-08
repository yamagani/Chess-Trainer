import shutil

import chess
import pytest

from chesslab.book import Book, build_book
from chesslab.cli import pgn_from_issue_body, summary_markdown
from chesslab.engine import Engine, classify_loss, eval_loss, score_to_cp, to_white_pov
from chesslab.review import ReviewError, parse_pgn, review_id, review_pgn, summarize

from test_book import STARTER

needs_stockfish = pytest.mark.skipif(shutil.which("stockfish") is None, reason="stockfish not installed")

SHORT_GAME = """\
[Event "Scholar's mate"]
[White "W"]
[Black "B"]
[Result "1-0"]

1. e4 e5 2. Bc4 Nc6 3. Qh5 Nf6 4. Qxf7# 1-0
"""


def test_score_to_cp_and_loss():
    assert score_to_cp({"type": "cp", "value": 37}) == 37
    assert score_to_cp({"type": "mate", "value": 3}) == 29_997
    assert score_to_cp({"type": "mate", "value": -2}) == -30_002
    assert eval_loss({"type": "cp", "value": 50}, {"type": "cp", "value": -100}) == 150
    assert eval_loss({"type": "cp", "value": 0}, {"type": "cp", "value": 20}) == 0


def test_classification_thresholds():
    assert classify_loss(0, True) == {"kind": "book", "glyph": "book"}
    assert classify_loss(49, False) is None
    assert classify_loss(50, False)["kind"] == "inaccuracy"
    assert classify_loss(100, False)["kind"] == "mistake"
    assert classify_loss(200, False)["glyph"] == "??"


def test_white_pov():
    assert to_white_pov({"type": "cp", "value": 30}, "b") == {"type": "cp", "value": -30}
    assert to_white_pov({"type": "mate", "value": 2}, "w") == {"type": "mate", "value": 2}


def test_parse_pgn_errors():
    with pytest.raises(ReviewError):
        parse_pgn("short")
    with pytest.raises(ReviewError):
        parse_pgn('[Event "x"]\n[White "no moves"]\n\n*')
    with pytest.raises(ReviewError):
        parse_pgn("x" * 300_000)


def test_placeholder_headers_fall_back():
    from chesslab.review import _header
    game = parse_pgn('[Date "????.??.??"]\n[White "?"]\n[Black "Bob"]\n\n1. e4 e5 *')[1]
    assert _header(game, "Date", "") == ""
    assert _header(game, "White", "White") == "White"
    assert _header(game, "Black", "Black") == "Bob"


def test_review_id_is_stable():
    assert review_id(SHORT_GAME) == review_id("  " + SHORT_GAME + "\n")
    assert len(review_id(SHORT_GAME)) == 12


def test_pgn_from_issue_body():
    body = "### Title\n\nMy game\n\n### PGN\n\n```pgn\n1. e4 e5 *\n```\n\n### Notes\n\nnone"
    assert pgn_from_issue_body(body) == "1. e4 e5 *"
    body = "### PGN\n\n1. d4 d5 *\n\n### Notes\n\n_No response_"
    assert pgn_from_issue_body(body) == "1. d4 d5 *"
    assert pgn_from_issue_body("1. c4 *") == "1. c4 *"


def test_summarize_picks_worst():
    moves = [
        {"ply": 1, "san": "a", "color": "w", "lossCp": 60, "annotation": {"kind": "inaccuracy", "glyph": "?!"}},
        {"ply": 2, "san": "b", "color": "b", "lossCp": 300, "annotation": {"kind": "blunder", "glyph": "??"}},
        {"ply": 3, "san": "c", "color": "w", "lossCp": 0, "annotation": {"kind": "book", "glyph": "book"}},
    ]
    s = summarize(moves)
    assert (s["inaccuracies"], s["mistakes"], s["blunders"]) == (1, 0, 1)
    assert s["worst"][0]["san"] == "b"


@needs_stockfish
def test_review_short_game_end_to_end():
    book = build_book([STARTER])
    with Engine() as engine:
        review = review_pgn(SHORT_GAME, engine, book, depth=6)
    assert review["status"] == "ready"
    assert review["progress"] == {"analyzed": 7, "total": 7}
    assert review["white"] == "W" and review["result"] == "1-0"
    assert review["startingFen"] == chess.Board().fen()
    moves = review["moves"]
    assert moves[0]["annotation"] == {"kind": "book", "glyph": "book"}
    assert moves[0]["openingName"]
    # 3...Nf6?? allows mate; the checkmating move is scored as mate in 1 for the mover
    assert moves[5]["annotation"]["kind"] == "blunder"
    assert moves[6]["evaluation"] == {"type": "mate", "value": 1}  # white POV, white mated
    assert "userId" not in review
    md = summary_markdown(review, "https://example.test/app/")
    assert "#/review/" + review["id"] in md


@needs_stockfish
def test_review_with_empty_book_has_no_book_marks():
    with Engine() as engine:
        review = review_pgn(SHORT_GAME, engine, Book(), depth=4)
    assert all(m.get("annotation", {}).get("kind") != "book" for m in review["moves"])
