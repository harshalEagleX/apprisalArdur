<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
|------|----------|
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Database Schema Policy

- Do not add or re-enable Flyway, Liquibase, Alembic for Java, or any other third-party Java migration runner.
- Java (backend) and SHALqc (Python) share ONE Postgres database (`shal_qc`). Their table names are disjoint, so both coexist without collision. (The legacy `ocr-service` and its separate DB were retired.)
- Java-owned tables are managed by JPA/Hibernate (`spring.jpa.hibernate.ddl-auto=update`) plus manual database work when needed.
- Python-owned tables (orders/runs/findings/item_verdicts/llm_interactions/corrections/config_audit) are created JPA-style via SQLAlchemy `Base.metadata.create_all` on first DB connection (`shalqc/app/persistence/repo.py`) — there is no `manage_db.py`. To wipe & recreate everything for a clean run: `psql "$SHAL_QC_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"`, then start Java (recreates its tables) and SHALqc (recreates its tables on first use).
- Keep comments, scripts, and docs aligned with this policy whenever database behavior changes.
