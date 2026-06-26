from utils.diff_utils import generate_diff, diff_stats


class TestGenerateDiff:
    def test_empty_diff_for_identical(self):
        content = "hello\nworld\n"
        diff = generate_diff(content, content, "test.txt")
        assert diff == "" or diff.strip() == ""

    def test_diff_shows_additions(self):
        original = "line1\nline2\n"
        modified = "line1\nline2\nline3\n"
        diff = generate_diff(original, modified, "test.txt")
        assert "+line3" in diff

    def test_diff_shows_deletions(self):
        original = "line1\nline2\nline3\n"
        modified = "line1\nline3\n"
        diff = generate_diff(original, modified, "test.txt")
        assert "-line2" in diff

    def test_diff_contains_file_path(self):
        original = "a\n"
        modified = "b\n"
        diff = generate_diff(original, modified, "src/file.py")
        assert "src/file.py" in diff


class TestDiffStats:
    def test_empty_diff(self):
        stats = diff_stats("")
        assert stats["additions"] == 0
        assert stats["deletions"] == 0
        assert stats["total"] == 0

    def test_counts_additions(self):
        diff = "--- a/file\n+++ b/file\n@@ -1 +1,2 @@\n old\n+new\n"
        stats = diff_stats(diff)
        assert stats["additions"] == 1

    def test_counts_deletions(self):
        diff = "--- a/file\n+++ b/file\n@@ -1,2 +1 @@\n-old\n new\n"
        stats = diff_stats(diff)
        assert stats["deletions"] == 1

    def test_counts_both(self):
        diff = "--- a/file\n+++ b/file\n@@ -1,3 +1,3 @@\n-one\n+two\n three\n-four\n+five\n"
        stats = diff_stats(diff)
        assert stats["additions"] == 2
        assert stats["deletions"] == 2
        assert stats["total"] == 4
