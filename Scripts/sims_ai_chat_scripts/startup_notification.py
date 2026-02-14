# Scripts/sims_ai_chat_scripts/startup_notification.py

from sims4.resources import Types
from sims4communitylib.events.event_handling.common_event_registry import CommonEventRegistry
from sims4communitylib.events.zone_spin.events.zone_late_load import S4CLZoneLateLoadEvent
from sims4communitylib.notifications.common_basic_notification import CommonBasicNotification
from sims4communitylib.utils.common_resource_utils import CommonResourceUtils
from distributor.shared_messages import IconInfoData
from sims_ai_chat_scripts.modinfo import ModInfo

class SimsAIStartupNotificationListener:
    # Flag to ensure we only show this once per game session
    _HAS_SHOWN_NOTIFICATION = False

    @staticmethod
    @CommonEventRegistry.handle_events(ModInfo.get_identity().name)
    def handle_zone_late_load(event_data: S4CLZoneLateLoadEvent):
        # 1. Check if we have already shown the notification
        if SimsAIStartupNotificationListener._HAS_SHOWN_NOTIFICATION:
            return

        # 2. Mark as shown immediately
        SimsAIStartupNotificationListener._HAS_SHOWN_NOTIFICATION = True

        # 3. Show the Notification
        SimsAIStartupNotificationListener._show_startup_notification()

    @staticmethod
    def _show_startup_notification():
        # Title and Description (Raw strings are accepted by S4CL)
        title = "SimsAIChat Ready"
        description = "Make sure your game is in Windowed Fullscreen, or you won't see me!"
        
        # Create Notification Object
        notification = CommonBasicNotification(
            title,
            description
        )

        try:
            # Construct the Custom Icon Key using S4CL Utility
            # Type: PNG
            # Instance: 0x00000000A7C03E84 (Your custom icon ID)
            custom_icon_key = CommonResourceUtils.get_resource_key(Types.PNG, 0x00000000A7C03E84)
            
            # Create Icon Data wrapper required by S4CL
            icon_data = IconInfoData(icon_resource=custom_icon_key)
            
            # Show with Icon
            notification.show(icon=icon_data)
            
        except Exception as e:
            # Fallback: Show notification without icon if resource fails
            notification.show()