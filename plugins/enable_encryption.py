import os
from typing import Iterable
from typing import List
import beancount.ops.documents
import logging
import inspect
from beancount.core.account import is_valid

__plugins__ = ['enable_encryption']

# Fava does not provide any way for an extension to get access to the FavaLedger object
# so we need to use inspection to find it.  This is incredibly brittle and terrible practice

def enable_encryption(entries, options_map, dirs):
    import  fava.core.watcher
    import  fava.core
    if fava.core.Watcher == fava.core.watcher.Watcher:
        # This will catch any future watchers
        fava.core.Watcher = Watcher
        # but if we got here, a watcher has already been set that we need to fix
        parent = inspect.currentframe()
        while True:
            try:
                parent = parent.f_back
            except:
                break
            try:
                if parent.f_locals['self'].__class__ == fava.core.FavaLedger:
                    parent.f_locals['self']._watcher = Watcher(parent.f_locals['self'])
                    break
            except:
                pass
    return entries, []

class Watcher:
    __slots__ = ["_encryption_file", "_watcher", "_decrypted"]

    def __init__(self, ledger=None) -> None:
        if ledger is None:
            try:
                ledger = inspect.currentframe().f_back.f_locals['self']
                assert ledger.__class__ == fava.core.FavaLedger
            except Exception as _e:
                lgging.error("Failed to setup encrypted watcher: %s", _e)
        path = ledger.beancount_file_path
        self._decrypted = False
        self._encryption_file = os.path.join(os.path.dirname(path), ".encrypted")
        self.is_decrypted()
        if hasattr(ledger, '_watcher'):
            self._watcher = ledger._watcher
        else:
            self._watcher = fava.core.watcher.Watcher()
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
