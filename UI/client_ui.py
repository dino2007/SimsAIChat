# UI/client_ui.py

import webview
import time
import requests
import sys
import threading
import os 
import ctypes 

SERVER_URL = "http://127.0.0.1:3000"

_global_window = None

class WindowApi:
    def show_window(self):
        if _global_window:
            if _global_window.minimized:
                _global_window.restore()
            _global_window.show()
            _global_window.on_top = False
            _global_window.on_top = True
            _global_window.restore()

    def hide_window(self):
        if _global_window:
            _global_window.hide()

    def end_session_signal(self):
        try:
            requests.post(f"{SERVER_URL}/ui/end")
        except:
            pass

    def quit_app(self):
        print("UI: Server lost. Closing application now.", flush=True)
        if _global_window:
            _global_window.destroy()
        os._exit(0) 

def on_closed():
    print("SimsAIChat UI Exited.", flush=True)
    os._exit(0) 

def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, 'UI', relative_path)
    else:
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), relative_path)

def start_ui():
    global _global_window

    try:
        myappid = 'simsaichat.ui.client.1.0' # Arbitrary unique ID
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception as e:
        print(f"UI: Could not set AppID: {e}")
    
    api = WindowApi()

    # 1. Resolve Icon Path
    icon_path = get_resource_path('icon.ico')

    # Debug: Verify path exists
    if not os.path.exists(icon_path):
        print(f"UI Warning: Icon file not found at {icon_path}")

    # 2. Create Window (Remove icon argument from here)
    _global_window = webview.create_window(
        title='SimsAIChat', 
        url=SERVER_URL, 
        width=400, 
        height=650,
        on_top=True,
        hidden=True,
        js_api=api
    )
    
    _global_window.events.closed += on_closed

    # 3. Pass Icon to Start (Place it here)
    webview.start(icon=icon_path)

if __name__ == "__main__":
    time.sleep(1)
    start_ui()