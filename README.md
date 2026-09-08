# Opening Lab

A chess training app: browse opening courses from a book, drill those lines on the board, and review games with Stockfish.

- **Frontend**: React + Vite, static, deployed to GitHub Pages.
- **Backend**: Python (`backend/`), runs **only inside GitHub Actions**. It builds the opening book from PGN files and reviews games with Stockfish, then commits the results as JSON for the site to read.

There is no server, no database, no accounts, and **no secrets** — the workflows use the built-in `GITHUB_TOKEN` and nothing else. Personal data (training progress, notes, saved studies) stays in your browser, with Export/Import for backups.

Live site: `https://<owner>.github.io/Chess-Trainer/`

## Features

| Route | What it does | Data source |
| --- | --- | --- |
| `#/` | Course catalog with search and line counts | `frontend/public/book.json` |
| `#/train`, `#/train/<slug>` | Play book moves; the app replies, or hints a correct continuation on a wrong / out-of-book move | book, in the browser |
| `#/review` | Request a Stockfish review (via a GitHub Issue), browse published reviews | `frontend/public/reviews/` |
| `#/review/<id>` | Annotated game: ?! ? ?? glyphs, eval bar, worst moves, book moves | one review JSON |
| `#/studies` | Save and reopen PGNs | `localStorage` |

Course names come from the PGN `Opening` header, else `ECO: Event`, else `Event`, else "Unnamed opening".

## How the pieces fit

```
book/*.pgn ──(Actions: build-book.yml → python -m chesslab.cli build-book)──▶ frontend/public/book.json ─┐
                                                                                                          ├─▶ pages.yml ──▶ GitHub Pages
GitHub Issue "Game review" ──(Actions: review.yml → review-game + Stockfish)──▶ frontend/public/reviews/ ─┘
```

### Adding openings to the book

Commit `.pgn` files under `book/` (one or many games per file, up to 24 plies each are used). On push to `main`, **Build opening book** regenerates `book.json` and commits it. Opening a pull request is the review gate — there is no admin upload.

### Reviewing a game

1. On the site, go to **Review**, paste a PGN, click **Request review on GitHub**. That opens a pre-filled issue using the *Game review* form (or open one yourself: New issue → Game review).
2. The **Review game** workflow installs Stockfish, analyzes the game (depth 14, MultiPV 3, ≤160 plies, ~1 s/move), writes `frontend/public/reviews/issue-<n>.json`, updates `reviews/index.json`, comments a summary on the issue, and closes it.
3. **Deploy to GitHub Pages** runs after it and the review appears at `#/review/issue-<n>`.

Reviews are public (they live in the repository). You can also run **Review game** from the Actions tab with a pasted PGN (`workflow_dispatch`), or run the analysis locally and load the JSON on the Review page.

## Run locally

Requirements: Node.js 22, Python 3.10+, and Stockfish (only for game reviews and the engine tests).

macOS (Homebrew):

```bash
brew install node@22 stockfish
```

Ubuntu / Debian:

```bash
sudo apt-get install -y stockfish
```

Frontend:

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173/
npm run build      # typecheck + production build (uses base /Chess-Trainer/)
npm run preview    # serve the build at http://localhost:4173/Chess-Trainer/
npm run lint       # oxlint
```

Backend, in a virtual environment (Homebrew and Debian Pythons refuse `pip install` outside one):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e "backend[dev]"
python -m chesslab.cli build-book                       # book/*.pgn -> frontend/public/book.json
python -m chesslab.cli review-game --pgn-file game.pgn  # -> frontend/public/reviews/<id>.json
```

Stockfish is found on `PATH`, or set `STOCKFISH_PATH=/path/to/stockfish`.

## Testing

### Locally (what CI runs)

```bash
source .venv/bin/activate
python -m chesslab.cli build-book --check   # fails if book.json is stale
pytest -q backend                           # engine tests skip when Stockfish is missing
cd frontend && npm run lint && npm run build
```

To try a review end to end without GitHub, run the analysis into a scratch folder and load the JSON on the Review page (**Review JSON** file input):

```bash
python -m chesslab.cli review-game --pgn-file game.pgn --id local-1 --out-dir /tmp/reviews --depth 12
```

Or drop the output into `frontend/dist/reviews/` after `npm run build` and open `npm run preview` at `/Chess-Trainer/#/review/local-1`.

### On GitHub

1. **Pull request** → the **CI** workflow runs pytest, the book freshness check, frontend lint + build, and gitleaks. Nothing deploys.
2. **Merge to `main`** → **Deploy to GitHub Pages** publishes the site. **Build opening book** runs too if `book/` changed.
3. **Review a game** → open a *Game review* issue (or use the site's **Request review on GitHub** button). Within a few minutes the **Review game** workflow comments a summary, closes the issue, and Pages redeploys with the review at `#/review/issue-<n>`. You can also start it from the Actions tab with **Run workflow** and a pasted PGN; that result lands at `#/review/run-<run id>`.

If a workflow fails, the Actions tab has the log; a failed review also leaves a comment on the issue and can be retried by editing the issue.

## GitHub setup (once)

1. **Settings → Pages → Build and deployment → Source: GitHub Actions**
2. **Settings → Actions → General → Workflow permissions: Read and write** (needed for the bot commits in `build-book.yml` / `review.yml`)
3. Push to `main`. Workflows:
   - [`ci.yml`](.github/workflows/ci.yml) — pytest, book freshness, frontend lint + build, secret scan (gitleaks)
   - [`pages.yml`](.github/workflows/pages.yml) — build + deploy the site
   - [`build-book.yml`](.github/workflows/build-book.yml) — regenerate `book.json` when `book/` changes
   - [`review.yml`](.github/workflows/review.yml) — Stockfish review from an issue or manual run

The Pages build derives the base path from the repository name, so forks work unchanged. `VITE_REPO_URL` (set automatically in `pages.yml`) tells the site which repository to open review issues in.

### Secrets policy

- No repository secrets are used or needed. Each workflow declares the minimum `permissions:` it requires.
- User input (issue bodies, dispatch inputs) is passed to scripts through environment variables and files, never interpolated into shell commands.
- `gitleaks` runs in CI over the full history; `.gitleaks.toml` allowlists only chess data files.
- `.gitignore` excludes `.env*` (except `.env.example`). Don't add credentials to the repo — nothing here needs them.

## Layout

```
backend/chesslab/   book.py (PGN -> book), engine.py (Stockfish, classification), review.py, cli.py
backend/tests/      pytest (Stockfish tests skip if the binary is missing)
book/               PGN sources for the opening book
frontend/           React app; public/book.json and public/reviews/ are generated
.github/            workflows + the "Game review" issue form
```

## License

MIT. See [LICENSE](LICENSE).
