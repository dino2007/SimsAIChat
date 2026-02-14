# main.py
import threading
import sys
import os
import time
import socket 

# Package Imports
from Server import server
from UI import client_ui

# --- SINGLE INSTANCE CHECKER ---
def is_already_running():
    """
    Tries to bind to a specific 'lock port'. 
    If it fails, another instance is already running.
    """
    try:
        # We use a socket on a distinct port (e.g., 2999) as a mutex lock.
        # This is lighter than file locking and works cross-platform.
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 2999)) # Port 2999 is our 'Lock'
        return s # Keep this socket open! If we close it, the lock is released.
    except socket.error:
        return None

def run_server_thread():
    server.start_app()

if __name__ == '__main__':
    # 1. CHECK LOCK
    lock_socket = is_already_running()
    if not lock_socket:
        print("App is already running. Exiting.")
        sys.exit(0)

    # 2. Start Server
    server_thread = threading.Thread(target=run_server_thread)
    server_thread.daemon = True
    server_thread.start()

    time.sleep(1)

    # 3. Start UI
    client_ui.start_ui()