"""
Document management, parsing, and change detection module exports.
"""

from src.documents.manager import DocumentManager
from src.documents.parser import DocumentParser
from src.documents.diff import DocumentDiffEngine

__all__ = ["DocumentManager", "DocumentParser", "DocumentDiffEngine"]
