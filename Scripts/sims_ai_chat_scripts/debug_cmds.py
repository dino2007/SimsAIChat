# Scripts/sims_ai_chat_scripts/debug_cmds.py

import os
import services
import sims4.resources
from sims4communitylib.services.commands.common_console_command import CommonConsoleCommand
from sims4communitylib.services.commands.common_console_command_output import CommonConsoleCommandOutput
from sims4communitylib.utils.sims.common_sim_utils import CommonSimUtils
from sims4communitylib.utils.sims.common_buff_utils import CommonBuffUtils # <--- Import for ID extraction
from sims4communitylib.utils.sims.common_sim_genealogy_utils import CommonSimGenealogyUtils
from sims4communitylib.utils.sims.common_relationship_utils import CommonRelationshipUtils
from sims4communitylib.utils.common_log_registry import CommonLogRegistry
from sims_ai_chat_scripts.modinfo import ModInfo

log = CommonLogRegistry.get().register_log(ModInfo.get_identity(), 'DebugCmds')

# --- STEP 1: GLOBAL EXTRACTOR (UPDATED) ---
@CommonConsoleCommand(ModInfo.get_identity(), 'ai_dump_buffs', 'Extracts ALL game buffs with Decimal IDs to a text file.')
def _ai_dump_all_buffs(output: CommonConsoleCommandOutput):
    output("Starting Global Buff Dump... this may take a moment.")
    
    # Get the Instance Manager for Buffs
    buff_manager = services.get_instance_manager(sims4.resources.Types.BUFF)
    
    results = []
    
    # Iterate through every loaded buff in the game
    for resource_key, buff_type in buff_manager.types.items():
        try:
            # 1. Get Decimal ID using S4CL
            decimal_id = CommonBuffUtils.get_buff_id(buff_type)
            
            # Skip if valid ID not found
            if not decimal_id:
                continue

            # 2. Get Metadata
            name = buff_type.__name__
            visible = getattr(buff_type, 'visible', False)
            
            mood_type = getattr(buff_type, 'mood_type', None)
            mood_name = mood_type.__name__ if mood_type else "None"
            
            # 3. Format Entry
            # Format: 12345: ("BuffName", "Mood"), # Visible: True
            entry = f"{decimal_id}: (\"{name}\", \"{mood_name}\"), # Visible: {visible}"
            results.append(entry)
            
        except Exception as e:
            # Silently skip broken buffs to prevent crash
            continue

    # Sort by ID for tidiness
    # (Or sort by Name if you prefer: results.sort(key=lambda x: x.split('"')[1]))
    results.sort()

    # Write to file in Mods folder
    base_path = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4', 'Mods')
    file_path = os.path.join(base_path, 'all_game_buffs_decimal.txt')
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("# FORMAT: DECIMAL_ID: (\"Name\", \"Mood\")\n")
            f.write("MOODLET_LOOKUP = {\n")
            f.write('\n'.join(results))
            f.write("\n}")
        output(f"Dump successful! Saved to: {file_path}")
    except Exception as e:
        output(f"Could not write file to {file_path}. Error: {e}")


# --- STEP 2: TARGET SIM BUFF INSPECTOR ---
@CommonConsoleCommand(ModInfo.get_identity(), 'ai_sim_buffs', 'Inspect active sim moodlets.')
def _ai_inspect_sim_buffs(output: CommonConsoleCommandOutput):
    sim_info = CommonSimUtils.get_active_sim_info()
    if not sim_info:
        output("No active sim.")
        return

    output(f"--- Inspecting {sim_info} ---")
    
    # S4CL Utility to get active buffs
    buffs = CommonBuffUtils.get_buffs(sim_info)
    
    results = []
    
    for buff in buffs:
        # Try to get ID via S4CL first, then native fallback
        buff_id = getattr(buff, 'guid64', None)
        if not buff_id and hasattr(buff, 'buff_type'):
            buff_id = getattr(buff.buff_type, 'guid64', None)

        # Name
        buff_name = buff.__class__.__name__
        if hasattr(buff, 'buff_type'):
            buff_name = buff.buff_type.__name__
            
        # Mood
        mood_name = "None"
        if hasattr(buff, 'mood_type') and buff.mood_type:
            mood_name = buff.mood_type.__name__
        elif hasattr(buff, 'buff_type') and hasattr(buff.buff_type, 'mood_type') and buff.buff_type.mood_type:
             mood_name = buff.buff_type.mood_type.__name__

        entry = f"ID: {buff_id} | Name: {buff_name} | Mood: {mood_name}"
        results.append(entry)

    # Write to file
    base_path = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4', 'Mods')
    file_path = os.path.join(base_path, 'sim_buff_snapshot.txt')
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
             f.write('\n'.join(results))
        output(f"Snapshot saved to: {file_path}")
    except:
        output("Could not write file. Printing to console:")
        for r in results:
            output(r)

# --- STEP 3: SOCIAL DIAGNOSTIC ---
@CommonConsoleCommand(ModInfo.get_identity(), 'ai_social_dump', 'Dump social/relationship info to file.')
def _ai_dump_social(output: CommonConsoleCommandOutput):
    sim_info = CommonSimUtils.get_active_sim_info()
    if not sim_info:
        output("No active sim.")
        return

    output(f"Dumping social info for {sim_info}...")
    
    logs = []
    logs.append(f"--- SOCIAL DUMP FOR: {sim_info} ---")

    # 1. GENEALOGY
    try:
        kids = list(CommonSimGenealogyUtils.get_children_sim_ids(sim_info))
        logs.append(f"Children IDs: {kids}")
    except Exception as e:
        logs.append(f"Genealogy Error: {e}")

    # 2. RELATIONSHIPS
    try:
        logs.append("\n--- RELATIONSHIP BITS ---")
        check_bits = {
            15822: "Spouse",
            15816: "Engaged",
            15825: "Sig. Other"
        }
        for bit_id, label in check_bits.items():
            sims = list(CommonRelationshipUtils.get_sim_info_of_all_sims_with_relationship_bit_to_sim(sim_info, bit_id))
            if sims:
                names = [str(s) for s in sims]
                logs.append(f"Found {label} ({bit_id}): {names}")
            else:
                logs.append(f"No {label} ({bit_id}) found.")
                    
    except Exception as e:
        logs.append(f"Relationship Error: {e}")

    base_path = os.path.join(os.path.expanduser('~'), 'Documents', 'Electronic Arts', 'The Sims 4', 'Mods')
    file_path = os.path.join(base_path, 'debug_social_dump.txt')
    
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(logs))
        output(f"Dump saved to: {file_path}")
    except Exception as e:
        output(f"Write failed: {e}")

# --- RESIDENCE TEST COMMAND ---
@CommonConsoleCommand(ModInfo.get_identity(), 'ai_my_home', 'Test fetching residence info.')
def _ai_test_residence(output: CommonConsoleCommandOutput):
    """
    Prints the World and Lot name of the active Sim's residence.
    """
    sim_info = CommonSimUtils.get_active_sim_info()
    if not sim_info:
        output("No active sim found.")
        return

    output(f"Checking residence for: {sim_info}")

    # 1. Check Household
    if sim_info.household is None:
        output("Sim has no household data.")
        return

    home_zone_id = sim_info.household.home_zone_id
    if home_zone_id == 0:
        output("Result: Currently Homeless (No Home Zone).")
        return

    # 2. Get Persistence Service
    persistence_service = services.get_persistence_service()
    if persistence_service is None:
        output("Error: Persistence Service unavailable.")
        return

    # 3. Get Zone Data (Lot Name)
    zone_proto = persistence_service.get_zone_proto_buff(home_zone_id)
    if zone_proto is None:
        output(f"Error: No zone data found for ID {home_zone_id}")
        return
        
    lot_name = zone_proto.name

    # 4. Get Neighborhood Data (World Name)
    neighborhood_id = zone_proto.neighborhood_id
    neighborhood_proto = persistence_service.get_neighborhood_proto_buff(neighborhood_id)
    
    world_name = "Unknown World"
    if neighborhood_proto is not None:
        world_name = neighborhood_proto.name

    # 5. Output Result
    result_str = f"Lives in {world_name}, {lot_name}"
    output(f"SUCCESS: {result_str}")