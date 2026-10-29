"""Data from the university's systems (SUPREME, HURIS) that the pages read but never edit.

Neither system has a spec or API yet (BRD 00 §5), so every page reads local copies in the
`ext_*` tables (migration 004). An adapter fills a whole system at a time: `sample` now
(`ocl seed sample`), a Data Warehouse adapter once access is granted. `ext_sources` records
which adapter filled each system and the data date, so the web can label sample data.
"""

from ocl_api.external.base import SYSTEMS, Adapter, Snapshot
from ocl_api.external.store import ExternalStore

__all__ = ["SYSTEMS", "Adapter", "ExternalStore", "Snapshot"]
