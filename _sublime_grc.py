import sublime
import sublime_plugin
import ctypes
import threading
import time
import os
import re
import platform
import json
from urllib.parse import quote
from ctypes import c_char, c_char_p, c_int, c_float, c_longlong, c_void_p, POINTER, Structure, CFUNCTYPE

def _grclib_library_name():
    system = platform.system()
    if system == "Windows":
        return "grclib.dll"
    if system == "Darwin":
        return "grclib.dylib"
    return "grclib.so"


def _grclib_library_path():
    package_dir = os.path.dirname(__file__)
    preferred = os.path.join(package_dir, _grclib_library_name())
    if os.path.exists(preferred):
        return preferred

    for name in ("grclib.dll", "grclib.dylib", "grclib.so"):
        candidate = os.path.join(package_dir, name)
        if os.path.exists(candidate):
            return candidate
    return preferred


dll_path = _grclib_library_path()
_grclib = None
try:
    _grclib = ctypes.CDLL(dll_path)
except Exception as e:
    import traceback
    print("RC: WARNING - Failed to load grclib library at {}: {}".format(dll_path, e))
    print(traceback.format_exc())
    print("RC: Plugin will continue loading with limited functionality")

class RCServer(Structure):
    _fields_ = [("name", c_char_p), ("ip", c_char_p), ("port", c_int), ("players", c_int), ("language", c_char_p), ("description", c_char_p)]

class RCPlayer(Structure):
    _fields_ = [("account", c_char_p), ("id", c_int), ("nick", c_char_p), ("level", c_char_p)]

class RCWeapon(Structure):
    _fields_ = [("name", c_char_p), ("image", c_char_p), ("script", c_char_p)]

class RCClass(Structure):
    _fields_ = [("name", c_char_p), ("script", c_char_p)]

class RCNPC(Structure):
    _fields_ = [("id", c_int), ("name", c_char_p), ("type", c_char_p), ("image", c_char_p), ("script", c_char_p)]

class RCLevel(Structure):
    _fields_ = [("name", c_char_p), ("type", c_char_p)]

class RCFileBrowserFolder(Structure):
    _fields_ = [("rights", c_char_p), ("pattern", c_char_p)]

class RCFileBrowserEntry(Structure):
    _fields_ = [("path", c_char_p), ("rights", c_char_p), ("size", c_int), ("modified", c_int), ("is_directory", c_int)]

RC_OnConnected = CFUNCTYPE(None, c_void_p)
RC_OnDisconnected = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnPlayerJoined = CFUNCTYPE(None, c_char_p, c_int, c_void_p)
RC_OnPlayerLeft = CFUNCTYPE(None, c_char_p, c_int, c_void_p)
RC_OnMessage = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnPrivateMessage = CFUNCTYPE(None, c_int, c_char_p, c_char_p, c_char_p, c_void_p)
RC_OnFileReceived = CFUNCTYPE(None, c_char_p, c_char_p, c_int, c_void_p)
RC_OnWeaponAdded = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnWeaponDeleted = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnClassAdded = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnClassDeleted = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnNPCAdded = CFUNCTYPE(None, c_int, c_char_p, c_void_p)
RC_OnNPCDeleted = CFUNCTYPE(None, c_int, c_void_p)
RC_OnNPCAttributes = CFUNCTYPE(None, c_int, c_char_p, c_void_p)
RC_OnPlayerPropChanged = CFUNCTYPE(None, c_int, c_char_p, c_char_p, c_void_p)
RC_OnWorldTime = CFUNCTYPE(None, c_int, c_void_p)
RC_OnMaxUploadFileSize = CFUNCTYPE(None, c_longlong, c_void_p)
RC_OnCommandResponse = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnPMServersUpdated = CFUNCTYPE(None, c_int, c_void_p)
RC_OnNPCFlags = CFUNCTYPE(None, c_int, c_char_p, c_void_p)
RC_OnPMServerPlayers = CFUNCTYPE(None, c_char_p, c_char_p, c_void_p)
RC_OnFileBrowserFolders = CFUNCTYPE(None, c_int, c_void_p)
RC_OnFileBrowserFiles = CFUNCTYPE(None, c_char_p, c_int, c_void_p)
RC_OnFileBrowserMessage = CFUNCTYPE(None, c_char_p, c_void_p)
RC_OnScriptReceived = CFUNCTYPE(None, c_char_p, c_char_p, c_int, c_char_p, c_void_p)
RC_OnServerData = CFUNCTYPE(None, c_char_p, c_char_p, c_void_p)
RC_OnPlayerRights = CFUNCTYPE(None, c_char_p, c_int, c_char_p, c_char_p, c_void_p)
RC_OnPlayerTextData = CFUNCTYPE(None, c_char_p, c_char_p, c_char_p, c_void_p)
RC_OnPlayerAttributes = CFUNCTYPE(None, c_char_p, c_char_p, c_char_p, c_void_p)
RC_OnLocalNPCs = CFUNCTYPE(None, c_char_p, c_char_p, c_void_p)
RC_OnIrcMessage = CFUNCTYPE(None, c_char_p, c_char_p, c_void_p)
RC_OnBanData = CFUNCTYPE(None, c_char_p, c_char_p, c_char_p, c_void_p)
RC_OnBanListData = CFUNCTYPE(None, c_char_p, c_char_p, c_char_p, c_void_p)
RC_OnAccountList = CFUNCTYPE(None, c_char_p, c_void_p)

if _grclib:
    _grclib.rc_connect.argtypes = [c_char_p, c_int, c_char_p, c_char_p]
    _grclib.rc_connect.restype = c_void_p
    _grclib.rc_last_error.argtypes = [c_void_p]
    _grclib.rc_last_error.restype = c_char_p
    _grclib.rc_get_servers.argtypes = [c_void_p, POINTER(POINTER(RCServer))]
    _grclib.rc_get_servers.restype = c_int
    _grclib.rc_connect_to_server.argtypes = [c_void_p, c_int]
    _grclib.rc_connect_to_server.restype = c_int
    _grclib.rc_connect_to_nc_server.argtypes = [c_void_p]
    _grclib.rc_connect_to_nc_server.restype = c_int
    _grclib.rc_is_connected.argtypes = [c_void_p]
    _grclib.rc_is_connected.restype = c_int
    _grclib.rc_is_authenticated.argtypes = [c_void_p]
    _grclib.rc_is_authenticated.restype = c_int
    _grclib.rc_is_nc_connected.argtypes = [c_void_p]
    _grclib.rc_is_nc_connected.restype = c_int
    _grclib.rc_on_connected.argtypes = [c_void_p, RC_OnConnected, c_void_p]
    _grclib.rc_on_disconnected.argtypes = [c_void_p, RC_OnDisconnected, c_void_p]
    _grclib.rc_on_player_joined.argtypes = [c_void_p, RC_OnPlayerJoined, c_void_p]
    _grclib.rc_on_player_left.argtypes = [c_void_p, RC_OnPlayerLeft, c_void_p]
    _grclib.rc_on_message.argtypes = [c_void_p, RC_OnMessage, c_void_p]
    _grclib.rc_on_private_message.argtypes = [c_void_p, RC_OnPrivateMessage, c_void_p]
    _grclib.rc_on_file_received.argtypes = [c_void_p, RC_OnFileReceived, c_void_p]
    _grclib.rc_on_weapon_added.argtypes = [c_void_p, RC_OnWeaponAdded, c_void_p]
    _grclib.rc_on_weapon_deleted.argtypes = [c_void_p, RC_OnWeaponDeleted, c_void_p]
    _grclib.rc_on_class_added.argtypes = [c_void_p, RC_OnClassAdded, c_void_p]
    _grclib.rc_on_class_deleted.argtypes = [c_void_p, RC_OnClassDeleted, c_void_p]
    _grclib.rc_on_npc_added.argtypes = [c_void_p, RC_OnNPCAdded, c_void_p]
    _grclib.rc_on_npc_deleted.argtypes = [c_void_p, RC_OnNPCDeleted, c_void_p]
    _grclib.rc_on_npc_attributes.argtypes = [c_void_p, RC_OnNPCAttributes, c_void_p]
    _grclib.rc_on_player_prop_changed.argtypes = [c_void_p, RC_OnPlayerPropChanged, c_void_p]
    _grclib.rc_on_world_time.argtypes = [c_void_p, RC_OnWorldTime, c_void_p]
    _grclib.rc_on_max_upload_file_size.argtypes = [c_void_p, RC_OnMaxUploadFileSize, c_void_p]
    _grclib.rc_on_command_response.argtypes = [c_void_p, RC_OnCommandResponse, c_void_p]
    _grclib.rc_on_pm_servers_updated.argtypes = [c_void_p, RC_OnPMServersUpdated, c_void_p]
    _grclib.rc_on_npc_flags.argtypes = [c_void_p, RC_OnNPCFlags, c_void_p]
    _grclib.rc_on_pm_server_players.argtypes = [c_void_p, RC_OnPMServerPlayers, c_void_p]
    _grclib.rc_on_filebrowser_folders.argtypes = [c_void_p, RC_OnFileBrowserFolders, c_void_p]
    _grclib.rc_on_filebrowser_files.argtypes = [c_void_p, RC_OnFileBrowserFiles, c_void_p]
    _grclib.rc_on_filebrowser_message.argtypes = [c_void_p, RC_OnFileBrowserMessage, c_void_p]
    _grclib.rc_on_script_received.argtypes = [c_void_p, RC_OnScriptReceived, c_void_p]
    _grclib.rc_on_server_data.argtypes = [c_void_p, RC_OnServerData, c_void_p]
    _grclib.rc_on_player_rights.argtypes = [c_void_p, RC_OnPlayerRights, c_void_p]
    _grclib.rc_on_player_text_data.argtypes = [c_void_p, RC_OnPlayerTextData, c_void_p]
    _grclib.rc_on_player_attributes.argtypes = [c_void_p, RC_OnPlayerAttributes, c_void_p]
    _grclib.rc_format_player_rights_text.argtypes = [c_int, c_char_p, c_char_p]
    _grclib.rc_format_player_rights_text.restype = c_void_p
    _grclib.rc_format_player_account_text.argtypes = [c_char_p]
    _grclib.rc_format_player_account_text.restype = c_void_p
    _grclib.rc_format_player_attributes_text.argtypes = [c_char_p]
    _grclib.rc_format_player_attributes_text.restype = c_void_p
    _grclib.rc_parse_player_rights_text.argtypes = [c_char_p]
    _grclib.rc_parse_player_rights_text.restype = c_void_p
    _grclib.rc_parse_player_account_text.argtypes = [c_char_p]
    _grclib.rc_parse_player_account_text.restype = c_void_p
    _grclib.rc_parse_player_attributes_text.argtypes = [c_char_p]
    _grclib.rc_parse_player_attributes_text.restype = c_void_p
    _grclib.rc_is_new_protocol.argtypes = [c_void_p]
    _grclib.rc_is_new_protocol.restype = c_int
    _grclib.rc_set_new_protocol.argtypes = [c_void_p, c_int]
    _grclib.rc_request_local_npcs.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_local_npcs.restype = c_int
    _grclib.rc_on_local_npcs.argtypes = [c_void_p, RC_OnLocalNPCs, c_void_p]
    _grclib.rc_on_irc_message.argtypes = [c_void_p, RC_OnIrcMessage, c_void_p]
    _grclib.rc_on_ban_data.argtypes = [c_void_p, RC_OnBanData, c_void_p]
    _grclib.rc_on_ban_list_data.argtypes = [c_void_p, RC_OnBanListData, c_void_p]
    _grclib.rc_on_account_list.argtypes = [c_void_p, RC_OnAccountList, c_void_p]
    _grclib.rc_send_irc_text.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p, c_char_p]
    _grclib.rc_send_irc_text.restype = c_int
    _grclib.rc_irc_login.argtypes = [c_void_p]
    _grclib.rc_irc_login.restype = c_int
    _grclib.rc_irc_join.argtypes = [c_void_p, c_char_p]
    _grclib.rc_irc_join.restype = c_int
    _grclib.rc_irc_part.argtypes = [c_void_p, c_char_p]
    _grclib.rc_irc_part.restype = c_int
    _grclib.rc_request_player_ban.argtypes = [c_void_p, c_char_p, c_int]
    _grclib.rc_request_player_ban.restype = c_int
    _grclib.rc_request_player_ban_by_account.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_player_ban_by_account.restype = c_int
    _grclib.rc_request_ban_types.argtypes = [c_void_p]
    _grclib.rc_request_ban_types.restype = c_int
    _grclib.rc_request_ban_history.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_ban_history.restype = c_int
    _grclib.rc_request_staff_activity.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_staff_activity.restype = c_int
    _grclib.rc_set_ban.argtypes = [c_void_p, c_char_p, c_char_p, c_int, c_char_p, c_char_p, c_char_p]
    _grclib.rc_set_ban.restype = c_int
    _grclib.rc_set_legacy_player_ban.argtypes = [c_void_p, c_char_p, c_int, c_char_p]
    _grclib.rc_set_legacy_player_ban.restype = c_int
    _grclib.rc_get_rights_names.argtypes = []
    _grclib.rc_get_rights_names.restype = c_void_p
    _grclib.rc_get_color_names.argtypes = []
    _grclib.rc_get_color_names.restype = c_void_p
    _grclib.rc_get_packet_names.argtypes = [c_int, c_int]
    _grclib.rc_get_packet_names.restype = c_void_p
    _grclib.rc_get_players.argtypes = [c_void_p, POINTER(POINTER(RCPlayer))]
    _grclib.rc_get_players.restype = c_int
    _grclib.rc_get_weapons.argtypes = [c_void_p, POINTER(POINTER(RCWeapon))]
    _grclib.rc_get_weapons.restype = c_int
    _grclib.rc_get_classes.argtypes = [c_void_p, POINTER(POINTER(RCClass))]
    _grclib.rc_get_classes.restype = c_int
    _grclib.rc_get_npcs.argtypes = [c_void_p, POINTER(POINTER(RCNPC))]
    _grclib.rc_get_npcs.restype = c_int
    _grclib.rc_get_levels.argtypes = [c_void_p, POINTER(POINTER(RCLevel))]
    _grclib.rc_get_levels.restype = c_int
    _grclib.rc_get_pm_servers.argtypes = [c_void_p, POINTER(POINTER(c_char_p))]
    _grclib.rc_get_pm_servers.restype = c_int
    _grclib.rc_get_cached_npc_flags.argtypes = [c_void_p, c_int]
    _grclib.rc_get_cached_npc_flags.restype = c_void_p
    _grclib.rc_get_filebrowser_folders.argtypes = [c_void_p, POINTER(POINTER(RCFileBrowserFolder))]
    _grclib.rc_get_filebrowser_folders.restype = c_int
    _grclib.rc_get_filebrowser_files.argtypes = [c_void_p, POINTER(POINTER(RCFileBrowserEntry))]
    _grclib.rc_get_filebrowser_files.restype = c_int
    _grclib.rc_get_server_options.argtypes = [c_void_p]
    _grclib.rc_get_server_options.restype = c_void_p
    _grclib.rc_get_server_flags.argtypes = [c_void_p]
    _grclib.rc_get_server_flags.restype = c_void_p
    _grclib.rc_get_folder_config.argtypes = [c_void_p]
    _grclib.rc_get_folder_config.restype = c_void_p
    _grclib.rc_get_max_upload_file_size.argtypes = [c_void_p]
    _grclib.rc_get_max_upload_file_size.restype = c_longlong
    _grclib.rc_execute.argtypes = [c_void_p, c_char_p]
    _grclib.rc_execute.restype = c_int
    _grclib.rc_upload_file.argtypes = [c_void_p, c_char_p, c_char_p, c_int]
    _grclib.rc_upload_file.restype = c_int
    _grclib.rc_download_file.argtypes = [c_void_p, c_char_p]
    _grclib.rc_download_file.restype = c_int
    _grclib.rc_warp_player.argtypes = [c_void_p, c_int, c_char_p, c_float, c_float]
    _grclib.rc_warp_player.restype = c_int
    _grclib.rc_disconnect_player.argtypes = [c_void_p, c_int, c_char_p]
    _grclib.rc_disconnect_player.restype = c_int
    _grclib.rc_add_weapon.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p]
    _grclib.rc_add_weapon.restype = c_int
    _grclib.rc_delete_weapon.argtypes = [c_void_p, c_char_p]
    _grclib.rc_delete_weapon.restype = c_int
    _grclib.rc_update_weapon.argtypes = [c_void_p, c_char_p, c_char_p, c_char_p]
    _grclib.rc_update_weapon.restype = c_int
    _grclib.rc_add_class.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_add_class.restype = c_int
    _grclib.rc_delete_class.argtypes = [c_void_p, c_char_p]
    _grclib.rc_delete_class.restype = c_int
    _grclib.rc_update_class.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_update_class.restype = c_int
    _grclib.rc_delete_npc.argtypes = [c_void_p, c_int]
    _grclib.rc_delete_npc.restype = c_int
    _grclib.rc_update_npc.argtypes = [c_void_p, c_int, c_char_p]
    _grclib.rc_update_npc.restype = c_int
    _grclib.rc_create_npc_on_server.argtypes = [c_void_p, c_char_p, c_int, c_char_p, c_char_p, c_char_p, c_char_p, c_char_p]
    _grclib.rc_create_npc_on_server.restype = c_int
    _grclib.rc_disconnect_nc.argtypes = [c_void_p]
    _grclib.rc_disconnect_nc.restype = c_int
    _grclib.rc_set_nickname.argtypes = [c_void_p, c_char_p]
    _grclib.rc_set_nickname.restype = c_int
    _grclib.rc_request_npc_script.argtypes = [c_void_p, c_int]
    _grclib.rc_request_npc_script.restype = c_int
    _grclib.rc_request_npc_attributes.argtypes = [c_void_p, c_int]
    _grclib.rc_request_npc_attributes.restype = c_int
    _grclib.rc_request_class_script.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_class_script.restype = c_int
    _grclib.rc_request_weapon_script.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_weapon_script.restype = c_int
    _grclib.rc_reset_npc.argtypes = [c_void_p, c_int]
    _grclib.rc_reset_npc.restype = c_int
    _grclib.rc_warp_npc.argtypes = [c_void_p, c_int, c_float, c_float, c_char_p]
    _grclib.rc_warp_npc.restype = c_int
    _grclib.rc_get_npc_flags.argtypes = [c_void_p, c_int]
    _grclib.rc_get_npc_flags.restype = c_int
    _grclib.rc_set_npc_flags.argtypes = [c_void_p, c_int, c_char_p]
    _grclib.rc_set_npc_flags.restype = c_int
    _grclib.rc_request_player_rights.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_player_rights.restype = c_int
    _grclib.rc_request_player_attrs.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_player_attrs.restype = c_int
    _grclib.rc_request_player_account.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_player_account.restype = c_int
    _grclib.rc_request_account_list.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_request_account_list.restype = c_int
    _grclib.rc_request_player_comments.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_player_comments.restype = c_int
    _grclib.rc_request_player_profile.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_player_profile.restype = c_int
    _grclib.rc_send_private_message.argtypes = [c_void_p, c_int, c_char_p]
    _grclib.rc_send_private_message.restype = c_int
    _grclib.rc_send_admin_message.argtypes = [c_void_p, c_int, c_char_p]
    _grclib.rc_send_admin_message.restype = c_int
    _grclib.rc_set_player_rights.argtypes = [c_void_p, c_char_p, c_int, c_char_p, c_char_p]
    _grclib.rc_set_player_rights.restype = c_int
    _grclib.rc_set_player_comments.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_set_player_comments.restype = c_int
    _grclib.rc_set_player_attributes.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_set_player_attributes.restype = c_int
    _grclib.rc_set_player_account.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_set_player_account.restype = c_int
    _grclib.rc_add_player_account.argtypes = [c_void_p, c_char_p]
    _grclib.rc_add_player_account.restype = c_int
    _grclib.rc_set_player_profile.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_set_player_profile.restype = c_int
    _grclib.rc_send_mass_pm.argtypes = [c_void_p, POINTER(c_int), c_int, c_char_p]
    _grclib.rc_send_mass_pm.restype = c_int
    _grclib.rc_send_admin_message_all.argtypes = [c_void_p, c_char_p]
    _grclib.rc_send_admin_message_all.restype = c_int
    _grclib.rc_filebrowser_start.argtypes = [c_void_p]
    _grclib.rc_filebrowser_start.restype = c_int
    _grclib.rc_filebrowser_cd.argtypes = [c_void_p, c_char_p]
    _grclib.rc_filebrowser_cd.restype = c_int
    _grclib.rc_filebrowser_download.argtypes = [c_void_p, c_char_p]
    _grclib.rc_filebrowser_download.restype = c_int
    _grclib.rc_filebrowser_delete.argtypes = [c_void_p, c_char_p]
    _grclib.rc_filebrowser_delete.restype = c_int
    _grclib.rc_filebrowser_rename.argtypes = [c_void_p, c_char_p, c_char_p]
    _grclib.rc_filebrowser_rename.restype = c_int
    _grclib.rc_request_server_options.argtypes = [c_void_p]
    _grclib.rc_request_server_options.restype = c_int
    _grclib.rc_upload_server_options.argtypes = [c_void_p, c_char_p]
    _grclib.rc_upload_server_options.restype = c_int
    _grclib.rc_request_server_flags.argtypes = [c_void_p]
    _grclib.rc_request_server_flags.restype = c_int
    _grclib.rc_upload_server_flags.argtypes = [c_void_p, c_char_p]
    _grclib.rc_upload_server_flags.restype = c_int
    _grclib.rc_request_folder_config.argtypes = [c_void_p]
    _grclib.rc_request_folder_config.restype = c_int
    _grclib.rc_upload_folder_config.argtypes = [c_void_p, c_char_p]
    _grclib.rc_upload_folder_config.restype = c_int
    _grclib.rc_reset_player.argtypes = [c_void_p, c_char_p]
    _grclib.rc_reset_player.restype = c_int
    _grclib.rc_upload_level.argtypes = [c_void_p, c_char_p, c_char_p, c_int]
    _grclib.rc_upload_level.restype = c_int
    _grclib.rc_download_level.argtypes = [c_void_p, c_char_p]
    _grclib.rc_download_level.restype = c_int
    _grclib.rc_request_pm_server_list.argtypes = [c_void_p]
    _grclib.rc_request_pm_server_list.restype = c_int
    _grclib.rc_request_pm_server_players.argtypes = [c_void_p, c_char_p]
    _grclib.rc_request_pm_server_players.restype = c_int
    _grclib.rc_send_toall_message.argtypes = [c_void_p, c_char_p]
    _grclib.rc_send_toall_message.restype = c_int
    _grclib.rc_gtokenize.argtypes = [c_char_p]
    _grclib.rc_gtokenize.restype = c_void_p
    _grclib.rc_gtokenize_reverse.argtypes = [c_char_p]
    _grclib.rc_gtokenize_reverse.restype = c_void_p
    _grclib.rc_get_1plus_text_net_string.argtypes = [c_char_p]
    _grclib.rc_get_1plus_text_net_string.restype = c_void_p
    _grclib.rc_read_gbyte.argtypes = [c_char_p, c_int, c_int, POINTER(c_int), POINTER(c_int)]
    _grclib.rc_read_gbyte.restype = c_int
    _grclib.rc_read_gshort.argtypes = [c_char_p, c_int, c_int, POINTER(c_int), POINTER(c_int)]
    _grclib.rc_read_gshort.restype = c_int
    _grclib.rc_read_gint5.argtypes = [c_char_p, c_int, c_int, POINTER(c_int), POINTER(c_int)]
    _grclib.rc_read_gint5.restype = c_int
    _grclib.rc_read_length_string.argtypes = [c_char_p, c_int, c_int, POINTER(c_int)]
    _grclib.rc_read_length_string.restype = c_void_p
    _grclib.rc_read_comma_text.argtypes = [c_char_p, c_int, c_int, c_int]
    _grclib.rc_read_comma_text.restype = c_void_p
    RC_OnRawPacket = CFUNCTYPE(None, c_int, POINTER(c_char), c_int, c_void_p)
    _grclib.rc_on_raw_packet.argtypes = [c_void_p, RC_OnRawPacket, c_void_p]
    _grclib.rc_on_raw_packet.restype = None
    _grclib.rc_free.argtypes = [c_void_p]
    _grclib.rc_disconnect.argtypes = [c_void_p]
    _grclib.rc_process_events.argtypes = [c_void_p]

SERVERS = []
def getSetting(key, default=""):
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    return settings.get(key, default)

def sortKey(name):
    name_lower = name.lower()
    prefix = '0' if name_lower[:1].isalnum() else '1'
    return prefix + name_lower

def getCleanServerName(server_name):
    cleaned = re.sub(r'^[🪙⏳🕶️🚧🌍]\s*', '', server_name)
    return sanitizePath(cleaned.strip())

def sanitizePath(path):
    invalid_chars = r'[\\/:*?"<>|]'
    parts = path.split('/')
    sanitized_parts = [re.sub(invalid_chars, '_', part) for part in parts]
    return '/'.join(sanitized_parts)

def urlEncodeFilename(filename):
    safe_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.'
    return ''.join(char if char in safe_chars else '%{:02X}'.format(ord(char)) for char in filename)

def getScriptsFolder():
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    default_folder = os.path.join(os.path.expanduser("~"), "SublimeRC") if platform.system() != "Windows" else "C:/SublimeRC"
    folder = settings.get("scripts_folder", default_folder)
    return os.path.normpath(folder)

def getListserverConfigs():
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    configs = []
    default_config = {
        "name": getSetting("listserver_name", "Listserver"),
        "host": getSetting("listserver_host", "listserver.graalonline.com"),
        "port": getSetting("listserver_port", 14922),
        "account": getSetting("listserver_account", getSetting("account", "")),
        "password": getSetting("listserver_password", getSetting("password", ""))
    }
    configs.append(default_config)
    i = 1
    while True:
        host_key = "listserver_host{}".format(i)
        port_key = "listserver_port{}".format(i)
        name_key = "listserver_name{}".format(i)
        account_key = "listserver_account{}".format(i)
        password_key = "listserver_password{}".format(i)
        host = settings.get(host_key)
        if not host: break
        config = {
            "name": settings.get(name_key, "Listserver {}".format(i)),
            "host": host,
            "port": settings.get(port_key, 14922),
            "account": settings.get(account_key, getSetting("account", "")),
            "password": settings.get(password_key, getSetting("password", ""))
        }
        configs.append(config)
        i += 1
    return configs

def getCredentials(cls):
    if cls.connected_server and cls.connected_server.get('listserver_config'):
        config = cls.connected_server['listserver_config']
        return config['account'], config['password']
    return getSetting('account'), getSetting('password')

def _readGrclibText(func, *args):
    if not _grclib:
        raise RuntimeError("grclib native library is required")
    ptr = func(*args)
    if not ptr:
        raise RuntimeError("grclib metadata call returned null")
    try:
        return ctypes.string_at(ptr).decode('latin-1', errors='ignore')
    finally:
        _grclib.rc_free(ptr)

def _loadGrclibList(func):
    text = _readGrclibText(func)
    if not text:
        raise RuntimeError("grclib metadata call returned empty list")
    return text.split('\n')

def _loadGrclibPacketMap(nc, direction):
    text = _readGrclibText(_grclib.rc_get_packet_names, nc, direction)
    if not text:
        raise RuntimeError("grclib packet metadata returned empty map")
    result = {}
    for line in text.split('\n'):
        key, sep, value = line.partition('=')
        if sep:
            try:
                result[int(key)] = value
            except ValueError:
                pass
    if not result:
        raise RuntimeError("grclib packet metadata returned no parseable entries")
    return result

class GPlugin:
    RIGHTS_NAMES = _loadGrclibList(_grclib.rc_get_rights_names)
    COLOR_NAMES = _loadGrclibList(_grclib.rc_get_color_names)
    PACKET_NAMES = _loadGrclibPacketMap(0, 0)
    NC_PACKET_NAMES = _loadGrclibPacketMap(1, 0)
    debug_mode = False
    servers = []
    weapons = []
    classes = []
    npcs = []
    players = []
    recent_servers = []
    weapon_scripts = {}
    class_scripts = {}
    npc_scripts = {}
    npc_flags = {}
    npc_attributes = {}
    pending_npc_flags_request = None
    pending_npc_attributes_request = None
    pending_npc_script_request = None
    pending_class_script_request = None
    pending_weapon_script_request = None
    pending_server_options_request = False
    pending_server_flags_request = False
    pending_folder_config_request = False
    player_rights = {}
    player_attributes = {}
    player_comments = {}
    player_profiles = {}
    server_options = {}
    server_flags = {}
    player_accounts = {}
    account_list = []
    account_list_callback = None
    pending_player_rights_request = None

    pending_player_attrs_request = None
    pending_player_comments_request = None
    pending_account_request = None
    pending_player_profile_request = None
    folders = []
    folder_files = []
    folder_config = None
    max_upload_file_size = 0
    server_options = None
    pm_servers = []
    pm_server_players = {}
    pm_server_update_timers = {}
    external_players = {}
    next_external_id = 16000
    pending_pm_server_request = None
    pending_pm_server_list_palette = False
    irc_channels = {}
    irc_bootstrapped = False
    server_flags = None
    file_browser_callback = None
    current_folder = ""
    pending_file_download = None
    open_after_download = False
    external_open_requested = False

    rc_handle = None
    raw_packet_callback = None
    connected_server = None
    current_listserver_config = None
    output_panel = None
    file_browser_log_view = None
    toalls_log_view = None
    nc_log_view = None
    authenticated = False
    nc_authenticated = False
    switching_servers = False
    event_thread = None
    _callbacks = {}

    @classmethod
    def log(cls, message, debug_only=False, show_panel=False):
        if debug_only and not cls.debug_mode: return
        from datetime import datetime
        timestamp = datetime.now().strftime("%I:%M %p")
        formatted = "[{}] {}".format(timestamp, message)
        if debug_only:
            print("RC: " + formatted)
            return
        view = cls.ensureChatView(focus=show_panel)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        print("RC: " + formatted)

    @classmethod
    def logPlain(cls, message):
        cls.log(message)

    @classmethod
    def getChatViewName(cls):
        if cls.connected_server and cls.connected_server.get('name'):
            return "💬 " + getCleanServerName(cls.connected_server.get('name'))
        return "💬 RC Chat"

    @classmethod
    def updateChatViewName(cls):
        view = cls.output_panel
        if view and getattr(view, "is_valid", lambda: False)() and view.settings().get("rc_chat_view"):
            view.set_name(cls.getChatViewName())

    @classmethod
    def ensureChatView(cls, window=None, focus=False):
        window = window or sublime.active_window()
        if not window:
            return None
        active_view = window.active_view()
        if cls.output_panel and getattr(cls.output_panel, "is_valid", lambda: False)() and cls.output_panel.settings().get("rc_chat_view"):
            view = cls.output_panel
        else:
            view = next((v for v in window.views() if v.settings().get("rc_chat_view")), None)
            if not view:
                view = window.new_file()
                view.set_scratch(True)
                view.assign_syntax("Packages/SublimeRC/terminal.sublime-syntax")
                view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                view.settings().set("rc_chat_view", True)
                view.run_command("rc_chat_insert", {"characters": "> "})
            cls.output_panel = view
        cls.updateChatViewName()
        if focus:
            window.focus_view(view)
            view.run_command("move_to", {"to": "eof"})
        elif active_view and active_view != view and getattr(active_view, "is_valid", lambda: False)():
            window.focus_view(active_view)
        return view

    @classmethod
    def ensureFileBrowserLogView(cls, window=None, focus=False):
        window = window or sublime.active_window()
        if not window:
            return None
        active_view = window.active_view()
        if cls.file_browser_log_view and getattr(cls.file_browser_log_view, "is_valid", lambda: False)() and cls.file_browser_log_view.settings().get("rc_file_browser_log_view"):
            view = cls.file_browser_log_view
        else:
            view = next((v for v in window.views() if v.settings().get("rc_file_browser_log_view")), None)
            if not view:
                view = window.new_file()
                view.set_scratch(True)
                view.assign_syntax("Packages/SublimeRC/terminal.sublime-syntax")
                view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                view.settings().set("rc_file_browser_log_view", True)
                view.set_name("📁 File Browser")
                view.run_command("rc_chat_insert", {"characters": "> "})
            cls.file_browser_log_view = view
        if focus:
            window.focus_view(view)
            view.run_command("move_to", {"to": "eof"})
        elif active_view and active_view != view and getattr(active_view, "is_valid", lambda: False)():
            window.focus_view(active_view)
        return view

    @classmethod
    def ensureToallsView(cls, window=None, focus=False):
        window = window or sublime.active_window()
        if not window:
            return None
        active_view = window.active_view()
        if cls.toalls_log_view and getattr(cls.toalls_log_view, "is_valid", lambda: False)() and cls.toalls_log_view.settings().get("rc_toalls_view"):
            view = cls.toalls_log_view
        else:
            view = next((v for v in window.views() if v.settings().get("rc_toalls_view")), None)
            if not view:
                view = window.new_file()
                view.set_scratch(True)
                view.assign_syntax("Packages/SublimeRC/terminal.sublime-syntax")
                view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                view.settings().set("rc_toalls_view", True)
                view.set_name("📣 Toalls")
                view.run_command("rc_chat_insert", {"characters": "> "})
            cls.toalls_log_view = view
        if focus:
            window.focus_view(view)
            view.run_command("move_to", {"to": "eof"})
        elif active_view and active_view != view and getattr(active_view, "is_valid", lambda: False)():
            window.focus_view(active_view)
        return view

    @classmethod
    def ensureNcLogView(cls, window=None, focus=False):
        window = window or sublime.active_window()
        if not window:
            return None
        active_view = window.active_view()
        created = False
        if cls.nc_log_view and getattr(cls.nc_log_view, "is_valid", lambda: False)() and cls.nc_log_view.settings().get("rc_nc_log_view"):
            view = cls.nc_log_view
        else:
            view = next((v for v in window.views() if v.settings().get("rc_nc_log_view")), None)
            if not view:
                view = window.new_file()
                created = True
                view.set_scratch(True)
                view.assign_syntax("Packages/SublimeRC/terminal.sublime-syntax")
                view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                view.settings().set("rc_nc_log_view", True)
                view.set_name("🧬 NC")
            cls.nc_log_view = view
        if focus:
            window.focus_view(view)
            view.run_command("move_to", {"to": "eof"})
        elif active_view and active_view != view and getattr(active_view, "is_valid", lambda: False)():
            window.focus_view(active_view)
            if created:
                sublime.set_timeout(lambda: window.focus_view(active_view) if getattr(active_view, "is_valid", lambda: False)() else None, 0)
                sublime.set_timeout(lambda: window.focus_view(active_view) if getattr(active_view, "is_valid", lambda: False)() else None, 50)
        return view

    @classmethod
    def logNc(cls, message, focus=False):
        from datetime import datetime
        formatted = "[{}] {}".format(datetime.now().strftime("%I:%M %p"), message)
        if not getSetting("separate_nc_messages", False):
            print("RC NC: " + formatted)
            return
        view = cls.ensureNcLogView(focus=focus)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        print("RC NC: " + formatted)

    @classmethod
    def ensureCompilerLogView(cls, window=None, focus=False):
        return cls.ensureNcLogView(window, focus)

    @classmethod
    def ensureCompilerPanel(cls, window=None, show=False):
        window = window or sublime.active_window()
        if not window:
            return None
        view = window.create_output_panel("sublimerc_compiler")
        view.assign_syntax("Packages/SublimeRC/terminal.sublime-syntax")
        view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
        view.settings().set("rc_compiler_panel_view", True)
        if show:
            window.run_command("show_panel", {"panel": "output.sublimerc_compiler"})
        return view

    @classmethod
    def compilerOutputLocation(cls):
        location = str(getSetting("compiler_output_location", "tab")).strip().lower()
        return "panel" if location in ("panel", "bottom", "output_panel") else "tab"

    @classmethod
    def showCompilerOutput(cls, window=None):
        if cls.compilerOutputLocation() == "panel":
            cls.ensureCompilerPanel(window, show=True)
        elif getSetting("separate_nc_messages", False):
            cls.ensureCompilerLogView(window, focus=True)
        else:
            print("RC Compiler: output is not shown because separate_nc_messages is disabled")

    @classmethod
    def logCompiler(cls, message, focus=False):
        from datetime import datetime
        formatted = "[{}] {}".format(datetime.now().strftime("%I:%M %p"), message)
        if cls.compilerOutputLocation() == "panel":
            show_panel = bool(focus or getSetting("compiler_panel_auto_show", True))
            view = cls.ensureCompilerPanel(show=show_panel)
            if view:
                view.run_command("rc_chat_append", {"characters": formatted + "\n"})
            print("RC Compiler: " + formatted)
        elif getSetting("separate_nc_messages", False):
            cls.logNc(message, focus=focus)
        else:
            print("RC Compiler: " + formatted)

    @classmethod
    def logToalls(cls, message, focus=False):
        from datetime import datetime
        formatted = "[{}] {}".format(datetime.now().strftime("%I:%M %p"), message)
        view = cls.ensureToallsView(focus=focus)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        print("RC Toalls: " + formatted)

    @classmethod
    def logFileBrowser(cls, message, focus=False):
        from datetime import datetime
        formatted = "[{}] {}".format(datetime.now().strftime("%I:%M %p"), message)
        view = cls.ensureFileBrowserLogView(focus=focus)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        print("RC File Browser: " + formatted)

    @classmethod
    def _eventLoop(cls):
        while cls.rc_handle:
            try:
                _grclib.rc_process_events(cls.rc_handle)
            except Exception as e:
                cls.log("Event loop error: " + str(e), debug_only=True)
            time.sleep(0.05)

    @classmethod
    def _onConnected(cls, user_data):
        cls.authenticated = True
        cls.log("Authenticated to server", debug_only=True)
        _grclib.rc_execute(cls.rc_handle, b'/npc sublimerc_grclib,2026.06.13')
        nickname = getSetting("nickname", "")
        if nickname:
            _grclib.rc_set_nickname(cls.rc_handle, nickname.encode('latin-1'))
        if not cls.irc_bootstrapped:
            cls.irc_bootstrapped = True
            _grclib.rc_irc_login(cls.rc_handle)
        if not cls.nc_authenticated:
            threading.Thread(target=cls._connectToNcAsync, daemon=True).start()

    @classmethod
    def _onDisconnected(cls, reason, user_data):
        if cls.switching_servers:
            return
        reason_str = reason.decode('utf-8') if reason else "Unknown"
        cls.log("Disconnected: " + reason_str)
        cls.authenticated = False
        cls.nc_authenticated = False

    @classmethod
    def _onPlayerJoined(cls, account, player_id, user_data):
        account_str = account.decode('utf-8') if account else ""
        cls.log("Player joined: {} (ID: {})".format(account_str, player_id), debug_only=True)
        cls._updatePlayerCache()
        if cls.pending_pm_server_request:
            sublime.set_timeout(cls._showPendingPMServerPlayers, 150)

    @classmethod
    def _onPlayerLeft(cls, account, player_id, user_data):
        account_str = account.decode('utf-8') if account else ""
        cls.log("Player left: {} (ID: {})".format(account_str, player_id), debug_only=True)
        cls._updatePlayerCache()

    @classmethod
    def _onMessage(cls, message, user_data):
        msg_str = message.decode('utf-8') if message else ""
        cls.log(msg_str)

    @classmethod
    def _onPrivateMessage(cls, player_id, account, nick, message, user_data):
        account_str = account.decode('latin-1', errors='ignore') if account else ""
        nick_str = nick.decode('latin-1', errors='ignore') if nick else ""
        msg_str = message.decode('latin-1', errors='ignore') if message else ""
        sender = nick_str or account_str or "player {}".format(player_id)
        if account_str and account_str != sender:
            sender = "{} ({})".format(sender, account_str)
        cls.log("PM from {}: {}".format(sender, msg_str))

    @classmethod
    def _onFileReceived(cls, path, content, length, user_data):
        path_str = path.decode('utf-8', errors='ignore') if path else ""
        content_bytes = ctypes.string_at(content, length) if content else b''
        if not path_str:
            path_str = "downloaded_file"
        folder = cls.current_folder.replace('*', '').replace('\\', '/').strip('/') if cls.current_folder else ""
        if '/' not in path_str and folder:
            path_str = folder + "/" + path_str
        server_name = getCleanServerName(cls.connected_server['name']) if cls.connected_server else "Unknown"
        local_path = os.path.join(getScriptsFolder(), server_name, "modified", *[sanitizePath(part) for part in path_str.replace('\\', '/').split('/') if part])
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, 'wb') as f:
            f.write(content_bytes)
        cls.log("File saved: {}".format(local_path))
        if cls.external_open_requested:
            cls.external_open_requested = False
            try:
                if hasattr(os, "startfile"):
                    os.startfile(local_path)
                else:
                    import subprocess
                    subprocess.Popen(["xdg-open", local_path])
                cls.log("Opened file externally: {}".format(os.path.basename(local_path)))
            except Exception as e:
                cls.log("Failed to open externally: {}".format(str(e)))
        elif cls.open_after_download:
            cls.open_after_download = False
            window = sublime.active_window()
            if window:
                view = window.open_file(local_path)
                def tag_view():
                    view.settings().set('rc_filebrowser_path', path_str)
                    try:
                        view.settings().set('rc_original_content', content_bytes.decode('utf-8'))
                    except:
                        view.settings().set('rc_original_content', '')
                sublime.set_timeout(tag_view, 250)
        cls.pending_file_download = None

    @classmethod
    def _onWeaponAdded(cls, name, user_data):
        name_str = name.decode('utf-8') if name else ""
        cls.log("Weapon added: {}".format(name_str), debug_only=True)
        cls._updateWeaponCache()

    @classmethod
    def _onWeaponDeleted(cls, name, user_data):
        name_str = name.decode('utf-8') if name else ""
        cls.log("Weapon deleted: {}".format(name_str), debug_only=True)
        cls._updateWeaponCache()

    @classmethod
    def _onClassAdded(cls, name, user_data):
        name_str = name.decode('utf-8') if name else ""
        cls.log("Class added: {}".format(name_str), debug_only=True)
        cls._updateClassCache()

    @classmethod
    def _onClassDeleted(cls, name, user_data):
        name_str = name.decode('utf-8') if name else ""
        cls.log("Class deleted: {}".format(name_str), debug_only=True)
        cls._updateClassCache()

    @classmethod
    def _onNPCAdded(cls, npc_id, name, user_data):
        name_str = name.decode('utf-8') if name else ""
        cls.log("NPC added: {} (ID: {})".format(name_str, npc_id), debug_only=True)
        cls._updateNPCCache()

    @classmethod
    def _onNPCDeleted(cls, npc_id, user_data):
        cls.log("NPC deleted: ID {}".format(npc_id), debug_only=True)
        cls._updateNPCCache()

    @classmethod
    def _onPlayerPropChanged(cls, player_id, prop, value, user_data):
        prop_str = prop.decode('utf-8') if prop else ""
        value_str = value.decode('utf-8') if value else ""
        if prop_str == "nick":
            for player in cls.players:
                if player.get('id') == player_id:
                    player['nickname'] = value_str
                    break
        cls.log("Player {} prop changed: {} = {}".format(player_id, prop_str, value_str), debug_only=True)

    @classmethod
    def _onWorldTime(cls, world_time, user_data):
        cls.log("World time: {}".format(world_time), debug_only=True)

    @classmethod
    def _onMaxUploadFileSize(cls, max_size, user_data):
        cls.max_upload_file_size = max_size
        cls.log("Max upload file size: {} bytes".format(max_size), debug_only=True)

    @classmethod
    def _onCommandResponse(cls, response, user_data):
        resp_str = response.decode('utf-8') if response else ""
        if resp_str:
            cls.logNc(resp_str)

    @classmethod
    def _onPMServersUpdated(cls, count, user_data):
        cls._updatePMServerCache()
        cls.log("Received {} PM servers".format(count), debug_only=True)
        if cls.pending_pm_server_list_palette:
            cls.pending_pm_server_list_palette = False
            def open_palette():
                window = sublime.active_window()
                if window:
                    window.run_command("rc_show_global_chat")
            sublime.set_timeout(open_palette, 0)

    @classmethod
    def _onNPCFlags(cls, npc_id, flags, user_data):
        flags_text = flags.decode('latin-1', errors='ignore') if flags else ""
        cls.npc_flags[npc_id] = flags_text
        cls.log("Received NPC flags for ID: {} ({} bytes)".format(npc_id, len(flags_text)), debug_only=True)
        pending = cls.pending_npc_flags_request
        if pending and pending.get('id') == npc_id:
            cls.pending_npc_flags_request = None
            def open_flags():
                window = sublime.active_window()
                if window:
                    RcShowNpcsCommand(window).openNpcFlags(pending)
            sublime.set_timeout(open_flags, 0)

    @classmethod
    def _onNPCAttributes(cls, npc_id, attributes, user_data):
        attr_text = attributes.decode('latin-1', errors='ignore') if attributes else ""
        pending = cls.pending_npc_attributes_request
        target_id = npc_id if npc_id >= 0 else (pending.get('id') if pending else npc_id)
        if target_id is not None and target_id >= 0:
            cls.npc_attributes[target_id] = attr_text
        if pending:
            cls.pending_npc_attributes_request = None
            def open_attrs():
                window = sublime.active_window()
                if window:
                    RcShowNpcsCommand(window).openNpcAttributes(pending)
            sublime.set_timeout(open_attrs, 0)

    @classmethod
    def _onPMServerPlayers(cls, server_name, player_data, user_data):
        name = server_name.decode('latin-1', errors='ignore') if server_name else ""
        data = player_data.decode('latin-1', errors='ignore') if player_data else ""
        cls.updatePMPlayers(name, data)

    @classmethod
    def _onIrcMessage(cls, channel, line, user_data):
        channel_text = channel.decode('latin-1', errors='ignore') if channel else ""
        line_text = line.decode('latin-1', errors='ignore') if line else ""
        if not channel_text or not line_text:
            return
        if not line_text.startswith("["):
            from datetime import datetime
            clock = datetime.now().strftime("%I:%M%p").lstrip("0").lower()
            line_text = "[{}] {}".format(clock, line_text)
        cls.appendIrcMessage(channel_text, line_text)
        cls.log("IRC {}: {}".format(channel_text, line_text), debug_only=True)

    @classmethod
    def _onBanData(cls, account, computer_id, details, user_data):
        account_text = account.decode('latin-1', errors='ignore') if account else ""
        computer_text = computer_id.decode('latin-1', errors='ignore') if computer_id else ""
        detail_text = details.decode('latin-1', errors='ignore') if details else ""
        cls.log("Received ban data for: {} ({})".format(account_text, computer_text), debug_only=True)
        if detail_text:
            cls.log("Ban details: " + detail_text, debug_only=True)

    @classmethod
    def _onBanListData(cls, data_type, account, content, user_data):
        kind = data_type.decode('latin-1', errors='ignore') if data_type else ""
        account_text = account.decode('latin-1', errors='ignore') if account else ""
        text = content.decode('latin-1', errors='ignore') if content else ""
        cls.log("Received {} for {} ({} bytes)".format(kind, account_text, len(text)), debug_only=True)

    @classmethod
    def _onAccountList(cls, accounts, user_data):
        text = accounts.decode('latin-1', errors='ignore') if accounts else ""
        cls.account_list = [line.strip() for line in text.splitlines() if line.strip()]
        cls.log("Received {} accounts".format(len(cls.account_list)), debug_only=True)
        if cls.account_list_callback:
            callback = cls.account_list_callback
            cls.account_list_callback = None
            sublime.set_timeout(callback, 0)

    @classmethod
    def _onFileBrowserFolders(cls, count, user_data):
        cls._updateFileBrowserFolders()
        cls.log("Received {} folders".format(count), debug_only=True)
        if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
            sublime.set_timeout(cls.file_browser_callback, 0)

    @classmethod
    def _onFileBrowserFiles(cls, folder, count, user_data):
        folder_path = folder.decode('latin-1', errors='ignore') if folder else ""
        cls.current_folder = folder_path
        cls._updateFileBrowserFiles()
        cls.log("Folder contains {} items".format(count), debug_only=True)
        if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
            sublime.set_timeout(cls.file_browser_callback, 0)

    @classmethod
    def _onFileBrowserMessage(cls, message, user_data):
        msg = message.decode('latin-1', errors='ignore') if message else ""
        if msg:
            cls.log(msg)

    @classmethod
    def _onScriptReceived(cls, script_type, name, script_id, script, user_data):
        kind = script_type.decode('latin-1', errors='ignore') if script_type else ""
        item_name = name.decode('latin-1', errors='ignore') if name else ""
        script_text = script.decode('latin-1', errors='ignore') if script else ""
        if kind == "npc":
            cls.npc_scripts[script_id] = script_text
            pending = cls.pending_npc_script_request
            if pending and pending.get('id') == script_id:
                cls.pending_npc_script_request = None
                def open_npc():
                    window = sublime.active_window()
                    if window:
                        RcShowNpcsCommand(window).openNpcScript(pending)
                sublime.set_timeout(open_npc, 0)
        elif kind == "class":
            cls.class_scripts[item_name] = script_text
            if cls.pending_class_script_request == item_name:
                cls.pending_class_script_request = None
                def open_class():
                    window = sublime.active_window()
                    if window:
                        RcShowClassesCommand(window).openClassScript(item_name)
                sublime.set_timeout(open_class, 0)
        elif kind == "weapon":
            cls.weapon_scripts[item_name] = script_text
            if cls.pending_weapon_script_request == item_name:
                cls.pending_weapon_script_request = None
                def open_weapon():
                    window = sublime.active_window()
                    if window:
                        RcShowWeaponsCommand(window).openWeaponScript(item_name)
                sublime.set_timeout(open_weapon, 0)

    @classmethod
    def _onServerData(cls, data_type, content, user_data):
        kind = data_type.decode('latin-1', errors='ignore') if data_type else ""
        text = content.decode('latin-1', errors='ignore') if content else ""
        if kind == "options":
            cls.server_options = text
            if cls.pending_server_options_request:
                cls.pending_server_options_request = False
                def open_options():
                    window = sublime.active_window()
                    if window:
                        RcEditServerOptionsCommand(window).openServerOptions()
                sublime.set_timeout(open_options, 0)
        elif kind == "flags":
            cls.server_flags = text
            if cls.pending_server_flags_request:
                cls.pending_server_flags_request = False
                def open_flags():
                    window = sublime.active_window()
                    if window:
                        RcEditServerFlagsCommand(window).openServerFlags()
                sublime.set_timeout(open_flags, 0)
        elif kind == "folder_config":
            cls.folder_config = text
            if cls.pending_folder_config_request:
                cls.pending_folder_config_request = False
                def open_config():
                    window = sublime.active_window()
                    if window:
                        RcEditFolderConfigCommand(window).openFolderConfig()
                sublime.set_timeout(open_config, 0)
        elif kind == "toall":
            if text:
                cls.logToalls(text)
        elif kind in ("nc_message", "nc_levellist"):
            if text:
                cls.logNc(text)
        elif kind == "admin_message":
            if text:
                print("RC Admin: " + text)

    @classmethod
    def _onPlayerRights(cls, account, rights, ip_range, folder_access, user_data):
        response_account = account.decode('latin-1', errors='ignore') if account else ""
        requested = cls.pending_player_rights_request or response_account
        cls.player_rights[requested] = {
            'rights': rights,
            'ip': ip_range.decode('latin-1', errors='ignore') if ip_range else "",
            'folders': folder_access.decode('latin-1', errors='ignore') if folder_access else ""
        }
        cls.pending_player_rights_request = None
        def open_editor():
            window = sublime.active_window()
            if window:
                RcShowPlayersCommand(window).editPlayerRights({'account': requested})
        sublime.set_timeout(open_editor, 0)

    @classmethod
    def _onPlayerTextData(cls, data_type, account, content, user_data):
        kind = data_type.decode('latin-1', errors='ignore') if data_type else ""
        response_account = account.decode('latin-1', errors='ignore') if account else ""
        text = content.decode('latin-1', errors='ignore') if content else ""
        if kind == "comments":
            requested = cls.pending_player_comments_request or response_account
            cls.player_comments[requested] = text
            cls.pending_player_comments_request = None
            sublime.set_timeout(lambda: RcShowPlayersCommand(sublime.active_window()).editPlayerComments({'account': requested}) if sublime.active_window() else None, 0)
        elif kind == "account":
            requested = cls.pending_account_request or response_account
            account_info = {}
            for line in text.split('\n'):
                key, sep, value = line.partition('=')
                if sep:
                    account_info[key] = value
            account_info['banned'] = account_info.get('banned') == '1'
            account_info['guest'] = account_info.get('guest') == '1'
            account_info['ban_time'] = 0
            cls.player_accounts[requested] = account_info
            cls.pending_account_request = None
            sublime.set_timeout(lambda: RcShowPlayersCommand(sublime.active_window()).editPlayerAccount({'account': requested}) if sublime.active_window() else None, 0)
        elif kind == "profile":
            requested = cls.pending_player_profile_request or response_account
            cls.player_profiles[requested] = text.split('\n') if text else []
            cls.pending_player_profile_request = None
            def open_profile():
                window = sublime.active_window()
                if window:
                    player = {'account': requested}
                    for p in cls.players:
                        if p.get('account') == requested:
                            player = p
                            break
                    RcShowPlayersCommand(window).viewPlayerProfile(player)
            sublime.set_timeout(open_profile, 0)

    @classmethod
    def _onPlayerAttributes(cls, account, properties_json, editor_text, user_data):
        response_account = account.decode('latin-1', errors='ignore') if account else ""
        raw = properties_json.decode('latin-1', errors='ignore') if properties_json else "{}"
        try:
            decoded = json.loads(raw)
        except Exception as e:
            cls.log("Failed to decode player attributes for {}: {}".format(response_account, e), debug_only=True)
            decoded = {}
        properties = {}
        for key, value in decoded.items():
            properties[int(key) if isinstance(key, str) and key.isdigit() else key] = value
        properties['_properties_json'] = raw
        requested = cls.pending_player_attrs_request or response_account or properties.get('account', '')
        if not requested:
            return
        cls.player_attributes[requested] = properties
        if editor_text:
            properties['_editor_text'] = editor_text.decode('latin-1', errors='ignore')
        cls.log("Received attributes for: " + requested)
        cls.pending_player_attrs_request = None
        def open_editor():
            window = sublime.active_window()
            if window:
                RcShowPlayersCommand(window).editPlayerAttributes({'account': requested})
        sublime.set_timeout(open_editor, 0)

    @classmethod
    def _setupCallbacks(cls):
        cls._callbacks['connected'] = RC_OnConnected(lambda ud: cls._onConnected(ud))
        cls._callbacks['disconnected'] = RC_OnDisconnected(lambda r, ud: cls._onDisconnected(r, ud))
        cls._callbacks['player_joined'] = RC_OnPlayerJoined(lambda a, i, ud: cls._onPlayerJoined(a, i, ud))
        cls._callbacks['player_left'] = RC_OnPlayerLeft(lambda a, i, ud: cls._onPlayerLeft(a, i, ud))
        cls._callbacks['message'] = RC_OnMessage(lambda m, ud: cls._onMessage(m, ud))
        cls._callbacks['private_message'] = RC_OnPrivateMessage(lambda i, a, n, m, ud: cls._onPrivateMessage(i, a, n, m, ud))
        cls._callbacks['file_received'] = RC_OnFileReceived(lambda p, c, l, ud: cls._onFileReceived(p, c, l, ud))
        cls._callbacks['weapon_added'] = RC_OnWeaponAdded(lambda n, ud: cls._onWeaponAdded(n, ud))
        cls._callbacks['weapon_deleted'] = RC_OnWeaponDeleted(lambda n, ud: cls._onWeaponDeleted(n, ud))
        cls._callbacks['class_added'] = RC_OnClassAdded(lambda n, ud: cls._onClassAdded(n, ud))
        cls._callbacks['class_deleted'] = RC_OnClassDeleted(lambda n, ud: cls._onClassDeleted(n, ud))
        cls._callbacks['npc_added'] = RC_OnNPCAdded(lambda i, n, ud: cls._onNPCAdded(i, n, ud))
        cls._callbacks['npc_deleted'] = RC_OnNPCDeleted(lambda i, ud: cls._onNPCDeleted(i, ud))
        cls._callbacks['npc_attributes'] = RC_OnNPCAttributes(lambda i, a, ud: cls._onNPCAttributes(i, a, ud))
        cls._callbacks['player_prop'] = RC_OnPlayerPropChanged(lambda i, p, v, ud: cls._onPlayerPropChanged(i, p, v, ud))
        cls._callbacks['world_time'] = RC_OnWorldTime(lambda t, ud: cls._onWorldTime(t, ud))
        cls._callbacks['max_upload_file_size'] = RC_OnMaxUploadFileSize(lambda s, ud: cls._onMaxUploadFileSize(s, ud))
        cls._callbacks['command_response'] = RC_OnCommandResponse(lambda r, ud: cls._onCommandResponse(r, ud))
        cls._callbacks['pm_servers_updated'] = RC_OnPMServersUpdated(lambda c, ud: cls._onPMServersUpdated(c, ud))
        cls._callbacks['npc_flags'] = RC_OnNPCFlags(lambda i, f, ud: cls._onNPCFlags(i, f, ud))
        cls._callbacks['pm_server_players'] = RC_OnPMServerPlayers(lambda s, p, ud: cls._onPMServerPlayers(s, p, ud))
        cls._callbacks['filebrowser_folders'] = RC_OnFileBrowserFolders(lambda c, ud: cls._onFileBrowserFolders(c, ud))
        cls._callbacks['filebrowser_files'] = RC_OnFileBrowserFiles(lambda f, c, ud: cls._onFileBrowserFiles(f, c, ud))
        cls._callbacks['filebrowser_message'] = RC_OnFileBrowserMessage(lambda m, ud: cls._onFileBrowserMessage(m, ud))
        cls._callbacks['script_received'] = RC_OnScriptReceived(lambda t, n, i, s, ud: cls._onScriptReceived(t, n, i, s, ud))
        cls._callbacks['server_data'] = RC_OnServerData(lambda t, c, ud: cls._onServerData(t, c, ud))
        cls._callbacks['player_rights'] = RC_OnPlayerRights(lambda a, r, i, f, ud: cls._onPlayerRights(a, r, i, f, ud))
        cls._callbacks['player_text_data'] = RC_OnPlayerTextData(lambda t, a, c, ud: cls._onPlayerTextData(t, a, c, ud))
        cls._callbacks['player_attributes'] = RC_OnPlayerAttributes(lambda a, p, t, ud: cls._onPlayerAttributes(a, p, t, ud))
        cls._callbacks['irc_message'] = RC_OnIrcMessage(lambda c, l, ud: cls._onIrcMessage(c, l, ud))
        cls._callbacks['ban_data'] = RC_OnBanData(lambda a, c, d, ud: cls._onBanData(a, c, d, ud))
        cls._callbacks['ban_list_data'] = RC_OnBanListData(lambda t, a, c, ud: cls._onBanListData(t, a, c, ud))
        cls._callbacks['account_list'] = RC_OnAccountList(lambda a, ud: cls._onAccountList(a, ud))
        
        if cls.debug_mode:
            cls._callbacks['raw_packet'] = RC_OnRawPacket(lambda pid, d, l, ud: cls._onRawPacket(pid, d, l, ud))
        
        _grclib.rc_on_connected(cls.rc_handle, cls._callbacks['connected'], None)
        _grclib.rc_on_disconnected(cls.rc_handle, cls._callbacks['disconnected'], None)
        _grclib.rc_on_player_joined(cls.rc_handle, cls._callbacks['player_joined'], None)
        _grclib.rc_on_player_left(cls.rc_handle, cls._callbacks['player_left'], None)
        _grclib.rc_on_message(cls.rc_handle, cls._callbacks['message'], None)
        _grclib.rc_on_private_message(cls.rc_handle, cls._callbacks['private_message'], None)
        _grclib.rc_on_file_received(cls.rc_handle, cls._callbacks['file_received'], None)
        _grclib.rc_on_weapon_added(cls.rc_handle, cls._callbacks['weapon_added'], None)
        _grclib.rc_on_weapon_deleted(cls.rc_handle, cls._callbacks['weapon_deleted'], None)
        _grclib.rc_on_class_added(cls.rc_handle, cls._callbacks['class_added'], None)
        _grclib.rc_on_class_deleted(cls.rc_handle, cls._callbacks['class_deleted'], None)
        _grclib.rc_on_npc_added(cls.rc_handle, cls._callbacks['npc_added'], None)
        _grclib.rc_on_npc_deleted(cls.rc_handle, cls._callbacks['npc_deleted'], None)
        _grclib.rc_on_npc_attributes(cls.rc_handle, cls._callbacks['npc_attributes'], None)
        _grclib.rc_on_player_prop_changed(cls.rc_handle, cls._callbacks['player_prop'], None)
        _grclib.rc_on_world_time(cls.rc_handle, cls._callbacks['world_time'], None)
        _grclib.rc_on_max_upload_file_size(cls.rc_handle, cls._callbacks['max_upload_file_size'], None)
        _grclib.rc_on_command_response(cls.rc_handle, cls._callbacks['command_response'], None)
        _grclib.rc_on_pm_servers_updated(cls.rc_handle, cls._callbacks['pm_servers_updated'], None)
        _grclib.rc_on_npc_flags(cls.rc_handle, cls._callbacks['npc_flags'], None)
        _grclib.rc_on_pm_server_players(cls.rc_handle, cls._callbacks['pm_server_players'], None)
        _grclib.rc_on_filebrowser_folders(cls.rc_handle, cls._callbacks['filebrowser_folders'], None)
        _grclib.rc_on_filebrowser_files(cls.rc_handle, cls._callbacks['filebrowser_files'], None)
        _grclib.rc_on_filebrowser_message(cls.rc_handle, cls._callbacks['filebrowser_message'], None)
        _grclib.rc_on_script_received(cls.rc_handle, cls._callbacks['script_received'], None)
        _grclib.rc_on_server_data(cls.rc_handle, cls._callbacks['server_data'], None)
        _grclib.rc_on_player_rights(cls.rc_handle, cls._callbacks['player_rights'], None)
        _grclib.rc_on_player_text_data(cls.rc_handle, cls._callbacks['player_text_data'], None)
        _grclib.rc_on_player_attributes(cls.rc_handle, cls._callbacks['player_attributes'], None)
        _grclib.rc_on_irc_message(cls.rc_handle, cls._callbacks['irc_message'], None)
        _grclib.rc_on_ban_data(cls.rc_handle, cls._callbacks['ban_data'], None)
        _grclib.rc_on_ban_list_data(cls.rc_handle, cls._callbacks['ban_list_data'], None)
        _grclib.rc_on_account_list(cls.rc_handle, cls._callbacks['account_list'], None)
        
        if cls.debug_mode:
            _grclib.rc_on_raw_packet(cls.rc_handle, cls._callbacks['raw_packet'], None)

    @classmethod
    def _updatePMServerCache(cls):
        if not cls.rc_handle: return
        try:
            servers_ptr = POINTER(c_char_p)()
            count = _grclib.rc_get_pm_servers(cls.rc_handle, ctypes.byref(servers_ptr))
            cls.pm_servers = []
            for i in range(count):
                try:
                    server_name = servers_ptr[i].decode('latin-1') if servers_ptr[i] else ''
                    if server_name:
                        cls.pm_servers.append(server_name)
                except:
                    break
        except Exception as e:
            cls.log("Error updating PM server cache: " + str(e), debug_only=True)

    @classmethod
    def _updateFileBrowserFolders(cls):
        if not cls.rc_handle: return
        try:
            folders_ptr = POINTER(RCFileBrowserFolder)()
            count = _grclib.rc_get_filebrowser_folders(cls.rc_handle, ctypes.byref(folders_ptr))
            cls.folders = []
            for i in range(count):
                folder = folders_ptr[i]
                rights = folder.rights.decode('latin-1', errors='ignore') if folder.rights else ''
                pattern = folder.pattern.decode('latin-1', errors='ignore') if folder.pattern else ''
                if pattern:
                    cls.folders.append({'name': pattern, 'rights': rights, 'pattern': pattern})
        except Exception as e:
            cls.log("Error updating file browser folders: " + str(e), debug_only=True)

    @classmethod
    def _updateFileBrowserFiles(cls):
        if not cls.rc_handle: return
        try:
            entries_ptr = POINTER(RCFileBrowserEntry)()
            count = _grclib.rc_get_filebrowser_files(cls.rc_handle, ctypes.byref(entries_ptr))
            cls.folder_files = []
            for i in range(count):
                entry = entries_ptr[i]
                path = entry.path.decode('latin-1', errors='ignore') if entry.path else ''
                rights = entry.rights.decode('latin-1', errors='ignore') if entry.rights else ''
                cls.folder_files.append({
                    'path': path,
                    'rights': rights,
                    'size': entry.size,
                    'modified': entry.modified,
                    'is_directory': bool(entry.is_directory)
                })
        except Exception as e:
            cls.log("Error updating file browser files: " + str(e), debug_only=True)

    @classmethod
    def _updatePlayerCache(cls):
        if not cls.rc_handle: return
        try:
            players_ptr = POINTER(RCPlayer)()
            count = _grclib.rc_get_players(cls.rc_handle, ctypes.byref(players_ptr))
            cls.players = []
            pm_players_by_server = {}
            for i in range(count):
                try:
                    p = players_ptr[i]
                    account = p.account.decode('latin-1') if p.account else ''
                    nickname = p.nick.decode('latin-1') if p.nick else ''
                    level = p.level.decode('latin-1') if p.level else ''
                    player_id = p.id
                    player = {'account': account, 'id': player_id, 'nickname': nickname, 'level': level}
                    if player_id >= 16000 and "(on " in nickname:
                        server_name = nickname.split("(on ", 1)[1].split(")", 1)[0].strip()
                        if server_name:
                            player['server'] = server_name
                            player['external'] = True
                            cls.external_players[player_id] = player
                            pm_players_by_server.setdefault(server_name, {})[account.lower()] = {
                                'account': account,
                                'nickname': nickname.split("(on ", 1)[0].strip()
                            }
                    cls.players.append(player)
                except:
                    break
            for server_name, player_map in pm_players_by_server.items():
                cls.pm_server_players[server_name] = list(player_map.values())
                if server_name not in cls.pm_servers:
                    cls.pm_servers.append(server_name)
            known_ids = set(p.get('id') for p in cls.players)
            for ext_player in cls.external_players.values():
                if ext_player.get('id') not in known_ids:
                    cls.players.append(ext_player)
            if cls.pending_pm_server_request:
                cls._showPendingPMServerPlayers()
        except Exception as e:
            cls.log("Error updating player cache: " + str(e), debug_only=True)

    @classmethod
    def _displayServerName(cls, server_name):
        for server in cls.servers:
            if server.get("name") == server_name:
                return server.get("display_name", server_name)
        prefixes = ["🌍 ", "🪐 ", "⏳ ", "🕶️ ", "🚧 "]
        for prefix in prefixes:
            if server_name.startswith(prefix):
                return server_name[len(prefix):].strip()
        return server_name

    @classmethod
    def _showPendingPMServerPlayers(cls):
        if not cls.pending_pm_server_request:
            return
        candidates = [cls.pending_pm_server_request, cls._displayServerName(cls.pending_pm_server_request)]
        for server in cls.servers:
            if server.get("name") == cls.pending_pm_server_request:
                candidates.append(server.get("display_name", ""))
        normalized = set(c.strip().lower() for c in candidates if c)
        for player in cls.players:
            server_name = player.get('server', '')
            if server_name and server_name.strip().lower() in normalized:
                cls.pending_pm_server_request = None
                def show_players():
                    window = sublime.active_window()
                    if window:
                        RcShowGlobalChatCommand(window).showServerPlayers(server_name)
                sublime.set_timeout(show_players, 0)
                return

    @classmethod
    def _updateWeaponCache(cls):
        if not cls.rc_handle: return
        try:
            weapons_ptr = POINTER(RCWeapon)()
            count = _grclib.rc_get_weapons(cls.rc_handle, ctypes.byref(weapons_ptr))
            cls.weapons = []
            for i in range(count):
                try:
                    w = weapons_ptr[i]
                    name = w.name.decode('latin-1') if w.name else ''
                    image = w.image.decode('latin-1') if w.image else ''
                    script = w.script.decode('latin-1') if w.script else ''
                    cls.weapons.append({'name': name, 'image': image, 'script': script})
                    if script:
                        cls.weapon_scripts[name] = script
                except:
                    break
        except Exception as e:
            cls.log("Error updating weapon cache: " + str(e), debug_only=True)

    @classmethod
    def _updateClassCache(cls):
        if not cls.rc_handle: return
        try:
            classes_ptr = POINTER(RCClass)()
            count = _grclib.rc_get_classes(cls.rc_handle, ctypes.byref(classes_ptr))
            cls.classes = []
            for i in range(count):
                try:
                    c = classes_ptr[i]
                    name = c.name.decode('latin-1') if c.name else ''
                    script = c.script.decode('latin-1') if c.script else ''
                    cls.classes.append({'name': name, 'script': script})
                    if script:
                        cls.class_scripts[name] = script
                except:
                    break
        except Exception as e:
            cls.log("Error updating class cache: " + str(e), debug_only=True)

    @classmethod
    def _updateNPCCache(cls):
        if not cls.rc_handle: return
        try:
            npcs_ptr = POINTER(RCNPC)()
            count = _grclib.rc_get_npcs(cls.rc_handle, ctypes.byref(npcs_ptr))
            cls.npcs = []
            for i in range(count):
                try:
                    n = npcs_ptr[i]
                    npc_id = n.id
                    name = n.name.decode('latin-1') if n.name else ''
                    npc_type = n.type.decode('latin-1') if n.type else ''
                    image = n.image.decode('latin-1') if n.image else ''
                    script = n.script.decode('latin-1') if n.script else ''
                    cls.npcs.append({'id': npc_id, 'name': name, 'type': npc_type, 'image': image, 'script': script})
                    if script:
                        cls.npc_scripts[npc_id] = script
                except:
                    break
        except Exception as e:
            cls.log("Error updating NPC cache: " + str(e), debug_only=True)

    @classmethod
    def _refreshServerCache(cls, listserver_config):
        if not cls.rc_handle: return
        servers_ptr = POINTER(RCServer)()
        count = _grclib.rc_get_servers(cls.rc_handle, ctypes.byref(servers_ptr))
        cls.servers = []
        for i in range(count):
            s = servers_ptr[i]
            desc = s.description.decode('utf-8') if s.description else ''
            if not desc: desc = 'No description.'
            raw_name = s.name.decode('utf-8')
            if len(raw_name) > 2 and raw_name[1] == ' ' and raw_name[0] in 'PH3U':
                icon = {'P': '🪙', 'H': '⏳', '3': '🕶️', 'U': '🚧'}[raw_name[0]]
                display_name = icon + ' ' + raw_name[2:]
            else:
                display_name = '🌍 ' + raw_name
            cls.servers.append({'name': display_name, 'ip': s.ip.decode('utf-8'), 'port': s.port, 'players': s.players, 'language': s.language.decode('utf-8') if s.language else '', 'description': desc, 'listserver_config': listserver_config})
    @classmethod
    def refreshServers(cls, listserver_config=None):
        try:
            if listserver_config is None:
                configs = getListserverConfigs()
                if cls.current_listserver_config:
                    listserver_config = cls.current_listserver_config
                else:
                    listserver_config = configs[0] if configs else None
                    if not listserver_config:
                        cls.log("No listserver configured")
                        return False
            cls.current_listserver_config = listserver_config
            listserver_host = listserver_config['host']
            listserver_port = listserver_config['port']
            account = listserver_config['account']
            password = listserver_config['password']
            if not account or not password:
                cls.log("Please set credentials first")
                return False
            cls.log("Connecting to listserver: {}:{}".format(listserver_host, listserver_port), debug_only=True)
            cls.log("Account: {}".format(account), debug_only=True)
            cls.rc_handle = _grclib.rc_connect(listserver_host.encode('latin-1'), listserver_port, account.encode('latin-1'), password.encode('latin-1'))
            if not cls.rc_handle:
                cls.log("Failed to connect to listserver (null handle)")
                return False
            error = _grclib.rc_last_error(cls.rc_handle)
            if error:
                cls.log("Listserver error: {}".format(error.decode('utf-8')))
            cls._refreshServerCache(listserver_config)
            cls.log("Retrieved {} servers".format(len(cls.servers)), debug_only=True)
            return True
        except Exception as e:
            cls.log("Failed to refresh servers: " + str(e))
            import traceback
            cls.log(traceback.format_exc())
            return False

    @classmethod
    def connectToServer(cls, server_info):
        try:
            if 'ip' not in server_info or 'port' not in server_info:
                cls.log("Server {} does not have IP/port information".format(server_info.get('name', 'Unknown')))
                return False
            if not cls.rc_handle:
                listserver_config = server_info.get('listserver_config')
                if not listserver_config:
                    configs = getListserverConfigs()
                    listserver_config = configs[0] if configs else None
                    if not listserver_config:
                        cls.log("No listserver configured")
                        return False
                listserver_host = listserver_config['host']
                listserver_port = listserver_config['port']
                account = listserver_config['account']
                password = listserver_config['password']
                cls.rc_handle = _grclib.rc_connect(listserver_host.encode('latin-1'), listserver_port, account.encode('latin-1'), password.encode('latin-1'))
                if not cls.rc_handle:
                    cls.log("Failed to connect to listserver")
                    return False
                cls._refreshServerCache(listserver_config)
            server_index = next((i for i, s in enumerate(cls.servers) if s['name'] == server_info['name']), -1)
            if server_index == -1:
                cls.log("Server not found in list")
                return False
            result = _grclib.rc_connect_to_server(cls.rc_handle, server_index)
            if result != 1:
                error = _grclib.rc_last_error(cls.rc_handle)
                cls.log("Connection failed: " + (error.decode('utf-8') if error else "Unknown error"))
                return False
            cls.connected_server = server_info
            cls.authenticated = False
            cls.nc_authenticated = False
            cls._setupCallbacks()
            if not cls.event_thread or not cls.event_thread.is_alive():
                cls.event_thread = threading.Thread(target=cls._eventLoop, daemon=True)
                cls.event_thread.start()
            cls.log("Connecting to " + server_info['name'], debug_only=True)
            return True
        except Exception as e:
            cls.log("Connection failed: " + str(e))
            return False

    @classmethod
    def _connectToNcAsync(cls):
        try:
            time.sleep(2.0)
            max_tries = 10
            for _ in range(max_tries):
                if cls.connectToNpcServer():
                    break
                time.sleep(1.0)
        except Exception as e:
            cls.logNc("NC async connection error: " + str(e))

    @classmethod
    def connectToNpcServer(cls):
        try:
            if not cls.rc_handle:
                cls.logNc("Not connected to server")
                return False
            if not cls.authenticated:
                cls.logNc("Not authenticated to game server yet")
                return False
            if _grclib.rc_is_nc_connected(cls.rc_handle):
                cls.nc_authenticated = True
                cls.logNc("Already connected to NPC server")
                return True
            result = _grclib.rc_connect_to_nc_server(cls.rc_handle)
            if result == 1:
                cls.nc_authenticated = True
                cls.logNc("Connected to NPC server")
                time.sleep(3.0)
                cls._updateWeaponCache()
                cls._updateClassCache()
                cls._updateNPCCache()
                print("RC: Loaded {} weapons, {} classes, {} NPCs".format(len(cls.weapons), len(cls.classes), len(cls.npcs)))
                if len(cls.weapons) == 0 and len(cls.classes) == 0 and len(cls.npcs) == 0:
                    print("RC: No weapons/classes/npcs. (BORK?)")
                return True
            else:
                error = _grclib.rc_last_error(cls.rc_handle)
                error_msg = error.decode('utf-8') if error else "Unknown error"
                cls.logNc("Failed to connect to NPC server: {}".format(error_msg))
                return False
        except Exception as e:
            cls.logNc("NC connection error: " + str(e))
            return False

    @classmethod
    def disconnect(cls):
        if cls.rc_handle:
            cls.switching_servers = True
            _grclib.rc_disconnect(cls.rc_handle)
            cls.rc_handle = None
            cls.connected_server = None
            cls.authenticated = False
            cls.nc_authenticated = False
            cls.switching_servers = False
            cls.servers = []
            cls.players = []
            cls.weapons = []
            cls.classes = []
            cls.npcs = []
            cls.irc_channels = {}
            cls.irc_bootstrapped = False
            cls.log("Disconnected from server")

    @classmethod
    def sendRcChat(cls, command):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        parts = command.strip().split(None, 1)
        slash = parts[0].lower() if parts else ""
        if slash in ("/ircjoin", "/joinirc"):
            channel = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "#graal"
            return cls.joinIrcChannel(channel)
        if slash in ("/ircpart", "/partirc"):
            channel = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
            return cls.partIrcChannel(channel) if channel else False
        result = _grclib.rc_execute(cls.rc_handle, command.encode('utf-8'))
        return result == 1

    @classmethod
    def sendAdminMessageAll(cls, message):
        if not cls.rc_handle or not cls.authenticated:
            cls.log("Not connected")
            return False
        return _grclib.rc_send_admin_message_all(cls.rc_handle, message.encode('latin-1')) == 1

    @classmethod
    def sendToallMessage(cls, message):
        if not cls.rc_handle or not cls.authenticated:
            cls.log("Not connected")
            return False
        return _grclib.rc_send_toall_message(cls.rc_handle, message.encode('latin-1')) == 1

    @classmethod
    def sendMassPm(cls, player_ids, message):
        if not cls.rc_handle or not cls.authenticated or not player_ids:
            cls.log("Not connected or no players selected")
            return False
        ids = (c_int * len(player_ids))(*[int(player_id) for player_id in player_ids])
        return _grclib.rc_send_mass_pm(cls.rc_handle, ids, len(player_ids), message.encode('latin-1')) == 1

    @classmethod
    def sendIrcText(cls, command, param1=None, param2=None, param3=None):
        if not cls.rc_handle or not cls.authenticated:
            cls.log("Not connected")
            return False
        def enc(value):
            return value.encode('latin-1') if value is not None else None
        return _grclib.rc_send_irc_text(cls.rc_handle, enc(command), enc(param1), enc(param2), enc(param3)) == 1

    @classmethod
    def openIrcChannel(cls, channel, focus=True):
        channel = (channel or "").strip()
        if not channel:
            return
        state = cls.irc_channels.setdefault(channel, {"messages": []})
        history = "\n".join(state["messages"])
        text = "{}{}> ".format(history + "\n" if history else "", "" if history.endswith("\n") else "")

        def openView():
            window = sublime.active_window()
            if not window:
                return
            view = next((v for v in window.views() if v.settings().get("rc_irc_view") and v.settings().get("rc_irc_channel") == channel), None)
            if not view:
                view = window.new_file()
                view.set_scratch(True)
                view.assign_syntax("Packages/SublimeRC/irc.sublime-syntax")
                view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                view.settings().set("rc_irc_view", True)
                view.settings().set("rc_irc_channel", channel)
            view.set_name("💬 " + channel)
            view.run_command("rc_replace_buffer_content", {"content": text, "read_only": False})
            if focus:
                window.focus_view(view)
                view.run_command("move_to", {"to": "eof"})
        sublime.set_timeout(openView, 0)

    @classmethod
    def appendIrcMessage(cls, channel, line):
        channel = (channel or "").strip()
        if not channel:
            return
        state = cls.irc_channels.setdefault(channel, {"messages": []})
        state["messages"].append(line)
        refreshed = False
        for window in sublime.windows():
            for view in window.views():
                if view.settings().get("rc_irc_view") and view.settings().get("rc_irc_channel") == channel:
                    refreshed = True
                    view.run_command("rc_chat_append", {"characters": line + "\n"})
                    if window.active_view() == view:
                        view.run_command("move_to", {"to": "eof"})
        if not refreshed:
            cls.openIrcChannel(channel, focus=False)

    @classmethod
    def joinIrcChannel(cls, channel):
        if not cls.rc_handle or not cls.authenticated:
            cls.log("Not connected")
            return False
        ok = _grclib.rc_irc_join(cls.rc_handle, channel.encode('latin-1')) == 1
        if ok:
            cls.openIrcChannel(channel, focus=False)
        return ok

    @classmethod
    def partIrcChannel(cls, channel):
        if not cls.rc_handle or not cls.authenticated:
            cls.log("Not connected")
            return False
        return _grclib.rc_irc_part(cls.rc_handle, channel.encode('latin-1')) == 1

    @classmethod
    def uploadFile(cls, filename, content):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        content_bytes = content.encode('utf-8') if isinstance(content, str) else content
        if cls.max_upload_file_size and len(content_bytes) > cls.max_upload_file_size:
            cls.logFileBrowser("Upload failed: file exceeds server limit of {} bytes".format(cls.max_upload_file_size))
            return False
        result = _grclib.rc_upload_file(cls.rc_handle, filename.encode('utf-8'), content_bytes, len(content_bytes))
        return result == 1

    @classmethod
    def downloadFile(cls, filename):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        cls.pending_file_download = filename
        cls.open_after_download = False
        cls.external_open_requested = False
        result = _grclib.rc_filebrowser_download(cls.rc_handle, filename.encode('latin-1'))
        return result == 1

    @classmethod
    def openFileForEditing(cls, filename):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        cls.pending_file_download = filename
        cls.open_after_download = True
        cls.external_open_requested = False
        cls.log("Opening file: " + filename)
        result = _grclib.rc_filebrowser_download(cls.rc_handle, filename.encode('latin-1'))
        return result == 1

    @classmethod
    def openFileExternally(cls, filename):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        cls.pending_file_download = filename
        cls.open_after_download = False
        cls.external_open_requested = True
        cls.log("Opening file externally: " + filename)
        result = _grclib.rc_filebrowser_download(cls.rc_handle, filename.encode('latin-1'))
        return result == 1

    @classmethod
    def deleteFile(cls, filename):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_filebrowser_delete(cls.rc_handle, filename.encode('latin-1'))
        if result == 1:
            cls.log("Deleting file: " + filename)
        return result == 1

    @classmethod
    def renameFile(cls, old_name, new_name):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_filebrowser_rename(
            cls.rc_handle,
            old_name.encode('latin-1'),
            new_name.encode('latin-1')
        )
        if result == 1:
            cls.log("Renaming file: {} -> {}".format(old_name, new_name))
        return result == 1

    @classmethod
    def disconnectPlayer(cls, player_id, reason=""):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_disconnect_player(cls.rc_handle, player_id, reason.encode('latin-1'))
        return result == 1

    @classmethod
    def warpPlayer(cls, player_id, level, x, y):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_warp_player(cls.rc_handle, player_id, level.encode('latin-1'), float(x), float(y))
        return result == 1

    @classmethod
    def sendPrivateMessage(cls, player_id, message):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_send_private_message(cls.rc_handle, player_id, message.encode('latin-1'))
        return result == 1

    @classmethod
    def formatPlayerRightsText(cls, rights_value, ip_range, folder_access):
        ptr = _grclib.rc_format_player_rights_text(
            rights_value,
            str(ip_range or "").encode('latin-1'),
            str(folder_access or "").encode('latin-1')
        )
        if not ptr:
            raise RuntimeError("grclib failed to format player rights")
        try:
            return ctypes.string_at(ptr).decode('latin-1', errors='ignore')
        finally:
            _grclib.rc_free(ptr)

    @classmethod
    def parsePlayerRightsText(cls, text):
        ptr = _grclib.rc_parse_player_rights_text(str(text or "").encode('latin-1'))
        if not ptr:
            raise RuntimeError("grclib failed to parse player rights")
        try:
            data = ctypes.string_at(ptr).decode('latin-1', errors='ignore')
        finally:
            _grclib.rc_free(ptr)
        values = {}
        lines = data.split('\n')
        for index, line in enumerate(lines):
            if index > 1 and lines[2].startswith("folders="):
                break
            if '=' in line:
                key, value = line.split('=', 1)
                values[key] = value
        if len(lines) >= 3 and lines[2].startswith("folders="):
            values['folders'] = lines[2].split('=', 1)[1]
            if len(lines) > 3:
                values['folders'] += '\n' + '\n'.join(lines[3:])
        return int(values.get('rights') or 0), values.get('ip', ''), values.get('folders', '')

    @classmethod
    def parsePlayerAttributesText(cls, text):
        ptr = _grclib.rc_parse_player_attributes_text(str(text or "").encode('latin-1'))
        if not ptr:
            raise RuntimeError("grclib failed to parse player attributes")
        try:
            return ctypes.string_at(ptr).decode('latin-1', errors='ignore')
        finally:
            _grclib.rc_free(ptr)

    @classmethod
    def parsePlayerAccountText(cls, text):
        ptr = _grclib.rc_parse_player_account_text(str(text or "").encode('latin-1'))
        if not ptr:
            raise RuntimeError("grclib failed to parse player account")
        try:
            return ctypes.string_at(ptr).decode('latin-1', errors='ignore')
        finally:
            _grclib.rc_free(ptr)

    @classmethod
    def formatPlayerAttributesText(cls, properties):
        if properties.get('_editor_text'):
            return properties.get('_editor_text')
        raw = properties.get('_properties_json')
        if not raw:
            serializable = {}
            for key, value in properties.items():
                if isinstance(key, int):
                    key = str(key)
                if not str(key).startswith('_'):
                    serializable[key] = value
            raw = json.dumps(serializable)
        ptr = _grclib.rc_format_player_attributes_text(raw.encode('latin-1'))
        if not ptr:
            raise RuntimeError("grclib failed to format player attributes")
        try:
            return ctypes.string_at(ptr).decode('latin-1', errors='ignore')
        finally:
            _grclib.rc_free(ptr)

    @classmethod
    def formatPlayerAccountText(cls, account_data):
        lines = []
        for key, value in account_data.items():
            if isinstance(value, bool):
                value = "1" if value else "0"
            lines.append("{}={}".format(key, value))
        ptr = _grclib.rc_format_player_account_text('\n'.join(lines).encode('latin-1'))
        if not ptr:
            raise RuntimeError("grclib failed to format player account")
        try:
            return ctypes.string_at(ptr).decode('latin-1', errors='ignore')
        finally:
            _grclib.rc_free(ptr)

    @classmethod
    def requestPlayerRights(cls, account):
        cls.log("Requesting rights for: " + account, debug_only=True)
        if cls.authenticated and cls.rc_handle:
            cls.pending_player_rights_request = account
            _grclib.rc_request_player_rights(cls.rc_handle, account.encode('latin-1'))

    @classmethod
    def requestPlayerComments(cls, account):
        if cls.authenticated and cls.rc_handle:
            cls.pending_player_comments_request = account
            _grclib.rc_request_player_comments(cls.rc_handle, account.encode('latin-1'))
            cls.log("Requesting comments for: " + account, debug_only=True)

    @classmethod
    def requestPlayerAttributes(cls, account):
        if cls.authenticated and cls.rc_handle:
            cls.pending_player_attrs_request = account
            _grclib.rc_request_player_attrs(cls.rc_handle, account.encode('latin-1'))
            cls.log("Requesting attributes for: " + account, debug_only=True)

    @classmethod
    def requestAccount(cls, account):
        if cls.authenticated and cls.rc_handle:
            cls.pending_account_request = account
            _grclib.rc_request_player_account(cls.rc_handle, account.encode('latin-1'))
            cls.log("Requesting account data for: " + account, debug_only=True)

    @classmethod
    def requestAccountList(cls, account_filter, conditions, callback=None):
        if not cls.authenticated or not cls.rc_handle:
            cls.log("Not connected")
            return False
        cls.account_list_callback = callback
        result = _grclib.rc_request_account_list(cls.rc_handle, str(account_filter or "").encode('latin-1'), str(conditions or "").encode('latin-1'))
        return result == 1

    @classmethod
    def addPlayerAccount(cls, account_data):
        if not cls.authenticated or not cls.rc_handle:
            cls.log("Not connected")
            return False
        content = cls.formatPlayerAccountText(account_data)
        return _grclib.rc_add_player_account(cls.rc_handle, content.encode('latin-1')) == 1

    @classmethod
    def uploadNpcScript(cls, npc_id, npc_name, content):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_update_npc(cls.rc_handle, npc_id, content.encode('latin-1'))
        return result == 1

    @classmethod
    def uploadNpcFlags(cls, npc_id, npc_name, content):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_set_npc_flags(cls.rc_handle, npc_id, content.encode('latin-1'))
        return result == 1

    @classmethod
    def _onRawPacket(cls, packet_id, data_ptr, length, user_data):
        try:
            if not data_ptr or length <= 0:
                return
            payload = bytearray(ctypes.string_at(data_ptr, length))
            hex_preview = ' '.join('{:02x}'.format(b) for b in payload[:20]) if len(payload) > 0 else "(empty)"
            packet_name = cls.PACKET_NAMES.get(packet_id, "UNKNOWN")
            if packet_id == 47 and len(payload) > 0:
                try:
                    decoded_data = payload.decode('latin-1', errors='ignore')
                    cls.log("RX pkt {} {} ({} bytes) [{}] {}".format(packet_id, packet_name, len(payload), hex_preview, decoded_data), debug_only=True)
                except Exception:
                    cls.log("RX pkt {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(payload), hex_preview), debug_only=True)
            else:
                cls.log("RX pkt {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(payload), hex_preview), debug_only=True)
        except Exception as e:
            cls.log("Error in raw packet logger: " + str(e))

    @classmethod
    def uploadClassScript(cls, class_name, content):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_update_class(cls.rc_handle, class_name.encode('latin-1'), content.encode('latin-1'))
        return result == 1

    @classmethod
    def updatePMPlayers(cls, server_name, player_list_data):
        if server_name not in cls.pm_server_players:
            cls.pm_server_players[server_name] = []
        if not player_list_data:
            if cls.pending_pm_server_request:
                pending_display_name = None
                for server in cls.servers:
                    if server.get("name") == cls.pending_pm_server_request:
                        pending_display_name = server.get("display_name")
                        break
                if not pending_display_name:
                    emoji_prefixes = ["🪙 ", "⏳ ", "🕶️ ", "🚧 ", "🌍 "]
                    pending_display_name = cls.pending_pm_server_request
                    for emoji_prefix in emoji_prefixes:
                        if cls.pending_pm_server_request.startswith(emoji_prefix):
                            pending_display_name = cls.pending_pm_server_request[len(emoji_prefix):]
                            break
                if server_name == pending_display_name or server_name == cls.pending_pm_server_request:
                    def show_players():
                        if cls.pending_pm_server_request:
                            window = sublime.active_window()
                            if window:
                                cmd = RcShowGlobalChatCommand(window)
                                cmd.showServerPlayers(server_name)
                            cls.pending_pm_server_request = None
                    sublime.set_timeout(show_players, 500)
            return
        player_lines = player_list_data.strip().split('\n')
        current_accounts = {}
        for i in range(0, len(player_lines), 2):
            if i + 1 < len(player_lines):
                account = player_lines[i].strip()
                nick = player_lines[i + 1].strip()
                if account:
                    current_accounts[account.lower()] = {'account': account, 'nickname': nick}
        existing_accounts = {}
        for ext_id, ext_player in cls.external_players.items():
            if ext_player.get('server') == server_name:
                existing_accounts[ext_player.get('account', '').lower()] = ext_id
        for account_lower, account_data in current_accounts.items():
            if account_lower not in existing_accounts:
                ext_id = cls.next_external_id
                cls.next_external_id += 1
                ext_player = {
                    'id': ext_id,
                    'account': account_data['account'],
                    'nickname': "%s (on %s)" % (account_data['nickname'], server_name),
                    'level': '',
                    'server': server_name,
                    'external': True
                }
                cls.external_players[ext_id] = ext_player
                cls.players.append(ext_player)
                cls.log("Added external player: %s (on %s)" % (account_data['nickname'], server_name), debug_only=True)
            else:
                ext_id = existing_accounts[account_lower]
                ext_player = cls.external_players.get(ext_id)
                if ext_player:
                    new_nickname = "%s (on %s)" % (account_data['nickname'], server_name)
                    if ext_player['nickname'] != new_nickname:
                        ext_player['nickname'] = new_nickname
                        for p in cls.players:
                            if p.get('id') == ext_id:
                                p['nickname'] = new_nickname
                                break
        removed_accounts = set(existing_accounts.keys()) - set(current_accounts.keys())
        for account_lower in removed_accounts:
            ext_id = existing_accounts[account_lower]
            ext_player = cls.external_players.get(ext_id)
            if ext_player:
                del cls.external_players[ext_id]
                for i, p in enumerate(cls.players):
                    if p.get('id') == ext_id:
                        cls.players.pop(i)
                        cls.log("Removed external player: %s (on %s)" % (ext_player.get('nickname', ''), server_name), debug_only=True)
                        break
        cls.pm_server_players[server_name] = list(current_accounts.values())
        if cls.pending_pm_server_request:
            pending_display_name = None
            for server in cls.servers:
                if server.get("name") == cls.pending_pm_server_request:
                    pending_display_name = server.get("display_name")
                    break
            if not pending_display_name:
                emoji_prefixes = ["🪙 ", "⏳ ", "🕶️ ", "🚧 ", "🌍 "]
                pending_display_name = cls.pending_pm_server_request
                for emoji_prefix in emoji_prefixes:
                    if cls.pending_pm_server_request.startswith(emoji_prefix):
                        pending_display_name = cls.pending_pm_server_request[len(emoji_prefix):]
                        break
            if server_name == pending_display_name or server_name == cls.pending_pm_server_request:
                def show_players():
                    if cls.pending_pm_server_request:
                        window = sublime.active_window()
                        if window:
                            cmd = RcShowGlobalChatCommand(window)
                            cmd.showServerPlayers(server_name)
                        cls.pending_pm_server_request = None
                sublime.set_timeout(show_players, 500)

    @classmethod
    def uploadWeaponScript(cls, weapon_name, content):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        # Parse //#IMAGE: header if present
        image_name = ""
        script_content = content
        if content.startswith("//#IMAGE:"):
            lines = content.split('\n', 2)
            if len(lines) >= 2:
                image_name = lines[0][9:].strip()
                script_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""
        result = _grclib.rc_update_weapon(
            cls.rc_handle,
            weapon_name.encode('latin-1'),
            image_name.encode('latin-1'),
            script_content.encode('latin-1')
        )
        return result == 1

    @classmethod
    def deleteNpcScript(cls, npc_id, npc_name):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_delete_npc(cls.rc_handle, npc_id)
        if result == 1:
            if npc_id in cls.npc_scripts:
                del cls.npc_scripts[npc_id]
        return result == 1

    @classmethod
    def deleteClassScript(cls, class_name):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_delete_class(cls.rc_handle, class_name.encode('latin-1'))
        if result == 1:
            if class_name in cls.class_scripts:
                del cls.class_scripts[class_name]
        return result == 1

    @classmethod
    def deleteWeaponScript(cls, weapon_name):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_delete_weapon(cls.rc_handle, weapon_name.encode('latin-1'))
        if result == 1:
            if weapon_name in cls.weapon_scripts:
                del cls.weapon_scripts[weapon_name]
        return result == 1

    @classmethod
    def openFileBrowser(cls):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        cls.folders = []
        cls.folder_files = []
        result = _grclib.rc_filebrowser_start(cls.rc_handle)
        cls.log("Opening file browser...")
        return result == 1

    @classmethod
    def requestFolder(cls, folder_path):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        cls.folder_files = []
        result = _grclib.rc_filebrowser_cd(cls.rc_handle, folder_path.encode('latin-1'))
        cls.log("Requesting folder: " + folder_path)
        return result == 1

    @classmethod
    def requestLocalNpcs(cls, level):
        if not cls.rc_handle:
            cls.log("Not connected")
            return False
        result = _grclib.rc_request_local_npcs(cls.rc_handle, str(level or "").encode('latin-1'))
        return result == 1

class RcChatInsertCommand(sublime_plugin.TextCommand):
    def run(self, edit, characters):
        self.view.insert(edit, self.view.size(), characters)

class RcNoopCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        pass

class RcChatReplacePromptCommand(sublime_plugin.TextCommand):
    def run(self, edit, start, characters):
        self.view.replace(edit, sublime.Region(start, self.view.size()), characters)

class RcReplaceBufferContentCommand(sublime_plugin.TextCommand):
    def run(self, edit, content, read_only=True):
        self.view.set_read_only(False)
        self.view.replace(edit, sublime.Region(0, self.view.size()), content)
        self.view.set_read_only(read_only)
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(self.view.size(), self.view.size()))

class RcChatAppendCommand(sublime_plugin.TextCommand):
    def run(self, edit, characters):
        content = self.view.substr(sublime.Region(0, self.view.size()))
        prompt = content.rfind("\n> ")
        if prompt >= 0:
            point = prompt + 1
        elif content.startswith("> "):
            point = 0
        else:
            point = self.view.size()
            if content and not content.endswith("\n"):
                characters = "\n" + characters
        self.view.insert(edit, point, characters)
        self.view.run_command("move_to", {"to": "eof"})

class RcRefreshServersCommand(sublime_plugin.WindowCommand):
    def run(self):
        listserver_configs = getListserverConfigs()
        if len(listserver_configs) == 1:
            threading.Thread(target=lambda: GPlugin.refreshServers(listserver_configs[0]), daemon=True).start()
        else:
            config_names = [config["name"] for config in listserver_configs]
            def onSelect(index):
                if index >= 0:
                    threading.Thread(target=lambda: GPlugin.refreshServers(listserver_configs[index]), daemon=True).start()
            self.window.show_quick_panel(config_names, onSelect)

class RcConnectServerCommand(sublime_plugin.WindowCommand):
    def run(self):
        listserver_configs = getListserverConfigs()
        if len(listserver_configs) == 1:
            self.fetchServersFromListserver(listserver_configs[0])
        else:
            config_names = [config["name"] for config in listserver_configs]
            self.window.show_quick_panel(config_names, lambda index: self.onListserverChosen(index, listserver_configs))
    def onListserverChosen(self, index, configs):
        if index == -1: return
        self.fetchServersFromListserver(configs[index])
    def fetchServersFromListserver(self, config):
        sublime.status_message("Fetching servers from {}...".format(config["name"]))
        threading.Thread(target=lambda: self.fetchAndShowServers(config), daemon=True).start()
    def fetchAndShowServers(self, config):
        if GPlugin.refreshServers(config):
            sorted_servers = sorted(GPlugin.servers, key=lambda x: sortKey(x['name']))
            items = [[s['name'], "{} players - {}".format(s['players'], s.get('description', 'No description.'))] for s in sorted_servers]
            sublime.set_timeout(lambda: self.window.show_quick_panel(items, lambda index: self.onServerChosen(index, sorted_servers)), 0)
        else:
            sublime.set_timeout(lambda: sublime.error_message("Failed to fetch servers from {}".format(config["name"])), 0)
    def onServerChosen(self, index, servers):
        if index == -1: return
        server = servers[index]
        threading.Thread(target=lambda: self.attemptConnection(server), daemon=True).start()
    def attemptConnection(self, server):
        try:
            if GPlugin.connectToServer(server):
                sublime.set_timeout(lambda: sublime.status_message("Connected to {}".format(server['name'])), 0)
                sublime.set_timeout(lambda: self.window.run_command('rc_show_chat'), 0)
            else:
                sublime.set_timeout(lambda: sublime.error_message("Failed to connect to {}".format(server['name'])), 0)
        except Exception as e:
            sublime.set_timeout(lambda: sublime.error_message("Connection error: {}".format(str(e))), 0)

class RcSetCredentialsCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onAccount(account):
            if account:
                def onPassword(password):
                    if password:
                        settings = sublime.load_settings("SublimeRC.sublime-settings")
                        settings.set("account", account)
                        settings.set("password", password)
                        sublime.save_settings("SublimeRC.sublime-settings")
                        sublime.status_message("Credentials saved")
                self.window.show_input_panel("Password:", "", onPassword, None, None)
        self.window.show_input_panel("Account:", "", onAccount, None, None)

class RcConnectNcCommand(sublime_plugin.WindowCommand):
    def run(self):
        threading.Thread(target=GPlugin.connectToNpcServer, daemon=True).start()

class RcDisconnectNcCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NC server")
            return
        if _grclib.rc_disconnect_nc(GPlugin.rc_handle):
            GPlugin.nc_authenticated = False
            sublime.status_message("Disconnected from NC server")
        else:
            sublime.error_message("Failed to disconnect from NC server")

class RcShowTerminalCommand(sublime_plugin.WindowCommand):
    def run(self):
        GPlugin.showCompilerOutput(self.window or sublime.active_window())

class RcShowChatCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        GPlugin.ensureChatView(self.window or sublime.active_window(), focus=True)

class RcShowNcCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        GPlugin.ensureNcLogView(self.window or sublime.active_window(), focus=True)

class RcShowToallsCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        GPlugin.ensureToallsView(self.window or sublime.active_window(), focus=True)

class RcSendCommandCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onDone(text):
            if text:
                GPlugin.sendRcChat(text)
        self.window.show_input_panel("RC Command:", "", onDone, None, None)

class RcOpenPmCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command("rc_show_players")

class RcOpenAllPmsCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.run_command("rc_show_terminal")

class RcReplyPmCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view:
            return
        player_id = view.settings().get("rc_pm_player_id")
        label = view.settings().get("rc_pm_label", "PM")
        if player_id is None:
            sublime.status_message("No active PM thread")
            self.window.run_command("rc_open_pm")
            return
        def onDone(message):
            if message:
                if GPlugin.sendPrivateMessage(int(player_id), message):
                    sublime.status_message("PM sent to " + label)
                else:
                    sublime.error_message("Failed to send PM")
        self.window.show_input_panel("Reply to {}:".format(label), "", onDone, None, None)

class RcIrcTabsCommand(sublime_plugin.WindowCommand):
    def run(self):
        channels = sorted(GPlugin.irc_channels.keys(), key=lambda c: c.lower())
        if not channels:
            sublime.status_message("No IRC tabs available.")
            return
        self.channels = channels
        self.window.show_quick_panel(["💬 " + channel for channel in channels], self.on_done)

    def on_done(self, index):
        if index < 0:
            return
        GPlugin.openIrcChannel(self.channels[index])

class RcShowPlayersCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        GPlugin._updatePlayerCache()
        rc_players = [p for p in GPlugin.players if not p.get('server') and not p.get('external')]
        if not rc_players:
            sublime.error_message("No RC players online")
            return
        sorted_players = sorted(rc_players, key=lambda x: x.get('nickname') or x.get('account'))
        player_display = []
        for p in sorted_players:
            emoji = "🟠" if not p.get('level') else "🟢"
            display = "{} {} ({}) (ID: {})".format(emoji, p.get('nickname') or p.get('account'), p.get('account'), p.get('id'))
            display += " [RC]" if not p.get('level') else " - {}".format(p.get('level'))
            player_display.append(display)
        def onDone(index):
            if index >= 0 and index < len(sorted_players):
                self.showPlayerMenu(sorted_players[index])
        self.window.show_quick_panel(player_display, onDone)

    def showPlayerMenu(self, player_data):
        items = [
            "📝 Edit Rights",
            "🏷️ Edit Attributes",
            "💬 Edit Comments",
            "👤 Edit Account",
            "📧 PM",
            "🌍 Warp",
            "📢 Admin Message",
            "🔄 Reset",
            "🚪 Disconnect",
            "📋 Profile"
        ]
        def onChoice(index):
            if index < 0: return
            if index == 0: self.editPlayerRights(player_data)
            elif index == 1: self.editPlayerAttributes(player_data)
            elif index == 2: self.editPlayerComments(player_data)
            elif index == 3: self.editPlayerAccount(player_data)
            elif index == 4: self.sendPM(player_data)
            elif index == 5: self.warpPlayer(player_data)
            elif index == 6: self.sendAdminMessage(player_data)
            elif index == 7: self.resetPlayer(player_data)
            elif index == 8: self.disconnectPlayer(player_data)
            elif index == 9: self.showProfile(player_data)
        self.window.show_quick_panel(items, onChoice)

    def editPlayerRights(self, player):
        account = player['account']
        GPlugin.log("edit_player_rights: " + player['account'], debug_only=True)
        if account in GPlugin.player_rights:
            data = GPlugin.player_rights[account]
            text = GPlugin.formatPlayerRightsText(data['rights'], data['ip'], data['folders'])
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
            os.makedirs(player_dir, exist_ok=True)
            rights_file = os.path.join(player_dir, urlEncodeFilename(account) + "_rights.goption")
            with open(rights_file, 'w', encoding='utf-8') as f:
                f.write(text)
            view = self.window.open_file(rights_file)
            view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
            view.settings().set('rc_player_account', account)
            view.settings().set('rc_player_data_type', 'rights')
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player rights.")
            else:
                GPlugin.requestPlayerRights(account)

    def openPlayerRights(self, player_data):
        account = player_data['account']
        if account not in GPlugin.player_rights:
            GPlugin.player_rights[account] = {'rights': 0, 'ip': '*', 'folders': ''}
        data = GPlugin.player_rights[account]
        text = GPlugin.formatPlayerRightsText(data['rights'], data.get('ip', '*'), data.get('folders', ''))
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
        os.makedirs(player_dir, exist_ok=True)
        rights_file = os.path.join(player_dir, urlEncodeFilename(account) + "_rights.goption")
        with open(rights_file, 'w', encoding='utf-8') as f:
            f.write(text)
        view = self.window.open_file(rights_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_player_account', account)
        view.settings().set('rc_player_data_type', 'rights')

    def editPlayerAttributes(self, player):
        GPlugin.log("CALLED edit_player_attributes for: " + player['account'], debug_only=True)
        account = player['account']
        if account in GPlugin.player_attributes:
            properties = GPlugin.player_attributes[account]
            text = GPlugin.formatPlayerAttributesText(properties)
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
            os.makedirs(player_dir, exist_ok=True)
            attrs_file = os.path.join(player_dir, urlEncodeFilename(account) + "_attributes.goption")
            with open(attrs_file, 'w', encoding='utf-8') as f:
                f.write(text)
            view = self.window.open_file(attrs_file)
            view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
            view.settings().set('rc_player_account', account)
            view.settings().set('rc_player_data_type', 'attributes')
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player attributes.")
            else:
                GPlugin.requestPlayerAttributes(account)

    def openPlayerAttributes(self, player_data):
        account = player_data['account']
        if account not in GPlugin.player_attributes:
            GPlugin.player_attributes[account] = {}
        properties = GPlugin.player_attributes[account]
        text = GPlugin.formatPlayerAttributesText(properties)
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
        os.makedirs(player_dir, exist_ok=True)
        attrs_file = os.path.join(player_dir, urlEncodeFilename(account) + "_attributes.goption")
        with open(attrs_file, 'w', encoding='utf-8') as f:
            f.write(text)
        view = self.window.open_file(attrs_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_player_account', account)
        view.settings().set('rc_player_data_type', 'attributes')

    def editPlayerComments(self, player):
        GPlugin.log("CALLED edit_player_comments for: " + player['account'], debug_only=True)
        account = player['account']
        if account in GPlugin.player_comments:
            comments = GPlugin.player_comments[account]
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
            os.makedirs(player_dir, exist_ok=True)
            comments_file = os.path.join(player_dir, urlEncodeFilename(account) + "_comments.goption")
            with open(comments_file, 'w', encoding='utf-8') as f:
                f.write(comments)
            view = self.window.open_file(comments_file)
            view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
            view.settings().set('rc_player_account', account)
            view.settings().set('rc_player_data_type', 'comments')
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player comments.")
            else:
                GPlugin.requestPlayerComments(account)

    def openPlayerComments(self, player_data):
        account = player_data['account']
        if account not in GPlugin.player_comments:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player comments.")
            else:
                GPlugin.requestPlayerComments(account)
            return
        comments = GPlugin.player_comments[account]
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
        os.makedirs(player_dir, exist_ok=True)
        comments_file = os.path.join(player_dir, urlEncodeFilename(account) + "_comments.goption")
        with open(comments_file, 'w', encoding='utf-8') as f:
            f.write(comments)
        view = self.window.open_file(comments_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_player_account', account)
        view.settings().set('rc_player_data_type', 'comments')

    def editPlayerAccount(self, player):
        account = player['account'] if isinstance(player, dict) else player
        GPlugin.log("edit_account: " + account, debug_only=True)
        if account in GPlugin.player_accounts:
            account_data = GPlugin.player_accounts[account]
            text = GPlugin.formatPlayerAccountText(account_data)
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
            os.makedirs(player_dir, exist_ok=True)
            account_file = os.path.join(player_dir, urlEncodeFilename(account) + "_account.goption")
            with open(account_file, 'w', encoding='utf-8') as f:
                f.write(text)
            view = self.window.open_file(account_file)
            view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
            view.settings().set('rc_player_account', account)
            view.settings().set('rc_player_data_type', 'account')
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load account data.")
            else:
                GPlugin.requestAccount(account)

    def openPlayerAccount(self, player_data):
        account = player_data['account']
        if account not in GPlugin.player_accounts:
            GPlugin.player_accounts[account] = {'account': account}
        account_data = GPlugin.player_accounts[account]
        text = GPlugin.formatPlayerAccountText(account_data)
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
        os.makedirs(player_dir, exist_ok=True)
        account_file = os.path.join(player_dir, urlEncodeFilename(account) + "_account.goption")
        with open(account_file, 'w', encoding='utf-8') as f:
            f.write(text)
        view = self.window.open_file(account_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_player_account', account)
        view.settings().set('rc_player_data_type', 'account')

    def sendPM(self, player_data):
        def onMessage(message):
            if message:
                GPlugin.sendPrivateMessage(player_data['id'], message)
                sublime.status_message("Sent PM to {}".format(player_data['nickname'] or player_data['account']))
        self.window.show_input_panel("Private Message to {}:".format(player_data['nickname'] or player_data['account']), "", onMessage, None, None)

    def warpPlayer(self, player_data):
        current_level = player_data.get('level') or 'onlinestartlocal.nw'
        def askLevel(level):
            if not level:
                level = current_level
            def onDone(location):
                if location:
                    parts = location.split(',')
                    if len(parts) >= 2:
                        try:
                            x = float(parts[0].strip())
                            y = float(parts[1].strip())
                            if GPlugin.warpPlayer(player_data['id'], level, x, y):
                                sublime.status_message("Warped {} to {} {},{}".format(player_data['nickname'] or player_data['account'], level, x, y))
                        except:
                            sublime.error_message("Invalid format. Use: x, y")
                    else:
                        sublime.error_message("Invalid format. Use: x, y")
            self.window.show_input_panel("Warp to (x, y):", "", onDone, None, None)
        self.window.show_input_panel("Level:", current_level, askLevel, None, None)

    def sendAdminMessage(self, player_data):
        def onDone(message):
            if message:
                result = _grclib.rc_send_admin_message(GPlugin.rc_handle, player_data['id'], message.encode('latin-1'))
                if result == 1:
                    sublime.status_message("Admin message sent to {}".format(player_data['nickname'] or player_data['account']))
                else:
                    sublime.status_message("Failed to send admin message")
        self.window.show_input_panel("Admin Message:", "", onDone, None, None)

    def resetPlayer(self, player_data):
        if sublime.ok_cancel_dialog("Reset player {}?".format(player_data['nickname'] or player_data['account']), "Reset"):
            result = _grclib.rc_reset_player(GPlugin.rc_handle, player_data['account'].encode('latin-1'))
            if result == 1:
                sublime.status_message("Reset player: {}".format(player_data['nickname'] or player_data['account']))
            else:
                sublime.status_message("Failed to reset player")

    def disconnectPlayer(self, player_data):
        def onDone(reason):
            reason_text = reason if reason else "Disconnected by admin"
            if GPlugin.disconnectPlayer(player_data['id'], reason_text):
                sublime.status_message("Disconnected {}".format(player_data['nickname'] or player_data['account']))
        self.window.show_input_panel("Disconnect reason:", "", onDone, None, None)

    def showProfile(self, player_data):
        account = player_data['account']
        GPlugin.log("Requesting profile for: " + account, debug_only=True)
        _grclib.rc_request_player_profile(GPlugin.rc_handle, account.encode('latin-1'))
        sublime.set_timeout(lambda: self.openPlayerProfile(player_data), 1000)

    def openPlayerProfile(self, player_data):
        account = player_data['account']
        if account not in GPlugin.player_profiles:
            GPlugin.player_profiles[account] = []
        profile = GPlugin.player_profiles[account]
        text = "Profile for {}\n\n".format(account)
        labels = ["Account", "Real Name", "Age", "Sex", "Country", "Messenger", "E-Mail", "Homepage", "Fav. Hangout", "Favourite Quote", "Online Time"]
        if isinstance(profile, list):
            for index, label in enumerate(labels[1:], 1):
                value = profile[index] if index < len(profile) else ""
                text += "{}: {}\n".format(label, value)
        else:
            for key, value in profile.items():
                text += "{}: {}\n".format(key, value)
        if not profile:
            text += "(No profile data available)\n"
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
        os.makedirs(player_dir, exist_ok=True)
        profile_file = os.path.join(player_dir, urlEncodeFilename(account) + "_profile.txt")
        with open(profile_file, 'w', encoding='utf-8') as f:
            f.write(text)
        view = self.window.open_file(profile_file)
        view.settings().set('rc_player_account', account)
        view.settings().set('rc_player_data_type', 'profile')

class RcAccountsCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        self.showAccounts()

    def showAccounts(self):
        items = ["Get Accounts", "Add Account"] + list(GPlugin.account_list)
        def onDone(index):
            if index == 0:
                self.getAccounts()
            elif index == 1:
                self.addAccount()
            elif index > 1:
                account = GPlugin.account_list[index - 2]
                RcShowPlayersCommand(self.window).editPlayerAccount({'account': account})
        self.window.show_quick_panel(items, onDone)

    def getAccounts(self):
        def onAccount(account_filter):
            def onConditions(conditions):
                if GPlugin.requestAccountList(account_filter, conditions, self.showAccounts):
                    sublime.status_message("Requesting accounts...")
                else:
                    sublime.error_message("Failed to request accounts")
            self.window.show_input_panel("Conditions:", "", onConditions, None, None)
        self.window.show_input_panel("Account name spec:", "", onAccount, None, None)

    def addAccount(self):
        data = {'admin_level': '0', 'admin_worlds': 'all', 'banned': '0', 'guest': '0', 'ban_reason': ''}
        def askPassword(account):
            if not account:
                return
            data['account'] = account
            self.window.show_input_panel("Password:", "", askEmail, None, None)
        def askEmail(password):
            data['password'] = password
            self.window.show_input_panel("E-mail address:", "", askAdminLevel, None, None)
        def askAdminLevel(email):
            data['email'] = email
            self.window.show_input_panel("Admin level:", data['admin_level'], askAdminWorlds, None, None)
        def askAdminWorlds(admin_level):
            data['admin_level'] = admin_level or '0'
            self.window.show_input_panel("Admin worlds:", data['admin_worlds'], askBanned, None, None)
        def askBanned(admin_worlds):
            data['admin_worlds'] = admin_worlds or 'all'
            self.window.show_input_panel("Banned? (0/1):", data['banned'], askGuest, None, None)
        def askGuest(banned):
            data['banned'] = '1' if str(banned).strip().lower() in ('1', 'true', 'yes', 'y') else '0'
            self.window.show_input_panel("Guest? (0/1):", data['guest'], askBanReason, None, None)
        def askBanReason(guest):
            data['guest'] = '1' if str(guest).strip().lower() in ('1', 'true', 'yes', 'y') else '0'
            self.window.show_input_panel("Ban reason/comments:", "", finish, None, None)
        def finish(ban_reason):
            data['ban_reason'] = ban_reason
            if GPlugin.addPlayerAccount(data):
                sublime.status_message("Added account: " + data['account'])
            else:
                sublime.error_message("Failed to add account")
        self.window.show_input_panel("Account name:", "", askPassword, None, None)

class RcShowNpcsCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server")
            return
        GPlugin._updateNPCCache()
        if not GPlugin.npcs:
            sublime.error_message("No NPCs available")
            return
        npc_names = ["{} (ID: {})".format(npc['name'] if npc['name'] else "(Unnamed NPC)", npc['id']) for npc in GPlugin.npcs]
        def onDone(index):
            if index >= 0:
                npc_data = GPlugin.npcs[index]
                items = ["📝 Edit Script", "⚙️ Edit Flags", "🌀 Warp", "🔄 Reset", "🗑️ Delete"]
                def onChoice(choice_index):
                    if choice_index == 2:
                        self.viewNpcAttributes(npc_data)
                        return
                    if choice_index > 2:
                        choice_index -= 1
                    if choice_index == 0:
                        self.editNpc(npc_data)
                    elif choice_index == 1:
                        self.editNpcFlags(npc_data)
                    elif choice_index == 2:
                        self.warpNpc(npc_data)
                    elif choice_index == 3:
                        npc_name = npc_data['name'] if npc_data['name'] else "(Unnamed NPC)"
                        if sublime.ok_cancel_dialog("Reset NPC {}?".format(npc_name), "Reset"):
                            _grclib.rc_reset_npc(GPlugin.rc_handle, npc_data['id'])
                            sublime.status_message("Reset NPC: {}".format(npc_name))
                    elif choice_index == 4:
                        npc_name = npc_data['name'] if npc_data['name'] else "(Unnamed NPC)"
                        if sublime.ok_cancel_dialog("Delete NPC {}?".format(npc_name), "Delete"):
                            GPlugin.deleteNpcScript(npc_data['id'], npc_data['name'])
                            sublime.status_message("Deleted NPC: {}".format(npc_name))
                items.insert(2, "⚙️ Attributes")
                self.window.show_quick_panel(items, onChoice)
        self.window.show_quick_panel(npc_names, onDone)

    def viewNpcAttributes(self, npc_data):
        GPlugin.pending_npc_attributes_request = npc_data
        if not _grclib.rc_request_npc_attributes(GPlugin.rc_handle, npc_data['id']):
            sublime.error_message("Failed to request NPC attributes")

    def openNpcAttributes(self, npc_data):
        attrs = GPlugin.npc_attributes.get(npc_data['id'], "")
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        encoded_name = urlEncodeFilename(npc_data['name'] or "npc_{}".format(npc_data['id']))
        attrs_dir = os.path.join(scripts_folder, server_name, "modified", "npc_attributes")
        os.makedirs(attrs_dir, exist_ok=True)
        attrs_file = os.path.join(attrs_dir, encoded_name + "_attributes.goption")
        with open(attrs_file, 'w', encoding='utf-8') as f:
            f.write(attrs)
        view = self.window.open_file(attrs_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_npc_id', npc_data['id'])
        view.settings().set('rc_npc_name', npc_data['name'])

    def editNpcFlags(self, npc_data):
        GPlugin.pending_npc_flags_request = npc_data
        _grclib.rc_get_npc_flags(GPlugin.rc_handle, npc_data['id'])

    def openNpcFlags(self, npc_data):
        GPlugin._updateNPCCache()
        flags = GPlugin.npc_flags.get(npc_data['id'])
        if flags is None:
            flags_ptr = _grclib.rc_get_cached_npc_flags(GPlugin.rc_handle, npc_data['id'])
            if flags_ptr:
                try:
                    result = ctypes.cast(flags_ptr, c_char_p).value
                    flags = result.decode('latin-1', errors='ignore') if result else ""
                finally:
                    _grclib.rc_free(flags_ptr)
            else:
                flags = ""
            GPlugin.npc_flags[npc_data['id']] = flags
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        encoded_name = urlEncodeFilename(npc_data['name'])
        original_dir = os.path.join(scripts_folder, server_name, "original", "npc_flags")
        modified_dir = os.path.join(scripts_folder, server_name, "modified", "npc_flags")
        original_file = os.path.join(original_dir, encoded_name + "_flags.goption")
        modified_file = os.path.join(modified_dir, encoded_name + "_flags.goption")
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(modified_dir, exist_ok=True)
        if not os.path.exists(original_file):
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write(flags)
        with open(modified_file, 'w', encoding='utf-8') as f:
            f.write(flags)
        view = self.window.open_file(modified_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_npc_id', npc_data['id'])
        view.settings().set('rc_npc_name', npc_data['name'])
        view.settings().set('rc_npc_flags', True)
        view.settings().set('rc_original_content', flags)

    def warpNpc(self, npc_data):
        def askLevel(level):
            if not level: level = "onlinestartlocal.nw"
            self.window.show_input_panel("X coordinate:", "30.0", lambda x: askY(level, x), None, None)
        def askY(level, x):
            def complete(y):
                try:
                    x_val = float(x)
                    y_val = float(y)
                    _grclib.rc_warp_npc(GPlugin.rc_handle, npc_data['id'], ctypes.c_float(x_val), ctypes.c_float(y_val), level.encode('latin-1'))
                    sublime.status_message("Warped NPC: {} to {}".format(npc_data['name'], level))
                except ValueError:
                    sublime.error_message("Invalid coordinates")
            self.window.show_input_panel("Y coordinate:", "30.0", complete, None, None)
        self.window.show_input_panel("Level name:", "onlinestartlocal.nw", askLevel, None, None)

    def editNpc(self, npc_data):
        GPlugin.pending_npc_script_request = npc_data
        _grclib.rc_request_npc_script(GPlugin.rc_handle, npc_data['id'])

    def openNpcScript(self, npc_data):
        GPlugin._updateNPCCache()
        script = GPlugin.npc_scripts.get(npc_data['id'], '')
        for npc in GPlugin.npcs:
            if npc['id'] == npc_data['id']:
                script = script or npc.get('script', '')
                break
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        encoded_name = urlEncodeFilename(npc_data['name'])
        original_dir = os.path.join(scripts_folder, server_name, "original", "npcs")
        modified_dir = os.path.join(scripts_folder, server_name, "modified", "npcs")
        original_file = os.path.join(original_dir, encoded_name + ".gscript")
        modified_file = os.path.join(modified_dir, encoded_name + ".gscript")
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(modified_dir, exist_ok=True)
        if not os.path.exists(original_file):
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write(script)
        with open(modified_file, 'w', encoding='utf-8') as f:
            f.write(script)
        view = self.window.open_file(modified_file)
        view.set_syntax_file("Packages/SublimeRC/gscript.sublime-syntax")
        view.settings().set('rc_npc_id', npc_data['id'])
        view.settings().set('rc_npc_name', npc_data['name'])
        view.settings().set('rc_original_content', script)

class RcShowClassesCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server")
            return
        GPlugin._updateClassCache()
        if not GPlugin.classes:
            sublime.error_message("No classes available")
            return
        class_names = [c['name'] for c in GPlugin.classes]
        def onDone(index):
            if index >= 0:
                self.editClass(GPlugin.classes[index])
        self.window.show_quick_panel(class_names, onDone)

    def editClass(self, class_data):
        class_name = class_data['name']
        GPlugin.pending_class_script_request = class_name
        _grclib.rc_request_class_script(GPlugin.rc_handle, class_name.encode('latin-1'))

    def openClassScript(self, class_name):
        GPlugin._updateClassCache()
        script = GPlugin.class_scripts.get(class_name, '')
        for cls in GPlugin.classes:
            if cls['name'] == class_name:
                script = script or cls.get('script', '')
                break
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        encoded_name = urlEncodeFilename(class_name)
        original_dir = os.path.join(scripts_folder, server_name, "original", "scripts")
        modified_dir = os.path.join(scripts_folder, server_name, "modified", "scripts")
        original_file = os.path.join(original_dir, encoded_name + ".gscript")
        modified_file = os.path.join(modified_dir, encoded_name + ".gscript")
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(modified_dir, exist_ok=True)
        if not os.path.exists(original_file):
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write(script)
        with open(modified_file, 'w', encoding='utf-8') as f:
            f.write(script)
        view = self.window.open_file(modified_file)
        view.set_syntax_file("Packages/SublimeRC/gscript.sublime-syntax")
        view.settings().set('rc_class_name', class_name)
        view.settings().set('rc_original_content', script)

class RcShowWeaponsCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server")
            return
        GPlugin._updateWeaponCache()
        if not GPlugin.weapons:
            sublime.error_message("No weapons available")
            return
        weapon_names = [w['name'] for w in GPlugin.weapons]
        def onDone(index):
            if index >= 0:
                self.editWeapon(GPlugin.weapons[index])
        self.window.show_quick_panel(weapon_names, onDone)

    def editWeapon(self, weapon_data):
        weapon_name = weapon_data['name']
        GPlugin.pending_weapon_script_request = weapon_name
        _grclib.rc_request_weapon_script(GPlugin.rc_handle, weapon_name.encode('latin-1'))

    def openWeaponScript(self, weapon_name):
        GPlugin._updateWeaponCache()
        script = GPlugin.weapon_scripts.get(weapon_name, '')
        for wpn in GPlugin.weapons:
            if wpn['name'] == weapon_name:
                script = script or wpn.get('script', '')
                break
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.servers[0]['name']) if GPlugin.servers else "Unknown"
        encoded_name = urlEncodeFilename(weapon_name)
        original_dir = os.path.join(scripts_folder, server_name, "original", "weapons")
        modified_dir = os.path.join(scripts_folder, server_name, "modified", "weapons")
        original_file = os.path.join(original_dir, encoded_name + ".gscript")
        modified_file = os.path.join(modified_dir, encoded_name + ".gscript")
        os.makedirs(original_dir, exist_ok=True)
        os.makedirs(modified_dir, exist_ok=True)
        if not os.path.exists(original_file):
            with open(original_file, 'w', encoding='utf-8') as f:
                f.write(script)
        with open(modified_file, 'w', encoding='utf-8') as f:
            f.write(script)
        view = self.window.open_file(modified_file)
        view.set_syntax_file("Packages/SublimeRC/gscript.sublime-syntax")
        view.settings().set('rc_weapon_name', weapon_name)
        view.settings().set('rc_original_content', script)

class RcFileBrowserCommand(sublime_plugin.WindowCommand):
    def __init__(self, window):
        super().__init__(window)
        self.current_path = []
        self.folder_tree = {}

    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if GPlugin.current_folder and GPlugin.folder_files:
            folder_path = GPlugin.current_folder.rstrip('/')
            if folder_path:
                self.current_path = [part for part in folder_path.split('/') if part]
            else:
                self.current_path = []
            sublime.set_timeout(lambda: self.showFiles(), 100)
        else:
            self.current_path = []
            if GPlugin.folders:
                sublime.set_timeout(lambda: self.showFolders(), 100)
            else:
                GPlugin.file_browser_callback = lambda: self.showFolders()
                GPlugin.openFileBrowser()

    def buildFolderTree(self):
        tree = {}
        for folder in GPlugin.folders:
            pattern = folder['pattern']
            rights = folder['rights']
            parts = pattern.split('/')
            current = tree
            for i, part in enumerate(parts):
                if part not in current:
                    current[part] = {'children': {}, 'pattern': '/'.join(parts[:i+1]), 'rights': rights, 'is_leaf': i == len(parts) - 1}
                current = current[part]['children']
        return tree

    def showFolders(self):
        if not GPlugin.folders:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load folders.")
                sublime.error_message("Not connected to server.")
                return
            if GPlugin.folder_files:
                GPlugin.log("No folder list from server, showing current directory files", debug_only=True)
                sublime.set_timeout(lambda: self.showFiles(), 100)
                return
            self.window.show_quick_panel(["(none)"], lambda index: None)
            return
        self.folder_tree = self.buildFolderTree()
        current = self.folder_tree
        for path_part in self.current_path:
            current = current[path_part]['children']
        folder_items = []
        folder_keys = []
        if self.current_path:
            folder_items.append("← Back")
            folder_keys.append(None)
        for key in sorted(current.keys()):
            item = current[key]
            if item['children']:
                folder_items.append("📁 " + key)
            else:
                folder_items.append("📄 " + key + " (" + item['rights'] + ")")
            folder_keys.append(key)
        self.folder_keys = folder_keys
        self.window.show_quick_panel(folder_items, self.onFolderSelected)

    def onFolderSelected(self, index):
        if index == -1: return
        selected_key = self.folder_keys[index]
        if selected_key is None:
            self.current_path.pop()
            sublime.set_timeout(lambda: self.showFolders(), 100)
            return
        current = self.folder_tree
        for path_part in self.current_path:
            current = current[path_part]['children']
        selected = current[selected_key]
        if selected['children']:
            self.current_path.append(selected_key)
            sublime.set_timeout(lambda: self.showFolders(), 100)
        else:
            GPlugin.file_browser_callback = lambda: self.showFiles()
            folder_path = selected['pattern']
            if '/' in folder_path:
                folder_path = folder_path.rsplit('/', 1)[0] + '/'
            elif folder_path.endswith('*'):
                folder_path = ''
            GPlugin.log("Requesting folder: {} (from pattern: {})".format(folder_path, selected['pattern']))
            GPlugin.requestFolder(folder_path)
            GPlugin.current_folder = folder_path
            sublime.set_timeout(lambda: self.showFiles(), 2000)

    def showFiles(self):
        GPlugin.log("folder_files count: {}".format(len(GPlugin.folder_files)), debug_only=True)
        if not GPlugin.folder_files:
            file_items = ["Upload File", "(empty)", "← Back to folders", "↻ Refresh"]
            def onEmptySelected(index):
                if index == 0:
                    self.uploadLocalFile()
                    return
                if index == 2:
                    sublime.set_timeout(lambda: self.showFolders(), 100)
                elif index == 3:
                    GPlugin.requestFolder(GPlugin.current_folder)
                    sublime.set_timeout(lambda: self.showFiles(), 1000)
            self.window.show_quick_panel(file_items, onEmptySelected)
            return
        directories = [f for f in GPlugin.folder_files if f.get('is_directory', False)]
        files = [f for f in GPlugin.folder_files if not f.get('is_directory', False)]
        file_items = ["Upload File"]
        file_items.extend(["📁 " + d['path'] for d in directories])
        for f in files:
            size = f.get('size', 0)
            size_str = "{} bytes".format(size) if size < 1024 else "{:.2f} KB".format(size / 1024.0) if size < 1024 * 1024 else "{:.2f} MB".format(size / 1024.0 / 1024.0)
            file_items.append("📄 {} ({}, {})".format(f['path'], size_str, f.get('rights', 'rw')))
        GPlugin.log("Showing {} directories and {} files".format(len(directories), len(files)), debug_only=True)
        file_items.append("← Back to folders")
        file_items.append("↻ Refresh")
        self.window.show_quick_panel(file_items, self.onFileSelected)

    def onFileSelected(self, index):
        if index == -1: return
        if index == 0:
            self.uploadLocalFile()
            return
        index -= 1
        if index == len(GPlugin.folder_files):
            sublime.set_timeout(lambda: self.showFolders(), 100)
            return
        if index == len(GPlugin.folder_files) + 1:
            GPlugin.requestFolder(GPlugin.current_folder)
            sublime.set_timeout(lambda: self.showFiles(), 1000)
            return
        directories = [f for f in GPlugin.folder_files if f.get('is_directory', False)]
        files = [f for f in GPlugin.folder_files if not f.get('is_directory', False)]
        all_items = directories + files
        selected_item = all_items[index]
        file_path = selected_item['path']
        if selected_item.get('is_directory', False):
            GPlugin.requestFolder(file_path + '*')
            GPlugin.current_folder = file_path + '*'
            sublime.set_timeout(lambda: self.showFiles(), 1000)
            return
        folder = GPlugin.current_folder.replace('*', '') if GPlugin.current_folder else ""
        self.selected_file = file_path if '/' in file_path or not folder else folder + file_path
        options = ["Open", "Open External", "Download", "Delete", "Rename", "Back"]
        self.window.show_quick_panel(options, self.onActionSelected)

    def uploadLocalFile(self):
        def onSelected(path):
            if not path:
                return
            try:
                with open(path, 'rb') as f:
                    content = f.read()
            except Exception as e:
                sublime.error_message("Failed to read file: {}".format(str(e)))
                return
            folder = GPlugin.current_folder.replace('*', '') if GPlugin.current_folder else ""
            if folder and not folder.endswith('/'):
                folder += '/'
            remote_path = folder + os.path.basename(path)
            if GPlugin.uploadFile(remote_path, content):
                sublime.status_message("Uploaded file: " + remote_path)
                GPlugin.log("Uploaded file: " + remote_path, debug_only=True)
                GPlugin.requestFolder(GPlugin.current_folder)
                sublime.set_timeout(lambda: self.showFiles(), 1000)
            else:
                sublime.error_message("Failed to upload file: " + remote_path)
        self.window.show_open_file_dialog(onSelected)

    def onActionSelected(self, index):
        if index == -1 or index == 5:
            sublime.set_timeout(lambda: self.showFiles(), 100)
            return
        if index == 0:
            GPlugin.openFileForEditing(self.selected_file)
        elif index == 1:
            GPlugin.openFileExternally(self.selected_file)
        elif index == 2:
            GPlugin.log("Downloading file: " + self.selected_file)
            GPlugin.downloadFile(self.selected_file)
        elif index == 3:
            if sublime.ok_cancel_dialog("Delete " + self.selected_file + "?", "Delete"):
                GPlugin.deleteFile(self.selected_file)
                sublime.set_timeout(lambda: self.showFiles(), 1000)
        elif index == 4:
            self.window.show_input_panel("New filename:", self.selected_file, self.onRename, None, None)

    def onRename(self, new_name):
        if new_name:
            GPlugin.renameFile(self.selected_file, new_name)
            sublime.set_timeout(lambda: self.showFiles(), 1000)

class RcShowGlobalChatCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if not GPlugin.pm_servers:
            GPlugin.pending_pm_server_list_palette = True
            _grclib.rc_request_pm_server_list(GPlugin.rc_handle)
            sublime.status_message("Requesting PM servers...")
            return
        recent_servers = GPlugin.recent_servers if hasattr(GPlugin, 'recent_servers') else []
        sorted_servers = sorted(GPlugin.pm_servers, key=lambda server_name: (
            0 if server_name in recent_servers else 1,
            -recent_servers.index(server_name) if server_name in recent_servers else 0,
            server_name.lower()
        ))
        items = []
        for server_name in sorted_servers:
            player_count = len([p for p in GPlugin.players if p.get('server') == server_name])
            server_display = server_name
            if player_count:
                server_display += " ({} players)".format(player_count)
            items.append(server_display)
        def onDone(index):
            if index >= 0 and index < len(sorted_servers):
                server_name = sorted_servers[index]
                if server_name not in recent_servers:
                    recent_servers.insert(0, server_name)
                    if len(recent_servers) > 10:
                        recent_servers.pop()
                else:
                    recent_servers.remove(server_name)
                    recent_servers.insert(0, server_name)
                GPlugin.recent_servers = recent_servers
                self.showServerPlayers(server_name)
        self.window.show_quick_panel(items, onDone)

    def showServerPlayers(self, server_name):
        if server_name.startswith(('🌍 ', '🪙 ', '⏳ ', '🕶️ ', '🚧 ')):
            server_name = server_name[2:].strip()
        server_players = [p for p in GPlugin.players if p.get('server') == server_name]
        if not server_players:
            GPlugin.pending_pm_server_request = server_name
            _grclib.rc_request_pm_server_players(GPlugin.rc_handle, server_name.encode('latin-1'))
            sublime.status_message("Requesting players from {}...".format(server_name))
            player_display = ["← Back", "(loading...)"]
            def onDone(index):
                if index == 0:
                    self.run()
            self.window.show_quick_panel(player_display, onDone)
            return
        sorted_players = sorted(server_players, key=lambda x: x.get('nickname') or x.get('account'))
        player_display = ["← Back"]
        for p in sorted_players:
            emoji = "🟠" if not p.get('level') else "🟢"
            display = "{} {} ({}) (ID: {})".format(emoji, p.get('nickname') or p.get('account'), p.get('account'), p.get('id'))
            if p.get('level'):
                display += " - {}".format(p.get('level'))
            player_display.append(display)
        def onDone(index):
            if index == 0:
                self.run()
            elif index > 0 and index <= len(sorted_players):
                player = sorted_players[index - 1]
                self.showPlayerMenu(player)
        self.window.show_quick_panel(player_display, onDone)

    def showPlayerMenu(self, player_data):
        items = ["📧 PM"]
        def onChoice(index):
            if index == 0:
                self.sendPM(player_data)
        self.window.show_quick_panel(items, onChoice)

    def sendPM(self, player_data):
        def onDone(message):
            if message:
                command = "privmessage {} {}".format(player_data['account'], message)
                GPlugin.sendRcChat(command)
                sublime.status_message("PM sent to {}".format(player_data['nickname'] or player_data['account']))
        self.window.show_input_panel("Private Message:", "", onDone, None, None)

class RcLocalNpcsCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        self.window.show_input_panel("Local NPCs level:", "", self.onDone, None, None)

    def onDone(self, level):
        if GPlugin.requestLocalNpcs(level):
            sublime.status_message("Requested local NPCs")
        else:
            sublime.error_message("Failed to request local NPCs")

class RcUploadFileCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if not GPlugin.current_folder:
            sublime.error_message("Open a File Browser folder before uploading.")
            return
        RcFileBrowserCommand(self.window).uploadLocalFile()

class RcEditServerOptionsCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if GPlugin.server_options:
            self.openServerOptions()
        else:
            GPlugin.pending_server_options_request = True
            result = _grclib.rc_request_server_options(GPlugin.rc_handle)
            if result == 1:
                sublime.status_message("Requesting server options...")
            else:
                GPlugin.pending_server_options_request = False
                sublime.error_message("Failed to request server options")

    def openServerOptions(self):
        if not GPlugin.server_options:
            return
        text = GPlugin.server_options
        scripts_folder = getScriptsFolder()
        if GPlugin.connected_server:
            server_name = getCleanServerName(GPlugin.connected_server['name'])
        else:
            server_name = "Unknown"
        server_dir = os.path.join(scripts_folder, server_name, "modified")
        os.makedirs(server_dir, exist_ok=True)
        options_file = os.path.join(server_dir, "server_options.goption")
        with open(options_file, 'w', encoding='utf-8') as f:
            f.write(text)
        view = self.window.open_file(options_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_server_data_type', 'options')

class RcEditServerFlagsCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if GPlugin.server_flags:
            self.openServerFlags()
        else:
            GPlugin.pending_server_flags_request = True
            result = _grclib.rc_request_server_flags(GPlugin.rc_handle)
            if result == 1:
                sublime.status_message("Requesting server flags...")
            else:
                GPlugin.pending_server_flags_request = False
                sublime.error_message("Failed to request server flags")

    def openServerFlags(self):
        if not GPlugin.server_flags:
            return
        text = GPlugin.server_flags
        scripts_folder = getScriptsFolder()
        if GPlugin.connected_server:
            server_name = getCleanServerName(GPlugin.connected_server['name'])
        else:
            server_name = "Unknown"
        server_dir = os.path.join(scripts_folder, server_name, "modified")
        os.makedirs(server_dir, exist_ok=True)
        flags_file = os.path.join(server_dir, "server_flags.goption")
        with open(flags_file, 'w', encoding='utf-8') as f:
            f.write(text)
        view = self.window.open_file(flags_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_server_data_type', 'flags')

class RcEditFolderConfigCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if GPlugin.folder_config:
            self.openFolderConfig()
        else:
            GPlugin.pending_folder_config_request = True
            result = _grclib.rc_request_folder_config(GPlugin.rc_handle)
            if result == 1:
                sublime.status_message("Requesting folder config...")
            else:
                GPlugin.pending_folder_config_request = False
                sublime.error_message("Failed to request folder config")

    def openFolderConfig(self):
        if not GPlugin.folder_config:
            return
        text = GPlugin.folder_config
        scripts_folder = getScriptsFolder()
        if GPlugin.connected_server:
            server_name = getCleanServerName(GPlugin.connected_server['name'])
        else:
            server_name = "Unknown"
        server_dir = os.path.join(scripts_folder, server_name, "modified")
        os.makedirs(server_dir, exist_ok=True)
        config_file = os.path.join(server_dir, "folder_config.goption")
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write(text)
        view = self.window.open_file(config_file)
        view.set_syntax_file("Packages/SublimeRC/goption.sublime-syntax")
        view.settings().set('rc_server_data_type', 'folder_config')

class RcCreateNpcOnServerCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server. Use 'RC: Connect to NC' first.")
            return
        self.npc_data = {}
        GPlugin._updateNPCCache()
        existing_ids = [npc['id'] for npc in GPlugin.npcs if npc['id'] != 10000]
        next_id = str(max(existing_ids) + 1) if existing_ids else "1000"
        account = getSetting("account", "")
        def askName(name):
            if not name:
                sublime.status_message("NPC name is required")
                return
            self.npc_data['name'] = name
            self.window.show_input_panel("NPC ID:", next_id, askId, None, None)
        def askId(npc_id):
            try:
                self.npc_data['id'] = int(npc_id)
            except:
                sublime.status_message("Invalid NPC ID, using " + next_id)
                self.npc_data['id'] = int(next_id)
            self.window.show_input_panel("NPC Type:", "OBJECT", askType, None, None)
        def askType(npc_type):
            self.npc_data['type'] = npc_type if npc_type else "OBJECT"
            self.window.show_input_panel("Scripter:", account, askScripter, None, None)
        def askScripter(scripter):
            self.npc_data['scripter'] = scripter if scripter else account
            self.window.show_input_panel("Level name:", "onlinestartlocal.nw", askLevel, None, None)
        def askLevel(level):
            self.npc_data['level'] = level if level else "onlinestartlocal.nw"
            self.window.show_input_panel("X coordinate:", "30.5", askX, None, None)
        def askX(x):
            self.npc_data['x'] = x if x else "30.5"
            self.window.show_input_panel("Y coordinate:", "30", askY, None, None)
        def askY(y):
            self.npc_data['y'] = y if y else "30"
            createNpc()
        def createNpc():
            result = _grclib.rc_create_npc_on_server(
                GPlugin.rc_handle,
                self.npc_data["name"].encode('latin-1'),
                self.npc_data["id"],
                self.npc_data["type"].encode('latin-1'),
                self.npc_data["scripter"].encode('latin-1'),
                self.npc_data["level"].encode('latin-1'),
                self.npc_data["x"].encode('latin-1'),
                self.npc_data["y"].encode('latin-1')
            )
            if result:
                sublime.status_message("Created NPC: {} (ID: {})".format(self.npc_data['name'], self.npc_data['id']))
            else:
                sublime.error_message("Failed to create NPC")
        self.window.show_input_panel("NPC Name:", "", askName, None, None)

class RcNewWeaponCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server. Use 'RC: Connect to NC' first.")
            return
        def onDone(weapon_name):
            if not weapon_name: return
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            encoded_name = urlEncodeFilename(weapon_name)
            original_dir = os.path.join(scripts_folder, server_name, "original", "weapons")
            modified_dir = os.path.join(scripts_folder, server_name, "modified", "weapons")
            original_file = os.path.join(original_dir, encoded_name + ".gscript")
            modified_file = os.path.join(modified_dir, encoded_name + ".gscript")
            os.makedirs(original_dir, exist_ok=True)
            os.makedirs(modified_dir, exist_ok=True)
            template = "//#IMAGE: " + weapon_name + ".png\nfunction onCreated() {\n    \n}\n"
            if not os.path.exists(original_file):
                with open(original_file, 'w', encoding='utf-8') as f:
                    f.write(template)
            with open(modified_file, 'w', encoding='utf-8') as f:
                f.write(template)
            view = self.window.open_file(modified_file)
            view.set_syntax_file("Packages/SublimeRC/gscript.sublime-syntax")
            view.settings().set('rc_weapon_name', weapon_name)
            view.settings().set('rc_original_content', template)
            view.settings().set('rc_was_deleted', False)
            sublime.status_message("Created new weapon: " + weapon_name)
        self.window.show_input_panel("New Weapon Name:", "", onDone, None, None)

class RcNewClassCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server. Use 'RC: Connect to NC' first.")
            return
        def onDone(class_name):
            if not class_name: return
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            encoded_name = urlEncodeFilename(class_name)
            original_dir = os.path.join(scripts_folder, server_name, "original", "scripts")
            modified_dir = os.path.join(scripts_folder, server_name, "modified", "scripts")
            original_file = os.path.join(original_dir, encoded_name + ".gscript")
            modified_file = os.path.join(modified_dir, encoded_name + ".gscript")
            os.makedirs(original_dir, exist_ok=True)
            os.makedirs(modified_dir, exist_ok=True)
            template = "function onCreated() {\n}\n"
            if not os.path.exists(original_file):
                with open(original_file, 'w', encoding='utf-8') as f:
                    f.write(template)
            with open(modified_file, 'w', encoding='utf-8') as f:
                f.write(template)
            view = self.window.open_file(modified_file)
            view.set_syntax_file("Packages/SublimeRC/gscript.sublime-syntax")
            view.settings().set('rc_class_name', class_name)
            view.settings().set('rc_original_content', template)
            view.settings().set('rc_was_deleted', False)
            sublime.status_message("Created new class: " + class_name)
        self.window.show_input_panel("New Class Name:", "", onDone, None, None)

class RcViewNpcAttributesCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server")
            return
        GPlugin._updateNPCCache()
        if not GPlugin.npcs:
            sublime.error_message("No NPCs available")
            return
        npc_names = ["{} (ID: {})".format(npc['name'] if npc['name'] else "(Unnamed NPC)", npc['id']) for npc in GPlugin.npcs]
        def onDone(index):
            if index >= 0:
                RcShowNpcsCommand(self.window).viewNpcAttributes(GPlugin.npcs[index])
        self.window.show_quick_panel(npc_names, onDone)

class RcAdminMessageAllCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onMessage(message):
            if message and not GPlugin.sendAdminMessageAll(message):
                sublime.error_message("Failed to send admin message")
        self.window.show_input_panel("Admin Message:", "", onMessage, None, None)

class RcToallMessageCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onMessage(message):
            if message and not GPlugin.sendToallMessage(message):
                sublime.error_message("Failed to send toall message")
        self.window.show_input_panel("To All Message:", "", onMessage, None, None)

class RcMassPmCommand(sublime_plugin.WindowCommand):
    def run(self):
        players = [p for p in GPlugin.players if p.get('id') is not None]
        player_ids = [p.get('id') for p in players if p.get('id') is not None]
        if not player_ids:
            sublime.error_message("No players online")
            return
        def onMessage(message):
            if message and GPlugin.sendMassPm(player_ids, message):
                sublime.status_message("Sent mass PM to {} players".format(len(player_ids)))
            elif message:
                sublime.error_message("Failed to send mass PM")
        self.window.show_input_panel("Mass PM:", "", onMessage, None, None)

class RcOpenProfileCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        account = getSetting("account", "").strip()
        if not account:
            sublime.error_message("No account configured")
            return
        RcShowPlayersCommand(self.window).showProfile({'account': account})

class RcSetNicknameCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onNickname(nickname):
            if nickname:
                settings = sublime.load_settings("SublimeRC.sublime-settings")
                settings.set("nickname", nickname)
                sublime.save_settings("SublimeRC.sublime-settings")
                if GPlugin.rc_handle and GPlugin.authenticated:
                    if _grclib.rc_set_nickname(GPlugin.rc_handle, nickname.encode('latin-1')) != 1:
                        sublime.error_message("Failed to send nickname")
                        return
                sublime.status_message("Nickname set to: " + nickname)
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current = settings.get("nickname", "")
        self.window.show_input_panel("Nickname:", current, onNickname, None, None)

class RcSetListserverCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current_host = settings.get("listserver_host", "listserver.graalonline.com")
        current_port = str(settings.get("listserver_port", 14922))
        current_name = settings.get("listserver_name", "Listserver")
        def onName(name):
            name = name.strip() or "Listserver"
            def onHost(host):
                host = host.strip()
                if not host:
                    sublime.error_message("Listserver host is required")
                    return
                def onPort(port):
                    try:
                        port_int = int(port.strip())
                    except:
                        sublime.error_message("Invalid listserver port")
                        return
                    settings.set("listserver_name", name)
                    settings.set("listserver_host", host)
                    settings.set("listserver_port", port_int)
                    sublime.save_settings("SublimeRC.sublime-settings")
                    GPlugin.current_listserver_config = None
                    sublime.status_message("Listserver set to {}:{} ({})".format(host, port_int, name))
                self.window.show_input_panel("Listserver Port:", current_port, onPort, None, None)
            self.window.show_input_panel("Listserver Host:", current_host, onHost, None, None)
        self.window.show_input_panel("Listserver Name:", current_name, onName, None, None)

class RcSetScriptsFolderCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onFolder(folder):
            if folder:
                settings = sublime.load_settings("SublimeRC.sublime-settings")
                settings.set("scripts_folder", folder)
                sublime.save_settings("SublimeRC.sublime-settings")
                sublime.status_message("Scripts folder set to: " + folder)
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current = getScriptsFolder()
        self.window.show_input_panel("Scripts Folder:", current, onFolder, None, None)

class RcDisconnectCommand(sublime_plugin.WindowCommand):
    def run(self):
        GPlugin.disconnect()


class RCScriptSaveListener(sublime_plugin.EventListener):
    def is_chat_like_view(self, view):
        return (
            view.settings().get("rc_chat_view")
            or view.settings().get("rc_irc_view")
            or view.settings().get("rc_file_browser_log_view")
            or view.settings().get("rc_toalls_view")
        )

    def prompt_insert_region(self, view):
        line = view.line(view.size())
        text = view.substr(line)
        start = line.begin() + 2 if text.startswith("> ") else view.size()
        return sublime.Region(start, view.size())

    def on_query_context(self, view, key, operator, operand, match_all):
        if key != "rc_chat_input" or not self.is_chat_like_view(view):
            return None
        allowed = self.prompt_insert_region(view)
        in_input = all(allowed.contains(sel.begin()) and allowed.contains(sel.end()) for sel in view.sel())
        return in_input == operand

    def on_text_command(self, view, command_name, args):
        if not self.is_chat_like_view(view):
            return None
        allowed = self.prompt_insert_region(view)
        edit_commands = {
            "insert", "insert_snippet", "left_delete", "right_delete", "paste", "cut",
            "indent", "unindent", "swap_line_up", "swap_line_down"
        }
        if command_name in edit_commands:
            if any(sel.begin() < allowed.begin() or sel.end() < allowed.begin() for sel in view.sel()):
                view.sel().clear()
                view.sel().add(sublime.Region(view.size(), view.size()))
                return ("rc_noop", {})
        if command_name not in ("insert", "insert_snippet"):
            return None
        text = ""
        if command_name == "insert":
            text = (args or {}).get("characters", "")
        elif command_name == "insert_snippet":
            text = (args or {}).get("contents", "")
        if text not in ("\n", "\r", "\r\n"):
            return None
        prompt_region = view.line(view.size())
        prompt_text = view.substr(prompt_region)
        if not prompt_text.startswith("> "):
            view.run_command("rc_chat_insert", {"characters": "\n> "})
            return ("rc_noop", {})
        message = prompt_text[2:].strip()
        if message:
            view.run_command("rc_chat_replace_prompt", {"start": prompt_region.begin(), "characters": "> "})
            if view.settings().get("rc_irc_view"):
                channel = view.settings().get("rc_irc_channel")
                if message.lower() == "/clear":
                    if channel in GPlugin.irc_channels:
                        GPlugin.irc_channels[channel]["messages"] = []
                    view.run_command("rc_replace_buffer_content", {"content": "> ", "read_only": False})
                    sublime.status_message("Cleared IRC tab")
                elif message.lower() == "/part":
                    GPlugin.sendIrcText("part", channel)
                elif channel:
                    GPlugin.sendIrcText("privmsg", channel, message)
                    from datetime import datetime
                    clock = datetime.now().strftime("%I:%M%p").lstrip("0").lower()
                    GPlugin.appendIrcMessage(channel, "[{}] <{}> {}".format(clock, getSetting("nickname") or getSetting("account") or "You", message))
            elif view.settings().get("rc_file_browser_log_view"):
                lowered = message.lower()
                if lowered == "/clear":
                    view.run_command("rc_replace_buffer_content", {"content": "> ", "read_only": False})
                    sublime.status_message("Cleared File Browser")
                elif lowered.startswith("/find ") or lowered == "/find" or lowered.startswith("/finddef ") or lowered == "/finddef":
                    GPlugin.sendRcChat(message)
                else:
                    sublime.status_message("File Browser only accepts /find and /finddef commands")
            elif view.settings().get("rc_toalls_view"):
                if message.lower() == "/clear":
                    view.run_command("rc_replace_buffer_content", {"content": "> ", "read_only": False})
                    sublime.status_message("Cleared Toalls")
                elif GPlugin.sendToallMessage(message):
                    GPlugin.logToalls(message)
                else:
                    sublime.error_message("Failed to send toall")
            else:
                if message.lower() == "/clear":
                    view.run_command("rc_replace_buffer_content", {"content": "> ", "read_only": False})
                    sublime.status_message("Cleared RC Chat")
                else:
                    GPlugin.sendRcChat(message)
        return ("rc_noop", {})

    def on_post_save(self, view):
        file_path = view.file_name()
        if not file_path: return
        scripts_folder = getScriptsFolder()
        file_path_norm = os.path.normpath(file_path).lower()
        scripts_folder_norm = scripts_folder.lower()
        if "modified" not in file_path_norm or scripts_folder_norm not in file_path_norm: return
        npc_id = view.settings().get('rc_npc_id')
        npc_name = view.settings().get('rc_npc_name')
        npc_flags = view.settings().get('rc_npc_flags')
        class_name = view.settings().get('rc_class_name')
        weapon_name = view.settings().get('rc_weapon_name')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            sublime.status_message("Failed to read file: " + str(e))
            return
        is_empty = content.strip() == ""
        was_deleted = view.settings().get('rc_was_deleted', False)
        filebrowser_path = view.settings().get('rc_filebrowser_path')
        if filebrowser_path:
            if GPlugin.uploadFile(filebrowser_path, content):
                view.settings().set('rc_original_content', content)
                sublime.status_message("Uploaded file: " + filebrowser_path)
                GPlugin.log("Uploaded file: " + filebrowser_path, debug_only=True)
            else:
                sublime.error_message("Failed to upload file: " + filebrowser_path)
            return
        if npc_flags and npc_id is not None and npc_name:
            sublime.status_message("Uploaded NPC flags: " + npc_name)
            GPlugin.uploadNpcFlags(npc_id, npc_name, content)
            if getSetting("show_terminal_on_script_save", True):
                GPlugin.showCompilerOutput(view.window())
        elif npc_id is not None and npc_name:
            sublime.status_message("Uploaded NPC script: " + npc_name)
            GPlugin.uploadNpcScript(npc_id, npc_name, content)
            if getSetting("show_terminal_on_script_save", True):
                GPlugin.showCompilerOutput(view.window())
        elif class_name:
            if is_empty:
                GPlugin.deleteClassScript(class_name)
                view.settings().set('rc_was_deleted', True)
                sublime.status_message("Deleted class script: " + class_name)
            else:
                if was_deleted:
                    GPlugin.log("Restoring class script: " + class_name)
                    sublime.status_message("Restored class script: " + class_name)
                    view.settings().set('rc_was_deleted', False)
                else:
                    sublime.status_message("Uploaded class script: " + class_name)
                GPlugin.uploadClassScript(class_name, content)
                if getSetting("show_terminal_on_script_save", True):
                    GPlugin.showCompilerOutput(view.window())
        elif weapon_name:
            if is_empty:
                GPlugin.deleteWeaponScript(weapon_name)
                view.settings().set('rc_was_deleted', True)
                sublime.status_message("Deleted weapon script: " + weapon_name)
            else:
                if was_deleted:
                    GPlugin.log("Restoring weapon script: " + weapon_name)
                    sublime.status_message("Restored weapon script: " + weapon_name)
                    view.settings().set('rc_was_deleted', False)
                else:
                    sublime.status_message("Uploaded weapon script: " + weapon_name)
                GPlugin.uploadWeaponScript(weapon_name, content)
                if getSetting("show_terminal_on_script_save", True):
                    GPlugin.showCompilerOutput(view.window())
        player_account = view.settings().get('rc_player_account')
        server_data_type = view.settings().get('rc_server_data_type')
        if server_data_type:
            if server_data_type == 'options':
                result = _grclib.rc_upload_server_options(GPlugin.rc_handle, content.encode('latin-1'))
                if result:
                    GPlugin.server_options = None
                    sublime.status_message("Updated server options")
                else:
                    sublime.error_message("Failed to update server options")
            elif server_data_type == 'flags':
                result = _grclib.rc_upload_server_flags(GPlugin.rc_handle, content.encode('latin-1'))
                if result:
                    GPlugin.server_flags = None
                    sublime.status_message("Updated server flags")
                else:
                    sublime.error_message("Failed to update server flags")
            elif server_data_type == 'folder_config':
                result = _grclib.rc_upload_folder_config(GPlugin.rc_handle, content.encode('latin-1'))
                if result:
                    GPlugin.folder_config = None
                    sublime.status_message("Updated folder config")
                else:
                    sublime.error_message("Failed to update folder config")
            if getSetting("show_terminal_on_script_save", True):
                GPlugin.showCompilerOutput(view.window())
            return

        player_account = view.settings().get('rc_player_account')
        player_data_type = view.settings().get('rc_player_data_type')
        if player_account and player_data_type:
            if player_data_type == 'rights':
                rights_value, ip_range, folder_access = GPlugin.parsePlayerRightsText(content)
                if GPlugin.rc_handle:
                    result = _grclib.rc_set_player_rights(GPlugin.rc_handle, player_account.encode('latin-1'), rights_value, ip_range.encode('latin-1'), folder_access.encode('latin-1'))
                    if result:
                        GPlugin.player_rights[player_account] = {'rights': rights_value, 'ip': ip_range, 'folders': folder_access}
                        sublime.status_message("Updated rights for: " + player_account)
                    else:
                        sublime.error_message("Failed to update rights")
            elif player_data_type == 'comments':
                if GPlugin.rc_handle:
                    result = _grclib.rc_set_player_comments(GPlugin.rc_handle, player_account.encode('latin-1'), content.encode('latin-1'))
                    if result:
                        GPlugin.player_comments[player_account] = content
                        sublime.status_message("Updated comments for: " + player_account)
                    else:
                        sublime.error_message("Failed to update comments")
            elif player_data_type == 'attributes':
                if GPlugin.rc_handle:
                    properties_json = GPlugin.parsePlayerAttributesText(content)
                    result = _grclib.rc_set_player_attributes(GPlugin.rc_handle, player_account.encode('latin-1'), properties_json.encode('latin-1'))
                    if result:
                        try:
                            properties = json.loads(properties_json)
                        except Exception:
                            properties = {}
                        properties['_properties_json'] = properties_json
                        properties['_editor_text'] = content
                        GPlugin.player_attributes[player_account] = properties
                        sublime.status_message("Updated attributes for: " + player_account)
                    else:
                        sublime.error_message("Failed to update attributes")
            elif player_data_type == 'account':
                if GPlugin.rc_handle:
                    account_text = GPlugin.parsePlayerAccountText(content)
                    result = _grclib.rc_set_player_account(GPlugin.rc_handle, player_account.encode('latin-1'), account_text.encode('latin-1'))
                    if result:
                        account_data = {}
                        for line in content.splitlines():
                            if ':' in line:
                                key, value = line.split(':', 1)
                                account_data[key.strip().lower().replace(' ', '_')] = value.strip()
                        GPlugin.player_accounts[player_account] = account_data
                        sublime.status_message("Updated account for: " + player_account)
                    else:
                        sublime.error_message("Failed to update account")
            elif player_data_type == 'profile':
                if GPlugin.rc_handle:
                    result = _grclib.rc_set_player_profile(GPlugin.rc_handle, player_account.encode('latin-1'), content.encode('latin-1'))
                    if result:
                        GPlugin.player_profiles[player_account] = {'_editor_text': content}
                        sublime.status_message("Updated profile for: " + player_account)
                    else:
                        sublime.error_message("Failed to update profile")

print("RC: Plugin loaded successfully - grclib native library integration active")
