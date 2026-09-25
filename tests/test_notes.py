import unittest

from badger_evidence.notes import note_paths, render_markdown, render_note


class NotesTest(unittest.TestCase):
    def test_markdown_subset(self):
        title, body, toc = render_markdown("# T\n\n## A b\n\n**x** *y* [l](https://e.x)\nnext\n\n- one\n- two\n\n| h | i |\n|---|---|\n| 1 | <2> |\n\n---\n")
        self.assertEqual(title, "T")
        self.assertEqual(toc, [("a-b", "A b")])
        self.assertIn('<p><strong>x</strong> <em>y</em> <a href="https://e.x">l</a><br>next</p>', body)
        self.assertIn("<ul><li>one</li><li>two</li></ul>", body)
        self.assertIn("<td>&lt;2&gt;</td>", body)
        self.assertIn("<hr>", body)

    def test_repo_notes_render(self):
        for path in note_paths():
            page = render_note(path)
            self.assertIn("../style.css", page)
            self.assertNotIn("**", page)


if __name__ == "__main__":
    unittest.main()
