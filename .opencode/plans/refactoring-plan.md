# Ledger Repository Refactoring Plan

**Generated:** 2026-03-15  
**Status:** Ready for Review  
**Execution Mode:** Wave-based with TDD approach

---

## Executive Summary

### Goals
1. **Improve Maintainability** - Reduce file sizes, extract shared patterns, eliminate duplication
2. **Enhance Code Quality** - Apply 2026 best practices for FastAPI and React 19
3. **Reduce Technical Debt** - Remove unused dependencies, dead code, and cache artifacts
4. **Strengthen Architecture** - Implement feature-based organization and generic patterns
5. **Increase Test Coverage** - Add unit tests for refactored components and services

### Success Metrics
- Backend: Largest service file reduced from 483 to <300 lines
- Frontend: API client split into domain modules, largest file reduced from 815 to <400 lines
- Test coverage: Add 15+ new unit tests for refactored code
- Dependencies: Remove 4 unused frontend packages
- Cache cleanup: Remove ~600KB of generated artifacts
- CI: All quality gates pass after each wave

### Scope
- **In Scope:** Backend services, frontend API client, forms, shared utilities, test coverage
- **Out of Scope:** Database schema changes, API contract changes, new features, authentication

### Timeline Estimate
- Wave 0 (Cleanup): 30 minutes
- Wave 1 (Backend Foundation): 2-3 hours
- Wave 2 (Frontend Foundation): 2-3 hours
- Wave 3 (Backend Services): 3-4 hours
- Wave 4 (Frontend Components): 2-3 hours
- Wave 5 (Testing): 2-3 hours
- **Total:** 12-16 hours

---

## Wave 0: Cleanup and Preparation

**Goal:** Remove cache artifacts, unused dependencies, and prepare for refactoring  
**Risk:** Low  
**Dependencies:** None  
**Verification:** CI passes, no functional changes

### Tasks (Parallel Execution)

#### Task 0.1: Remove Cache Artifacts
**Category:** quick  
**Files:**
- `.ruff_cache/`
- `backend/.ruff_cache/`
- `backend/.pytest_cache/`
- `backend/ledger_backend.egg-info/`
- All `__pycache__/` directories
- `.DS_Store` files

**Commands:**
```bash
find . -type d -name "__pycache__" -exec rm -rf {} +
find . -type d -name ".pytest_cache" -exec rm -rf {} +
find . -type d -name ".ruff_cache" -exec rm -rf {} +
find . -type d -name "*.egg-info" -exec rm -rf {} +
find . -name ".DS_Store" -delete
```

**Verification:**
```bash
git status  # Should show deletions only
```

**Commit:** `chore: remove cache artifacts and generated files`

---

#### Task 0.2: Remove Unused Frontend Dependencies
**Category:** quick  
**Files:**
- `frontend/package.json`

**Changes:**
Remove these unused dependencies:
- `tw-animate-css` (0 usage)
- `embla-carousel-react` (0 usage)
- `input-otp` (0 usage)
- `vaul` (0 usage)

**Commands:**
```bash
cd frontend
pnpm remove tw-animate-css embla-carousel-react input-otp vaul
pnpm install
```

**Verification:**
```bash
cd frontend
pnpm lint
pnpm typecheck
pnpm build
```

**Commit:** `chore(frontend): remove unused dependencies`

---

#### Task 0.3: Add .gitignore Entries
**Category:** quick  
**Files:**
- `.gitignore`
- `backend/.gitignore`

**Changes:**
Ensure these patterns are ignored:
```
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/
*.egg-info/
.DS_Store
```

**Verification:**
```bash
git status  # Should not show cache files
```

**Commit:** `chore: improve .gitignore for cache artifacts`

---

## Wave 1: Backend Foundation Refactoring

**Goal:** Establish base patterns and reduce repository boilerplate  
**Risk:** Medium  
**Dependencies:** Wave 0 complete  
**Verification:** All backend tests pass

### Tasks (Sequential Execution)

#### Task 1.1: Create Generic Base Repository
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `backend/app/repositories/base.py` (NEW)
- All 14 repository files in `backend/app/repositories/`

**Implementation:**
1. Create `BaseRepository[ModelType]` with generic CRUD methods:
   - `__init__(self, session: Session)`
   - `add(self, entity: ModelType) -> ModelType`
   - `get(self, id: Any) -> ModelType | None`
   - `list_all(self) -> list[ModelType]`
   - `delete(self, entity: ModelType) -> None`

2. Update all 14 repositories to inherit from `BaseRepository`:
   - `PortfolioRepository`
   - `BalanceRepository`
   - `PositionRepository`
   - `TradeRepository`
   - `LlmConfigRepository`
   - `PromptTemplateRepository`
   - `SnippetRepository`
   - `ConversationRepository`
   - `RunRepository`
   - `RequestRepository`
   - `ResponseRepository`
   - `VersionRepository`
   - `SettingsRepository`
   - `QuoteRepository`

3. Keep domain-specific query methods (e.g., `list_for_portfolio()`)

**Expected Reduction:** ~200 lines of boilerplate code

**Verification:**
```bash
cd backend
pytest tests/test_api.py -v
mypy app
```

**Commit:** `refactor(backend): add generic base repository pattern`

---

#### Task 1.2: Extract Stock Analysis Schema Definitions
**Category:** visual-engineering  
**Skills:** None  
**Files:**
- `backend/app/services/stock_analysis/parser.py` (310 lines → ~150 lines)
- `backend/app/services/stock_analysis/schemas.py` (NEW, ~160 lines)

**Implementation:**
1. Create `schemas.py` with:
   - `FRESH_ANALYSIS_SCHEMA`
   - `COMPARE_DECIDE_REFLECT_SCHEMA`
   - Helper functions for schema validation

2. Update `parser.py` to import from `schemas.py`

3. Keep parsing logic in `parser.py`

**Verification:**
```bash
cd backend
pytest tests/test_stock_analysis_schema.py -v
pytest tests/test_openai_responses_service.py -v
mypy app
```

**Commit:** `refactor(backend): extract stock analysis schemas to separate module`

---

#### Task 1.3: Split Stock Analysis Context Service
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `backend/app/services/stock_analysis/context.py` (483 lines → ~200 lines)
- `backend/app/services/stock_analysis/placeholder_discovery.py` (NEW, ~100 lines)
- `backend/app/services/stock_analysis/context_enricher.py` (NEW, ~150 lines)

**Implementation:**
1. Extract `PlaceholderDiscoveryService` to `placeholder_discovery.py`
   - Keep all placeholder discovery logic
   - No dependencies on market data

2. Extract context enrichment logic to `context_enricher.py`
   - Quote/history enrichment
   - Market data integration
   - Warning aggregation

3. Keep `AnalysisContextService` in `context.py` as orchestrator
   - Compose placeholder discovery + enrichment
   - Template rendering

**Verification:**
```bash
cd backend
pytest tests/test_stock_analysis.py -v
mypy app
```

**Commit:** `refactor(backend): split stock analysis context service into focused modules`

---

## Wave 2: Frontend Foundation Refactoring

**Goal:** Split large API client and establish domain-based organization  
**Risk:** Medium  
**Dependencies:** Wave 0 complete  
**Verification:** All frontend tests pass

### Tasks (Sequential Execution)

#### Task 2.1: Split API Client into Domain Modules
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `frontend/src/lib/api.ts` (815 lines → ~150 lines core)
- `frontend/src/lib/api/core.ts` (NEW, ~100 lines)
- `frontend/src/lib/api/portfolios.ts` (NEW, ~120 lines)
- `frontend/src/lib/api/stock-analysis.ts` (NEW, ~200 lines)
- `frontend/src/lib/api/market-data.ts` (NEW, ~80 lines)
- `frontend/src/lib/api/llm-resources.ts` (NEW, ~150 lines)
- `frontend/src/lib/api/index.ts` (NEW, re-exports)

**Implementation:**
1. Create `api/core.ts`:
   - `request()` function
   - `ApiRequestError` class
   - Base URL configuration

2. Create domain modules:
   - `portfolios.ts`: Portfolio, Balance, Position, Trade endpoints
   - `stock-analysis.ts`: Settings, Conversations, Runs, Responses, Versions
   - `market-data.ts`: Quotes, History endpoints
   - `llm-resources.ts`: LLM Configs, Prompt Templates, Snippets

3. Create `index.ts` that re-exports all domain functions

4. Update all imports in hooks and components

**Expected Reduction:** Main file from 815 to ~150 lines

**Verification:**
```bash
cd frontend
pnpm typecheck
pnpm lint
pnpm test:run
```

**Commit:** `refactor(frontend): split API client into domain modules`

---

#### Task 2.2: Split API Types into Domain Modules
**Category:** visual-engineering  
**Skills:** None  
**Files:**
- `frontend/src/lib/api-types.ts` (550 lines → ~100 lines shared)
- `frontend/src/lib/types/portfolios.ts` (NEW, ~120 lines)
- `frontend/src/lib/types/stock-analysis.ts` (NEW, ~150 lines)
- `frontend/src/lib/types/market-data.ts` (NEW, ~60 lines)
- `frontend/src/lib/types/llm-resources.ts` (NEW, ~120 lines)
- `frontend/src/lib/types/index.ts` (NEW, re-exports)

**Implementation:**
1. Create `types/` directory with domain-specific type files

2. Keep shared types in `api-types.ts`:
   - `ApiError`
   - `PaginatedResponse`
   - Common utility types

3. Move domain types to respective files

4. Update all imports

**Verification:**
```bash
cd frontend
pnpm typecheck
```

**Commit:** `refactor(frontend): organize API types by domain`

---

#### Task 2.3: Extract Form Composition Hook
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `frontend/src/hooks/use-form-defaults.ts` (NEW, ~50 lines)
- `frontend/src/components/forms/llm-config-form.tsx`
- `frontend/src/components/forms/prompt-template-form.tsx`
- `frontend/src/components/forms/snippet-form.tsx`
- `frontend/src/components/portfolios/portfolio-form.tsx`

**Implementation:**
1. Create `useFormDefaults<T>(initial: T, schema: ZodSchema<T>)` hook:
   - Returns form instance with proper defaults
   - Handles reset on initial value change
   - Integrates zodResolver

2. Refactor 4+ forms to use the hook

**Expected Reduction:** ~80 lines across forms

**Verification:**
```bash
cd frontend
pnpm typecheck
pnpm test:run
```

**Commit:** `refactor(frontend): extract form composition hook`

---

## Wave 3: Backend Service Layer Improvements

**Goal:** Simplify complex services and extract validators  
**Risk:** Medium-High  
**Dependencies:** Wave 1 complete  
**Verification:** All backend tests pass

### Tasks (Sequential Execution)

#### Task 3.1: Extract Prompt Template Validator
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `backend/app/services/prompt_template_service.py` (266 lines → ~180 lines)
- `backend/app/services/validators/prompt_template_validator.py` (NEW, ~100 lines)

**Implementation:**
1. Create `validators/` directory

2. Extract validation logic:
   - Mode validation
   - Payload validation
   - Field change detection

3. Keep CRUD orchestration in service

**Verification:**
```bash
cd backend
pytest tests/test_api.py::test_prompt_templates -v
mypy app
```

**Commit:** `refactor(backend): extract prompt template validator`

---

#### Task 3.2: Extract CSV Parser Utility
**Category:** visual-engineering  
**Skills:** None  
**Files:**
- `backend/app/services/csv_import_service.py` (260 lines → ~150 lines)
- `backend/app/core/csv_parser.py` (NEW, ~120 lines)

**Implementation:**
1. Create `csv_parser.py` with:
   - `ParsedCsvRow` dataclass
   - CSV parsing logic
   - File validation

2. Keep preview/commit orchestration in service

**Verification:**
```bash
cd backend
pytest tests/test_api.py::test_csv_import -v
mypy app
```

**Commit:** `refactor(backend): extract CSV parser utility`

---

#### Task 3.3: Refactor Trading Operation Service with Strategy Pattern
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `backend/app/services/trading_operation_service.py` (234 lines → ~120 lines)
- `backend/app/services/trading_operations/base.py` (NEW, ~40 lines)
- `backend/app/services/trading_operations/buy_handler.py` (NEW, ~50 lines)
- `backend/app/services/trading_operations/sell_handler.py` (NEW, ~50 lines)
- `backend/app/services/trading_operations/dividend_handler.py` (NEW, ~40 lines)
- `backend/app/services/trading_operations/split_handler.py` (NEW, ~40 lines)

**Implementation:**
1. Create `trading_operations/` directory

2. Define `BaseOperationHandler` abstract class:
   - `execute(portfolio, payload, session) -> Trade`
   - Common validation logic

3. Create handler classes for each operation type

4. Update service to use strategy pattern

**Expected Reduction:** Main service from 234 to ~120 lines

**Verification:**
```bash
cd backend
pytest tests/test_api.py::test_trading_operations -v
mypy app
```

**Commit:** `refactor(backend): apply strategy pattern to trading operations`

---

## Wave 4: Frontend Component Improvements

**Goal:** Extract shared form patterns and reduce component complexity  
**Risk:** Medium  
**Dependencies:** Wave 2 complete  
**Verification:** All frontend tests pass

### Tasks (Sequential Execution)

#### Task 4.1: Create FormDialog Wrapper Component
**Category:** visual-engineering  
**Skills:** None  
**Files:**
- `frontend/src/components/shared/form-dialog.tsx` (NEW, ~80 lines)
- `frontend/src/components/portfolios/balance-dialog.tsx`
- `frontend/src/components/portfolios/position-dialog.tsx`
- `frontend/src/components/portfolios/trading-operation-dialog.tsx`

**Implementation:**
1. Create `FormDialog` component:
   - Wraps Dialog + Form submission
   - Handles open/close state
   - Standard layout (header, content, footer)

2. Refactor 3 portfolio dialogs to use wrapper

**Expected Reduction:** ~60 lines across dialogs

**Verification:**
```bash
cd frontend
pnpm typecheck
pnpm test:run
```

**Commit:** `refactor(frontend): create FormDialog wrapper component`

---

#### Task 4.2: Extract Run Builder Form Sections
**Category:** visual-engineering  
**Skills:** None  
**Files:**
- `frontend/src/components/stock-analysis/run-builder-form.tsx` (546 lines → ~250 lines)
- `frontend/src/components/stock-analysis/run-builder-mode-section.tsx` (NEW, ~100 lines)
- `frontend/src/components/stock-analysis/run-builder-config-section.tsx` (NEW, ~120 lines)
- `frontend/src/components/stock-analysis/run-builder-context-section.tsx` (NEW, ~100 lines)

**Implementation:**
1. Extract mode selection to `run-builder-mode-section.tsx`

2. Extract config selection to `run-builder-config-section.tsx`

3. Extract context inputs to `run-builder-context-section.tsx`

4. Keep form orchestration in main component

**Expected Reduction:** Main component from 546 to ~250 lines

**Verification:**
```bash
cd frontend
pnpm typecheck
pnpm test:run
```

**Commit:** `refactor(frontend): extract run builder form sections`

---

#### Task 4.3: Extract Prompt Template Form Sections
**Category:** visual-engineering  
**Skills:** None  
**Files:**
- `frontend/src/components/forms/prompt-template-form.tsx` (365 lines → ~200 lines)
- `frontend/src/components/forms/prompt-template-editor-section.tsx` (NEW, ~100 lines)
- `frontend/src/components/forms/prompt-template-reference-section.tsx` (NEW, ~80 lines)

**Implementation:**
1. Extract template editor to separate component

2. Extract placeholder reference guide to separate component

3. Keep form orchestration in main component

**Expected Reduction:** Main component from 365 to ~200 lines

**Verification:**
```bash
cd frontend
pnpm typecheck
pnpm test:run
```

**Commit:** `refactor(frontend): extract prompt template form sections`

---

## Wave 5: Testing and Documentation

**Goal:** Add unit tests for refactored code and update documentation  
**Risk:** Low  
**Dependencies:** Waves 1-4 complete  
**Verification:** All tests pass, coverage increases

### Tasks (Parallel Execution)

#### Task 5.1: Add Backend Repository Tests
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `backend/tests/test_repositories.py` (NEW, ~200 lines)

**Implementation:**
1. Test `BaseRepository` generic methods

2. Test domain-specific repository methods

3. Test error handling

**Verification:**
```bash
cd backend
pytest tests/test_repositories.py -v --cov=app/repositories
```

**Commit:** `test(backend): add repository layer unit tests`

---

#### Task 5.2: Add Backend Service Tests
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `backend/tests/test_prompt_template_validator.py` (NEW, ~100 lines)
- `backend/tests/test_csv_parser.py` (NEW, ~100 lines)
- `backend/tests/test_trading_operation_handlers.py` (NEW, ~150 lines)

**Implementation:**
1. Test prompt template validator logic

2. Test CSV parser edge cases

3. Test trading operation handlers in isolation

**Verification:**
```bash
cd backend
pytest tests/test_*.py -v --cov=app/services
```

**Commit:** `test(backend): add service layer unit tests`

---

#### Task 5.3: Add Frontend Page Tests
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `frontend/src/pages/responses.test.tsx` (NEW, ~100 lines)
- `frontend/src/pages/stock-analysis/run-builder.test.tsx` (NEW, ~100 lines)
- `frontend/src/pages/dashboard.test.tsx` (NEW, ~80 lines)

**Implementation:**
1. Test page rendering with mock data

2. Test filter interactions

3. Test navigation flows

**Verification:**
```bash
cd frontend
pnpm test:run
```

**Commit:** `test(frontend): add page component unit tests`

---

#### Task 5.4: Add Frontend Hook Tests
**Category:** ultrabrain  
**Skills:** None  
**Files:**
- `frontend/src/hooks/use-form-defaults.test.ts` (NEW, ~80 lines)

**Implementation:**
1. Test hook initialization

2. Test reset behavior

3. Test schema integration

**Verification:**
```bash
cd frontend
pnpm test:run
```

**Commit:** `test(frontend): add custom hook unit tests`

---

#### Task 5.5: Update AGENTS.md Documentation
**Category:** quick  
**Skills:** None  
**Files:**
- `backend/app/repositories/AGENTS.md`
- `backend/app/services/AGENTS.md`
- `backend/app/services/stock_analysis/AGENTS.md`
- `frontend/src/lib/AGENTS.md`
- `frontend/src/hooks/AGENTS.md`
- `frontend/src/components/AGENTS.md`

**Implementation:**
1. Document new base repository pattern

2. Document API client domain organization

3. Document new service structure

4. Update file references and line counts

**Verification:**
```bash
grep -r "AGENTS.md" . | wc -l  # Should match before
```

**Commit:** `docs: update AGENTS.md for refactored structure`

---

## Risk Assessment

### High-Risk Areas
1. **Trading Operation Refactoring (Task 3.3)**
   - Complex business logic with financial implications
   - Mitigation: Extensive test coverage, careful validation
   - Rollback: Revert single commit

2. **API Client Split (Task 2.1)**
   - Many import updates across codebase
   - Mitigation: TypeScript will catch broken imports
   - Rollback: Revert single commit

### Medium-Risk Areas
1. **Base Repository Pattern (Task 1.1)**
   - Changes all repository classes
   - Mitigation: Existing test suite validates behavior
   - Rollback: Revert single commit

2. **Context Service Split (Task 1.3)**
   - Complex orchestration logic
   - Mitigation: Existing stock analysis tests
   - Rollback: Revert single commit

### Low-Risk Areas
1. **Cleanup Tasks (Wave 0)**
   - No functional changes
   - Easy rollback

2. **Documentation Updates (Task 5.5)**
   - No code changes
   - Easy rollback

---

## Rollback Strategy

### Per-Wave Rollback
Each wave is a logical unit with atomic commits. If issues arise:

1. **Identify failing wave**
   ```bash
   git log --oneline --grep="refactor\|test\|chore"
   ```

2. **Revert wave commits**
   ```bash
   git revert <commit-range> --no-commit
   git commit -m "revert: rollback Wave X due to <reason>"
   ```

3. **Verify CI passes**
   ```bash
   .github/workflows/ci.yml
   ```

### Per-Task Rollback
Each task is a single atomic commit. To rollback a specific task:

```bash
git revert <commit-hash>
```

### Emergency Rollback
If multiple waves need rollback:

```bash
git reset --hard <commit-before-refactoring>
git push --force-with-lease
```

**Note:** Only use force-push if working on a feature branch.

---

## Atomic Commit Strategy

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `refactor`: Code restructuring without behavior change
- `test`: Adding or updating tests
- `chore`: Maintenance tasks (cleanup, dependencies)
- `docs`: Documentation updates

**Scopes:**
- `backend`: Backend changes
- `frontend`: Frontend changes
- `ci`: CI/CD changes

### Example Commits

**Wave 0:**
```
chore: remove cache artifacts and generated files
chore(frontend): remove unused dependencies
chore: improve .gitignore for cache artifacts
```

**Wave 1:**
```
refactor(backend): add generic base repository pattern
refactor(backend): extract stock analysis schemas to separate module
refactor(backend): split stock analysis context service into focused modules
```

**Wave 2:**
```
refactor(frontend): split API client into domain modules
refactor(frontend): organize API types by domain
refactor(frontend): extract form composition hook
```

**Wave 3:**
```
refactor(backend): extract prompt template validator
refactor(backend): extract CSV parser utility
refactor(backend): apply strategy pattern to trading operations
```

**Wave 4:**
```
refactor(frontend): create FormDialog wrapper component
refactor(frontend): extract run builder form sections
refactor(frontend): extract prompt template form sections
```

**Wave 5:**
```
test(backend): add repository layer unit tests
test(backend): add service layer unit tests
test(frontend): add page component unit tests
test(frontend): add custom hook unit tests
docs: update AGENTS.md for refactored structure
```

---

## Verification Checklist

After each wave, verify:

- [ ] All tests pass locally
  ```bash
  cd backend && pytest
  cd frontend && pnpm test:run
  ```

- [ ] Type checking passes
  ```bash
  cd backend && mypy app
  cd frontend && pnpm typecheck
  ```

- [ ] Linting passes
  ```bash
  cd backend && ruff check app tests
  cd frontend && pnpm lint
  ```

- [ ] CI pipeline passes
  ```bash
  # Push to feature branch and check GitHub Actions
  ```

- [ ] No functional regressions
  ```bash
  cd frontend && pnpm test:e2e
  ```

- [ ] Git history is clean
  ```bash
  git log --oneline -10
  ```

---

## Post-Refactoring Metrics

### Expected Improvements

**Backend:**
- Largest file: 483 → ~200 lines (58% reduction)
- Repository boilerplate: -200 lines
- Service complexity: 3 services split into focused modules
- Test coverage: +450 lines of new tests

**Frontend:**
- Largest file: 815 → ~150 lines (82% reduction)
- API client: Split into 5 domain modules
- Form boilerplate: -80 lines
- Component complexity: 3 large components split
- Test coverage: +360 lines of new tests
- Dependencies: -4 unused packages

**Overall:**
- Total lines removed: ~800 (boilerplate + duplication)
- Total lines added: ~1200 (new structure + tests)
- Net change: +400 lines (better organized, more tested)
- File count: +25 new files (better separation of concerns)

---

## Next Steps

1. **Review this plan** with the team
2. **Create feature branch** for refactoring work
3. **Execute Wave 0** (cleanup, low risk)
4. **Execute Waves 1-2** (foundation, parallel if possible)
5. **Execute Waves 3-4** (services and components)
6. **Execute Wave 5** (testing and documentation)
7. **Final review** and merge to main

---

## Questions for Review

Before starting execution, please confirm:

1. **Scope Agreement:** Are all identified refactoring targets in scope?
2. **Timeline:** Is the 12-16 hour estimate acceptable?
3. **Risk Tolerance:** Are you comfortable with the medium-risk tasks?
4. **Testing Strategy:** Should we add more test coverage beyond what's planned?
5. **Documentation:** Are the AGENTS.md updates sufficient?
6. **Commit Strategy:** Is the atomic commit approach acceptable?
7. **Rollback Plan:** Is the rollback strategy clear and acceptable?

---

**Plan Status:** ✅ Ready for Execution  
**Last Updated:** 2026-03-15  
**Estimated Duration:** 12-16 hours  
**Risk Level:** Medium (with mitigation strategies)
