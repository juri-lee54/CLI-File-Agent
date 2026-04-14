import os
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


class NewFileHandler(FileSystemEventHandler):

    def __init__(self, callback, watch_root: str):
        self.callback = callback
        self.watch_root = os.path.abspath(os.path.realpath(watch_root))

    def _is_direct_child_path(self, path: str) -> bool:
        if not path:
            return False
        name = os.path.basename(path)
        if name.startswith(".") or name.endswith("~"):
            return False
        parent = os.path.dirname(os.path.abspath(path))
        return parent == self.watch_root

    def on_created(self, event):
        if event.is_directory:
            return
        if self._is_direct_child_path(event.src_path):
            self.callback(event.src_path)

    def on_moved(self, event):
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", None) or ""
        if self._is_direct_child_path(dest):
            self.callback(dest)


def start_watching(path: str, callback):
    root = os.path.abspath(os.path.realpath(path))
    event_handler = NewFileHandler(callback, root)
    observer = Observer()
    observer.schedule(event_handler, root, recursive=False)
    observer.start()
    return observer
