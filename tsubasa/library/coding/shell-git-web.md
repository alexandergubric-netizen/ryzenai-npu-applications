# PowerShell, Git, JavaScript and SQL quick reference

## PowerShell 7 essentials
- Help and discovery: `Get-Help Get-ChildItem -Examples`, `Get-Command *service*`, `Get-Member` on any object.
- Files: `Get-ChildItem -Recurse -Filter *.py`, `Copy-Item a b -Recurse`, `Move-Item`, `New-Item -ItemType Directory -Force path`, `Test-Path path`.
- Read and write text: `Get-Content file -Raw`, `Set-Content file -Value $text -Encoding utf8`, `Add-Content`.
- Pipelines pass objects: `Get-Process | Sort-Object WS -Descending | Select-Object -First 5 Name, Id, WS`.
- Filtering: `Where-Object { $_.Length -gt 1MB }`; loops: `ForEach-Object { $_.Name }`, `foreach ($f in $files) { }`.
- Variables `$name = 'x'`; strings: double quotes expand `"$HOME\docs"`, single quotes do not. Here-string: `@' ... '@`.
- Environment: `$env:PATH`, `$env:USERPROFILE`; current folder `$PWD`; change with `Set-Location`.
- Errors: `try { ... } catch { $_.Exception.Message }`; `-ErrorAction Stop` turns errors into exceptions; `$LASTEXITCODE` holds a native program's exit code.
- JSON/CSV: `Get-Content x.json -Raw | ConvertFrom-Json`, `$obj | ConvertTo-Json -Depth 5`, `Import-Csv`, `Export-Csv -NoTypeInformation`.
- Web: `Invoke-RestMethod https://api.example.com/items`, `Invoke-WebRequest -OutFile file url`.
- Run a script: `& "C:\path\script.ps1"`; execution policy for the current user: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.
- Packages: `winget search name`, `winget install --id Python.Python.3.12 -e`.

## Git
- Start: `git init`, `git clone URL`; identity: `git config --global user.name "Name"`, `user.email`.
- Daily: `git status`, `git add -A`, `git commit -m "message"`, `git log --oneline -10`, `git diff`, `git diff --staged`.
- Branches: `git switch -c feature`, `git switch main`, `git merge feature`, `git branch -d feature`.
- Remote: `git remote add origin URL`, `git push -u origin main`, `git pull --rebase`.
- Undo: `git restore file` (discard changes), `git restore --staged file` (unstage), `git commit --amend` (last commit, before pushing), `git revert <sha>` (safe undo of a pushed commit), `git stash` / `git stash pop`.
- `.gitignore` examples: `.venv/`, `__pycache__/`, `node_modules/`, `*.log`, `.env`.

## JavaScript / Node
- Run: `node app.js`; project: `npm init -y`, `npm install express`, scripts in package.json run with `npm run dev`.
- Modern syntax: `const`/`let`, arrow functions `x => x * 2`, destructuring `const {a, b} = obj`, spread `[...arr]`, optional chaining `user?.address?.city`, nullish `value ?? 'default'`.
- Async: `const r = await fetch(url); const data = await r.json();` inside `async function`. Handle errors with try/catch.
- Arrays: `map`, `filter`, `reduce`, `find`, `some`, `every`, `sort((a, b) => a - b)`, `structuredClone(obj)`.
- DOM: `document.querySelector('#id')`, `el.addEventListener('click', fn)`, `el.textContent = text` (safe; avoid innerHTML with user text).

## SQL (SQLite / PostgreSQL)
- `SELECT col, COUNT(*) FROM t WHERE x > 5 GROUP BY col HAVING COUNT(*) > 1 ORDER BY 2 DESC LIMIT 10;`
- Joins: `SELECT o.id, c.name FROM orders o JOIN customers c ON c.id = o.customer_id;` (`LEFT JOIN` keeps unmatched rows).
- Change data: `INSERT INTO t(a, b) VALUES (?, ?)`, `UPDATE t SET a = ? WHERE id = ?`, `DELETE FROM t WHERE id = ?`.
- Always use parameters (`?`) instead of building SQL strings from user input (prevents SQL injection).
- Indexes speed up WHERE/JOIN columns: `CREATE INDEX idx_orders_customer ON orders(customer_id);`.
- Window functions: `ROW_NUMBER() OVER (PARTITION BY dept ORDER BY salary DESC)`.

## A careful workflow
1. Restate the goal and constraints. 2. Write the smallest version that works. 3. Run it and read the actual error text. 4. Fix one thing at a time. 5. Add a test for the bug you fixed. 6. Keep secrets (keys, passwords) out of code; read them from environment variables.
