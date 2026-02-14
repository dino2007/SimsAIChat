#sims_ai_chat_scripts/modinfo.py

from sims4communitylib.mod_support.common_mod_info import CommonModInfo

class ModInfo(CommonModInfo):
    """ Mod info for the SimsAIChat Mod. """
    _FILE_PATH: str = str(__file__)

    @property
    def _name(self) -> str:
        return 'SimsAIChat'

    @property
    def _author(self) -> str:
        return 'dino2007'

    @property
    def _base_namespace(self) -> str:
        # This must match the folder name where your scripts are located
        return 'sims_ai_chat_scripts'

    @property
    def _file_path(self) -> str:
        return ModInfo._FILE_PATH