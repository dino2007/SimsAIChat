# Scripts/sims_ai_chat_scripts/heartbeat_service.py

import urllib.request
import threading
import time
from sims4communitylib.services.common_service import CommonService
from sims4communitylib.events.event_handling.common_event_registry import CommonEventRegistry
from sims4communitylib.events.zone_spin.events.zone_late_load import S4CLZoneLateLoadEvent
from sims_ai_chat_scripts.modinfo import ModInfo

class SimsAIHeartbeatService(CommonService):
    def __init__(self):
        self._is_running = False
        self._thread = None

    def start_heartbeat(self):
        if self._is_running: return
        
        self._is_running = True
        self._thread = threading.Thread(target=self._heartbeat_loop)
        # Daemon threads die automatically when the main process (The Sims 4) quits
        self._thread.setDaemon(True) 
        self._thread.start()

    def stop_heartbeat(self):
        self._is_running = False

    def _heartbeat_loop(self):
        url = "http://127.0.0.1:3000/system/heartbeat"
        while self._is_running:
            try:
                # Send Pulse (Timeout is important so it doesn't hang)
                req = urllib.request.Request(url, method='POST')
                with urllib.request.urlopen(req, timeout=2) as _:
                    pass
            except:
                # Server might be down or starting up; ignore errors silently
                pass
            
            # Sleep 5 seconds (Real time)
            time.sleep(5)

# --- REGISTER LIFECYCLE HOOK (S4CL Compliant) ---
class SimsAIHeartbeatListener:
    @staticmethod
    @CommonEventRegistry.handle_events(ModInfo.get_identity().name)
    def handle_zone_late_load(event_data: S4CLZoneLateLoadEvent):
        # Triggered when a lot finishes loading
        SimsAIHeartbeatService.get().start_heartbeat()
        return True