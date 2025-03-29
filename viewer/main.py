import asyncio
import sys

import qasync
from PySide6.QtWidgets import QApplication

from utils import logcfg
from .ui import ImageViewer


async def main_async():
    """
    Main coroutine. We create the QApplication + ImageViewer, show it,
    and let the event loop run via qasync.
    """
    viewer = ImageViewer()
    viewer.show()
    # Optionally do an initial empty search or something here:
    await asyncio.sleep(0)
    await viewer.search_and_update_gallery()


def main():
    """
    Standard if __name__ == '__main__': approach to run the app with qasync.
    """
    logcfg.apply()
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(main_async())
        loop.run_forever()
    finally:
        loop.close()


if __name__ == "__main__":
    main()
