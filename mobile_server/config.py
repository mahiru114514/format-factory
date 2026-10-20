from dataclasses import dataclass, field
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    storage_dir: Path = field(default_factory=lambda: Path(os.getenv('FACTORY_STORAGE', '.work/mobile-jobs')).resolve())
    max_upload_bytes: int = 50 * 1024 * 1024
    worker_timeout_seconds: float = 120
    retention_seconds: float = 3600
    max_workers: int = 2
    max_jobs: int = 64
    cleanup_interval_seconds: float = 30
    max_uncompressed_bytes: int = 200 * 1024 * 1024
    validation_timeout_seconds: float = 15
    validation_memory_bytes: int = 768 * 1024 * 1024

    def __post_init__(self):
        object.__setattr__(self, 'storage_dir', Path(self.storage_dir).resolve())
        for key in ('max_upload_bytes', 'worker_timeout_seconds', 'retention_seconds', 'max_workers',
                    'max_jobs', 'cleanup_interval_seconds', 'max_uncompressed_bytes',
                    'validation_timeout_seconds', 'validation_memory_bytes'):
            if getattr(self, key) <= 0:
                raise ValueError(f'{key} must be positive')

    @classmethod
    def from_env(cls):
        values = {}
        for name in ('max_upload_bytes', 'max_workers', 'max_jobs', 'max_uncompressed_bytes', 'validation_memory_bytes'):
            if value := os.getenv('FACTORY_' + name.upper()):
                values[name] = int(value)
        for name in ('worker_timeout_seconds', 'retention_seconds', 'cleanup_interval_seconds', 'validation_timeout_seconds'):
            if value := os.getenv('FACTORY_' + name.upper()):
                values[name] = float(value)
        return cls(**values)
