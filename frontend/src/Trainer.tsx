import { useMemo, useState, type CSSProperties } from "react";
import { Chess, type Square } from "chess.js";
import { Chessboard } from "react-chessboard";
import { tryTrainerMove } from "./api";
import { navigate } from "./hashRoute";
import { useBoardWidth } from "./useBoardWidth";
import type { OpeningCourse, OpeningProgress } from "./types";

const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

export function Trainer({
  course,
  courses,
  progress,
  onProgress,
}: {
  course: OpeningCourse | null;
  courses: OpeningCourse[];
  progress: OpeningProgress;
  onProgress: (next: OpeningProgress) => void;
}) {
  const { ref, width } = useBoardWidth(true);
  const [fen, setFen] = useState(START_FEN);
  const [selected, setSelected] = useState<Square | null>(null);
  const [message, setMessage] = useState(
    course
      ? `Training ${course.name}. Play from the start.`
      : "Play a move from the starting position.",
  );
  const [notes, setNotes] = useState(progress.notes);
  const [notesDirty, setNotesDirty] = useState(false);
  const turn = fen.split(" ")[1] === "b" ? "b" : "w";
  const learned = new Set(progress.learnedLineIds);
  const ratio =
    course && course.lineCount > 0
      ? Math.min(1, learned.size / course.lineCount)
      : 0;

  const targets = useMemo(() => {
    if (!selected) {
      return new Set<string>();
    }
    const chess = new Chess(fen);
    return new Set(
      chess.moves({ square: selected, verbose: true }).map((move) => move.to),
    );
  }, [fen, selected]);

  const styles = useMemo(() => {
    const next: Record<string, CSSProperties> = {};
    if (selected) {
      next[selected] = { backgroundColor: "rgba(139, 92, 246, 0.4)" };
    }
    for (const square of targets) {
      next[square] = {
        background:
          "radial-gradient(circle, rgba(0,0,0,0.28) 22%, transparent 24%)",
      };
    }
    return next;
  }, [selected, targets]);

  const markLineComplete = () => {
    if (!course) {
      return;
    }
    const nextId = course.lines.find((line) => !learned.has(line.id))?.id;
    if (!nextId) {
      return;
    }
    onProgress(
      {
        ...progress,
        notes,
        learnedLineIds: [...progress.learnedLineIds, nextId],
        updatedAt: new Date().toISOString(),
      },
    );
    setMessage(`Line complete. ${course.name} progress updated.`);
  };

  const submit = async (from: string, to: string, promotion?: string) => {
    try {
      const result = await tryTrainerMove({
        fen,
        from,
        to,
        promotion,
        preferredOpening: course?.name,
      });
      setMessage(result.message);
      if (result.status === "book" && result.nextFen) {
        setFen(result.nextFen);
        setSelected(null);
        if (result.replyFen) {
          window.setTimeout(() => {
            setFen(result.replyFen ?? result.nextFen ?? fen);
            if (result.reply) {
              setMessage(
                result.lineComplete
                  ? `End of book after ${result.reply.san}.`
                  : `Book reply ${result.reply.san}. Your move.`,
              );
            }
            if (result.lineComplete) {
              markLineComplete();
            }
          }, 280);
        } else if (result.lineComplete) {
          markLineComplete();
        }
      }
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Could not check that move");
    }
  };

  const onDrop = (sourceSquare: string, targetSquare: string, piece: string) => {
    const local = new Chess(fen);
    const needsPromotion = local
      .moves({ square: sourceSquare as Square, verbose: true })
      .some((move) => move.to === targetSquare && Boolean(move.promotion));
    const raw = piece[1]?.toLowerCase();
    const promotion = needsPromotion
      ? raw && raw !== "p"
        ? raw
        : "q"
      : undefined;
    try {
      local.move({
        from: sourceSquare,
        to: targetSquare,
        ...(promotion ? { promotion } : {}),
      });
    } catch {
      return false;
    }
    void submit(sourceSquare, targetSquare, promotion);
    return false;
  };

  const onClick = (square: string) => {
    if (selected && targets.has(square)) {
      const chess = new Chess(fen);
      const options = chess
        .moves({ square: selected, verbose: true })
        .filter((move) => move.to === square);
      const needsPromotion = options.some((move) => move.promotion);
      void submit(selected, square, needsPromotion ? "q" : undefined);
      setSelected(null);
      return;
    }
    const chess = new Chess(fen);
    const piece = chess.get(square as Square);
    if (piece && piece.color === turn) {
      setSelected(square as Square);
    } else {
      setSelected(null);
    }
  };

  const saveNotes = () => {
    onProgress({
      ...progress,
      notes,
      updatedAt: new Date().toISOString(),
    });
    setNotesDirty(false);
  };

  return (
    <main className="play-layout">
      <section className="board-column">
        <div ref={ref} className="board-wrap">
          <Chessboard
            position={fen}
            onPieceDrop={onDrop}
            onSquareClick={onClick}
            boardWidth={width}
            arePiecesDraggable
            animationDuration={180}
            customSquareStyles={styles}
            customBoardStyle={{
              borderRadius: "8px",
              boxShadow: "0 12px 40px rgba(0,0,0,0.35)",
            }}
            customDarkSquareStyle={{ backgroundColor: "#739552" }}
            customLightSquareStyle={{ backgroundColor: "#ebecd0" }}
            isDraggablePiece={({ piece }) =>
              piece.startsWith(turn === "w" ? "w" : "b")
            }
          />
        </div>
        <p className="status">{message}</p>
        <button
          type="button"
          className="ghost compact"
          onClick={() => {
            setFen(START_FEN);
            setSelected(null);
            setMessage(
              course
                ? `Training ${course.name}. Play from the start.`
                : "Play a move from the starting position.",
            );
          }}
        >
          Reset board
        </button>
      </section>
      <aside className="sidebar">
        <label className="field">
          <span>Opening</span>
          <select
            value={course?.slug ?? ""}
            onChange={(event) => {
              const slug = event.target.value;
              navigate(slug ? { name: "train", slug } : { name: "train" });
            }}
          >
            <option value="">Starting position (all book)</option>
            {courses.map((item) => (
              <option key={item.slug} value={item.slug}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {course ? (
          <>
            <p className="muted tight">{course.preview}</p>
            <p className="course-meta">
              {learned.size}/{course.lineCount} lines learned
            </p>
            <div
              className="progress-track"
              role="progressbar"
              aria-valuenow={Math.round(ratio * 100)}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <span style={{ width: `${Math.round(ratio * 100)}%` }} />
            </div>
          </>
        ) : null}
        <label className="field">
          <span>Notes</span>
          <textarea
            value={notes}
            rows={8}
            placeholder="Commentary and notes for this opening will go here."
            onChange={(event) => {
              setNotes(event.target.value);
              setNotesDirty(true);
            }}
          />
        </label>
        <button
          type="button"
          className="primary"
          disabled={!notesDirty}
          onClick={saveNotes}
        >
          {notesDirty ? "Save notes" : "Notes saved"}
        </button>
      </aside>
    </main>
  );
}
