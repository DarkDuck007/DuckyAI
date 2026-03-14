import unittest

from message_utils import split_message


class SplitMessageTests(unittest.TestCase):
    def test_returns_single_chunk_when_under_limit(self):
        self.assertEqual(split_message("short text", max_length=2800), ["short text"])

    def test_splits_long_text_to_max_length_chunks(self):
        text = "a" * 6001

        chunks = split_message(text, max_length=2800)

        self.assertEqual([len(chunk) for chunk in chunks], [2800, 2800, 401])
        self.assertEqual("".join(chunks), text)

    def test_prefers_splitting_on_whitespace(self):
        text = ("word " * 700).strip()

        chunks = split_message(text, max_length=2800)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 2800 for chunk in chunks))
        self.assertEqual(" ".join(" ".join(chunks).split()), text)


if __name__ == "__main__":
    unittest.main()
