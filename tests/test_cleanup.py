import tempfile
from pathlib import Path

from utils.cleanup import clean, get_cache_dirs, get_cache_files, format_size


class TestCleanup:
    def test_format_size_bytes(self):
        assert "B" in format_size(100)

    def test_format_size_kb(self):
        result = format_size(2048)
        assert "KB" in result

    def test_format_size_mb(self):
        result = format_size(1048576)
        assert "MB" in result

    def test_clean_dry_run_returns_dict(self):
        result = clean(dry_run=True)
        assert "removed_dirs" in result
        assert "removed_files" in result
        assert "freed_bytes" in result
        assert result["dry_run"] == True

    def test_get_cache_dirs_returns_list(self):
        dirs = get_cache_dirs()
        assert isinstance(dirs, list)

    def test_get_cache_files_returns_list(self):
        files = get_cache_files()
        assert isinstance(files, list)

    def test_clean_with_max_age(self):
        result = clean(max_age=0, dry_run=True)
        assert isinstance(result["removed_dirs"], int)
