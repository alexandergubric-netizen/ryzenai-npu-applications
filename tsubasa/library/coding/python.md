# Python quick reference (Python 3.12+)

## Running and environments
- Run a script: `python "C:\path\app.py"`. Windows launcher: `py -3.12 app.py`.
- Virtual environment: `python -m venv .venv`, then activate in PowerShell with `.venv\Scripts\Activate.ps1`; deactivate with `deactivate`.
- Install packages inside the venv: `python -m pip install requests`. Freeze: `python -m pip freeze > requirements.txt`. Restore: `python -m pip install -r requirements.txt`.
- Run a module: `python -m http.server 8000`, `python -m json.tool data.json`, `python -m pytest -q`.

## Core syntax
- f-strings: `f"{name!r} has {count:,} items, {ratio:.1%}"`.
- Comprehensions: `[x*x for x in nums if x > 0]`, `{k: v for k, v in pairs}`, `{x for x in items}`.
- Unpacking: `first, *rest = items`; swap `a, b = b, a`; `dict | other` merges dicts.
- `match` statement (3.10+): `match cmd: case "quit": ... case ["go", direction]: ... case _: ...`.
- Walrus: `while (line := f.readline()):`.
- Type hints: `def total(prices: list[float], tax: float = 0.2) -> float:`; optional: `str | None`.
- Dataclasses: `@dataclass(frozen=True, slots=True) class Point: x: float; y: float`.

## Files and paths (pathlib)
```python
from pathlib import Path
p = Path.home() / "Documents" / "notes.txt"
text = p.read_text(encoding="utf-8")
p.write_text(text.upper(), encoding="utf-8")
for f in Path("data").rglob("*.csv"):
    print(f.name, f.stat().st_size)
```
- Always pass `encoding="utf-8"` when reading or writing text on Windows.
- Use `with open(path, "rb") as f:` for binary data.

## Common standard library
- `json.loads / json.dumps(obj, indent=2, ensure_ascii=False)`; `csv.DictReader(f)` / `csv.DictWriter`.
- `datetime.datetime.now()`, `datetime.timedelta(days=7)`, `datetime.date.fromisoformat("2026-11-03")`.
- `subprocess.run(["git", "status"], capture_output=True, text=True, check=True)`.
- `collections.Counter`, `defaultdict(list)`, `deque(maxlen=100)`; `itertools.groupby`, `chain`, `batched` (3.12).
- `functools.lru_cache`, `functools.partial`; `re.findall(r"\d+", s)`, `re.sub`.
- `logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")`.
- `argparse.ArgumentParser()` for command-line tools; `sqlite3.connect("app.db")` for a local database.
- HTTP without packages: `urllib.request.urlopen(url, timeout=10)`; with packages: `requests.get(url, timeout=10)`.

## Errors and debugging
- Catch specific exceptions: `except FileNotFoundError as e:`; re-raise with context `raise ValueError("bad input") from e`.
- `breakpoint()` opens the debugger; `python -X dev` shows extra warnings; `traceback.print_exc()` prints the stack.
- Common errors: `IndentationError` (mixed tabs/spaces), `UnicodeDecodeError` (missing encoding), `ModuleNotFoundError` (package not installed in the active venv), `KeyError` (use `d.get(key)`), `TypeError: 'NoneType'` (a function returned None).

## Testing
- pytest: files `test_*.py`, functions `def test_x(): assert f(2) == 4`; run `python -m pytest -q`; fixtures with `@pytest.fixture`; `tmp_path` gives a temporary folder.
- unittest: `class T(unittest.TestCase): def test_x(self): self.assertEqual(...)`; run `python -m unittest -v`.

## Performance
- Measure first: `python -m cProfile -s cumtime app.py`, `timeit`.
- Use sets/dicts for membership, `str.join` instead of `+=` in loops, generators for large data, `concurrent.futures.ThreadPoolExecutor` for I/O, `ProcessPoolExecutor` for CPU work.
