"""Tests for graphs/common/utils.py — build_code_summary, format_code_files."""

from common.utils import build_code_summary, format_code_files


class TestBuildCodeSummary:
    def test_empty_files(self):
        result = build_code_summary([], "My task")
        assert "My task" in result
        assert "No code files" in result

    def test_with_files(self):
        files = [
            {"path": "app.py", "language": "python", "content": "print(1)"},
            {"path": "index.html", "language": "html", "content": "<h1>Hi</h1>"},
        ]
        result = build_code_summary(files, "Build app")
        assert "Build app" in result
        assert "2 file(s)" in result
        assert "### app.py" in result
        assert "### index.html" in result
        assert "```python" in result

    def test_missing_fields_fallback(self):
        files = [{"some_key": "val"}]
        result = build_code_summary(files, "task")
        assert "### unknown" in result


class TestFormatCodeFiles:
    def test_empty(self):
        assert format_code_files([]) == "No code files"

    def test_single_file(self):
        files = [{"path": "main.py", "language": "python", "content": "x = 1"}]
        result = format_code_files(files)
        assert "### main.py" in result
        assert "```python" in result
        assert "x = 1" in result

    def test_multiple_files(self):
        files = [
            {"path": "a.py", "language": "python", "content": "a"},
            {"path": "b.js", "language": "javascript", "content": "b"},
        ]
        result = format_code_files(files)
        assert "### a.py" in result
        assert "### b.js" in result
        assert "```javascript" in result
