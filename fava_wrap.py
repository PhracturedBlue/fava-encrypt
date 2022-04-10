#!/usr/bin/env python3
import inotify.adapters
import os
import sys
import time

MOUNT_DIR = "/tmp/.beancount"
WATCH_DIR = DIRECTORY
WATCH_FILE = f"{WATCH_DIR}/.encrypted"
def do_exec():
    print(f"Checking for {WATCH_FILE}")
    if os.path.exists(WATCH_FILE):
        print(f"Found {WATCH_FILE}.  Starting fava")
        os.execvp("fava", ["fava"] + sys.argv[1:])
        print("Exec failed")
        sys.exit(1)

def _main():
    while True:
        i = inotify.adapters.Inotify()
        i.add_watch(MOUNT_DIR)
        do_exec()
        try:
            for event in i.event_gen(yield_nones=False):
                (_, type_names, path, filename) = event
                print(f"Got event: {event}")
                do_exec()
        except inotify.adapters.TerminalEventException:
            print(f"Got unexpected exception.  Restarting watcher")
            time.sleep(0.5)
if __name__ == '__main__':
    _main()


