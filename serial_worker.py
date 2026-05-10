from __future__ import annotations

import serial
import serial.tools.list_ports
from queue import Queue, Empty
from PyQt6.QtCore import QThread, pyqtSignal


def list_ports() -> list[str]:
    """Return sorted list of available COM port device strings."""
    return sorted(p.device for p in serial.tools.list_ports.comports())


class SerialWorker(QThread):
    """Background thread that owns the serial port.

    Continuously reads newline-terminated lines and emits them as signals.
    Commands are queued from the main thread and sent on the next loop tick.
    """

    line_received = pyqtSignal(str)        # every complete line from Arduino
    connection_changed = pyqtSignal(bool)  # True = connected, False = dropped
    error_occurred = pyqtSignal(str)       # human-readable error text

    BAUD = 250_000

    def __init__(self, port: str, parent=None) -> None:
        super().__init__(parent)
        self.port = port
        self._running = False
        self._write_queue: Queue[str] = Queue()
        self._ser: serial.Serial | None = None

    # ------------------------------------------------------------------
    # Public API (called from main thread)
    # ------------------------------------------------------------------

    def send(self, command: str) -> None:
        """Queue a command to be written to the serial port."""
        self._write_queue.put(command.strip().upper())

    def stop(self) -> None:
        """Signal the thread to stop and wait for it to finish."""
        self._running = False
        self.wait(3000)

    # ------------------------------------------------------------------
    # Thread body
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._ser = serial.Serial(
                self.port,
                self.BAUD,
                timeout=0.05,   # short read timeout keeps the loop responsive
            )
        except serial.SerialException as exc:
            self.error_occurred.emit(f"Cannot open {self.port}: {exc}")
            return

        self._running = True
        self.connection_changed.emit(True)

        try:
            while self._running:
                # --- send any queued commands ---
                try:
                    cmd = self._write_queue.get_nowait()
                    self._ser.write((cmd + "\n").encode("utf-8"))
                except Empty:
                    pass

                # --- read one line if available ---
                try:
                    raw = self._ser.readline()
                    if raw:
                        line = raw.decode("utf-8", errors="replace").strip()
                        if line:
                            self.line_received.emit(line)
                except serial.SerialException as exc:
                    self.error_occurred.emit(f"Read error on {self.port}: {exc}")
                    break

        finally:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._running = False
            self.connection_changed.emit(False)
