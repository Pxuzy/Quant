# Ponytail - Lazy Senior Dev Mode
# Quant Project Rules

## Core Principle
The best code is the code you never wrote.

## Decision Ladder (before writing any code)
1. Does this need to exist? -> No: skip (YAGNI)
2. Stdlib has it? -> use stdlib
3. Native platform feature? -> use native
4. Installed dependency? -> use it
5. One line? -> one line
6. Only then: minimum that works

## Quant-Specific Rules
- Parquet > CSV
- DuckDB > Pandas full load
- Functions > Classes (when possible)
- dict > dataclass (unless type checking needed)
- FastAPI default HTTPException > custom error handlers
- AntD components > custom components
- CSS animations > JS animations
- useState/useContext > Redux/Zustand (unless truly needed)
- Tests before code (TDD)
- One test file < 500 lines

## Forbidden
- "Might need later" code
- Comments explaining bad code -> rewrite the code instead
- Nested depth > 3
- Functions > 50 lines (unless data transformation)
- New dependencies without checking stdlib/existing deps first
