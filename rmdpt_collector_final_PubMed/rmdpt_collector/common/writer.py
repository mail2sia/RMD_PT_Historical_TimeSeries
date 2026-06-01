import csv, threading
from common import utils

class CSVWriter:
    def __init__(self, filepath: str):
        self._f = open(filepath, "w", encoding=utils.ENCODING, newline="")
        self._w = csv.writer(self._f)
        self._lock = threading.Lock()
        # No header per your schema

    def write_rows(self, rows: list[tuple[str,str,int]]):
        with self._lock:
            for r in rows:
                self._w.writerow([r[0], r[1], str(r[2])])
            self._f.flush()

    def close(self):
        with self._lock:
            self._f.close()
