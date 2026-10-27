"""Chat accuracy check: runs typical questions through retrieval + the local model and flags common mistakes.

    python tests\\chat_eval.py            (uses your real scan data, read-only; the AI engine must be running)

Checks per answer: unknown [F]/[P] tags (hallucinated items), numbers that don't appear in the data, uninstall advice
in an edition that forbids it, empty answers, and whether retrieval found anything at all.
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import ai, chat, edition  # noqa: E402

QUESTIONS = [
    "What can I safely clean up first?",
    "Which programs haven't I used in ages?",
    "What are my biggest files that I don't use?",
    "How can I improve my Seiton score?",
    "Which folder needs the most attention?",
    "Do I have duplicate files?",
    "What is in my Downloads folder that I should move?",
    "How much space can I free?",
]


def numbers(text):
    return {n.replace(",", ".") for n in re.findall(r"\d+(?:[.,]\d+)?", text)}


def main():
    eng = ai.npu
    eng.kind = eng.choose()
    if not ai._ping(eng.base):
        print("AI engine not running - start Kaizen first")
        return 1
    eng.model = eng.model or ai.db.get_settings()["model"] if eng.kind == "flm" else (ai._server_models(eng.base) or [""])[0]
    problems = 0
    for q in QUESTIONS:
        system, items = chat.build_context(q)
        refs = {i["ref"] for i in items}
        t = time.time()
        answer = eng.complete([{"role": "system", "content": system}, {"role": "user", "content": q}], max_tokens=450,
                              temperature=0.2)
        if re.search(r"\[[FP]\d+\]\s*(to|-|–)\s*\[[FP]\d+\]", answer):
            print("  (tag range)")
        copied = [line for line in system.split("\n") if len(line) > 60 and line[20:60] in answer]
        if copied:
            print(f"  (copied {len(copied)} data line(s))")
        used = set(re.findall(r"\[([FP]\d+)\]", answer))
        issues = []
        if not answer.strip():
            issues.append("empty answer")
        if used - refs:
            issues.append(f"unknown tags {sorted(used - refs)}")
        if not items and "No scan" not in system:
            issues.append("retrieval found nothing")
        stray = {n for n in numbers(answer) - numbers(system) - numbers(q) if len(n) > 1 and not re.fullmatch(r"20\d\d", n)}
        if stray:
            issues.append(f"numbers not in data {sorted(stray)[:6]}")
        if not edition.get()["allow_uninstall"] and re.search(r"\buninstall", answer, re.I):
            issues.append("suggests uninstalling")
        problems += bool(issues)
        print(f"\n### {q}   ({time.time() - t:.1f}s, {len(items)} items retrieved)")
        print(answer.strip())
        print("  ->", "; ".join(issues) if issues else "OK")
    print(f"\n{problems} of {len(QUESTIONS)} answers had problems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
