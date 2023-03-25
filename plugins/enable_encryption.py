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
    __slots__ = ["_encryption_file", "_watcher", "_decrypted"]

    def __init__(self, ledger) -> None:
        path = ledger.beancount_file_path
        self._decrypted = False
        self._encryption_file = os.path.join(os.path.dirname(path), ".encrypted")
        self.is_decrypted()
        self._watcher = ledger._watcher
        logging.warning(f"Enable socket watcher for: {path} Decrypted: {self._decrypted}")
        pass

    def is_decrypted(self):
        decrypted = os.path.exists(self._encryption_file)
        if decrypted != self._decrypted:
            logging.warning("Encryption status changed to: "
                           f"{'decrypted' if decrypted else 'encrypted'}")
            self._decrypted = decrypted
        return decrypted

    def update(self, files: Iterable[str], folders: Iterable[str]) -> None:
        return self._watcher.update(files, folders)

    def check(self) -> bool:
        if not self.is_decrypted():
            return False
        last_checked = self._watcher.last_checked
        status = self._watcher.check()
        if not self.is_decrypted():
            # decyprtion status change happened during check revert status
            self._watcher.last_checked = last_checked
            return False
        return status

    @property
    def last_checked(self):
        return self._watcher.last_checked
