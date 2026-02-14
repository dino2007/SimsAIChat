# Scripts/sims_ai_chat_scripts/chat_service.py

import json
import urllib.request
import threading
import time
import os 
import services
import sims4.resources
from sims4communitylib.utils.common_time_utils import CommonTimeUtils
from sims4communitylib.services.common_service import CommonService
from sims4communitylib.utils.common_log_registry import CommonLogRegistry
from sims4communitylib.services.commands.common_console_command import CommonConsoleCommand
from sims4communitylib.services.commands.common_console_command_output import CommonConsoleCommandOutput
from sims4communitylib.utils.sims.common_sim_utils import CommonSimUtils
from sims4communitylib.utils.sims.common_sim_genealogy_utils import CommonSimGenealogyUtils
from sims4communitylib.utils.sims.common_gender_utils import CommonGenderUtils
from sims_ai_chat_scripts.modinfo import ModInfo
from sims_ai_chat_scripts.trait_data import TRAIT_LOOKUP

# --- IMPORTS ---
from sims_ai_chat_scripts.moodlet_data import MOODLET_LOOKUP
from sims_ai_chat_scripts.context_buff_data import CONTEXT_BUFF_LOOKUP
from sims4communitylib.utils.sims.common_buff_utils import CommonBuffUtils 

# --- S4CL UTILITIES ---
from sims4communitylib.utils.sims.common_sim_name_utils import CommonSimNameUtils
from sims4communitylib.utils.sims.common_mood_utils import CommonMoodUtils
from sims4communitylib.utils.sims.common_trait_utils import CommonTraitUtils
from sims4communitylib.utils.sims.common_relationship_utils import CommonRelationshipUtils
from sims4communitylib.utils.sims.common_age_utils import CommonAgeUtils
from sims4communitylib.utils.sims.common_species_utils import CommonSpeciesUtils
from sims4communitylib.utils.sims.common_sim_skill_utils import CommonSimSkillUtils

log = CommonLogRegistry.get().register_log('SimsAIChat', 'ChatService')

class SimsAIChatService(CommonService):
    def __init__(self):
        self._polling_thread = None
        self._is_polling = False
        self.current_targets = [] # Stores SimInfo objects for re-scraping

    # ------------------------------------------------------------------
    # 1. CHAT SESSIONS
    # ------------------------------------------------------------------

    def start_chat_session(self, target_sim_info):
        try:
            # 1. Save Target for Dynamic Updates
            target_sim_info = CommonSimUtils.get_sim_info(target_sim_info)
            self.current_targets = [target_sim_info] 

            # 2. Initial Scrape
            active_sim_info = CommonSimUtils.get_active_sim_info()
            player_profile = self._scrape_player_profile(active_sim_info)
            location_data = self._scrape_location_data()
            time_data = self._scrape_time_context()

            target_profile = self._scrape_sim_profile(target_sim_info, active_sim_info)

            context_payload = target_profile.copy() 
            context_payload["sim_name"] = target_profile["name"]
            context_payload["player_sim"] = player_profile
            context_payload["location"] = location_data
            context_payload["time_context"] = time_data
            context_payload["mode"] = "SINGLE"

            self._send_payload(context_payload)

        except Exception as e:
            log.error("Failed to start session", exception=e)
            CommonTimeUtils.set_game_speed_normal()

    def start_group_chat_session(self, target_sims_list):
        try:
            # 1. Save Targets
            self.current_targets = [CommonSimUtils.get_sim_info(t) for t in target_sims_list]

            # 2. Initial Scrape
            active_sim_info = CommonSimUtils.get_active_sim_info()
            player_profile = self._scrape_player_profile(active_sim_info)
            location_data = self._scrape_location_data()
            time_data = self._scrape_time_context()

            participants_data = []
            participant_names = []

            # 3. Scrape each Sim, passing the REST of the group for relationship checks
            for target in self.current_targets:
                # Create a list of 'other' sims (excluding the current target)
                other_sims = [t for t in self.current_targets if t is not target]
                
                profile = self._scrape_sim_profile(target, active_sim_info, other_sims)
                participants_data.append(profile)
                participant_names.append(profile['name'].split()[0])

            if len(participant_names) > 3: display_name = "Group Chat"
            else: display_name = ", ".join(participant_names)

            context_payload = {
                "mode": "GROUP",
                "sim_name": display_name,
                "player_sim": player_profile,
                "location": location_data,
                "time_context": time_data,
                "participants": participants_data
            }

            self._send_payload(context_payload)

        except Exception as e:
            log.error("Failed to start group session", exception=e)
            CommonTimeUtils.set_game_speed_normal()

    # ------------------------------------------------------------------
    # 2. DYNAMIC UPDATE LOGIC (NEW)
    # ------------------------------------------------------------------
    def _perform_context_update(self):
        """ Re-scrapes current targets and sends update to server. """
        try:
            log.debug("Performing Context Update...")
            
            # 1. Force Pause (Requested Requirement)
            CommonTimeUtils.pause_the_game()

            active_sim_info = CommonSimUtils.get_active_sim_info()
            
            # 2. Re-Scrape Environment
            update_payload = {
                "location": self._scrape_location_data(),
                "time_context": self._scrape_time_context(),
                "participants": [] # List of updated profiles
            }

            # 3. Re-Scrape Sims
            for target in self.current_targets:
                # Ensure sim is still valid
                if target:
                    # --- FIX: Define the peer group for this target ---
                    other_sims = [t for t in self.current_targets if t is not target]
                    
                    # --- FIX: Pass other_sims to the scraper ---
                    profile = self._scrape_sim_profile(target, active_sim_info, other_sims)
                    
                    update_payload["participants"].append(profile)

            # 4. Send to UPDATE endpoint
            url = "http://127.0.0.1:3000/game/update"
            data = json.dumps(update_payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            urllib.request.urlopen(req)
            log.debug("Context Update Sent.")

        except Exception as e:
            log.error("Failed to update context", exception=e)

    # ------------------------------------------------------------------
    # 3. POLLING LOOP
    # ------------------------------------------------------------------
    def _start_polling_thread(self):
        if self._polling_thread is not None and self._polling_thread.is_alive():
            self._is_polling = False
            time.sleep(0.5)
        self._is_polling = True
        self._polling_thread = threading.Thread(target=self._poll_server_loop)
        self._polling_thread.setDaemon(True) 
        self._polling_thread.start()

    def _poll_server_loop(self):
        url = "http://127.0.0.1:3000/game/status"
        while self._is_polling:
            try:
                time.sleep(0.5) # Poll frequently for responsiveness
                with urllib.request.urlopen(url) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    command = data.get("command")
                    
                    if command == "RESUME":
                        self._resume_game()
                        break
                    
                    elif command == "SCRAPE":
                        # Server needs fresh data before replying
                        self._perform_context_update()

            except:
                # Connection lost or server restarting
                time.sleep(2) 

    def _resume_game(self):
        self._is_polling = False
        self.current_targets = [] # Clear memory
        CommonTimeUtils.set_game_speed_normal()

    # ------------------------------------------------------------------
    # 4. SCRAPING HELPERS (Existing)
    # ------------------------------------------------------------------
    def _scrape_sim_profile(self, target_sim_info, active_sim_info, other_sims=None):
        target_sim_info = CommonSimUtils.get_sim_info(target_sim_info)
        sim_id = CommonSimUtils.get_sim_id(target_sim_info)
           
        general_traits = []
        gender_orientation_traits = []
        preference_traits = []
        GENDER_CATEGORIES = {"ORIENTATION", "IDENTITY", "BIOLOGY", "RELATIONSHIP_STYLE"}
        PREFERENCE_CATEGORIES = {"PREFERENCE"} 

        if hasattr(target_sim_info, 'trait_tracker'):
            for trait in target_sim_info.trait_tracker.equipped_traits:
                guid = getattr(trait, 'guid64', None)
                match = TRAIT_LOOKUP.get(guid)
                if match:
                    trait_name, trait_category = match
                    if trait_category in GENDER_CATEGORIES: gender_orientation_traits.append(trait_name)
                    elif trait_category in PREFERENCE_CATEGORIES: preference_traits.append(trait_name)
                    else: general_traits.append(trait_name)
        
        if not general_traits: general_traits.append("Unknown Personality")
        if not gender_orientation_traits: gender_orientation_traits.append("Standard")
        if not preference_traits: preference_traits.append("No strong preferences")

        active_moodlet_descriptions = [] 
        active_activity_descriptions = [] 
        sim_buffs = list(CommonBuffUtils.get_buffs(target_sim_info))
        if not sim_buffs and hasattr(target_sim_info, 'Buffs'):
             sim_buffs = list(target_sim_info.Buffs)
        
        for buff in sim_buffs:
            buff_id = getattr(buff, 'guid64', None)
            if not buff_id and hasattr(buff, 'buff_type'):
                buff_id = getattr(buff.buff_type, 'guid64', None)
            
            if buff_id in MOODLET_LOOKUP:
                desc = MOODLET_LOOKUP[buff_id]
                active_moodlet_descriptions.append(desc[0] if isinstance(desc, tuple) else desc)
            if buff_id in CONTEXT_BUFF_LOOKUP:
                raw_desc = CONTEXT_BUFF_LOOKUP[buff_id]
                is_redundant = False
                for trait in general_traits:
                    if trait.lower() in raw_desc.lower():
                        is_redundant = True
                        break
                if not is_redundant:
                    active_activity_descriptions.append(raw_desc)

        moodlets_str = "; ".join(active_moodlet_descriptions) if active_moodlet_descriptions else "No specific emotional thoughts."
        activity_str = "; ".join(active_activity_descriptions) if active_activity_descriptions else "Idle / No specific action."

        sim_name = CommonSimNameUtils.get_full_name(target_sim_info)
        mood_name = self._get_mood_string(target_sim_info)
        career_str = self._get_career_string(target_sim_info)
        skills_str = self._get_top_skills(target_sim_info, limit=7)
        social_status_str = self._get_social_status_string(target_sim_info)
        
        age_name = str(CommonAgeUtils.get_age(target_sim_info)).split('.')[-1].title()
        species_name = str(CommonSpeciesUtils.get_species(target_sim_info)).split('.')[-1].title()

        # --- NEW: RESIDENCE EXTRACTION ---
        residence_str = "Looking for the home to move in."
        try:
            if target_sim_info.household and target_sim_info.household.home_zone_id != 0:
                p_service = services.get_persistence_service()
                if p_service:
                    home_zone_id = target_sim_info.household.home_zone_id
                    zone_proto = p_service.get_zone_proto_buff(home_zone_id)
                    
                    if zone_proto:
                        lot_name = zone_proto.name
                        
                        # Get World Name
                        neighborhood_id = zone_proto.neighborhood_id
                        neigh_proto = p_service.get_neighborhood_proto_buff(neighborhood_id)
                        world_name = neigh_proto.name if neigh_proto else "Unknown World"
                        
                        residence_str = f"{world_name}, {lot_name}"
        except Exception as e:
            # Fallback in case of error, keeping original flow safe
            pass

        # --- RELATIONSHIPS WITH PLAYER ---
        friendship = CommonRelationshipUtils.get_friendship_level(target_sim_info, active_sim_info)
        romance = CommonRelationshipUtils.get_romance_level(target_sim_info, active_sim_info)

        # --- NEW: RELATIONSHIPS WITH CAST MEMBERS ---
        cast_relations = []
        if other_sims:
            for peer in other_sims:
                p_name = CommonSimNameUtils.get_full_name(peer).split()[0] # First name only
                p_friend = CommonRelationshipUtils.get_friendship_level(target_sim_info, peer)
                p_romance = CommonRelationshipUtils.get_romance_level(target_sim_info, peer)
                
                # Only include significant relationships to save tokens
                if p_friend != 0 or p_romance != 0:
                    cast_relations.append({
                        "name": p_name,
                        "friend": p_friend,
                        "romance": p_romance
                    })

        return {
            "sim_id": sim_id,
            "name": sim_name,
            "demographics": f"{age_name} {species_name}",
            "residence": residence_str, 
            "mood_id": mood_name,
            "social_status": social_status_str,
            "active_moodlets": moodlets_str,
            "active_activity": activity_str,
            "traits": general_traits,             
            "gender_options": gender_orientation_traits, 
            "preferences": preference_traits,
            "skills": skills_str,
            "career": career_str,
            "relationship_with_player": {
                "friendship": friendship,
                "romance": romance
            },
            "relationship_with_cast": cast_relations # <--- New Data Field
        }

    def _scrape_time_context(self):
        try:
            date_and_time = CommonTimeUtils.get_current_date_and_time()
            day_index = CommonTimeUtils.get_day_of_week(date_and_time)
            days_map = {0: "Sunday", 1: "Monday", 2: "Tuesday", 3: "Wednesday", 4: "Thursday", 5: "Friday", 6: "Saturday"}
            day_str = days_map.get(day_index, "Unknown Day")

            hour_24 = CommonTimeUtils.get_current_hour(date_and_time)
            minute = CommonTimeUtils.get_current_minute(date_and_time)
            
            period = "AM"
            hour_12 = hour_24
            if hour_24 >= 12:
                period = "PM"
                if hour_24 > 12: hour_12 = hour_24 - 12
            elif hour_24 == 0: hour_12 = 12

            time_str = f"{hour_12}:{minute:02d} {period}"

            season_str = "Standard"
            season_service = services.season_service()
            if season_service is not None:
                current_season = season_service.season
                season_str = str(current_season).split('.')[-1].title()

            return f"{day_str}, {time_str}, {season_str}"

        except Exception as e:
            return "Time Unknown"

    def _scrape_player_profile(self, active_sim_info):
        player_gender = "Unknown"
        if CommonGenderUtils.is_male(active_sim_info): player_gender = "Male"
        elif CommonGenderUtils.is_female(active_sim_info): player_gender = "Female"

        player_age = "Sim"
        if CommonAgeUtils.is_teen(active_sim_info): player_age = "Teen"
        elif CommonAgeUtils.is_young_adult(active_sim_info): player_age = "Young Adult"
        elif CommonAgeUtils.is_mature_adult(active_sim_info): player_age = "Adult"
        elif CommonAgeUtils.is_elder(active_sim_info): player_age = "Elder"
        elif CommonAgeUtils.is_child(active_sim_info): player_age = "Child"
        
        sim_id = CommonSimUtils.get_sim_id(active_sim_info)
        
        return {
            "sim_id": sim_id,
            "name": CommonSimNameUtils.get_full_name(active_sim_info),
            "gender": player_gender,
            "age": player_age
        }

    def _scrape_location_data(self):
        current_zone = services.current_zone()
        zone_id = current_zone.id
        raw_val_a = current_zone.neighborhood_id 
        persistence_service = services.get_persistence_service()
        raw_val_b = 0
        if persistence_service:
            zone_proto = persistence_service.get_zone_proto_buff(zone_id)
            if zone_proto: raw_val_b = zone_proto.world_id 
        
        return {
            "zone_id": zone_id,
            "world_id": raw_val_a,        
            "neighborhood_id": raw_val_b, 
            "lot_name": current_zone.lot.get_lot_name() if current_zone.lot else "Unknown"
        }

    def _send_payload(self, payload):
        log.debug(f"Payload Mode: {payload.get('mode')}")
        CommonTimeUtils.pause_the_game()
        url = "http://127.0.0.1:3000/game/init"
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
        urllib.request.urlopen(req)
        self._start_polling_thread()

    def _get_social_status_string(self, target_sim_info):
        try:
            status_parts = []
            partners_gen = CommonRelationshipUtils.get_sim_info_of_all_sims_romantically_committed_to_generator(
                target_sim_info, instanced_only=False)
            partners = list(partners_gen)

            if not partners:
                status_parts.append("Single")
            else:
                partner_names = [CommonSimNameUtils.get_full_name(p) for p in partners]
                status_parts.append(f"In a committed relationship with {', '.join(partner_names)}")

            kids_names = []
            is_male = CommonGenderUtils.is_male(target_sim_info)
            all_sims_gen = CommonSimUtils.get_sim_info_for_all_sims_generator()

            for potential_child in all_sims_gen:
                if potential_child is target_sim_info: continue
                is_parent = False
                if is_male:
                    if CommonSimGenealogyUtils.is_father_of(target_sim_info, potential_child): is_parent = True
                else:
                    if CommonSimGenealogyUtils.is_mother_of(target_sim_info, potential_child): is_parent = True
                if is_parent: kids_names.append(CommonSimNameUtils.get_full_name(potential_child))

            count = len(kids_names)
            if count > 0:
                display_str = ", ".join(kids_names[:5])
                if count > 5: display_str += ", ..."
                status_parts.append(f"Has {count} children ({display_str})")
            else:
                status_parts.append("Has no children")
            return ". ".join(status_parts)
        except Exception as e:
            return "Social status unknown."

    def _get_top_skills(self, sim_info, limit=5):
        skill_list = []
        try:
            all_skills = CommonSimSkillUtils.get_all_skills_available_for_sim_gen(sim_info)
            for skill in all_skills:
                if CommonSimSkillUtils.has_skill(sim_info, skill):
                    level = int(CommonSimSkillUtils.get_current_skill_level(sim_info, skill, use_effective_skill_level=False))
                    if level > 0:
                        skill_name = "Unknown Skill"
                        if hasattr(skill, '__name__'): raw_name = skill.__name__
                        else: raw_name = str(skill)
                        clean_name = raw_name.replace("Statistic_", "").replace("Skill_", "").replace("AdultMajor_", "").replace("AdultMinor_", "").replace("Toddler_", "").replace("Child_", "").replace("Species_", "").replace("_", " ")
                        skill_list.append((clean_name, level))
            skill_list.sort(key=lambda x: x[1], reverse=True)
            top_skills = [f"{name} ({level})" for name, level in skill_list[:limit]]
            return ", ".join(top_skills) if top_skills else "None"
        except Exception as e:
            return "Unknown"

    def _get_mood_string(self, sim_info):
        try:
            mood_instance = CommonMoodUtils.get_current_mood(sim_info)
            return str(mood_instance).split("Mood_")[-1].replace("'>", "") if mood_instance else "Fine"
        except: return "Fine"
        
    def _get_career_string(self, sim_info):
        try:
             if hasattr(sim_info, 'career_tracker'):
                 careers = [type(c).__name__.replace('Career_','') for c in sim_info.career_tracker.careers.values()]
                 return ", ".join(careers) if careers else "Unemployed"
        except: return "Unemployed"

    def _start_polling_thread(self):
        if self._polling_thread is not None and self._polling_thread.is_alive():
            self._is_polling = False
            time.sleep(0.5)
        self._is_polling = True
        self._polling_thread = threading.Thread(target=self._poll_server_loop)
        self._polling_thread.setDaemon(True) 
        self._polling_thread.start()

    def _poll_server_loop(self):
        url = "http://127.0.0.1:3000/game/status"
        while self._is_polling:
            try:
                time.sleep(0.5)
                with urllib.request.urlopen(url) as response:
                    data = json.loads(response.read().decode('utf-8'))
                    command = data.get("command")
                    
                    if command == "RESUME":
                        self._resume_game()
                        break
                    elif command == "SCRAPE":
                        self._perform_context_update()

            except:
                time.sleep(2)

    def _resume_game(self):
        self._is_polling = False
        self.current_targets = []
        CommonTimeUtils.set_game_speed_normal()

@CommonConsoleCommand(ModInfo.get_identity(), 'ai_chat', 'Force start chat.')
def _force_start_chat(output: CommonConsoleCommandOutput):
    sim = CommonSimUtils.get_active_sim_info()
    if sim:
        SimsAIChatService.get().start_chat_session(sim)
        output("Chat Forced.")
    else:
        output("No active sim found.")