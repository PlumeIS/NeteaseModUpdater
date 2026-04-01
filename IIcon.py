import ctypes
import time
from ctypes import wintypes
from threading import Thread

import pystray
from pystray._util import win32


class IIcon(pystray.Icon):
    def __init__(self, *args, **kwargs):
        self.on_update_callable = kwargs.pop("on_update", lambda: None)
        self.on_init_callable = kwargs.pop("on_init", lambda: None)
        super().__init__(*args, **kwargs)

        def wait_init():
            time.sleep(1)
            self.on_update_callable()

        Thread(target=wait_init, daemon=True).start()

    def _mainloop(self):
        """The body of the main loop thread.

                This method retrieves all events from *Windows* and makes sure to
                dispatch clicks.
                """
        # Pump messages
        try:
            msg = wintypes.MSG()
            lpmsg = ctypes.byref(msg)
            while True:
                time.sleep(0.1)
                self.on_update_callable()
                r = win32.GetMessage(lpmsg, None, 0, 0, 1)
                if r == -1:
                    break
                else:
                    win32.TranslateMessage(lpmsg)
                    win32.DispatchMessage(lpmsg)

        except:
            self._log.error(
                'An error occurred in the main loop', exc_info=True)

        finally:
            try:
                self._hide()
                del self._HWND_TO_ICON[self._hwnd]
            except:
                # Ignore
                pass

            win32.DestroyWindow(self._hwnd)
            win32.DestroyWindow(self._menu_hwnd)
            if self._menu_handle:
                hmenu, callbacks = self._menu_handle
                win32.DestroyMenu(hmenu)
            self._unregister_class(self._atom)
