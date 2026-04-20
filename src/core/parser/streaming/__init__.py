"""Streaming infrastructure for large file processing (>100MB)."""

from src.core.parser.streaming.memory_budget import MemoryBudget, MemoryAllocation
from src.core.parser.streaming.fact_index import FactReference, InMemoryFactIndex
from src.core.parser.streaming.disk_spill import DiskSpilledFactIndex
from src.core.parser.streaming.fact_store import FactStore
from src.core.parser.streaming.mmap_reader import MMapReader
from src.core.parser.streaming.chunked_reader import ChunkedReader
from src.core.parser.streaming.storage_detector import StorageDetector
from src.core.parser.streaming.counting_wrapper import CountingFileWrapper

__all__ = [
    "MemoryBudget",
    "MemoryAllocation",
    "FactReference",
    "InMemoryFactIndex",
    "DiskSpilledFactIndex",
    "FactStore",
    "MMapReader",
    "ChunkedReader",
    "StorageDetector",
    "CountingFileWrapper",
]
