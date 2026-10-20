import threading

from PySide6.QtCore import QObject, QRunnable, Signal


class TaskSignals(QObject):
    success = Signal(object)
    failure = Signal(str)
    finished = Signal()


class Task(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = TaskSignals()

    def run(self):
        try:
            self.signals.success.emit(self.function())
        except Exception as error:
            self.signals.failure.emit(str(error) or type(error).__name__)
        finally:
            self.signals.finished.emit()


class BatchSignals(QObject):
    status = Signal(int, str)
    result = Signal(int, object)
    error = Signal(int, str)
    finished = Signal(int, int, int)


class BatchTask(QRunnable):
    def __init__(self, category, files, target, output, options):
        super().__init__()
        self.category, self.files, self.target = category, list(files), target
        self.output, self.options = output, options
        self.cancel = threading.Event()
        self.signals = BatchSignals()

    def run(self):
        from .service import convert
        good = bad = skipped = 0
        for index, source in enumerate(self.files):
            if self.cancel.is_set():
                self.signals.status.emit(index, '已取消')
                skipped += 1
                continue
            self.signals.status.emit(index, '转换中…')
            try:
                result = convert(self.category, source, self.target, self.output, self.options)
                good += 1
                self.signals.result.emit(index, result)
            except Exception as error:
                bad += 1
                self.signals.error.emit(index, str(error) or type(error).__name__)
        self.signals.finished.emit(good, bad, skipped)
