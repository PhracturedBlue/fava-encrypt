import os
from typing import Iterable
from typing import List
import beancount.ops.documents
import logging
from beancount.core.account import is_valid
__plugins__ = ['enable_encryption']

def enable_encryption(entries, options_map, dirs):
    import fava.application
    orig_update_ledger_slugs = fava.application.update_ledger_slugs
    def update_ledger_slugs(ledgers):
        for ledger in ledgers:
            ledger._watcher = Watcher(ledger)
        return orig_update_ledger_slugs(ledgers)
    if orig_update_ledger_slugs != update_ledger_slugs:
        fava.application.update_ledger_slugs = update_ledger_slugs
    return entries, []

class Watcher:
    __slots__ = ["_encryption_file", "_watcher", "_encrypted"]

    def __init__(self, ledger) -> None:
        path = ledger.beancount_file_path
        self._encryption_file = os.path.join(os.path.dirname(path), ".encrypted")
        self._encrypted = self.is_encrypted()
        self._watcher = ledger._watcher
        logging.warning(f"Enable socket watcher for: {path} Encrypted: {self._encrypted}")
        pass

    def is_encrypted(self):
        return os.path.exists(self._encryption_file)
        
    def update(self, files: Iterable[str], folders: Iterable[str]) -> None:
        return self._watcher.update(files, folders)

    def check(self) -> bool:
        encrypted = self.is_encrypted()
        if encrypted != self._encrypted:
            logging.warning(f"Encryption status changed to: {encrypted}")
            self._encrypted = encrypted
        if not encrypted:
            return False
        return self._watcher.check()
  
