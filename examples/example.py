import os
from pathlib import Path


class DataProcessor:
    """Cleans and prints incoming records."""

    def __init__(self, root):
        self.root = Path(root)

    def process(self, data):
        if not data:
            return None

        for item in data:
            print(f"Processing {item}")

        return True

    @staticmethod
    def load(path, encoding="utf-8", strict=False, retries=3, timeout=10):
        with open(os.path.join(path), encoding=encoding) as handle:
            return handle.read()


class ProcessingError(Exception):
    pass


def helper_function():
    pass
