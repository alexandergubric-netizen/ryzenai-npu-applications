"""The calculate tool: exact results, nothing but arithmetic, and when Chat offers it."""
import unittest

from core.calc import evaluate, HINT, validate


class CalcTests(unittest.TestCase):
    def test_exact_results(self):
        self.assertEqual(evaluate("3*7.5 + 2*4.2"), "3*7.5 + 2*4.2 = 30.9")
        self.assertEqual(evaluate("(1250*12)*0.21"), "(1250*12)*0.21 = 3150")
        self.assertEqual(evaluate("7 × 6"), "7 × 6 = 42")
        self.assertEqual(evaluate("2^10"), "2^10 = 1024")
        self.assertTrue(evaluate("sqrt(2*9.81*20)").endswith("= 19.8090888231"))
        self.assertEqual(evaluate("round(10/3, 2)"), "round(10/3, 2) = 3.33")

    def test_nothing_but_arithmetic(self):
        for bad in ('__import__("os")', "(1).__class__", "9**9**9", "a+b", 'open("x")', "[1,2]", "lambda: 1",
                    "1/0", "x" * 301, "sqrt(-1)"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                evaluate(bad)
        with self.assertRaises(ValueError):
            validate({"expression": "1+1", "extra": 1})

    def test_offered_only_for_number_questions(self):
        for q in ("What is the total price of this order? 3 mugs at 7.5", "How much is 15 percent of 240?", "12*7?",
                  "Calculate the average of 4, 8 and 15"):
            self.assertTrue(HINT.search(q), q)
        for q in ("Tell me a joke", "Write a poem about 3 cats", "Summarize the attached PDF"):
            self.assertFalse(HINT.search(q), q)


class FakeModel:
    """Asks for the calculator once, then answers with the result it was given."""
    port = 0
    def models(self):
        return []
    def stream(self, model, messages, **kw):
        if messages[-1]["role"] == "tool":
            assert "30.9" in messages[-1]["content"]
            yield "text", "The total is 30.90."
        else:
            assert any(t["function"]["name"] == "calculate" for t in kw["tools"])
            yield "tool_delta", [{"index": 0, "id": "c1", "function": {"name": "calculate",
                                                                      "arguments": '{"expression": "3*7.5 + 2*4.2"}'}}]


class ToolLoopCalcTests(unittest.TestCase):
    def test_chat_uses_the_calculator_and_gets_the_exact_result(self):
        import tempfile
        import threading
        from pathlib import Path
        from core.storage import Store
        from core.tool_loop import ToolLoop
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1] / ".test-runs") as h:
            events = []
            loop = ToolLoop(Store(h), h)
            out = list(loop.stream(FakeModel(), "m", [{"role": "system", "content": "s"},
                                   {"role": "user", "content": "What is the total of 3 mugs at 7.5 and 2 teas at 4.2?"}],
                                   workspace="default", turn="t", emit=lambda k, d: events.append((k, d)),
                                   cancelled=threading.Event(), file_tools=True))
            self.assertIn(("text", "The total is 30.90."), out)
            result = next(d for k, d in events if k == "tool_result")
            self.assertEqual((result["name"], result["decision"], result["result"]), ("calculate", "read", "3*7.5 + 2*4.2 = 30.9"))


if __name__ == "__main__":
    unittest.main()
