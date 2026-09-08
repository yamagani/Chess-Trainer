import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { listOpenings } from "./api";
import { Home } from "./Home";
import { ReviewScreen } from "./ReviewScreen";
import { Studies } from "./Studies";
import { Trainer } from "./Trainer";
import { navigate, parseHash, type AppRoute } from "./hashRoute";
import {
  STORAGE_NOTE,
  createStudy,
  deleteStudy,
  downloadText,
  exportBackup,
  getStudy,
  importBackup,
  listStudies,
  loadProgress,
  writeOpeningProgress,
} from "./localStore";
import type { OpeningCourse, OpeningProgress, StudyListItem } from "./types";
import "./App.css";

function emptyProgress(): OpeningProgress {
  return {
    learnedLineIds: [],
    notes: "",
    updatedAt: new Date().toISOString(),
  };
}

function navClass(active: boolean) {
  return active ? "nav-link active" : "nav-link";
}

export default function App() {
  const [route, setRoute] = useState<AppRoute>(() =>
    typeof window === "undefined"
      ? { name: "home" }
      : parseHash(window.location.hash),
  );
  const [courses, setCourses] = useState<OpeningCourse[]>([]);
  const [progress, setProgress] = useState<Record<string, OpeningProgress>>(
    () => loadProgress(),
  );
  const [studies, setStudies] = useState<StudyListItem[]>(() => listStudies());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [reviewPgn, setReviewPgn] = useState<string | undefined>();
  const importInput = useRef<HTMLInputElement>(null);

  const trainSlug = route.name === "train" ? route.slug : undefined;
  const course = useMemo(
    () => courses.find((item) => item.slug === trainSlug) ?? null,
    [courses, trainSlug],
  );
  const openingId = course?.slug ?? "_default";
  const openingProgress = progress[openingId] ?? emptyProgress();

  useEffect(() => {
    const sync = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  useEffect(() => {
    void listOpenings()
      .then(setCourses)
      .catch((err) => {
        setCourses([]);
        setError(err instanceof Error ? err.message : "Could not load the opening book");
      });
  }, []);

  useEffect(() => {
    if (!notice) {
      return;
    }
    const timer = window.setTimeout(() => setNotice(null), 4000);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const onProgress = useCallback(
    (next: OpeningProgress) => {
      const saved = writeOpeningProgress(openingId, {
        learnedLineIds: next.learnedLineIds,
        notes: next.notes,
      });
      setProgress((current) => ({ ...current, [openingId]: saved }));
    },
    [openingId],
  );

  const onCreateStudy = useCallback((title: string, pgn: string) => {
    setBusy(true);
    setError(null);
    try {
      createStudy(title, pgn);
      setStudies(listStudies());
      setNotice("Study saved in this browser.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save study");
    } finally {
      setBusy(false);
    }
  }, []);

  const onDeleteStudy = useCallback((id: string) => {
    deleteStudy(id);
    setStudies(listStudies());
  }, []);

  const onOpenStudy = useCallback((id: string) => {
    try {
      setReviewPgn(getStudy(id).pgn);
      navigate({ name: "review" });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not open study");
    }
  }, []);

  const onExport = useCallback(() => {
    const stamp = new Date().toISOString().slice(0, 10);
    downloadText(`opening-lab-backup-${stamp}.json`, exportBackup());
  }, []);

  const onImportFile = useCallback((file: File | undefined) => {
    if (!file) {
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      try {
        const result = importBackup(String(reader.result ?? ""));
        setProgress(loadProgress());
        setStudies(listStudies());
        setNotice(
          `Imported ${result.openings} opening(s) and ${result.studies} new study(ies).`,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Could not import backup");
      }
    };
    reader.readAsText(file);
  }, []);

  return (
    <div className="app-shell">
      <header className="site-header">
        <button
          type="button"
          className="site-brand"
          onClick={() => navigate({ name: "home" })}
        >
          Opening Lab
        </button>
        <nav className="site-nav">
          <button
            type="button"
            className={navClass(route.name === "home")}
            onClick={() => navigate({ name: "home" })}
          >
            Courses
          </button>
          <button
            type="button"
            className={navClass(route.name === "train")}
            onClick={() => navigate({ name: "train" })}
          >
            Train
          </button>
          <button
            type="button"
            className={navClass(route.name === "review")}
            onClick={() => navigate({ name: "review" })}
          >
            Review
          </button>
          <button
            type="button"
            className={navClass(route.name === "studies")}
            onClick={() => navigate({ name: "studies" })}
          >
            Studies
          </button>
        </nav>
        <div className="site-auth">
          <span className="user-label" title={STORAGE_NOTE}>
            Local data
          </span>
          <button type="button" className="text-btn" onClick={onExport}>
            Export
          </button>
          <button
            type="button"
            className="text-btn"
            onClick={() => importInput.current?.click()}
          >
            Import
          </button>
          <input
            ref={importInput}
            type="file"
            accept="application/json,.json"
            hidden
            onChange={(event) => {
              onImportFile(event.target.files?.[0]);
              event.target.value = "";
            }}
          />
        </div>
      </header>

      {notice ? <p className="guest-banner">{notice}</p> : null}
      {error && route.name === "home" ? <p className="error">{error}</p> : null}

      {route.name === "home" ? (
        <Home
          courses={courses}
          progress={progress}
          search={search}
          onSearch={setSearch}
        />
      ) : route.name === "train" ? (
        <Trainer
          key={openingId}
          course={course}
          courses={courses}
          progress={openingProgress}
          onProgress={onProgress}
        />
      ) : route.name === "studies" ? (
        <Studies
          studies={studies}
          busy={busy}
          error={error}
          onCreate={onCreateStudy}
          onDelete={onDeleteStudy}
          onOpen={onOpenStudy}
        />
      ) : (
        <ReviewScreen
          key={`${route.id ?? ""}:${reviewPgn ?? ""}`}
          reviewId={route.id}
          initialPgn={reviewPgn}
          onSaveStudy={(title, pgn) => {
            onCreateStudy(title, pgn);
          }}
        />
      )}
    </div>
  );
}
