"""Application bootstrap: single instance, wiring, shutdown."""
from __future__ import annotations

import logging
import sys

from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from . import __version__, autostart
from .config import load_settings
from .engine import Sampler
from .paths import log_path
from .rollup import rebuild_day
from .storage import Store, day_key
from .tariff import TariffEngine
from .ui import icons, theme
from .ui.context import AppContext
from .ui.main_window import MainWindow
from .ui.tray import Tray

log = logging.getLogger(__name__)

SERVER_NAME = "PowerWatcher.SingleInstance"


class SingleInstance:
    """Named-pipe guard: a second launch just raises the existing window."""

    def __init__(self, key: str = SERVER_NAME) -> None:
        self.key = key
        self.server: QLocalServer | None = None
        self.on_show = None

    def acquire(self) -> bool:
        probe = QLocalSocket()
        probe.connectToServer(self.key)
        if probe.waitForConnected(150):
            probe.write(b"show")
            probe.waitForBytesWritten(300)
            probe.disconnectFromServer()
            return False

        QLocalServer.removeServer(self.key)
        self.server = QLocalServer()
        self.server.newConnection.connect(self._on_connection)
        self.server.listen(self.key)
        return True

    def _on_connection(self) -> None:
        while self.server and self.server.hasPendingConnections():
            conn = self.server.nextPendingConnection()
            if conn:
                conn.readyRead.connect(lambda c=conn: c.readAll())
                conn.disconnectFromServer()
        if self.on_show:
            self.on_show()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    background = "--background" in argv
    argv = [a for a in argv if not a.startswith("--")]

    logging.basicConfig(
        filename=str(log_path()),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )
    log.info("starting PowerWatcher %s", __version__)

    QApplication.setApplicationName("PowerWatcher")
    QApplication.setOrganizationName("PowerWatcher")
    app = QApplication(argv)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLESHEET)
    app.setWindowIcon(icons.app_icon())
    app.setQuitOnLastWindowClosed(False)

    instance = SingleInstance()
    if not instance.acquire():
        log.info("another instance is running, asking it to show")
        return 0

    settings = load_settings()
    store = Store()
    engine = TariffEngine(settings.tariff)

    # A past day may have been closed before its rollup ran.
    try:
        rebuild_day(store, engine, day_key(int(__import__("time").time())), settings.hardware)
    except Exception:
        log.exception("startup rollup failed")

    sampler = Sampler(store, settings, engine)
    ctx = AppContext(store=store, settings=settings, engine=engine, sampler=sampler)

    window = MainWindow(ctx)
    tray = Tray(ctx, window)
    instance.on_show = window.show_from_tray

    sampler.ticked.connect(window.on_tick)
    sampler.ticked.connect(tray.on_tick)
    sampler.flushed.connect(lambda _day: tray.refresh())

    if settings.autostart and not autostart.is_enabled():
        if not autostart.set_enabled(True):
            log.warning("could not register autostart")

    def shutdown() -> None:
        log.info("shutting down")
        sampler.stop()
        tray.hide()
        store.close()
        app.quit()

    tray.quit_requested.connect(shutdown)
    app.aboutToQuit.connect(lambda: sampler.stop())

    sampler.start()

    # Started by the login entry -> stay in the tray. Launched by hand -> show
    # the window, otherwise a double-click appears to do nothing.
    if background and QSystemTrayIcon.isSystemTrayAvailable():
        window.hide()
    else:
        window.show()

    code = app.exec()
    log.info("exit %s", code)
    return code
