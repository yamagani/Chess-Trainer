"""JSON shapes shared with the React frontend (see frontend/src/types.ts).

Everything here is a plain dict so it serialises 1:1 with the TypeScript
types; optional keys are simply omitted (never set to null) to match what
the Express backend used to emit.
"""

from __future__ import annotations

from typing import Literal, TypedDict

EvalType = Literal["cp", "mate"]
Color = Literal["w", "b"]
AnnotationKind = Literal["book", "inaccuracy", "mistake", "blunder"]
Glyph = Literal["book", "?!", "?", "??"]


class Evaluation(TypedDict):
    type: EvalType
    value: int


class MoveAnnotation(TypedDict):
    kind: AnnotationKind
    glyph: Glyph


class BookMove(TypedDict, total=False):
    uci: str
    san: str
    from_: str  # serialised as "from" (see book.serialize_move)
    to: str
    promotion: str
    openingName: str


class BookSource(TypedDict, total=False):
    id: str
    openingName: str
    eco: str
    preview: str
    plyCount: int
    uploadedAt: str


class ReviewedMove(TypedDict, total=False):
    ply: int
    san: str
    to: str
    color: Color
    promotion: str
    fen: str
    evaluation: Evaluation | None
    bestEvaluation: Evaluation | None
    lossCp: int
    annotation: MoveAnnotation
    bestMove: str
    openingName: str


class WorstMove(TypedDict):
    ply: int
    san: str
    color: Color
    lossCp: int
    kind: AnnotationKind


class ReviewSummary(TypedDict):
    inaccuracies: int
    mistakes: int
    blunders: int
    worst: list[WorstMove]


class Progress(TypedDict):
    analyzed: int
    total: int


# Tunables (kept as module constants like types.ts did)
ANALYZE_DEPTH = 14
ANALYZE_MULTI_PV = 3
MAX_REVIEW_PLIES = 160
MAX_BOOK_PLIES = 24
MAX_PGN_CHARS = 200_000
