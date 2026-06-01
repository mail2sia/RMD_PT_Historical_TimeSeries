import csv, threading
from common import utils

class CSVWriter:
    def __init__(self, filepath: str, header: list[str] | None = None):
        self._f = open(filepath, "w", encoding="utf-8", newline="")
        self._w = csv.writer(self._f)
        self._lock = threading.Lock()
        if header:
            self._w.writerow(header)
            self._f.flush()

    def write_rows(self, rows: list[tuple]):
        with self._lock:
            self._w.writerows(rows)
            self._f.flush()

    def close(self):
        with self._lock:
            self._f.close()
