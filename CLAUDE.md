# VSTEP Study App — Claude Context

## Project Overview
Pure HTML/CSS/JS VSTEP study app. No build tools. App lives in `app/` subfolder.
Root `index.html` redirects to `app/index.html` for GitHub Pages.

## Key Files
- `build_data.py` — Python 3.9, parses MD files → JS data files in `app/data/`
- `app/test.html` — Full practice tests (Listening, Reading, Writing, Speaking)
- `app/study.html` — Study tabs: Vocabulary, Phrases, Speaking Tests, Essay Bank, etc.
- `app/index.html` — Landing/home page
- `app/data/` — Generated JS data files (do not edit manually)
- `md_output/` — Markdown source files parsed by build_data.py

## Python Rules
- Runtime is Python 3.9 — do NOT use `dict | None` union syntax (Python 3.10+)
- Use `Optional[dict]` from `typing` or just omit the return type annotation

## Data Files (app/data/)
| File | Source | Content |
|------|--------|---------|
| `tests.js` | 7 test MDs + collection | Tests 1–12 (284KB) |
| `answers.js` | key.md | Answer keys |
| `tapescripts.js` | test MDs | Listening tapescripts |
| `writing_samples.js` | writing MD | Writing model answers |
| `speaking_samples.js` | speaking MD | Speaking model answers (Tests 1–7) |
| `speaking_tests.js` | speaking_30 MD | 28 speaking practice tests |
| `speaking_topic_answers.js` | speaking_topics MD | 13 topic Q&A banks |
| `extra_essays.js` | essays_30 MD | 30 B1/B2 writing essays |

## Reading Section (test.html) Layout
Stacked full-width layout (NOT side-by-side):
1. Sticky question navigator bar
2. Full-width passage block
3. Full-width question/answer block

Key CSS: `width: 100%; box-sizing: border-box` overrides global `max-width: 800px` on `.question-area`.
Answer options use CSS grid `grid-template-columns: 1fr 1fr` for 2-column display.

## Passage Text Rendering
PDF word-wrap artifacts: single `\n` = line-wrap (join with space), `\n\n` = real paragraph.
Fix in `renderPassage()`:
```javascript
item.passage.text
  .replace(/\n\n+/g, '</p><p>')  // real paragraph breaks
  .replace(/\n/g, ' ')           // join PDF word-wrap lines
```

## Deployment
- GitHub Pages: `https://tilo2402.github.io/aptis-study-app/`
- Branch: `main`, served from root `/`
- After push, wait ~1 min then hard-refresh (`Cmd+Shift+R`)

## OCR / Parser Notes
- Speaking test number OCR artifacts: `1ó` → 16, lone `1\n` → 17 (pre-process with regex)
- Part III topic regex: 2-step — find header line first, then search `^Topic:` in subsequent text
- Malformed topic filter: skip if `len(words) > 5` or any word > 20 chars
- `cleanPrompt()` JS function strips "You should spend 40 minutes..." prefix from essay prompts
