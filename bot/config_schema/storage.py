from dataclasses import dataclass, field


@dataclass(frozen=True)
class SQLiteConfig:
    sessions_path: str = "workspace/sessions.db"
    memory_path: str = "workspace/memory/memory.db"


@dataclass(frozen=True)
class StorageConfig:
    backend: str = "sqlite"
    sqlite: SQLiteConfig = field(default_factory=SQLiteConfig)
