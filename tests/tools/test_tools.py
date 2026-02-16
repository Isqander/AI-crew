"""
Tests for agent tools
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from graphs.dev_team.tools.github import (
    create_pull_request,
    create_branch,
    commit_file,
    get_file_content,
    list_repository_files,
)
from graphs.dev_team.tools.filesystem import (
    write_file,
    read_file,
    list_files,
    delete_file,
    create_directory,
    WORKSPACE_DIR,
)


class TestGitHubTools:
    """Test GitHub integration tools."""
    
    @patch('graphs.dev_team.tools.github.get_github_client')
    def test_create_pull_request_success(self, mock_get_client):
        """Test successful PR creation."""
        mock_client = Mock()
        mock_repo = Mock()
        mock_pr = Mock(html_url="https://github.com/owner/repo/pull/1")
        mock_repo.create_pull.return_value = mock_pr
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client
        
        result = create_pull_request.invoke({
            "repo_name": "owner/repo",
            "title": "Test PR",
            "body": "Test description",
            "branch": "feature-branch",
            "base": "main",
        })
        
        assert "Pull request created" in result
        assert "https://github.com/owner/repo/pull/1" in result
    
    @patch('graphs.dev_team.tools.github.get_github_client')
    def test_create_pull_request_no_client(self, mock_get_client):
        """Test PR creation without GitHub client."""
        mock_get_client.return_value = None
        
        result = create_pull_request.invoke({
            "repo_name": "owner/repo",
            "title": "Test PR",
            "body": "Test description",
            "branch": "feature-branch",
        })
        
        assert "Error" in result
        assert "not configured" in result
    
    @patch('graphs.dev_team.tools.github.get_github_client')
    def test_create_branch_success(self, mock_get_client):
        """Test successful branch creation."""
        mock_client = Mock()
        mock_repo = Mock()
        mock_branch = Mock(commit=Mock(sha="abc123"))
        mock_repo.get_branch.return_value = mock_branch
        mock_repo.create_git_ref.return_value = None
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client
        
        result = create_branch.invoke({
            "repo_name": "owner/repo",
            "branch_name": "new-feature",
            "base_branch": "main",
        })
        
        assert "Branch 'new-feature' created" in result
    
    @patch('graphs.dev_team.tools.github.get_github_client')
    def test_commit_file_new_file(self, mock_get_client):
        """Test committing a new file."""
        mock_client = Mock()
        mock_repo = Mock()
        
        # Simulate file not existing
        mock_repo.get_contents.side_effect = Exception("File not found")
        
        # Mock create_file
        mock_commit = Mock(sha="def456")
        mock_repo.create_file.return_value = {"commit": mock_commit}
        
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client
        
        result = commit_file.invoke({
            "repo_name": "owner/repo",
            "file_path": "src/new_file.py",
            "content": "print('hello')",
            "commit_message": "Add new file",
            "branch": "main",
        })
        
        assert "File committed" in result
    
    @patch('graphs.dev_team.tools.github.get_github_client')
    def test_get_file_content_success(self, mock_get_client):
        """Test getting file content."""
        mock_client = Mock()
        mock_repo = Mock()
        mock_content = Mock()
        mock_content.decoded_content = b"file content"
        mock_repo.get_contents.return_value = mock_content
        mock_client.get_repo.return_value = mock_repo
        mock_get_client.return_value = mock_client
        
        result = get_file_content.invoke({
            "repo_name": "owner/repo",
            "file_path": "README.md",
            "branch": "main",
        })
        
        assert result == "file content"


class TestFileSystemTools:
    """Test filesystem tools."""
    
    @pytest.fixture(autouse=True)
    def cleanup(self):
        """Clean up test files after each test."""
        yield
        # Cleanup logic if needed
        import shutil
        if Path(WORKSPACE_DIR).exists():
            # Only clean test files, not the entire workspace
            pass
    
    def test_write_file_success(self, tmp_path, monkeypatch):
        """Test writing a file."""
        monkeypatch.setattr(
            'graphs.dev_team.tools.filesystem.WORKSPACE_DIR',
            str(tmp_path)
        )
        
        result = write_file.invoke({
            "file_path": "test.txt",
            "content": "Hello, World!",
        })
        
        assert "File written" in result
        assert (tmp_path / "test.txt").exists()
        assert (tmp_path / "test.txt").read_text() == "Hello, World!"
    
    def test_write_file_with_subdirectory(self, tmp_path, monkeypatch):
        """Test writing a file in a subdirectory."""
        monkeypatch.setattr(
            'graphs.dev_team.tools.filesystem.WORKSPACE_DIR',
            str(tmp_path)
        )
        
        result = write_file.invoke({
            "file_path": "subdir/nested/file.txt",
            "content": "Nested content",
        })
        
        assert "File written" in result
        assert (tmp_path / "subdir" / "nested" / "file.txt").exists()
    
    def test_read_file_success(self, tmp_path, monkeypatch):
        """Test reading a file."""
        monkeypatch.setattr(
            'graphs.dev_team.tools.filesystem.WORKSPACE_DIR',
            str(tmp_path)
        )
        
        # Create a test file
        test_file = tmp_path / "read_test.txt"
        test_file.write_text("Content to read")
        
        result = read_file.invoke({
            "file_path": "read_test.txt",
        })
        
        assert result == "Content to read"
    
    def test_read_file_not_found(self, tmp_path, monkeypatch):
        """Test reading a non-existent file."""
        monkeypatch.setattr(
            'graphs.dev_team.tools.filesystem.WORKSPACE_DIR',
            str(tmp_path)
        )
        
        result = read_file.invoke({
            "file_path": "nonexistent.txt",
        })
        
        assert "File not found" in result
    
    def test_list_files(self, tmp_path, monkeypatch):
        """Test listing files in a directory."""
        monkeypatch.setattr(
            'graphs.dev_team.tools.filesystem.WORKSPACE_DIR',
            str(tmp_path)
        )
        
        # Create some test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")
        (tmp_path / "subdir").mkdir()
        
        result = list_files.invoke({
            "directory": "",
        })
        
        assert "file1.txt" in result
        assert "file2.py" in result
        assert "subdir" in result
    
    def test_delete_file_success(self, tmp_path, monkeypatch):
        """Test deleting a file."""
        monkeypatch.setattr(
            'graphs.dev_team.tools.filesystem.WORKSPACE_DIR',
            str(tmp_path)
        )
        
        # Create a test file
        test_file = tmp_path / "delete_me.txt"
        test_file.write_text("Delete this")
        
        result = delete_file.invoke({
            "file_path": "delete_me.txt",
        })
        
        assert "File deleted" in result
        assert not test_file.exists()
    
    def test_create_directory_success(self, tmp_path, monkeypatch):
        """Test creating a directory."""
        monkeypatch.setattr(
            'graphs.dev_team.tools.filesystem.WORKSPACE_DIR',
            str(tmp_path)
        )
        
        result = create_directory.invoke({
            "directory": "new_dir/nested",
        })
        
        assert "Directory created" in result
        assert (tmp_path / "new_dir" / "nested").exists()
