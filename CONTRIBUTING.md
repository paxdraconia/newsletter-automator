# Contributing

Thanks for your interest in contributing! This guide will help you get set up.

## Prerequisites

- Python 3.10+
- A Google Cloud service account (see README.md for setup)
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)

## Development Setup

1. **Clone the repo** and install dependencies:
   ```bash
   git clone https://github.com/paxdraconia/newsletter-automator.git
   cd newsletter-automator
   pip install -r requirements.txt
   ```

2. **Configure credentials** — copy the template and fill in your values:
   ```bash
   cp .env.template .env
   ```

3. **Set up Google Sheets** — follow Steps 2-3 in the README.

4. **Run locally:**
   ```bash
   streamlit run app.py
   ```

## Code Conventions

This project is beginner-friendly. Here's how the code is organized:

| File | Responsibility |
|---|---|
| `app.py` | Streamlit UI — page rendering, user interaction |
| `sheets.py` | Data layer — all Google Sheets CRUD operations |
| `gemini.py` | AI layer — all Gemini API interactions |
| `config.py` | Authentication — credential loading for local + cloud |
| `constants.py` | Shared constants — magic strings, session keys, defaults |

**Patterns to follow:**
- UI helper functions in `app.py` are prefixed with `_render_` (private helpers)
- All session state keys are defined in `constants.py` as `SK_` constants
- Section names use `SECTION_` constants from `constants.py`
- Google Sheets operations go in `sheets.py`, never in `app.py`
- Gemini calls go through `_call_gemini()` in `gemini.py`

## Starter Books

The `starter_books.json` file is gitignored (personal data). If you want to test the import feature, create your own from `starter_books.json.template`.

## Submitting Changes

1. Fork the repository
2. Create a feature branch: `git checkout -b my-feature`
3. Make your changes and test locally
4. Commit with a descriptive message
5. Push and open a Pull Request against `master`

## Questions?

Open an issue on GitHub — happy to help!
