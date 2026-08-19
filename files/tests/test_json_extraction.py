import unittest
import _testkit  # noqa: F401

from agents import _extract_json


class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(_extract_json('{"a": 1}'), {"a": 1})

    def test_json_in_code_fence(self):
        text = '```json\n{"a": 1, "b": [1, 2]}\n```'
        self.assertEqual(_extract_json(text), {"a": 1, "b": [1, 2]})

    def test_json_with_surrounding_prose(self):
        text = 'Sure, here is the result:\n{"a": 1}\nLet me know if you need more.'
        self.assertEqual(_extract_json(text), {"a": 1})

    def test_malformed_json_raises(self):
        with self.assertRaises(Exception):
            _extract_json("not json at all")


if __name__ == "__main__":
    unittest.main()
