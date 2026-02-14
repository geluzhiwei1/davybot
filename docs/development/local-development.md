

### Backend (Python/FastAPI)

```bash
cd agent

# Install dependencies (using UV)
uv pip install -e . -i https://mirrors.aliyun.com/pypi/simple/

# Run development server (auto-reload)
uv run python -m dawei.server
# Or directly with uvicorn
uv run uvicorn dawei.server:app --host 0.0.0.0 --port 8465 --reload

# Run TUI (Text User Interface)
dawei tui --workspace ./my-workspace    # Start TUI
dawei agent run ./my-workspace "msg"   # Run agent directly
dawei server start                     # Start FastAPI server
dawei server status                     # Check server status

# Run tests
pytest                              # Run all tests
pytest tests/ -v                    # Run all tests with verbose output
pytest tests/test_real_workspace_persistence.py -v  # Run specific test

# Run tests with specific markers
pytest -m unit                    # Unit tests only
pytest -m integration             # Integration tests only
pytest -m "not slow"              # Exclude slow tests
pytest -m agent                   # Agent-specific tests

# Run with coverage
pytest --cov=dawei --cov-report=html --cov-report=term
```

The backend runs on **port 8465** by default.


### Frontend (Vue 3/TypeScript)

```bash
cd webui

# Install dependencies
pnpm install

# Run development server
pnpm dev

# Production build
pnpm build

# Type checking
pnpm type-check

# Linting
pnpm lint

# Format code
pnpm format

# Unit/Component Testing (Vitest)
pnpm test                          # Run unit tests
pnpm test:watch                    # Watch mode
pnpm test:ui                       # Run with UI
pnpm test:coverage                 # Run with coverage report

# E2E Testing (Playwright)
pnpm test:e2e                      # Run E2E tests
pnpm test:e2e:ui                   # Run with UI
pnpm test:e2e:debug                # Run in debug mode
pnpm test:e2e:headed               # Run with headed browser
pnpm test:e2e:install              # Install Playwright browsers
pnpm test:e2e:report               # Show Playwright test report

# Run all tests
pnpm test:all                      # Run both Vitest and Playwright
```