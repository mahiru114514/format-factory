from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

import psutil


def kill_tree(process):
    """Kill the dedicated session plus descendants of conversion subprocesses."""
    children = []
    try:
        children = psutil.Process(process.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        pass
    if os.name != 'nt':
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for child in reversed(children):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=5)
    psutil.wait_procs(children, timeout=2)


def run_isolated(args, timeout, cwd, on_start=None, memory_limit_bytes=None):
    process = subprocess.Popen(args, cwd=cwd, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               start_new_session=os.name != 'nt',
                               creationflags=(getattr(subprocess, 'CREATE_NO_WINDOW', 0) | (0x4 if os.name == 'nt' else 0)))
    containment = None
    try:
        if os.name == 'nt':
            from .windows_job import ProcessJob
            containment = ProcessJob(process, memory_limit_bytes=memory_limit_bytes)
        if on_start:
            on_start(process)
        if containment:
            containment.resume(process)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as error:
            raise TimeoutError('转换超时，请缩小文件或分批处理。') from error
        if code:
            raise RuntimeError('转换进程异常退出，请检查文件与引擎安装。')
    finally:
        try:
            kill_tree(process)
        finally:
            if containment:
                containment.close()


@dataclass
class Job:
    id: str
    token_digest: bytes
    directory: Path
    created_at: float
    stem: str
    state: str = 'queued'
    error: str | None = None
    outputs: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    process: object = None
    cancelled: bool = False

    def status(self):
        return {'id': self.id, 'state': self.state, 'error': self.error,
                'result_name': self.stem + '.zip' if self.state == 'succeeded' else None,
                'result_media_type': 'application/zip' if self.state == 'succeeded' else None,
                'outputs': self.outputs, 'warnings': self.warnings}


class JobManager:
    def __init__(self, settings):
        self.settings = settings
        self.storage = settings.storage_dir
        self.storage.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.jobs = {}
        self.validators = {}
        self.lock = threading.RLock()
        self.stopped = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=settings.max_workers, thread_name_prefix='conversion')
        self.janitor = None

    def start(self):
        # Tokens live only in memory. A restart invalidates and removes prior
        # service jobs, never arbitrary directories in the configured storage.
        for directory in self.storage.iterdir():
            if directory.is_dir() and not directory.is_symlink() and re.fullmatch('[0-9a-f]{32}', directory.name):
                manifest = directory / 'request.json'
                try:
                    if json.loads(manifest.read_text(encoding='utf-8')).get('owner') in ('mobile_server_v1', 'mobile_server_validation_v1'):
                        shutil.rmtree(directory)
                except (OSError, ValueError):
                    pass
        self.janitor = threading.Thread(target=self._janitor, daemon=True, name='job-retention')
        self.janitor.start()

    def _janitor(self):
        while not self.stopped.wait(self.settings.cleanup_interval_seconds):
            self.cleanup()

    def validate_input(self, data, source, options):
        """Consent has already been checked; parse bytes only in a bounded child.

        The generated directory and filenames are never supplied by the client.
        Staging is removed for success, rejected content, crash, and hard timeout.
        """
        directory = self.storage / uuid.uuid4().hex
        with self.lock:
            if self.stopped.is_set():
                raise ValueError('服务正在关闭，请稍后重试。')
            directory.mkdir(mode=0o700)
        try:
            (directory / 'input.bin').write_bytes(data)
            manifest = {'owner': 'mobile_server_validation_v1', 'source': source, 'options': options,
                        'max_uncompressed_bytes': self.settings.max_uncompressed_bytes,
                        'memory_limit_bytes': self.settings.validation_memory_bytes}
            (directory / 'request.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')

            def on_start(process):
                with self.lock:
                    self.validators[directory] = process
                    if self.stopped.is_set():
                        kill_tree(process)

            try:
                run_isolated([sys.executable, '-m', 'mobile_server.validation_worker', str(directory)],
                             timeout=self.settings.validation_timeout_seconds,
                             cwd=Path(__file__).resolve().parents[1], on_start=on_start,
                             memory_limit_bytes=self.settings.validation_memory_bytes)
            except TimeoutError as error:
                raise TimeoutError('文件校验超时，请缩小文件或检查文件是否损坏。') from error
            except (RuntimeError, OSError) as error:
                raise ValueError('文件校验进程异常退出或超过内存限制，请缩小文件或检查文件是否损坏。') from error
            try:
                outcome = json.loads((directory / 'validation.json').read_text(encoding='utf-8'))
            except (OSError, ValueError) as error:
                raise ValueError('文件校验进程未生成有效结果。') from error
            if not outcome.get('valid'):
                raise ValueError(outcome.get('error') or '文件内容无效。')
        finally:
            with self.lock:
                self.validators.pop(directory, None)
            shutil.rmtree(directory)

    def create(self, data, stem, source, category, target, options):
        with self.lock:
            if self.stopped.is_set() or len(self.jobs) >= self.settings.max_jobs:
                raise OverflowError('任务存储已满，请等待任务过期或删除已下载的任务。')
            identifier, token = uuid.uuid4().hex, secrets.token_urlsafe(32)
            directory = self.storage / identifier
            directory.mkdir(mode=0o700)
            try:
                (directory / ('input.' + source)).write_bytes(data)
                manifest = {'owner': 'mobile_server_v1', 'category': category, 'source': source,
                            'target': target, 'stem': stem, 'options': options,
                            'max_result_bytes': self.settings.max_uncompressed_bytes}
                (directory / 'request.json').write_text(json.dumps(manifest, ensure_ascii=False), encoding='utf-8')
                job = Job(identifier, hashlib.sha256(token.encode()).digest(), directory, time.time(), stem)
                self.jobs[identifier] = job
                self.executor.submit(self._convert, job)
            except BaseException:
                self.jobs.pop(identifier, None)
                shutil.rmtree(directory)
                raise
            return {'id': identifier, 'token': token, 'state': job.state}

    def _convert(self, job):
        with self.lock:
            if job.cancelled or self.stopped.is_set():
                return
            job.state = 'running'

        def on_start(process):
            with self.lock:
                job.process = process
                if job.cancelled or self.stopped.is_set():
                    kill_tree(process)

        try:
            root = Path(__file__).resolve().parents[1]
            run_isolated([sys.executable, '-m', 'mobile_server.worker', str(job.directory)],
                         timeout=self.settings.worker_timeout_seconds, cwd=root, on_start=on_start)
            with self.lock:
                if job.cancelled:
                    return
                outcome = json.loads((job.directory / 'outcome.json').read_text(encoding='utf-8'))
                job.state = outcome['state']
                job.error = outcome['error']
                job.outputs = outcome['outputs']
                job.warnings = outcome['warnings']
        except Exception as error:
            with self.lock:
                if not job.cancelled:
                    job.state, job.error = 'failed', str(error)[:1500]
        finally:
            with self.lock:
                job.process = None

    def authorized(self, identifier, token):
        self.cleanup()
        with self.lock:
            job = self.jobs.get(identifier)
            digest = hashlib.sha256(token.encode()).digest()
            if job is None or not hmac.compare_digest(job.token_digest, digest):
                return None
            return job

    def delete(self, identifier):
        with self.lock:
            job = self.jobs.pop(identifier, None)
            if job is None:
                return
            job.cancelled = True
            if job.process is not None:
                kill_tree(job.process)
            shutil.rmtree(job.directory, ignore_errors=False)

    def cleanup(self, now=None):
        now = time.time() if now is None else now
        with self.lock:
            for identifier, job in list(self.jobs.items()):
                if now - job.created_at >= self.settings.retention_seconds:
                    self.delete(identifier)

    def close(self):
        self.stopped.set()
        if self.janitor:
            self.janitor.join(timeout=5)
        with self.lock:
            for process in self.validators.values():
                kill_tree(process)
            for identifier in list(self.jobs):
                self.delete(identifier)
        self.executor.shutdown(wait=True, cancel_futures=True)
