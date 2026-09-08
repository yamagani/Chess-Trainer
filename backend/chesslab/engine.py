"""Stockfish wrapper — port of backend1/src/engine.ts + classify.ts.

Evaluations are always relative to the side to move (as UCI reports them);
`to_white_pov` flips them for display, exactly like the old backend.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass

import chess
import chess.engine

from .schema import Evaluation, MoveAnnotation

INACCURACY_LOSS = 50
MISTAKE_LOSS = 100
BLUNDER_LOSS = 200
MATE_CP = 30_000


def score_to_cp(evaluation: Evaluation) -> int:
    if evaluation["type"] == "mate":
        n = evaluation["value"]
        if n > 0:
            return MATE_CP - n
        if n < 0:
            return -MATE_CP + n
        return 0
    return evaluation["value"]


def eval_loss(best: Evaluation, played: Evaluation) -> int:
    return max(0, score_to_cp(best) - score_to_cp(played))


def flip(evaluation: Evaluation) -> Evaluation:
    return {"type": evaluation["type"], "value": -evaluation["value"]}


def to_white_pov(evaluation: Evaluation, side_to_move: str) -> Evaluation:
    return evaluation if side_to_move == "w" else flip(evaluation)


def classify_loss(loss_cp: int, in_book: bool) -> MoveAnnotation | None:
    if in_book:
        return {"kind": "book", "glyph": "book"}
    if loss_cp >= BLUNDER_LOSS:
        return {"kind": "blunder", "glyph": "??"}
    if loss_cp >= MISTAKE_LOSS:
        return {"kind": "mistake", "glyph": "?"}
    if loss_cp >= INACCURACY_LOSS:
        return {"kind": "inaccuracy", "glyph": "?!"}
    return None


def _evaluation_from_score(score: chess.engine.PovScore) -> Evaluation:
    rel = score.relative
    mate = rel.mate()
    if mate is not None:
        return {"type": "mate", "value": int(mate)}
    return {"type": "cp", "value": int(rel.score(mate_score=MATE_CP))}


@dataclass
class ScoredLine:
    uci: str
    evaluation: Evaluation


@dataclass
class Analysis:
    bestmove: str | None
    lines: list[ScoredLine]


def find_stockfish() -> str:
    """Path to the engine: $STOCKFISH_PATH, else `stockfish` on PATH."""
    candidate = os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish")
    if not candidate:
        raise RuntimeError(
            "Stockfish not found. Install it (apt-get install stockfish) or set STOCKFISH_PATH."
        )
    return candidate


class Engine:
    """Single serialized Stockfish process (like the old backend's queue)."""

    def __init__(self, path: str | None = None, *, hash_mb: int = 64, threads: int = 1):
        self._engine = chess.engine.SimpleEngine.popen_uci(path or find_stockfish())
        self._engine.configure({"Hash": hash_mb, "Threads": threads})

    def close(self) -> None:
        self._engine.quit()

    def __enter__(self) -> "Engine":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def analyze(self, board: chess.Board, depth: int, multipv: int = 1) -> Analysis:
        multipv = max(1, multipv)
        infos = self._engine.analyse(board, chess.engine.Limit(depth=depth), multipv=multipv)
        return self._collect(infos)

    def analyze_move(self, board: chess.Board, move: chess.Move, depth: int) -> Evaluation | None:
        """Evaluate one specific move at the same depth as the main search (fixes the old depth mismatch)."""
        infos = self._engine.analyse(
            board, chess.engine.Limit(depth=depth), multipv=1, root_moves=[move]
        )
        analysis = self._collect(infos)
        return analysis.lines[0].evaluation if analysis.lines else None

    @staticmethod
    def _collect(infos: list[chess.engine.InfoDict]) -> Analysis:
        seen: set[str] = set()
        lines: list[ScoredLine] = []
        for info in infos:
            pv = info.get("pv")
            score = info.get("score")
            if not pv or score is None:
                continue
            uci = pv[0].uci()
            if uci in seen:
                continue
            seen.add(uci)
            lines.append(ScoredLine(uci=uci, evaluation=_evaluation_from_score(score)))
        return Analysis(bestmove=lines[0].uci if lines else None, lines=lines)
