

### Backend (Python/FastAPI)

```bash
cd agent

# Install dependencies (using UV)
uv pip install -e .

# Start FastAPI server (with auto-reload)
dawei server start --reload

# Alternative: Using python -m (if dawei command is not found)
python -m dawei.cli.dawei server start --reload

# Start with custom host and port
dawei server start --host 0.0.0.0 --port 8465

# Check server status
dawei server status

# Stop the server
dawei server stop

# Run TUI (Text User Interface)
dawei tui --workspace ./my-workspace

# Run agent directly
dawei agent run ./my-workspace "Create hello world"

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