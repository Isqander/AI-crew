"""
File System Tools

Provides tools for working with local files (for code generation output).
"""

import os
from pathlib import Path
from typing import Optional
from langchain_core.tools import tool


# Working directory for generated files
WORKSPACE_DIR = os.getenv("WORKSPACE_DIR", "/tmp/aicrew_workspace")


def ensure_workspace():
    """Ensure workspace directory exists."""
    Path(WORKSPACE_DIR).mkdir(parents=True, exist_ok=True)


@tool
def write_file(
    file_path: str,
    content: str,
) -> str:
    """
    Write content to a file in the workspace.
    
    Args:
        file_path: Relative path to the file
        content: File content to write
        
    Returns:
        Confirmation message
    """
    ensure_workspace()
    
    try:
        full_path = Path(WORKSPACE_DIR) / file_path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        return f"File written: {file_path}"
    except Exception as e:
        return f"Error writing file: {str(e)}"


@tool
def read_file(
    file_path: str,
) -> str:
    """
    Read content from a file in the workspace.
    
    Args:
        file_path: Relative path to the file
        
    Returns:
        File content
    """
    ensure_workspace()
    
    try:
        full_path = Path(WORKSPACE_DIR) / file_path
        
        if not full_path.exists():
            return f"File not found: {file_path}"
        
        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"


@tool
def list_files(
    directory: str = "",
) -> str:
    """
    List files in a directory in the workspace.
    
    Args:
        directory: Relative path to directory (empty for root)
        
    Returns:
        List of files and directories
    """
    ensure_workspace()
    
    try:
        full_path = Path(WORKSPACE_DIR) / directory
        
        if not full_path.exists():
            return f"Directory not found: {directory}"
        
        items = []
        for item in full_path.iterdir():
            type_indicator = "📁" if item.is_dir() else "📄"
            items.append(f"{type_indicator} {item.name}")
        
        return "\n".join(sorted(items)) if items else "Empty directory"
    except Exception as e:
        return f"Error listing directory: {str(e)}"


@tool
def delete_file(
    file_path: str,
) -> str:
    """
    Delete a file from the workspace.
    
    Args:
        file_path: Relative path to the file
        
    Returns:
        Confirmation message
    """
    ensure_workspace()
    
    try:
        full_path = Path(WORKSPACE_DIR) / file_path
        
        if not full_path.exists():
            return f"File not found: {file_path}"
        
        full_path.unlink()
        return f"File deleted: {file_path}"
    except Exception as e:
        return f"Error deleting file: {str(e)}"


@tool
def create_directory(
    directory: str,
) -> str:
    """
    Create a directory in the workspace.
    
    Args:
        directory: Relative path to the directory
        
    Returns:
        Confirmation message
    """
    ensure_workspace()
    
    try:
        full_path = Path(WORKSPACE_DIR) / directory
        full_path.mkdir(parents=True, exist_ok=True)
        return f"Directory created: {directory}"
    except Exception as e:
        return f"Error creating directory: {str(e)}"


# Export tools as a list
filesystem_tools = [
    write_file,
    read_file,
    list_files,
    delete_file,
    create_directory,
]
