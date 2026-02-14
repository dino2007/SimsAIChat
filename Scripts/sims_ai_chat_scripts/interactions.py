# Scripts/sims_ai_chat_scripts/interactions.py

# --- STANDARD IMPORTS ---
from typing import Tuple, Any, List
from sims.sim_info import SimInfo
import services

# --- S4CL IMPORTS ---
from sims4communitylib.classes.interactions.common_immediate_super_interaction import CommonImmediateSuperInteraction
from sims4communitylib.classes.testing.common_test_result import CommonTestResult
from sims4communitylib.utils.common_type_utils import CommonTypeUtils
from sims4communitylib.utils.common_log_registry import CommonLogRegistry
from sims4communitylib.services.interactions.interaction_registration_service import CommonInteractionRegistry, CommonInteractionType, CommonScriptObjectInteractionHandler
from sims4communitylib.utils.sims.common_sim_utils import CommonSimUtils
from sims4communitylib.utils.sims.common_species_utils import CommonSpeciesUtils
from sims4communitylib.utils.sims.common_age_utils import CommonAgeUtils # <--- NEW IMPORT

# --- NEW PICKER IMPORTS (Standard Dialog) ---
from sims4communitylib.dialogs.common_choose_sims_dialog import CommonChooseSimsDialog
from sims4communitylib.dialogs.common_choose_sim_dialog import SimPickerRow
from sims4communitylib.dialogs.common_choice_outcome import CommonChoiceOutcome

# --- LOCAL IMPORTS ---
from sims_ai_chat_scripts.modinfo import ModInfo
from sims_ai_chat_scripts.location_service import SimsAILocationService
from sims_ai_chat_scripts.chat_service import SimsAIChatService

# --- LOGGING SETUP ---
log = CommonLogRegistry.get().register_log(ModInfo.get_identity(), 'debug_interactions')

# --- CONFIGURATION ---
AI_CHAT_INTERACTION_ID = 3473934492 
EDIT_LOCATION_INTERACTION_ID = 2232829793 
GROUP_CHAT_INTERACTION_ID = 3809631617 

# ==============================================================================
# 1. SINGLE CHAT INTERACTION
# ==============================================================================
class ChatWithAIInteraction(CommonImmediateSuperInteraction):
    @classmethod
    def get_mod_identity(cls): return ModInfo.get_identity()
    @classmethod
    def get_log_identifier(cls): return 'chat_with_ai_interaction'

    @classmethod
    def on_test(cls, interaction_sim, interaction_target, interaction_context, **kwargs):
        if interaction_target is None: return CommonTestResult.NONE
        if not CommonTypeUtils.is_sim_or_sim_info(interaction_target): return CommonTestResult.NONE
        if interaction_sim is interaction_target: return CommonTestResult.NONE
        
        # --- NEW FILTERS ---
        # 1. Must be Human (No Pets)
        if not CommonSpeciesUtils.is_human(interaction_target):
            return CommonTestResult.NONE
            
        # 2. Must be Teen or Older (No Toddlers/Children)
        if not CommonAgeUtils.is_teen_adult_or_elder(interaction_target):
             return CommonTestResult.NONE
        # -------------------

        return CommonTestResult.TRUE

    def on_started(self, interaction_sim, interaction_target):
        try:
             SimsAIChatService.get().start_chat_session(interaction_target)
        except Exception as e:
             log.error("Failed to start chat service", exception=e)
        return True
    
# ==============================================================================
# 2. EDIT LOCATION INTERACTION
# ==============================================================================
class EditLocationContextInteraction(CommonImmediateSuperInteraction):
    @classmethod
    def get_mod_identity(cls): return ModInfo.get_identity()
    @classmethod
    def get_log_identifier(cls): return 'edit_location_context_interaction'

    @classmethod
    def on_test(cls, interaction_sim, interaction_target, interaction_context, **kwargs):
        return CommonTestResult.TRUE

    def on_started(self, interaction_sim, interaction_target):
        try:
             SimsAILocationService.get().edit_location_description()
        except Exception as e:
             log.error("Failed to start location service", exception=e)
        return True

# ==============================================================================
# 3. GROUP CHAT INTERACTION
# ==============================================================================
class GroupChatInteraction(CommonImmediateSuperInteraction):
    @classmethod
    def get_mod_identity(cls): return ModInfo.get_identity()
    @classmethod
    def get_log_identifier(cls): return 'group_chat_interaction'

    @classmethod
    def on_test(cls, interaction_sim, interaction_target, interaction_context, **kwargs):
        return CommonTestResult.TRUE

    def on_started(self, interaction_sim, interaction_target):
        log.debug("Group Chat Picker Triggered.")
        try:
            active_sim_info = CommonSimUtils.get_sim_info(interaction_sim)

            # 1. Build the list of nearby Sims manually
            option_rows = []
            
            for sim_info in CommonSimUtils.get_sim_info_for_all_sims_generator():
                
                # Filter A: Don't pick yourself
                if sim_info is active_sim_info:
                    continue
                
                # Filter B: Must be "Instanced" (Spawned/Nearby/Visible)
                if CommonSimUtils.get_sim_instance(sim_info) is None:
                    continue
                
                # --- NEW FILTERS FOR PICKER ---
                # Filter C: Must be Human
                if not CommonSpeciesUtils.is_human(sim_info):
                    continue
                    
                # Filter D: Must be Teen or Older
                if not CommonAgeUtils.is_teen_adult_or_elder(sim_info):
                    continue
                # ------------------------------

                # Create the Row
                sim_id = CommonSimUtils.get_sim_id(sim_info)
                # S4CL uses 'tag' internally to resolve the selection back to the object
                row = SimPickerRow(sim_id, select_default=False, tag=sim_info)
                option_rows.append(row)

            if not option_rows:
                log.debug("No nearby sims found for group chat.")
                return True

            # 2. Callback when player finishes selection
            def _on_sims_chosen(chosen_sims: Tuple[SimInfo], outcome: CommonChoiceOutcome):
                if outcome == CommonChoiceOutcome.CANCEL or not chosen_sims:
                    return
                
                SimsAIChatService.get().start_group_chat_session(list(chosen_sims))

            # 3. Show the Dialog
            dialog = CommonChooseSimsDialog(
                "Select Group Chat Members",        # Title
                "Choose up to 3 Sims nearby.",      # Description
                tuple(option_rows),                 # Choices
                mod_identity=ModInfo.get_identity() # ModIdentity
            )

            dialog.show(
                on_chosen=_on_sims_chosen,
                min_selectable=1,
                max_selectable=3
            )

        except Exception as e:
            log.error("Failed to open group picker", exception=e)
        return True

# ==============================================================================
# 4. REGISTRATION HANDLER
# ==============================================================================
@CommonInteractionRegistry.register_interaction_handler(CommonInteractionType.ON_SCRIPT_OBJECT_LOAD)
class ChatInteractionHandler(CommonScriptObjectInteractionHandler):
    @property
    def interactions_to_add(self):
        # Register ALL THREE
        return (AI_CHAT_INTERACTION_ID, EDIT_LOCATION_INTERACTION_ID, GROUP_CHAT_INTERACTION_ID)

    def should_add(self, script_object, *args, **kwargs) -> bool:
        if CommonTypeUtils.is_sim_or_sim_info(script_object):
            return True
        return False