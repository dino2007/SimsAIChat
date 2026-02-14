# Scripts/sims_ai_chat_scripts/location_service.py

import services
import json
import urllib.request
from sims4communitylib.services.common_service import CommonService
from sims4communitylib.utils.common_log_registry import CommonLogRegistry
from sims4communitylib.dialogs.common_input_text_dialog import CommonInputTextDialog
from sims_ai_chat_scripts.modinfo import ModInfo

# --- NEW IMPORTS FOR CONSOLE COMMAND ---
from sims4communitylib.services.commands.common_console_command import CommonConsoleCommand
from sims4communitylib.services.commands.common_console_command_output import CommonConsoleCommandOutput

log = CommonLogRegistry.get().register_log(ModInfo.get_identity(), 'LocationService')

class SimsAILocationService(CommonService):
    def edit_location_description(self):
        """
        Opens a dialog to edit the description of the current lot.
        """
        try:
            # 1. Scrape IDs
            zone_id = services.current_zone_id()
            current_zone = services.current_zone()
            
            # Safe name retrieval
            lot_name = "Current Lot"
            if current_zone and current_zone.lot:
                lot_name = current_zone.lot.get_lot_name()

            # 2. Check Server for existing description
            existing_desc = ""
            try:
                url = "http://127.0.0.1:3000/location/get"
                data = json.dumps({"zone_id": zone_id}).encode('utf-8')
                req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
                with urllib.request.urlopen(req) as response:
                     resp_data = json.loads(response.read().decode('utf-8'))
                     existing_desc = resp_data.get("description", "")
            except Exception as e:
                log.error("Failed to fetch existing description", exception=e)
                existing_desc = ""

            # 3. Prepare Dialog Info
            status_text = "Described" if existing_desc else "Undescribed"
            description_msg = (
                f"You are modifying: {lot_name}\n"
                f"Status: {status_text}\n\n"
                f"Enter a brief visual description (approx 25 words). "
                f"The AI will use this to understand where it is."
            )

            # 4. Show Dialog
            dialog = CommonInputTextDialog(
                ModInfo.get_identity(),
                title_identifier=f"Edit Location: {lot_name}",
                description_identifier=description_msg,
                initial_value=existing_desc
            )

            dialog.show(
                on_submit=lambda value, outcome: self._on_description_submitted(zone_id, value, outcome)
            )

        except Exception as e:
            log.error("Error in edit_location_description", exception=e)

    def _on_description_submitted(self, zone_id, value, outcome):
        # outcome is CommonChoiceOutcome
        if not value or value.strip() == "":
            return

        try:
            # 5. Send Update to Server
            url = "http://127.0.0.1:3000/location/update"
            payload = {
                "zone_id": zone_id,
                "description": value
            }
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req)
            log.debug(f"Updated description for zone {zone_id}")
        except Exception as e:
            log.error("Failed to save description to server", exception=e)

# --- NEW CONSOLE COMMAND PLACED HERE (OUTSIDE THE CLASS) ---

@CommonConsoleCommand(ModInfo.get_identity(), 'ai_loc_info', 'Prints IDs for the current location.')
def _print_location_ids(output: CommonConsoleCommandOutput):
    try:
        # Get the current zone (Lot)
        zone = services.current_zone()
        zone_id = zone.id
        
        # Get the Neighborhood (Open Street ID)
        neighborhood_id = zone.neighborhood_id
        
        # Get the World ID via Persistence Service (FIXED LOGIC)
        persistence_service = services.get_persistence_service()
        world_id = 0
        if persistence_service:
            # We get World ID from the ZONE proto, not the Neighborhood proto
            zone_proto = persistence_service.get_zone_proto_buff(zone_id)
            if zone_proto:
                world_id = zone_proto.world_id
        
        output(f"--- LOCATION IDs ---")
        output(f"World ID: {world_id}")
        output(f"Neighborhood ID: {neighborhood_id}")
        output(f"Zone (Lot) ID: {zone_id}")
        
    except Exception as e:
        output(f"Error retrieving IDs: {e}")