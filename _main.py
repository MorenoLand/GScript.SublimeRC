import sublime
import sublime_plugin
import threading
import time
import struct
import zlib
import random
import os
import re
import csv
import platform
import hashlib
import ctypes
import socket
from urllib.parse import quote

SERVERS = []
LISTSERVER_SEED = 4
LISTSERVER_ICONS = (
    "\U0001f310",
    "\U0001f4e1",
    "\U0001f9ed",
    "\U0001f4ab",
    "\u2728",
    "\U0001f680",
    "\U0001f6f0\ufe0f",
    "\U0001f5a5\ufe0f",
)
GSCRIPT_EDITOR_COLOR_SCHEME = "Packages/SublimeRC/SublimeRC-gscript-editor.sublime-color-scheme"
GOPTION_EDITOR_COLOR_SCHEME = "Packages/SublimeRC/SublimeRC-goption-editor.sublime-color-scheme"

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

def sanitizeDisplayFilename(name):
    return re.sub(r'[\\/:*?"<>|]+', '_', name).strip() or "Untitled"

def urlEncodeFilename(filename):
    safe_chars = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.'
    return ''.join(char if char in safe_chars else '%{:02X}'.format(ord(char)) for char in filename)

def getScriptsFolder():
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    default_folder = os.path.join(os.path.expanduser("~"), "SublimeRC") if platform.system() != "Windows" else "C:/SublimeRC"
    folder = settings.get("scripts_folder", default_folder)
    return os.path.normpath(folder)

def md5RevHex(data):
    if not data:
        return ""
    digest = hashlib.md5(bytes(data or b"")).digest()
    hexchars = "0123456789abcdef"
    return ''.join(hexchars[b & 0x0f] + hexchars[(b >> 4) & 0x0f] for b in digest)

def getWindowsIDBytes():
    if platform.system() != "Windows":
        return b""
    try:
        import winreg
        paths = (
            r"Software\Microsoft\Windows\CurrentVersion",
            r"Software\Microsoft\Windows NT\CurrentVersion",
        )
        for path in paths:
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as key:
                    value, _ = winreg.QueryValueEx(key, "DigitalProductId")
                    if value:
                        return bytes(value)
            except OSError:
                pass
    except:
        pass
    return b""

def getNetworkIDBytes():
    if platform.system() != "Windows":
        return b""
    try:
        class IP_ADDR_STRING(ctypes.Structure):
            pass
        IP_ADDR_STRING._fields_ = [
            ("Next", ctypes.POINTER(IP_ADDR_STRING)),
            ("IpAddress", ctypes.c_char * 16),
            ("IpMask", ctypes.c_char * 16),
            ("Context", ctypes.c_ulong),
        ]
        class IP_ADAPTER_INFO(ctypes.Structure):
            pass
        IP_ADAPTER_INFO._fields_ = [
            ("Next", ctypes.POINTER(IP_ADAPTER_INFO)),
            ("ComboIndex", ctypes.c_ulong),
            ("AdapterName", ctypes.c_char * 260),
            ("Description", ctypes.c_char * 132),
            ("AddressLength", ctypes.c_uint),
            ("Address", ctypes.c_ubyte * 8),
            ("Index", ctypes.c_ulong),
            ("Type", ctypes.c_uint),
            ("DhcpEnabled", ctypes.c_uint),
            ("CurrentIpAddress", ctypes.POINTER(IP_ADDR_STRING)),
            ("IpAddressList", IP_ADDR_STRING),
            ("GatewayList", IP_ADDR_STRING),
            ("DhcpServer", IP_ADDR_STRING),
            ("HaveWins", ctypes.c_bool),
            ("PrimaryWinsServer", IP_ADDR_STRING),
            ("SecondaryWinsServer", IP_ADDR_STRING),
            ("LeaseObtained", ctypes.c_long),
            ("LeaseExpires", ctypes.c_long),
        ]
        iphlpapi = ctypes.WinDLL("iphlpapi")
        size = ctypes.c_ulong(0)
        if iphlpapi.GetAdaptersInfo(None, ctypes.byref(size)) != 111 or size.value <= 0:
            return b""
        buf = ctypes.create_string_buffer(size.value)
        if iphlpapi.GetAdaptersInfo(ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_INFO)), ctypes.byref(size)) != 0:
            return b""
        adapter = ctypes.cast(buf, ctypes.POINTER(IP_ADAPTER_INFO))
        while adapter:
            info = adapter.contents
            if info.AddressLength >= 6:
                ip = info.IpAddressList.IpAddress.decode("ascii", errors="ignore").strip("\x00")
                if ip and ip not in ("0", "0.0.0.0", "127.0.0.1"):
                    return bytes(info.Address[:6])
            adapter = info.Next
    except:
        pass
    return b""

def getHarddiskIDBytes():
    if platform.system() != "Windows":
        return b""
    try:
        serial = ctypes.c_ulong(0)
        ok = ctypes.windll.kernel32.GetVolumeInformationW(
            ctypes.c_wchar_p("C:\\"),
            None,
            0,
            ctypes.byref(serial),
            None,
            None,
            None,
            0
        )
        if ok:
            return int(serial.value).to_bytes(4, "little", signed=False)
    except:
        pass
    return b""

def generatePcid(account=None):
    return gtokenize("\n".join([
        "win",
        md5RevHex(getWindowsIDBytes()),
        md5RevHex(getNetworkIDBytes()),
        md5RevHex(getHarddiskIDBytes()),
    ]))

class ListServerScrambler:
    def __init__(self, seed):
        self.mask = 0x4A80B38
        self.seed = seed
        self.MASK_ROTATION = 0x8088405
    def decrypt(self, data):
        result = bytearray(data)
        rotations = 4
        offset = 0
        while offset < 4 * rotations and offset < len(data):
            self.mask = (self.mask * self.MASK_ROTATION + self.seed) & 0xFFFFFFFF
            index = offset
            while index < len(data) and index < offset + 4:
                byte_mask = (self.mask >> (8 * (index % 4))) & 0xFF
                result[index] = data[index] ^ byte_mask
                index += 1
            offset += 4
        return bytes(result)

def writeGByte(value): return (value & 0xFF) + 0x20
def decodeGByte(byte): return (byte & 0xFF) - 0x20

def writeGShort(value):
    high = ((value >> 7) & 0xFF) + 32
    low = (value & 0x7F) + 32
    return bytes([high, low])

def decodeGShort(data, offset=0):
    return ((data[offset] - 32) << 7) + (data[offset + 1] - 32)

def writeGInt3(value):
    b0 = ((value >> 14) & 0x7F) + 32
    b1 = ((value >> 7) & 0x7F) + 32
    b2 = (value & 0x7F) + 32
    return bytes([b0, b1, b2])

def decodeGInt3(data, offset=0):
    return ((data[offset] - 32) << 14) + ((data[offset + 1] - 32) << 7) + (data[offset + 2] - 32)

def findTerminator(buf, start=0):
    for i in range(start, len(buf)):
        if buf[i] == 0x0A: return i
    return -1

def getCredentials(cls):
    if cls.connected_server and cls.connected_server.get('listserver_config'):
        config = cls.connected_server['listserver_config']
        return config['account'], config['password']
    return getSetting('account'), getSetting('password')

def scrambleData(data, seed, compression_type):
    mask = 0x4A80B38
    MASK_ROTATION = 0x8088405
    result = bytearray(data)
    rotations = 12 if compression_type == 0x02 else 4
    offset = 0
    while offset < 4 * rotations and offset < len(data):
        mask = (mask * MASK_ROTATION + seed) & 0xFFFFFFFF
        index = offset
        while index < len(data) and index < offset + 4:
            byte_mask = (mask >> (8 * (index % 4))) & 0xFF
            result[index] = data[index] ^ byte_mask
            index += 1
        offset += 4
    return bytes(result)

def getListserverConfigs():
    settings = sublime.load_settings("SublimeRC.sublime-settings")
    configs = []
    default_config = {
        "name": getSetting("listserver_name", "Listserver"),
        "host": getSetting("listserver_host", "127.0.0.1"),
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

def getListserverIcon(config):
    key = "{}|{}|{}".format(
        str(config.get("host", "")).lower(),
        str(config.get("name", "")).lower(),
        config.get("port", "")
    )
    index = (zlib.crc32(key.encode("utf-8")) + LISTSERVER_SEED) % len(LISTSERVER_ICONS)
    return LISTSERVER_ICONS[index]

def getListserverLabel(config):
    account = config.get("account") or "unknown"
    return "{} {} ({})".format(getListserverIcon(config), config.get("name", "Listserver"), account)

def fetchServerList(listserver_config=None):
    if listserver_config is None:
        listserver_config = {
            "host": getSetting("listserver_host", "127.0.0.1"),
            "port": getSetting("listserver_port", 14922),
            "account": getSetting("account", ""),
            "password": getSetting("password", "")
        }
    sock = None
    listserver_debug = bool(getSetting("listserver_debug", False))
    def debug(message):
        if listserver_debug:
            print(message)
    try:
        listserver_host = listserver_config["host"]
        listserver_port = listserver_config["port"]
        listserver_account = listserver_config["account"]
        listserver_password = listserver_config["password"]
        debug("Connecting to {}:{}".format(listserver_host, listserver_port))
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(15.0)
        sock.connect((listserver_host, listserver_port))
        debug("Connected, sending edition packet")
        edition_payload = bytearray()
        edition_payload.append(writeGByte(7))
        edition_payload.append(writeGByte(4))
        edition_payload.extend(b"G3D30123")
        edition_payload.extend(b"rc2")
        edition_payload.append(0x0a)
        compressed_edition = zlib.compress(bytes(edition_payload))
        edition_packet = struct.pack('>H', len(compressed_edition)) + compressed_edition
        sock.send(edition_packet)
        debug("Edition sent, waiting...")
        time.sleep(0.2)
        debug("Sending login packet")
        login_payload = bytearray()
        login_payload.append(writeGByte(1))
        login_payload.append(writeGByte(len(listserver_account)))
        login_payload.extend(listserver_account.encode('latin-1'))
        login_payload.append(writeGByte(len(listserver_password)))
        login_payload.extend(listserver_password.encode('latin-1'))
        login_payload.append(0x0a)
        if len(login_payload) > 40:
            compressed_login = zlib.compress(bytes(login_payload))
            compression_type = 0x04
        else:
            compressed_login = bytes(login_payload)
            compression_type = 0x02
        encrypted_login = scrambleData(compressed_login, LISTSERVER_SEED, compression_type)
        login_packet = struct.pack('>H', len(encrypted_login) + 1) + bytes([compression_type]) + encrypted_login
        sock.send(login_packet)
        debug("Login sent (compression {}), waiting for response...".format(compression_type))
        length_bytes = sock.recv(2)
        if len(length_bytes) != 2:
            debug("Failed to read packet length")
            return []
        packet_length = struct.unpack('>H', length_bytes)[0]
        debug("Reading {} bytes".format(packet_length))
        packet_data = bytearray()
        while len(packet_data) < packet_length:
            chunk = sock.recv(packet_length - len(packet_data))
            if not chunk: break
            packet_data.extend(chunk)
        if len(packet_data) < packet_length:
            debug("Incomplete packet: got {} of {}".format(len(packet_data), packet_length))
            return []
        debug("Received packet, decoding...")
        format_type = packet_data[0]
        debug("Format type: {}".format(format_type))
        unscrambled = scrambleData(bytes(packet_data[1:]), LISTSERVER_SEED, format_type)
        try: decompressed = zlib.decompress(unscrambled)
        except Exception as e:
            debug("Decompress failed: {}".format(str(e)))
            decompressed = unscrambled
        debug("Decompressed {} bytes".format(len(decompressed)))
        servers = []
        offset = 0
        if offset >= len(decompressed): return []
        packet_type = decodeGByte(decompressed[offset])
        offset += 1
        debug("Packet type: {}".format(packet_type))
        if packet_type != 0:
            if packet_type == 16:
                msg = decompressed[offset:].decode('latin-1', errors='ignore').split('\n')[0]
                debug("Server rejected: {}".format(msg))
            elif packet_type == 4:
                msg = decompressed[offset:].decode('latin-1', errors='ignore').strip()
                debug("Server disconnected: {}".format(msg))
            return []
        if offset >= len(decompressed): return []
        server_count = decodeGByte(decompressed[offset])
        offset += 1
        debug("Server count: {}".format(server_count))
        for _ in range(server_count):
            if offset >= len(decompressed): break
            attr_count = decodeGByte(decompressed[offset])
            offset += 1
            attributes = []
            for _ in range(attr_count):
                if offset >= len(decompressed): break
                attr_len = decodeGByte(decompressed[offset])
                offset += 1
                if offset + attr_len > len(decompressed): break
                attr_value = decompressed[offset:offset + attr_len].decode('latin-1', errors='ignore')
                attributes.append(attr_value)
                offset += attr_len
            if len(attributes) >= 8:
                servers.append({"name": ("{} {}".format({"P": "🪙", "H": "⏳", "3": "🕶️", "U": "🚧"}[attributes[0][0]], attributes[0][2:]) if len(attributes[0]) > 2 and attributes[0][1] == ' ' and attributes[0][0] in "PH3U" else "🌍 " + attributes[0]), "ip": attributes[6], "port": int(attributes[7]), "type": "listserver", "language": attributes[1], "description": attributes[2], "players": int(attributes[5])})
        return servers
    except Exception as e:
        debug("Listserver error ({}): {}".format(type(e).__name__, str(e)))
        return []
    finally:
        if sock:
            try: sock.close()
            except: pass

def get1PlusTextNetString(s):
    if len(s) > 223: return chr(255) + s[223:]
    else: return chr(32 + len(s)) + s

def gtokenize(text):
    text = text.replace('\r', '')
    lines = text.split('\n')
    result = []
    for line in lines:
        if not line:
            result.append('')
            continue
        needs_quotes = False
        if line[0] == '"':
            needs_quotes = True
        for char in line:
            if ord(char) < 33 or ord(char) > 126 or char in ',/':
                needs_quotes = True
                break
        if line.strip() == '': needs_quotes = True
        if needs_quotes:
            escaped = line.replace('\\', '\\\\').replace('"', '""')
            result.append('"' + escaped + '"')
        else: result.append(line)
    return ','.join(result)

def gtokenizeReverse(content):
    output = []
    currently_inside_quotes = False
    line_quoted = False
    pos = 0
    i = 0
    while i < len(content):
        if content[i] == '"':
            if currently_inside_quotes:
                if i + 1 < len(content) and content[i + 1] == '"':
                    i += 1
                    i += 1
                    continue
            line_quoted = True
            currently_inside_quotes = not currently_inside_quotes
        if not currently_inside_quotes:
            if content[i] == ',' or i + 1 == len(content):
                line_start = pos + (1 if line_quoted else 0)
                line_length = i - pos - (2 if line_quoted else 0) + (1 if i + 1 == len(content) and content[i] != ',' else 0)
                line = content[line_start:line_start + line_length]
                if line_quoted:
                    line = line.replace('""', '"')
                    line = line.replace('\\\\', '\\')
                    line = line.replace('\n', '')
                    line = line.replace('\r', '')
                output.append(line)
                pos = i + 1
                line_quoted = False
        i += 1
    return '\n'.join(output)

class GRCProtocol:
    def __init__(self):
        self.encryption_key = None
        self.iterator_out = 0x4A80B38
        self.iterator_in = 0x4A80B38
    
    def setEncryptionKey(self, key): self.encryption_key = key
    def getIteratorLimit(self, compression_type): return 0x0C if compression_type == 0x02 else 0x04
    
    def applyEncryption(self, direction, buf, compression_type):
        if self.encryption_key is None or not buf: return buf
        limit = self.getIteratorLimit(compression_type)
        result = bytearray(buf)
        for i in range(len(result)):
            if i % 4 == 0:
                if limit <= 0: break
                limit -= 1
                if direction == 0:
                    self.iterator_out = (self.iterator_out * 0x8088405 + self.encryption_key) & 0xFFFFFFFF
                    iterator_val = self.iterator_out
                else:
                    self.iterator_in = (self.iterator_in * 0x8088405 + self.encryption_key) & 0xFFFFFFFF
                    iterator_val = self.iterator_in
            result[i] ^= (iterator_val >> ((i % 4) * 8)) & 0xFF
        return bytes(result)
    
    def sendPacket(self, socket_conn, packet_type, data):
        payload = bytearray()
        payload.append(packet_type + 32)
        payload.extend(data)
        payload.append(0x0A)
        if len(data) > 40:
            compressed_payload = zlib.compress(payload)
            compression_type = 0x04
        else:
            compressed_payload = payload
            compression_type = 0x02
        if self.encryption_key is not None:
            encrypted_buffer = self.applyEncryption(0, compressed_payload, compression_type)
            length = len(encrypted_buffer) + 1
            final_packet = struct.pack('>H', length) + bytes([compression_type]) + encrypted_buffer
        else:
            length = len(compressed_payload)
            final_packet = struct.pack('>H', length) + compressed_payload
        socket_conn.send(final_packet)
        return final_packet

    def sendRawBlock(self, socket_conn, data):
        raw_payload = bytes(data)
        if len(raw_payload) > 40:
            compressed_payload = zlib.compress(raw_payload)
            compression_type = 0x04
        else:
            compressed_payload = raw_payload
            compression_type = 0x02
        if self.encryption_key is not None:
            encrypted_buffer = self.applyEncryption(0, compressed_payload, compression_type)
            length = len(encrypted_buffer) + 1
            final_packet = struct.pack('>H', length) + bytes([compression_type]) + encrypted_buffer
        else:
            length = len(compressed_payload)
            final_packet = struct.pack('>H', length) + compressed_payload
        socket_conn.send(final_packet)
        return final_packet
    
    def decrypt(self, buf):
        if self.encryption_key is None: return buf
        if len(buf) < 1: return buf
        compression_type = buf[0]
        encrypted_data = buf[1:]
        decrypted_data = self.applyEncryption(1, encrypted_data, compression_type)
        if compression_type == 0x04:
            try: return zlib.decompress(decrypted_data)
            except: return decrypted_data
        else: return decrypted_data

class NCProtocol:
    def __init__(self):
        self.iterator = 0x4A80B38
    
    def sendPacket(self, socket_conn, packet_type, data):
        payload = bytearray()
        payload.append(packet_type + 32)
        payload.extend(data)
        payload.append(0x0A)
        compressed_payload = zlib.compress(payload)
        length_bytes = struct.pack('>H', len(compressed_payload))
        socket_conn.send(length_bytes + compressed_payload)
        return length_bytes + compressed_payload
    
    def decrypt(self, buf):
        try: return zlib.decompress(buf)
        except: return buf

class GPlugin:
    RIGHTS_NAMES = [
        'Warp to XY', 'Warp to Player', 'Warp player', 'Update Level',
        'Disconnect', 'View Attributes', 'Set Attributes', 'Set Own Attributes',
        'Reset Attributes', 'Admin Message', 'Change Rights', 'Ban Players',
        'Comments', '', 'Staff Accounts', 'Server Flags',
        'Server Options', 'Folder Configuration', 'Folder Rights', 'NPC Control'
    ]
    COLOR_NAMES = ['White', 'Yellow', 'Orange', 'Pink', 'Red', 'Darkred', 'Lightgreen', 'Green', 'Darkgreen', 'Lightblue', 'Blue', 'Darkblue', 'Brown', 'Cynober', 'Purple', 'Darkpurple', 'Lightgray', 'Gray', 'Black', 'Transparent']
    servers = []
    weapons = []
    classes = []
    npcs = []
    players = []
    external_players = {}
    pm_servers = []
    pm_server_players = {}
    pm_server_update_timers = {}
    recent_servers = []
    next_external_id = 16000
    weapon_scripts = {}
    class_scripts = {}
    npc_scripts = {}
    npc_flags = {}
    server_options = None
    server_flags = None
    folder_config = None
    pending_weapon_request = None
    pending_class_request = None
    pending_npc_request = None
    pending_npc_flags_request = None
    pending_npc_props_request = None
    pending_account_request = None
    player_accounts = {}
    pending_weapon_callback = None
    pending_class_callback = None
    pending_npc_callback = None
    npc_sort_timer = None
    class_sort_timer = None
    connected_server = None
    socket_connection = None
    nc_socket = None
    protocol = None
    nc_protocol = None
    output_panel = None
    file_browser_log_view = None
    toalls_log_view = None
    compiler_log_view = None
    nc_log_view = None
    authenticated = False
    nc_authenticated = False
    switching_servers = False
    has_set_nickname = False
    has_received_welcome = False
    shown_not_authenticated = False
    npc_server_address = None
    npcserver_player_id = None
    debug_mode = False
    ignore_world_time_debug = True
    pending_player_rights_request = None
    pending_player_attrs_request = None
    pending_player_comments_request = None
    pending_player_profile_request = None
    account_list = []
    account_list_callback = None
    player_rights = {}
    player_attributes = {}
    player_comments = {}
    player_profiles = {}
    pending_player_ban_request = None
    pending_player_ban_request_id = None
    player_bans = {}
    ban_types = []
    isNewProtocol = False
    current_listserver_config = None
    folders = []
    current_folder = None
    folder_files = []
    file_transfers = {}
    pending_file_download = None
    open_after_download = False
    external_file_watchers = {}
    external_file_watch_timer = None
    file_upload_chunk_size = 49152
    expecting_folder_list = False
    pending_local_npcs_request = None
    find_results = []
    find_result_base = ""
    find_result_links = {}
    pending_server_options_request = False
    pending_server_flags_request = False
    pending_folder_config_request = False
    pending_pm_server_request = None
    private_messages = {}
    private_message_order = []
    private_message_open_index = 0
    pm_chat_links = {}
    irc_channels = {}
    irc_bootstrapped = False
    compiler_output_target = None
    npc_defined_commands = set()
    LISTSERVER_CLIENT = {
        "EDITION_PACKET": 7,
        "EDITION_TYPE": 4,
        "LOGIN_PACKET": 1,
        "ERROR_REJECTED": 16,
        "ERROR_DISCONNECTED": 4
    }
    RC_TO_SERVER = {
        "PLI_TOALL": 6,
        "PLI_RAWDATA": 50,
        "PLI_RC_SERVEROPTIONSGET": 51, "PLI_RC_SERVEROPTIONSSET": 52, "PLI_RC_FOLDERCONFIGGET": 53, "PLI_RC_FOLDERCONFIGSET": 54,
        "PLI_RC_RESPAWNSET": 55, "PLI_RC_HORSELIFESET": 56, "PLI_RC_APINCREMENTSET": 57, "PLI_RC_BODYRESPAWNSET": 58,
        "PLI_RC_PLAYERPROPSGET": 59, "PLI_RC_PLAYERPROPSSET": 2, "PLI_PRIVATEMESSAGE": 28, "PLI_RC_DISCONNECTPLAYER": 61, "PLI_RC_UPDATELEVELS": 62,
        "PLI_RC_ADMINMESSAGE": 63, "PLI_RC_PRIVADMINMESSAGE": 64, "PLI_RC_LISTRCS": 65, "PLI_RC_DISCONNECTRC": 66,
        "PLI_RC_APPLYREASON": 67, "PLI_RC_SERVERFLAGSGET": 68, "PLI_RC_SERVERFLAGSSET": 69, "PLI_RC_ACCOUNTADD": 70,
        "PLI_RC_ACCOUNTDEL": 71, "PLI_RC_ACCOUNTLISTGET": 72, "PLI_RC_PLAYERPROPSGET2": 73, "PLI_RC_PLAYERPROPSGET3": 74,
        "PLI_RC_PLAYERPROPSRESET": 75, "PLI_RC_PLAYERPROPSSET2": 76, "PLI_RC_ACCOUNTGET": 77, "PLI_RC_ACCOUNTSET": 78,
        "PLI_RC_CHAT": 79, "PLI_RC_PROFILEGET": 80, "PLI_RC_PROFILESET": 81, "PLI_RC_WARPPLAYER": 82,
        "PLI_RC_PLAYERRIGHTSGET": 83, "PLI_RC_PLAYERRIGHTSSET": 84, "PLI_RC_PLAYERCOMMENTSGET": 85, "PLI_RC_PLAYERCOMMENTSSET": 86,
        "PLI_RC_PLAYERBANGET": 87, "PLI_RC_PLAYERBANSET": 88, "PLI_RC_FILEBROWSER_START": 89, "PLI_RC_FILEBROWSER_CD": 90,
        "PLI_RC_FILEBROWSER_END": 91, "PLI_RC_FILEBROWSER_DOWN": 92, "PLI_RC_FILEBROWSER_UP": 93, "PLI_NPCSERVERQUERY": 94,
        "PLI_RC_FILEBROWSER_MOVE": 96, "PLI_RC_FILEBROWSER_DELETE": 97, "PLI_RC_FILEBROWSER_RENAME": 98, "PLI_NC_LISTNPCS": 100,
        "PLI_NC_NPCGET": 103, "PLI_NC_NPCDELETE": 104, "PLI_NC_NPCRESET": 105, "PLI_NC_NPCSCRIPTGET": 106,
        "PLI_NC_NPCWARP": 107, "PLI_NC_NPCFLAGSGET": 108, "PLI_NC_NPCSCRIPTSET": 109, "PLI_NC_NPCFLAGSSET": 110,
        "PLI_NC_NPCADD": 111, "PLI_NC_CLASSEDIT": 112, "PLI_NC_CLASSADD": 113, "PLI_NC_LOCALNPCSGET": 114,
        "PLI_NC_WEAPONLISTGET": 115, "PLI_NC_WEAPONGET": 116, "PLI_NC_WEAPONADD": 117, "PLI_NC_WEAPONDELETE": 118,
        "PLI_NC_CLASSDELETE": 119, "PLI_REQUESTUPDATEBOARD": 130, "PLI_NC_LEVELLISTGET": 150, "PLI_NC_LEVELLISTSET": 151,
        "PLI_REQUESTTEXT": 152, "PLI_SENDTEXT": 154, "PLI_RC_LARGEFILESTART": 155, "PLI_RC_LARGEFILEEND": 156,
        "PLI_UPDATEGANI": 157, "PLI_UPDATESCRIPT": 158, "PLI_UPDATEPACKAGEREQUESTFILE": 159, "PLI_RC_FOLDERDELETE": 160,
        "PLI_UPDATECLASS": 161
    }
    NC_TO_SERVER = {
        "PLI_NC_LOGIN": 3,
        "PLI_NC_NPCGET": 103, "PLI_NC_NPCDELETE": 104, "PLI_NC_NPCRESET": 105, "PLI_NC_NPCSCRIPTGET": 106,
        "PLI_NC_NPCWARP": 107, "PLI_NC_NPCFLAGSGET": 108, "PLI_NC_NPCSCRIPTSET": 109, "PLI_NC_NPCFLAGSSET": 110,
        "PLI_NC_NPCADD": 111, "PLI_NC_CLASSEDIT": 112, "PLI_NC_CLASSADD": 113, "PLI_NC_LOCALNPCSGET": 114,
        "PLI_NC_WEAPONLISTGET": 115, "PLI_NC_WEAPONGET": 116, "PLI_NC_WEAPONADD": 117, "PLI_NC_WEAPONDELETE": 118,
        "PLI_NC_CLASSDELETE": 119, "PLI_NC_LEVELLISTGET": 150, "PLI_NC_LEVELLISTSET": 151
    }
    prop_map = {
        'Account': (34, str),
        'Hearts': (1, int),
        'Full Hearts': (2, lambda x: int(float(x) * 2)),
        'Level': (20, str),
        'X': (5, float),
        'Y': (6, float),
        5: ('x', float),
        6: ('y', float),
        17: ('glove', int),
        19: ('bombs', int),
        4: (4, int),
        'Sword Power': ('sword_power', str),
        'Sword Image': ('sword_image', str),
        'Shield Power': ('shield_power', str),
        'Shield Image': ('shield_image', str),
        'Head Image': ('head_image', str),
        'Body Image': ('body_image', str),
        'Health': (26, int),
        'Max Health': (27, int),
        'MP': (27, int),
        'Max Magic': (28, int),
        'Gralats': (30, int),
        'Glove': (17, int),
        'Bombs': (19, int),
        'Male': ('status_male', lambda x: 4 if x.lower() == 'true' else 0),
        'Weapons Enabled': ('status_weapons', lambda x: 16 if x.lower() == 'true' else 0),
        'Spin Attack': ('status_spin', lambda x: 64 if x.lower() == 'true' else 0),
    }
    color_map = {
        'Skin Color': 0,
        'Coat Color': 1,
        'Sleeves Color': 2,
        'Shoes Color': 3,
        'Belt Color': 4,
    }
    status_map = {
        'Paused': 1,
        'Hidden': 2,
        'Male': 4,
        'Dead': 8,
        'Weapons allowed': 16,
        'Hide sword': 32,
        'Has spin attack': 64,
    }
    SERVER_TO_RC = {
        "PLO_PLAYERPROPS": 8, "PLO_UNKNOWN11": 11, "PLO_TOALL": 13, "PLO_FILESENDFAILED": 30,
        "PLO_NEWWORLDTIME": 42,
        "PLO_RC_ADMINMESSAGE": 35, "PLO_RC_ACCOUNTADD": 50, "PLO_RC_ACCOUNTSTATUS": 51, "PLO_RC_ACCOUNTNAME": 52, "PLO_RC_ACCOUNTDEL": 53,
        "PLO_RC_ACCOUNTPROPS": 54, "PLO_ADDPLAYER": 55, "PLO_DELPLAYER": 56, "PLO_RC_ACCOUNTPROPSGET": 57, "PLO_RC_ACCOUNTCHANGE": 58,
        "PLO_RC_PLAYERPROPSCHANGE": 59, "PLO_UNKNOWN60": 60, "PLO_RC_SERVERFLAGSGET": 61, "PLO_RC_PLAYERRIGHTSGET": 62,
        "PLO_RC_PLAYERCOMMENTSGET": 63, "PLO_RC_PLAYERBANGET": 64, "PLO_RC_FILEBROWSER_DIRLIST": 65, "PLO_RC_FILEBROWSER_DIR": 66,
        "PLO_RC_FILEBROWSER_MESSAGE": 67, "PLO_LARGEFILESTART": 68, "PLO_LARGEFILEEND": 69, "PLO_RC_ACCOUNTLISTGET": 70,
        "PLO_RC_PLAYERPROPS": 71, "PLO_RC_PLAYERPROPSGET": 72, "PLO_RC_ACCOUNTGET": 73, "PLO_RC_CHAT": 74, "PLO_PROFILE": 75,
        "PLO_RC_SERVEROPTIONSGET": 76, "PLO_RC_FOLDERCONFIGGET": 77, "PLO_NC_CONTROL": 78, "PLO_NPCSERVERADDR": 79, "PLO_NC_LEVELLIST": 80,
        "PLO_SERVERTEXT": 82, "PLO_EDITION_PACKET": 16, "PLO_RC_LOGIN": 25, "PLO_PRIVATEMESSAGE": 37, "PLO_BOARDPACKET": 101, "PLO_SVI_SERVERINFO": 47,
        "PLO_LARGEFILESIZE": 84, "PLO_FILE": 102, "PLO_NC_NPCATTRIBUTES": 103,
        "PLO_RC_MAXUPLOADFILESIZE": 103, "PLO_NC_NPCADD": 158,
        "PLO_NC_NPCDELETE": 159, "PLO_NC_NPCSCRIPT": 160, "PLO_NC_NPCFLAGS": 161, "PLO_NC_CLASSGET": 162,
        "PLO_NC_CLASSADD": 163, "PLO_NC_LEVELDUMP": 164, "PLO_NC_WEAPONLISTGET": 167, "PLO_NC_CLASSDELETE": 188, "PLO_STATUSLIST": 180,
        "PLO_NC_WEAPONGET": 192, "PLO_CLEARWEAPONS": 194, "PLO_UNKNOWN190": 190
    }
    SERVER_TO_NC = {
        "PLO_NC_NPCATTRIBUTES": 157, "PLO_NC_NPCADD": 158, "PLO_NC_NPCDELETE": 159, "PLO_NC_NPCSCRIPT": 160,
        "PLO_NC_NPCFLAGS": 161, "PLO_NC_CLASSGET": 162, "PLO_NC_CLASSADD": 163, "PLO_NC_LEVELDUMP": 164,
        "PLO_NC_WEAPONLISTGET": 167, "PLO_NC_CLASSDELETE": 188, "PLO_NC_WEAPONGET": 192
    }
    @classmethod
    def log(cls, message, debug_only=False, show_panel=False):
        if debug_only and not cls.debug_mode: return
        if debug_only: message = "Debug: " + message
        try:
            if "Game files found (relative to" in message:
                import re
                match = re.search(r'relative to\s+(.+?),\s*max', message)
                cls.find_result_base = match.group(1).strip() if match else ""
                cls.find_results = []
                cls.find_results.append(message)
                cls.logFileBrowser(message)
                return
            parsed_find_result = cls.parseFindResultMessage(message)
            if parsed_find_result:
                filename, status, ftype, size, date = parsed_find_result
                cls.find_results.append(message)
                cls.showFindResultLine(filename, status, ftype, size, date)
                return
            if "Also found default files matching this" in message:
                cls.logFileBrowser(message)
                return
            if cls.isFileBrowserChatMessage(message):
                cls.logFileBrowser(message)
                return
            if cls.handleScriptCompilerMessage(message):
                return
            if cls.isScriptUpdateMessage(message):
                cls.logCompiler(message)
                return
            cls.logPlain(message, show_panel)
        except Exception as e:
            print("RC log error:", str(e))
            cls.logPlain(message, show_panel)

    @classmethod
    def isFileBrowserChatMessage(cls, message):
        message_lower = message.lower()
        return bool(re.search(r'\bprob:\s+file\s+.+\s+not found\b', message_lower))

    @classmethod
    def parseFindResultMessage(cls, message):
        import re
        match = re.match(r'^\[[^\]]+\]\s+', message)
        message_content = message[match.end():] if match else message
        match = re.match(r'^([^:]+):\s*(.*?),\s*(?:(.*?),\s*)?(\d+)\s*byte,\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})', message_content)
        if not match:
            return None
        filename, status, ftype, size, date = match.groups()
        if "/" not in filename and "." not in filename:
            return None
        return filename, status, ftype or "", size, date

    @classmethod
    def handleScriptCompilerMessage(cls, message):
        import re
        target_match = re.match(r'^Script compiler output for\s+(.+):$', message)
        if target_match:
            cls.compiler_output_target = target_match.group(1).strip()
            cls.logCompiler(message)
            return True
        error_match = re.search(r'\berror:\s+(.+?)\s+at line\s+(\d+):\s*(.*)$', message)
        if error_match and cls.compiler_output_target:
            error_text = error_match.group(1).strip()
            line_number = int(error_match.group(2))
            line_text = error_match.group(3).strip()
            cls.logCompiler(message)
            cls.markScriptCompilerError(cls.compiler_output_target, line_number, error_text, line_text)
            return True
        if cls.compiler_output_target and (
            message.startswith("Will keep running the old NPC script")
            or message.startswith("Script compiler")
            or message.lower().startswith("warning:")
        ):
            cls.logCompiler(message)
            return True
        return False

    @classmethod
    def isScriptUpdateMessage(cls, message):
        return bool(
            re.search(r'\bWeapon/GUI-script .+ added/updated by\b', message)
            or re.search(r'\bThe script of NPC .+ has been updated by\b', message)
            or re.search(r'\bScript .+ updated by\b', message)
        )

    @classmethod
    def markScriptCompilerError(cls, target, line_number, error_text, line_text):
        target_lower = target.lower()
        annotation = "{}: {}".format(error_text, line_text) if line_text else error_text
        flags = sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SQUIGGLY_UNDERLINE
        for window in sublime.windows():
            for view in window.views():
                names = [
                    view.settings().get("rc_weapon_name"),
                    view.settings().get("rc_class_name"),
                    view.settings().get("rc_npc_name")
                ]
                display_name = view.settings().get("rc_display_name") or view.name()
                if display_name:
                    names.append(display_name)
                if not any(name and target_lower in str(name).lower() for name in names):
                    continue
                point = view.text_point(max(line_number - 1, 0), 0)
                line_region = view.line(point)
                if line_region.empty():
                    line_region = sublime.Region(point, point)
                try:
                    view.add_regions(
                        "sublimerc_compile_errors",
                        [line_region],
                        "invalid",
                        "dot",
                        flags,
                        annotations=[annotation],
                        annotation_color="#ff6b6b"
                    )
                except TypeError:
                    view.add_regions("sublimerc_compile_errors", [line_region], "invalid", "dot", flags)
                    view.set_status("sublimerc_compile_error", "Line {}: {}".format(line_number, annotation))
                window.focus_view(view)
                return

    @classmethod
    def logPlain(cls, message, show_panel=False):
        from datetime import datetime
        timestamp_console = datetime.now().strftime("%I:%M:%S %p")
        timestamp_terminal = datetime.now().strftime("%I:%M:%S %p")
        alert_scope = None
        if message.startswith('#ALERT'):
            match = re.match(r'^#ALERT([A-Z]*)\s*(.*)', message)
            if match:
                alert_type = '#ALERT' + match.group(1)
                alert_msg = match.group(2)
                prefix_map = {'#ALERT': '⚠ ALERT ', '#ALERTF': '⚠ ALERT ', '#ALERTP': '🔔 PRIORITY ', '#ALERTFS': '💬 NOTICE ', '#ALERTPS': 'ℹ️ INFO '}
                scope_map = {'#ALERT': 'alert.red', '#ALERTF': 'alert.red', '#ALERTP': 'alert.yellow', '#ALERTFS': 'alert.blue', '#ALERTPS': 'alert.green'}
                prefix = prefix_map.get(alert_type, 'ALERT ')
                alert_scope = scope_map.get(alert_type)
                formatted = "[{}] {}{}".format(timestamp_terminal, prefix, alert_msg)
                cls.sendAlert(alert_type, None, alert_msg, 'red')
            else:
                formatted = "[{}] {}".format(timestamp_terminal, message)
        else:
            formatted = "[{}] {}".format(timestamp_terminal, message)
        view = cls.ensureChatView(focus=show_panel)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        formatted_console = "[{}] {}".format(timestamp_console, message)
        print("RC: " + formatted_console)

    @classmethod
    def handleRcControlMessage(cls, message):
        if message.startswith("#DEFINECMD "):
            raw_name = message[len("#DEFINECMD "):].strip()
            cmd_name = raw_name.split()[0] if raw_name else ""
            if cmd_name and len(cmd_name) < 0x100:
                cmd_key = cmd_name.lower()
                if not re.fullmatch(r'[0-9a-fA-F]+', cmd_name) and not cmd_key.startswith(("global", "npc")):
                    cls.npc_defined_commands.add(cmd_key)
                    cls.log("Registered NPC command alias: /{}".format(cmd_name), debug_only=True)
            return True
        if message.startswith("#HIDENCMESSAGES"):
            return True
        if message.startswith("#SHOWNCMESSAGES"):
            return True
        if message.startswith("#ALERT"):
            cls.log(message)
            return True
        return False

    @classmethod
    def logPrivateMessageReceived(cls, label, key):
        from datetime import datetime
        timestamp_console = datetime.now().strftime("%I:%M:%S %p")
        timestamp_terminal = datetime.now().strftime("%I:%M:%S %p")
        link_text = "from " + label
        formatted = "[{}] PM received: {}".format(timestamp_terminal, link_text)
        view = cls.ensureChatView()
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
            content = view.substr(sublime.Region(0, view.size()))
            line_start = content.rfind(formatted)
            if line_start >= 0:
                start = line_start + formatted.find(link_text)
                end = start + len(link_text)
                view_id = view.id()
                links = cls.pm_chat_links.setdefault(view_id, [])
                links.append((start, end, key))
                regions = [sublime.Region(a, b) for a, b, _ in links]
                view.add_regions("sublimerc_pm_links", regions, "entity.name.function", "", sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SOLID_UNDERLINE)
        print("RC: [{}] PM received: {}".format(timestamp_console, link_text))

    @classmethod
    def showFindResultLine(cls, filename, status, ftype, size, date):
        from datetime import datetime
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        details = [status]
        if ftype:
            details.append(ftype)
        details.extend([size + " byte", date])
        formatted = "[{}] {}: {}".format(timestamp, filename, ", ".join(details))
        icon = cls.getFileIcon(filename)
        file_browser_formatted = "[{}] {} {}: {}".format(timestamp, icon, filename, ", ".join(details))
        cls.appendFindResultLineToView(cls.ensureFileBrowserLogView(), file_browser_formatted, filename)
        print("RC: " + formatted)

    @classmethod
    def getFileIcon(cls, filename):
        ext = os.path.splitext(filename.lower())[1]
        if ext in (".nw", ".graal", ".zelda"):
            return "\U0001f5fa\ufe0f"
        if ext in (".png", ".gif", ".jpg", ".jpeg", ".bmp", ".webp"):
            return "\U0001f5bc\ufe0f"
        if ext in (".gani",):
            return "\U0001f3ad"
        if ext in (".txt", ".log", ".md"):
            return "\U0001f4dd"
        if ext in (".gs2", ".gscript"):
            return "\U0001f4dc"
        if ext in (".wav", ".mp3", ".ogg", ".mid", ".midi"):
            return "\U0001f3b5"
        if ext in (".assetbundle", ".bundle"):
            return "\U0001f4e6"
        if ext in (".zip", ".rar", ".7z", ".gz"):
            return "\U0001f5dc\ufe0f"
        return "\U0001f4c4"

    @classmethod
    def appendFindResultLineToView(cls, view, formatted, filename):
        if not view:
            return
        view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        content = view.substr(sublime.Region(0, view.size()))
        line_start = content.rfind(formatted)
        if line_start < 0:
            return
        start = line_start + formatted.find(filename)
        end = start + len(filename)
        base = cls.find_result_base or "levels/"
        full_path = (base.rstrip("/") + "/" + filename.lstrip("/")) if base else filename
        view_id = view.id()
        links = cls.find_result_links.setdefault(view_id, [])
        links.append((start, end, full_path))
        regions = [sublime.Region(a, b) for a, b, _ in links]
        view.add_regions("sublimerc_find_result_links", regions, "entity.name.function", "", sublime.DRAW_NO_FILL | sublime.DRAW_NO_OUTLINE | sublime.DRAW_SOLID_UNDERLINE)

    @classmethod
    def showFindResultActions(cls, filename):
        window = sublime.active_window()
        if not window:
            return
        items = [
            ["Open for Editing", filename],
            ["Download", filename],
            ["Open Externally", filename],
            ["Copy Path", filename],
        ]
        def on_done(index):
            if index == 0:
                cls.openServerPathForEditing(filename)
            elif index == 1:
                cls.downloadServerPath(filename)
                sublime.status_message("Downloading: " + filename)
            elif index == 2:
                cls.openServerPathExternally(filename)
            elif index == 3:
                sublime.set_clipboard(filename)
                sublime.status_message("Copied: " + filename)
        window.show_quick_panel(items, on_done)

    @classmethod
    def splitServerFilePath(cls, filename):
        filename = filename.replace("\\", "/").strip("/")
        if "/" not in filename:
            return "", filename
        folder, basename = filename.rsplit("/", 1)
        return folder.rstrip("/") + "/", basename

    @classmethod
    def requestServerPathFile(cls, filename, open_after=False, external=False, label="Downloading file"):
        if not cls.authenticated:
            cls.logNotAuthenticated()
            return
        folder, basename = cls.splitServerFilePath(filename)
        cls.pending_file_download = filename
        cls.open_after_download = open_after
        cls.external_open_requested = external
        if folder:
            cls.current_folder = folder
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_CD"], folder.encode('latin-1'))
        def request_file():
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_DOWN"], basename.encode('latin-1'))
        sublime.set_timeout(request_file, 150 if folder else 0)
        cls.logFileBrowser("{}: {}".format(label, filename))

    @classmethod
    def openServerPathForEditing(cls, filename):
        cls.requestServerPathFile(filename, open_after=True, external=False, label="Opening file")

    @classmethod
    def downloadServerPath(cls, filename):
        cls.requestServerPathFile(filename, open_after=False, external=False, label="Downloading file")

    @classmethod
    def openServerPathExternally(cls, filename):
        cls.requestServerPathFile(filename, open_after=False, external=True, label="Downloading file")

    @classmethod
    def openLocalFileExternally(cls, file_path):
        import subprocess
        system = platform.system()
        if system == 'Windows':
            try:
                os.startfile(file_path)
            except Exception:
                subprocess.Popen(['rundll32', 'shell32.dll,OpenAs_RunDLL', file_path])
        elif system == 'Darwin':
            subprocess.Popen(['open', file_path])
        else:
            subprocess.Popen(['xdg-open', file_path])

    @classmethod
    def watchExternalFile(cls, local_path, server_path):
        try:
            local_path = os.path.abspath(local_path)
            stat = os.stat(local_path)
        except Exception as e:
            cls.logFileBrowser("External file watch failed: {}".format(str(e)))
            return
        cls.external_file_watchers[local_path] = {
            "server_path": server_path.replace("\\", "/").strip("/"),
            "mtime": stat.st_mtime,
            "size": stat.st_size,
            "pending": None,
            "uploading": False
        }
        cls.logFileBrowser("Watching external file: {}".format(server_path))
        cls.ensureExternalFileWatchTimer()

    @classmethod
    def ensureExternalFileWatchTimer(cls):
        if cls.external_file_watch_timer is None:
            cls.external_file_watch_timer = sublime.set_timeout(cls.pollExternalFileWatchers, 1000)

    @classmethod
    def pollExternalFileWatchers(cls):
        cls.external_file_watch_timer = None
        if not cls.external_file_watchers:
            return
        for local_path, info in list(cls.external_file_watchers.items()):
            try:
                stat = os.stat(local_path)
            except FileNotFoundError:
                cls.external_file_watchers.pop(local_path, None)
                continue
            except Exception:
                continue
            current = (stat.st_mtime, stat.st_size)
            known = (info.get("mtime"), info.get("size"))
            if current == known:
                info["pending"] = None
                continue
            pending = info.get("pending")
            if pending == current and not info.get("uploading"):
                info["mtime"], info["size"] = current
                info["pending"] = None
                cls.uploadWatchedExternalFile(local_path, info)
            else:
                info["pending"] = current
        cls.ensureExternalFileWatchTimer()

    @classmethod
    def uploadWatchedExternalFile(cls, local_path, info):
        if not cls.authenticated:
            return
        server_path = info.get("server_path", "")
        folder, basename = cls.splitServerFilePath(server_path)
        if not basename:
            return
        try:
            with open(local_path, 'rb') as f:
                content = f.read()
        except Exception as e:
            cls.logFileBrowser("External upload failed: {}".format(str(e)))
            return
        def send_upload():
            try:
                info["uploading"] = True
                cls.logFileBrowser("Uploading external edit: {}".format(server_path))
                cls.uploadFile(basename, content)
            finally:
                info["uploading"] = False
        if folder and cls.current_folder != folder:
            cls.current_folder = folder
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_CD"], folder.encode('latin-1'))
            sublime.set_timeout(send_upload, 150)
        else:
            send_upload()

    @classmethod
    def getChatViewName(cls):
        if cls.connected_server:
            name = cls.connected_server.get('name')
            if name:
                return str(name)
        return "RC Chat"

    @classmethod
    def joinListRows(cls, rows, separator="\n"):
        rows = rows or ["No entries returned."]
        return separator.join(rows)

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
        return view

    @classmethod
    def ensureFileBrowserLogView(cls, window=None, focus=False):
        window = window or sublime.active_window()
        if not window:
            return None
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
        return view

    @classmethod
    def ensureToallsView(cls, window=None, focus=False):
        window = window or sublime.active_window()
        if not window:
            return None
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
        return view

    @classmethod
    def logToalls(cls, message, focus=False):
        from datetime import datetime
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        formatted = "[{}] {}".format(timestamp, message)
        view = cls.ensureToallsView(focus=focus)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        print("RC Toalls: " + formatted)

    @classmethod
    def logFileBrowser(cls, message, focus=False):
        from datetime import datetime
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        formatted = "[{}] {}".format(timestamp, message)
        view = cls.ensureFileBrowserLogView(focus=focus)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        print("RC File Browser: " + formatted)

    @classmethod
    def logFileBrowserLines(cls, prefix, message, focus=False):
        text = str(message).replace("\r\n", "\n").replace("\r", "\n")
        for line in text.split("\n"):
            line = line.strip()
            if line:
                cls.logFileBrowser(prefix + line, focus=focus)

    @classmethod
    def logFileBrowserServerMessage(cls, message):
        text = str(message).replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if not lines:
            return

        first = lines[0]
        if first.startswith("Uploading big file "):
            path = first[len("Uploading big file "):].strip()
            path = path[:-3].strip() if path.endswith("...") else path
            filename = os.path.basename(path.replace("\\", "/"))
            size_line = lines[1] if len(lines) > 1 else ""
            if size_line.startswith("size "):
                size_text = size_line[len("size "):].strip().rstrip(".")
                total = getattr(cls, "pending_upload_total", 0)
                if total:
                    cls.logFileBrowser("Uploaded chunk: {}/{} bytes for {}".format(size_text, total, filename))
                else:
                    cls.logFileBrowser("Uploaded chunk: {} bytes for {}".format(size_text, filename))
                return
            if not first.endswith("..."):
                return

        if first.startswith("Uploaded big file "):
            cls.pending_upload_filename = None
            cls.pending_upload_total = 0

        for line in lines:
            cls.logFileBrowser(line)

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
        else:
            cls.ensureCompilerLogView(window, focus=True)

    @classmethod
    def logCompiler(cls, message, focus=False):
        from datetime import datetime
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        formatted = "[{}] {}".format(timestamp, message)
        if cls.compilerOutputLocation() == "panel":
            show_panel = bool(focus or getSetting("compiler_panel_auto_show", True))
            view = cls.ensureCompilerPanel(show=show_panel)
            if view:
                view.run_command("rc_chat_append", {"characters": formatted + "\n"})
            print(formatted)
        else:
            cls.logNc(message, focus=focus)

    @classmethod
    def ensureNcLogView(cls, window=None, focus=False):
        window = window or sublime.active_window()
        if not window:
            return None
        if cls.nc_log_view and getattr(cls.nc_log_view, "is_valid", lambda: False)() and cls.nc_log_view.settings().get("rc_nc_log_view"):
            view = cls.nc_log_view
        else:
            view = next((v for v in window.views() if v.settings().get("rc_nc_log_view")), None)
            if not view:
                view = window.new_file()
                view.set_scratch(True)
                view.assign_syntax("Packages/SublimeRC/terminal.sublime-syntax")
                view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                view.settings().set("rc_nc_log_view", True)
                view.set_name("🧬 NC")
            cls.nc_log_view = view
        if focus:
            window.focus_view(view)
            view.run_command("move_to", {"to": "eof"})
        return view

    @classmethod
    def logNc(cls, message, focus=False):
        from datetime import datetime
        timestamp = datetime.now().strftime("%I:%M:%S %p")
        formatted = "[{}] {}".format(timestamp, message)
        if not getSetting("separate_nc_messages", False):
            cls.logPlain(message)
            return
        view = cls.ensureNcLogView(focus=focus)
        if view:
            view.run_command("rc_chat_append", {"characters": formatted + "\n"})
        print(formatted)

    @classmethod
    def onFilePhantomClicked(cls, filename, status):
        if status != "downloadable":
            cls.logFileBrowser("File '{}' is marked not downloadable".format(filename))
            return
        if cls.authenticated:
            cls.pending_file_download = filename
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_DOWN"], filename.encode('latin-1'))
            cls.logFileBrowser("Downloading file: " + filename)
            window = sublime.active_window()
            if window:
                def show_menu():
                    selected_file = filename
                    options = ["📂 Open", "🔗 Open External", "⬇️ Download", "🗑️ Delete", "✏️ Rename", "← Back"]
                    def on_selected(index):
                        if index == 0:
                            cls.openFileForEditing(selected_file)
                        elif index == 1:
                            cls.openFileExternally(selected_file)
                        elif index == 2:
                            cls.downloadFile(selected_file)
                        elif index == 3:
                            if sublime.ok_cancel_dialog("Delete " + selected_file + "?", "Delete"):
                                cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_DELETE"], selected_file.encode('latin-1'))
                                cls.log("Deleted file: " + selected_file)
                        elif index == 4:
                            window.show_input_panel("Rename to:", selected_file, lambda new_name: None, None, None)
                        elif index == 5:
                            return
                    window.show_quick_panel(options, on_selected)
                sublime.set_timeout(show_menu, 500)
        else:
            cls.log("Not authenticated - cannot download")

    @classmethod
    def sendAlert(cls, alert_type, role=None, message="", alert_color=None):
        if not cls.authenticated:
            cls.log("Not authenticated - cannot send alert")
            return
        window = sublime.active_window()
        if not window:
            return
        if alert_type == '#ALERTF':
            window.run_command('rc_show_chat')
            sublime.status_message(message)
            sublime.error_message(message)
        elif alert_type == '#ALERTP':
            window.run_command('rc_show_chat')
            sublime.status_message(message)
            sublime.error_message(message)
        elif alert_type == '#ALERTFS':
            sublime.status_message(message)
        elif alert_type == '#ALERTPS':
            window.run_command('rc_show_chat')
            sublime.status_message(message)

    @classmethod
    def logNotAuthenticated(cls):
        if not cls.shown_not_authenticated:
            cls.log("Not authenticated")
            cls.shown_not_authenticated = True

    @classmethod
    def clearCaches(cls):
        cls.npc_sort_timer = None
        cls.class_sort_timer = None
        for server_name in list(cls.pm_server_update_timers.keys()):
            cls._stopPMServerPolling(server_name)
        cls.players = []
        cls.external_players = {}
        cls.pm_servers = []
        cls.pm_server_players = {}
        cls.servers = []
        cls.next_external_id = 16000
        cls.folders = []
        cls.folder_files = []
        cls.current_folder = None
        cls.npcs = []
        cls.npc_ids = set()
        cls.npc_batch_count = 0
        cls.weapons = []
        cls.classes = []
        cls.class_names = set()
        cls.class_batch_count = 0
        cls.weapon_scripts = {}
        cls.class_scripts = {}
        cls.npc_scripts = {}
        cls.player_rights = {}
        cls.player_attributes = {}
        cls.player_comments = {}
        cls.player_profiles = {}
        cls.npc_flags = {}
        cls.server_options = None
        cls.server_flags = None
        cls.folder_config = None
        cls.pending_server_options_request = False
        cls.pending_server_flags_request = False
        cls.pending_folder_config_request = False
        cls.pending_weapon_request = None
        cls.pending_class_request = None
        cls.pending_npc_request = None
        cls.pending_weapon_callback = None
        cls.pending_class_callback = None
        cls.pending_npc_callback = None
        cls.pending_npc_flags_request = None
        cls.pending_npc_props_request = None
        cls.pending_player_rights_request = None
        cls.pending_player_attrs_request = None
        cls.pending_player_comments_request = None
        cls.pending_player_profile_request = None
        cls.pending_player_ban_request_id = None
        cls.isNewProtocol = False
        cls.pending_file_download = None
        cls.open_after_download = False
        cls.expecting_folder_list = False
        cls.pending_local_npcs_request = None
        cls.shown_not_authenticated = False
        cls.private_messages = {}
        cls.private_message_order = []
        cls.private_message_open_index = 0
        cls.irc_channels = {}
        cls.irc_bootstrapped = False

    @classmethod
    def connectToServer(cls, server_info):
        try:
            if 'ip' not in server_info or 'port' not in server_info:
                cls.log("Server {} does not have IP/port information".format(server_info.get('name', 'Unknown')))
                return False
            if cls.socket_connection or cls.nc_socket:
                cls.switching_servers = True
            if cls.socket_connection:
                try:
                    old_socket = cls.socket_connection
                    cls.socket_connection = None
                    cls.authenticated = False
                    old_socket.close()
                    cls.log("Closed old RC connection", debug_only=True)
                except: pass
            if cls.nc_socket:
                try:
                    old_nc = cls.nc_socket
                    cls.nc_socket = None
                    cls.nc_authenticated = False
                    old_nc.close()
                    cls.log("Closed old NC connection", debug_only=True)
                except: pass
            import time
            time.sleep(0.2)
            cls.clearCaches()
            listserver_config = server_info.get('listserver_config') or cls.current_listserver_config or {}
            listserver_host = str(listserver_config.get('host', '')).strip().lower()
            cls.isNewProtocol = (listserver_host == "listserver.graalonline.com")
            cls.log("Ban protocol host flag: {} ({})".format(cls.isNewProtocol, listserver_host or "unknown"), debug_only=True)
            cls.socket_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cls.socket_connection.settimeout(60.0)
            cls.socket_connection.connect((server_info['ip'], server_info['port']))
            cls.connected_server = server_info
            cls.updateChatViewName()
            cls.authenticated = False
            cls.nc_authenticated = False
            cls.has_set_nickname = False
            cls.has_received_welcome = False
            cls.npc_server_address = None
            cls.protocol = GRCProtocol()
            cls.nc_protocol = NCProtocol()
            cls.log("Connected to " + server_info['name'])
            cls.sendLogin()
            threading.Thread(target=cls.listenForData, daemon=True).start()
            return True
        except Exception as e:
            cls.log("Connection failed: " + str(e))
            return False
    
    @classmethod
    def sendLogin(cls):
        try:
            account, password = getCredentials(cls)
            pcid = generatePcid(account)
            login_payload = "vGSERV025"
            login_payload += get1PlusTextNetString(account)
            login_payload += get1PlusTextNetString(password)
            login_payload += pcid
            packet = cls.protocol.sendPacket(cls.socket_connection, 6, login_payload.encode('latin-1'))
            cls.protocol.setEncryptionKey(0x56)
        except Exception as e: cls.log("Login failed: " + str(e))
        
    @classmethod
    def sendPacket(cls, packet_id, data=None):
        if data is None: data = bytearray()
        packet_name = next((k for k, v in cls.RC_TO_SERVER.items() if v == packet_id), "UNKNOWN")
        hex_data = ' '.join('{:02x}'.format(b) for b in data)
        cls.log("SEND RC PKT {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(data), hex_data), debug_only=True)
        return cls.protocol.sendPacket(cls.socket_connection, packet_id, data)
    
    @classmethod
    def sendNcPacket(cls, packet_id, data=None):
        if data is None: data = bytearray()
        packet_name = next((k for k, v in cls.NC_TO_SERVER.items() if v == packet_id), next((k for k, v in cls.RC_TO_SERVER.items() if v == packet_id), "UNKNOWN"))
        hex_data = ' '.join('{:02x}'.format(b) for b in data)
        cls.log("SEND NC PKT {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(data), hex_data), debug_only=True)
        if cls.nc_socket: return cls.nc_protocol.sendPacket(cls.nc_socket, packet_id, data)
    
    @classmethod
    def connectToNpcServer(cls):
        if cls.nc_authenticated:
            cls.log("Already connected to NPC server")
            return
        if cls.nc_socket:
            cls.log("NPC connection in progress, skipping duplicate")
            return
        if not cls.npc_server_address:
            cls.log("No NPC server address available, requesting...")
            cls.requestNpcServer()
            return
        cls.log("Connecting to NPC server at: {}".format(cls.npc_server_address), debug_only=True)
        try:
            host, port = cls.npc_server_address.split(',')
            port = int(port)
            cls.log("Obtained host: {}, port: {}".format(host, port), debug_only=True)
            cls.log("Creating socket to {}:{}".format(host, port), debug_only=True)
            cls.nc_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            cls.nc_socket.settimeout(None)
            cls.nc_socket.connect((host, port)) 
            account, password = getCredentials(cls)
            login_payload = "NCL21075"
            login_payload += get1PlusTextNetString(account)
            login_payload += get1PlusTextNetString(password)
            cls.nc_protocol.sendPacket(cls.nc_socket, cls.NC_TO_SERVER["PLI_NC_LOGIN"], login_payload.encode('latin-1'))
            cls.log("Sent NC login, waiting for authentication...", debug_only=True)
            threading.Thread(target=cls.listenNcData, daemon=True).start()
        except Exception as e: cls.log("NC connection failed: " + str(e))
    
    @classmethod
    def requestNpcServer(cls):
        if not cls.npcserver_player_id:
            cls.log("No npcserver detected, cannot connect")
            return
        cls.log("Requesting NPC server address...", debug_only=True)
        payload = writeGShort(cls.npcserver_player_id) + b"location"
        cls.sendPacket(cls.RC_TO_SERVER["PLI_NPCSERVERQUERY"], payload)

    @classmethod
    def requestLocalNpcs(cls, text):
        if not cls.nc_authenticated:
            cls.log("Not connected to NPC server")
            sublime.error_message("Not connected to NPC server.")
            return False
        payload = gtokenize(text or "").encode('latin-1')
        cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_LOCALNPCSGET"], payload)
        cls.pending_local_npcs_request = text or "localnpcs"
        cls.log("Requested local NPCs: {}".format(text), debug_only=True)
        return True

    @classmethod
    def disconnectPlayer(cls, player_id, reason):
        if cls.authenticated:
            payload = bytearray()
            payload.extend(writeGShort(player_id))
            payload.extend(reason.encode('latin-1'))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_SERVERFLAGSGET"], payload)
            cls.log("Disconnected player ID {} with reason: {}".format(player_id, reason))

    @classmethod
    def disconnect(cls):
        if cls.socket_connection:
            try: cls.socket_connection.close()
            except: pass
        cls.socket_connection = None
        cls.connected_server = None
        cls.updateChatViewName()
        cls.authenticated = False
        cls.clearCaches()
        if not cls.switching_servers:
            cls.log("Disconnected from server")

    @classmethod
    def requestPlayerRights(cls, account):
        cls.log("Requesting rights for: " + account, debug_only=True)
        if cls.authenticated:
            payload = account.encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERRIGHTSGET"], payload)
            cls.pending_player_rights_request = account
    
    @classmethod
    def requestPlayerAttributes(cls, account):
        if cls.authenticated:
            payload = bytearray()
            account_bytes = account.encode('latin-1')
            payload.append(len(account_bytes) + 32)
            payload.extend(account_bytes)
            payload.append(32)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERPROPSGET3"], payload)
            cls.pending_player_attrs_request = account
            cls.log("Requesting attributes for: " + account, debug_only=True)
    
    @classmethod
    def requestAccount(cls, account):
        if cls.authenticated:
            payload = account.encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_ACCOUNTGET"], payload)
            cls.pending_account_request = account
            cls.log("Requesting account data for: " + account, debug_only=True)

    @classmethod
    def requestAccountList(cls, account_filter, conditions, callback=None):
        if cls.authenticated:
            payload = bytearray()
            payload.extend(writeRcLenString(str(account_filter or "").strip()))
            payload.extend(writeRcLenString(str(conditions or "").strip()))
            cls.account_list_callback = callback
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_ACCOUNTLISTGET"], payload)
            cls.log("Requesting accounts: account='{}', conditions='{}'".format(account_filter or "", conditions or ""), debug_only=True)
            return True
        return False
    
    @classmethod
    def requestPlayerComments(cls, account):
        if cls.authenticated:
            payload = account.encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERCOMMENTSGET"], payload)
            cls.pending_player_comments_request = account
            cls.log("Requesting comments for: " + account, debug_only=True)
    
    @classmethod
    def requestPlayerProfile(cls, account):
        if cls.authenticated:
            payload = account.encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PROFILEGET"], payload)
            cls.pending_player_profile_request = account
            cls.log("Requesting profile for: " + account, debug_only=True)

    @classmethod
    def requestPlayerBan(cls, account):
        if cls.authenticated:
            cls.pending_player_ban_request_id = None
            payload = account.encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERBANGET"], payload)
            cls.pending_player_ban_request = account
            cls.log("Requesting ban data for: " + account, debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def requestPlayerBanById(cls, account, player_id=None):
        if cls.authenticated:
            lookup_id = player_id if player_id is not None else account
            data = "GraalEngine\nlister\ngetbanbyid\n{}".format(lookup_id)
            payload = gtokenize(data).encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_SENDTEXT"], payload)
            cls.pending_player_ban_request = account
            cls.pending_player_ban_request_id = player_id
            cls.log("Ban request text: {}".format(repr(data)), debug_only=True)
            cls.log("Requesting ban data for: {} ({})".format(account, player_id), debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def requestPlayerBanByAccount(cls, account):
        if cls.authenticated:
            data = "GraalEngine\nlister\ngetban\n{}".format(account)
            payload = gtokenize(data).encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_SENDTEXT"], payload)
            cls.pending_player_ban_request = account
            cls.pending_player_ban_request_id = None
            cls.log("Requesting account ban data for: {}".format(account), debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def requestStaffActivity(cls, account):
        if cls.authenticated:
            data = "GraalEngine\nlister\ngetstaffactivity\n{}".format(account)
            payload = gtokenize(data).encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_SENDTEXT"], payload)
            cls.log("Requested staff activity for: {}".format(account), debug_only=True)
            return True
        else: cls.logNotAuthenticated()
        return False

    @classmethod
    def requestBanHistory(cls, account):
        if cls.authenticated:
            data = "GraalEngine\nlister\ngetbanhistory\n{}".format(account)
            payload = gtokenize(data).encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_SENDTEXT"], payload)
            cls.log("Requested ban history for account: {}".format(account), debug_only=True)
            return True
        else: cls.logNotAuthenticated()
        return False

    @classmethod
    def findPlayerForBanCommand(cls, query):
        query = str(query or '').strip()
        if not query:
            return None
        if query.isdigit():
            player_id = int(query)
            return next((p for p in cls.players if p.get('id') == player_id), {'id': player_id, 'account': query})
        query_lower = query.lower()
        return next((p for p in cls.players if str(p.get('account', '')).lower() == query_lower or str(p.get('nickname', '')).lower() == query_lower), None)

    @classmethod
    def requestBanTypes(cls):
        if cls.authenticated:
            data = "GraalEngine\nlister\nbantypes"
            payload = gtokenize(data).encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_REQUESTTEXT"], payload)
            cls.log("Requested ban types", debug_only=True)

    @classmethod
    def _formatBanTypeDuration(cls, seconds):
        try:
            seconds = int(seconds)
        except:
            seconds = 0
        if seconds >= 315360000:
            return "unlimited"
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        if days > 0 and hours > 0:
            return "{} days {} hours".format(days, hours)
        if days > 0:
            return "{} days".format(days)
        if hours > 0:
            return "{} hours".format(hours)
        return "{} seconds".format(seconds)

    @classmethod
    def _formatTimeRemaining(cls, seconds):
        try:
            seconds = max(0, int(seconds))
        except:
            return str(seconds)
        days = seconds // 86400
        seconds = seconds % 86400
        hours = seconds // 3600
        seconds = seconds % 3600
        minutes = seconds // 60
        parts = []
        if days:
            parts.append("{} day{}".format(days, "" if days == 1 else "s"))
        if hours:
            parts.append("{} hour{}".format(hours, "" if hours == 1 else "s"))
        if minutes or not parts:
            parts.append("{} min{}".format(minutes, "" if minutes == 1 else "s"))
        return ", ".join(parts)

    @classmethod
    def updateBanTypes(cls, entries):
        ban_types = []
        for entry in entries:
            try:
                row = next(csv.reader([entry]))
            except:
                row = []
            if len(row) < 2:
                continue
            name = row[0].strip()
            try:
                seconds = int(row[1].strip())
            except:
                seconds = 0
            if name:
                ban_types.append({"name": name, "seconds": seconds})
        if ban_types:
            cls.ban_types = ban_types
            cls.BAN_REASONS = [""] + ["{} ({})".format(b["name"], cls._formatBanTypeDuration(b["seconds"])) for b in ban_types]
            cls.log("Loaded {} ban types".format(len(ban_types)), debug_only=True)

    @classmethod
    def handleBanBootstrap(cls, account, computer_id):
        pending_account = cls.pending_player_ban_request
        pending_id = cls.pending_player_ban_request_id
        cls.log("Ban raw: account={}, computer_id={}, pending={} ({})".format(account, computer_id, pending_account, pending_id), debug_only=True)
        ban_data = {
            "account": account,
            "computer_id": computer_id
        }
        for section in ("local", "global", "computer", "global_computer"):
            ban_data[section] = {
                "active": False,
                "ban_reason": "",
                "time_remaining": "-",
                "reset_timer": False,
                "reason_for_update": ""
            }
        cls.player_bans[account] = ban_data
        cls.pending_player_ban_request = None
        cls.pending_player_ban_request_id = None
        def openEditor():
            window = sublime.active_window()
            if window:
                cmd = RcShowExplorerCommand(window)
                cmd.editPlayerBan({"account": account, "_open_cached_ban": True})
        sublime.set_timeout(openEditor, 0)

    @classmethod
    def handleBanResponse(cls, parts):
        account = parts[3] if len(parts) > 3 else cls.pending_player_ban_request
        computer_id = parts[4] if len(parts) > 4 else ""
        if account == "GraalEngine" and computer_id == "0" and cls.pending_player_ban_request:
            account = cls.pending_player_ban_request
            computer_id = ""
        cls.handleBanBootstrap(account, computer_id)
        if len(parts) < 6:
            return
        details = {}
        try:
            row = next(csv.reader([parts[5]]))
        except:
            row = [parts[5]]
        for item in row:
            key, sep, value = item.partition('=')
            if sep:
                details[key.strip().lower()] = value.strip().strip('"')
        ban_data = cls.player_bans.get(account)
        if not ban_data:
            return
        local_ban = ban_data.setdefault("local", {})
        local_ban["active"] = True
        if details.get("bantype"):
            local_ban["ban_reason"] = details.get("bantype")
        if details.get("releasetime"):
            local_ban["time_remaining"] = cls._formatTimeRemaining(details.get("releasetime"))
        local_ban["reason_for_update"] = ""
        cls.player_bans[account] = ban_data
        cls.log("Parsed ban details for {}: {}".format(account, repr(details)), debug_only=True)

    @classmethod
    def buildListViewText(cls, title, rows, account=None, row_separator="\n"):
        text = "{} for {}\n\n".format(title, account) if account else title + "\n\n"
        text += cls.joinListRows(rows, row_separator)
        if not text.endswith("\n"):
            text += "\n"
        return text

    @classmethod
    def listViewIcon(cls, suffix):
        icons = {
            "staffactivity": "📋",
            "banhistory": "🚫",
            "local_npcs": "🧩"
        }
        return icons.get(suffix, "📄")

    @classmethod
    def openListView(cls, suffix, title, rows, account=None, read_only=True, view_settings=None, row_separator="\n"):
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(cls.connected_server['name']) if cls.connected_server else "Unknown"
        out_dir = os.path.join(scripts_folder, server_name, "modified", "players" if account else "lists")
        os.makedirs(out_dir, exist_ok=True)
        filename = "{}_{}".format(urlEncodeFilename(account), suffix) if account else suffix
        list_file = os.path.join(out_dir, urlEncodeFilename(filename) + ".goption")
        text = cls.buildListViewText(title, rows, account, row_separator)
        with open(list_file, 'w', encoding='utf-8') as f:
            f.write(text)
        def openView():
            window = sublime.active_window()
            if window:
                list_key = "{}:{}".format(suffix, account or "")
                view = next((v for v in window.views() if v.settings().get("rc_list_view") and v.settings().get("rc_list_key") == list_key), None)
                if not view:
                    view = window.new_file()
                    view.set_scratch(True)
                    view.assign_syntax("Packages/SublimeRC/list.sublime-syntax")
                    view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                    view.settings().set("rc_list_view", True)
                    view.settings().set("rc_list_key", list_key)
                view.set_name("{} {}".format(cls.listViewIcon(suffix), title if not account else "{} - {}".format(title, account)))
                view.settings().set('rc_player_data_type', suffix)
                if account:
                    view.settings().set('rc_player_account', account)
                if view_settings:
                    for key, value in view_settings.items():
                        view.settings().set(key, value)
                view.run_command("rc_replace_buffer_content", {"content": text, "read_only": read_only})
                window.focus_view(view)
                view.run_command("move_to", {"to": "bof"})
        sublime.set_timeout(openView, 0)

    @classmethod
    def refreshOpenPrivateMessageThread(cls, key):
        thread = cls.private_messages.get(key)
        if not thread:
            return False
        account = thread.get("account") if thread.get("account") != "Unknown" else None
        text = cls.buildListViewText("Private Messages", thread.get("messages", []), account, "\n\n")
        refreshed = False
        for window in sublime.windows():
            for view in window.views():
                if view.settings().get("rc_pm_thread_key") == key:
                    refreshed = True
                    if view.settings().get("rc_pm_view"):
                        if thread.get("messages"):
                            view.run_command("rc_chat_append", {"characters": thread.get("messages", [""])[-1] + "\n\n"})
                        else:
                            view.run_command("rc_replace_buffer_content", {"content": text + "\n> ", "read_only": False})
                    else:
                        view.run_command("rc_replace_buffer_content", {"content": text, "read_only": True})
                    view.run_command("move_to", {"to": "eof"})
        return refreshed

    @classmethod
    def appendPrivateMessageLog(cls, key, entry):
        pms_dir = os.path.join(getScriptsFolder(), "pms")
        os.makedirs(pms_dir, exist_ok=True)
        log_file = os.path.join(pms_dir, urlEncodeFilename(key) + ".txt")
        needs_spacing = os.path.exists(log_file) and os.path.getsize(log_file) > 0
        with open(log_file, "a", encoding="utf-8") as f:
            if needs_spacing:
                f.write("\n\n")
            f.write(entry)
            if not entry.endswith("\n"):
                f.write("\n")

    @classmethod
    def privateMessageLogPath(cls, key):
        return os.path.join(getScriptsFolder(), "pms", urlEncodeFilename(key) + ".txt")

    @classmethod
    def loadPrivateMessageHistory(cls, key):
        log_file = cls.privateMessageLogPath(key)
        if not os.path.exists(log_file):
            return []
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read().strip()
        if not content:
            return []
        return [entry for entry in re.split(r"\n{2,}", content) if entry.strip()]

    @classmethod
    def clearPrivateMessageThread(cls, key):
        thread = cls.private_messages.get(key)
        if thread:
            thread["messages"] = []
        log_file = cls.privateMessageLogPath(key)
        if os.path.exists(log_file):
            os.remove(log_file)
        cls.refreshOpenPrivateMessageThread(key)

    @classmethod
    def recordPrivateMessage(cls, player_id, nickname, account, message, incoming=True):
        from datetime import datetime
        def ordinal(n):
            if 10 <= n % 100 <= 20:
                suffix = "th"
            else:
                suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
            return "{}{}".format(n, suffix)
        account = account or "Unknown"
        nickname = nickname or account
        if isinstance(message, str) and len(message) >= 2 and message[0] == '"' and message[-1] == '"':
            message = message[1:-1]
        key = account if account != "Unknown" else str(player_id)
        thread = cls.private_messages.setdefault(key, {
            "player_id": player_id,
            "nickname": nickname,
            "account": account,
            "messages": []
        })
        thread["player_id"] = player_id
        thread["nickname"] = nickname
        thread["account"] = account
        direction = "From"
        display_name = nickname if incoming else (getSetting("nickname") or getSetting("account") or "You")
        now = datetime.now()
        clock = now.strftime("%I:%M%p").lstrip("0").lower()
        timestamp = "{} {} {}, at {}".format(now.strftime("%B"), ordinal(now.day), now.year, clock)
        entry = "{} {} {}:\n{}".format(timestamp, direction, display_name, message)
        thread["messages"].append(entry)
        cls.appendPrivateMessageLog(key, entry)
        if key in cls.private_message_order:
            cls.private_message_order.remove(key)
        cls.private_message_order.append(key)
        if incoming:
            cls.private_message_open_index = 0
        refreshed = cls.refreshOpenPrivateMessageThread(key)
        thread["last_refreshed_open_view"] = refreshed
        return key

    @classmethod
    def openPrivateMessageThread(cls, key):
        thread = cls.private_messages.get(key)
        if not thread:
            sublime.error_message("No PM thread found.")
            return
        if not thread.get("messages"):
            thread["messages"] = cls.loadPrivateMessageHistory(key)
        account = thread.get("account") if thread.get("account") != "Unknown" else None
        label = thread.get("nickname") or thread.get("account") or key
        if thread.get("account") and thread.get("account") != label:
            label = "{} ({})".format(label, thread.get("account"))
        text = cls.buildListViewText("Private Messages", thread.get("messages", []), account, "\n\n") + "\n> "
        def openView():
            window = sublime.active_window()
            if not window:
                return
            view = next((v for v in window.views() if v.settings().get("rc_pm_view") and v.settings().get("rc_pm_thread_key") == key), None)
            if not view:
                view = window.new_file()
                view.set_scratch(True)
                view.assign_syntax("Packages/SublimeRC/pm.sublime-syntax")
                view.settings().set("color_scheme", "Packages/SublimeRC/terminal.sublime-color-scheme")
                view.settings().set("rc_pm_view", True)
                view.settings().set("rc_pm_thread_key", key)
                view.settings().set("rc_pm_player_id", thread.get("player_id"))
                view.settings().set("rc_pm_label", label)
            view.set_name("💬 PM - " + label)
            view.run_command("rc_replace_buffer_content", {"content": text, "read_only": False})
            window.focus_view(view)
            view.run_command("move_to", {"to": "eof"})
        sublime.set_timeout(openView, 0)

    @classmethod
    def openPrivateMessageForPlayer(cls, player):
        if not player:
            sublime.status_message("No player found for PM.")
            return
        player_id = player.get("id")
        account = player.get("account") or "Unknown"
        nickname = player.get("nickname") or account
        if player_id is None:
            sublime.status_message("No player ID found for PM.")
            return
        key = account if account != "Unknown" else str(player_id)
        thread = cls.private_messages.setdefault(key, {
            "player_id": player_id,
            "nickname": nickname,
            "account": account,
            "messages": []
        })
        thread["player_id"] = player_id
        thread["nickname"] = nickname
        thread["account"] = account
        if not thread.get("messages"):
            thread["messages"] = cls.loadPrivateMessageHistory(key)
        cls.openPrivateMessageThread(key)

    @classmethod
    def findPlayerByChatName(cls, name):
        name = str(name or "").strip().lower()
        if not name:
            return None
        for player in cls.players:
            for key in ("nickname", "account"):
                value = str(player.get(key, "")).strip().lower()
                if value and value == name:
                    return player
        return None

    @classmethod
    def openNextPrivateMessageThread(cls):
        ordered = [key for key in reversed(cls.private_message_order) if key in cls.private_messages]
        if not ordered:
            sublime.error_message("No PMs received.")
            return
        key = ordered[cls.private_message_open_index % len(ordered)]
        cls.private_message_open_index += 1
        cls.openPrivateMessageThread(key)

    @classmethod
    def openAllPrivateMessageThreads(cls):
        ordered = [key for key in reversed(cls.private_message_order) if key in cls.private_messages]
        if not ordered:
            sublime.error_message("No PMs received.")
            return
        for key in ordered:
            cls.openPrivateMessageThread(key)

    @classmethod
    def sendIrcText(cls, command, *params):
        if not cls.authenticated:
            cls.log("Not connected - cannot send IRC message")
            return False
        data = "\n".join(["GraalEngine", "irc", command] + [str(p) for p in params])
        payload = gtokenize(data).encode('latin-1')
        cls.sendPacket(cls.RC_TO_SERVER["PLI_SENDTEXT"], payload)
        return True

    @classmethod
    def bootstrapIrcBridge(cls):
        if cls.irc_bootstrapped:
            return
        cls.irc_bootstrapped = True
        cls.sendIrcText("login", "-")

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
    def handleIrcResponse(cls, parts):
        if len(parts) < 3:
            return
        command = parts[2]
        if command == "join" and len(parts) >= 4:
            channel = parts[3]
            cls.openIrcChannel(channel, focus=False)
            cls.appendIrcMessage(channel, "* Joined {}".format(channel))
        elif command == "part" and len(parts) >= 4:
            cls.appendIrcMessage(parts[3], "* Left {}".format(parts[3]))
        elif command in ("privmsg", "notice") and len(parts) >= 6:
            source, destination, message = parts[3], parts[4], parts[5]
            from datetime import datetime
            clock = datetime.now().strftime("%I:%M%p").lstrip("0").lower()
            if command == "notice":
                line = "[{}] * {}: {}".format(clock, source, message)
            else:
                line = "[{}] <{}> {}".format(clock, source, message)
            cls.appendIrcMessage(destination, line)

    BAN_REASONS = [""]

    @classmethod
    def banToText(cls, ban_data):
        text = "Account: {}\n".format(ban_data.get('account', ''))
        text += "Computer ID: {}\n\n".format(ban_data.get('computer_id', ''))
        for section, label in [('local', 'Local Ban'), ('global', 'Global Ban'), ('computer', 'Computer Ban'), ('global_computer', 'Global Computer Ban')]:
            b = ban_data.get(section, {})
            text += "# {}:\n".format(label)
            text += "Active: {}\n".format('true' if b.get('active', False) else 'false')
            text += "Ban Reason: {}\n".format(cls._banReasonForText(b.get('ban_reason', '')))
            text += "Time Remaining: {}\n".format(b.get('time_remaining', '-'))
            text += "Reset Timer: {}\n".format('true' if b.get('reset_timer', False) else 'false')
            text += "Reason for update: {}\n\n".format(b.get('reason_for_update', ''))
        text += "# Ban Reasons:\n"
        for i, reason in enumerate(cls.BAN_REASONS[1:], 1):
            text += "{}. {}\n".format(i, reason)
        return text

    @classmethod
    def textToBan(cls, text):
        ban_data = {}
        section = None
        section_map = {'Local Ban': 'local', 'Global Ban': 'global', 'Computer Ban': 'computer', 'Global Computer Ban': 'global_computer'}
        for line in text.split('\n'):
            line = line.rstrip()
            if line.startswith('# '):
                heading = line[2:].rstrip(':')
                if heading in section_map:
                    section = section_map[heading]
                    ban_data.setdefault(section, {})
                else:
                    section = None
                continue
            if ':' not in line:
                continue
            label, _, value = line.partition(':')
            label = label.strip()
            value = value.strip()
            if section is None:
                if label == 'Account':
                    ban_data['account'] = value
                elif label == 'Computer ID':
                    ban_data['computer_id'] = value
            else:
                b = ban_data.setdefault(section, {})
                if label == 'Active':
                    b['active'] = value.lower() == 'true'
                elif label == 'Ban Type':
                    b['ban_reason'] = value
                elif label == 'Ban Reason':
                    b['ban_reason'] = value
                elif label == 'Time Remaining':
                    b['time_remaining'] = value
                elif label == 'Reset Timer':
                    b['reset_timer'] = value.lower() == 'true'
                elif label == 'Reason for update':
                    b['reason_for_update'] = value
        return ban_data

    @classmethod
    def _banTypeName(cls, reason):
        reason = str(reason or '').strip()
        if reason.isdigit():
            index = int(reason)
            if index > 0 and index <= len(cls.ban_types):
                return cls.ban_types[index - 1].get("name", "")
        match = re.match(r'^(.*?)\s*\(', reason)
        if match:
            reason = match.group(1).strip()
        return reason

    @classmethod
    def _banReasonForText(cls, reason):
        reason_name = cls._banTypeName(reason)
        for index, ban_type in enumerate(cls.ban_types, 1):
            if ban_type.get("name") == reason_name:
                return str(index)
        return str(reason or '').strip()

    @classmethod
    def _banReleaseTime(cls, reason):
        reason_name = cls._banTypeName(reason)
        for ban_type in cls.ban_types:
            if ban_type.get("name") == reason_name:
                return str(ban_type.get("seconds", ""))
        return ""

    @classmethod
    def _sendSetBan(cls, account, target, world, ban_entry):
        active = bool(ban_entry.get('active', False))
        ban_type = cls._banTypeName(ban_entry.get('ban_reason', ''))
        reason = str(ban_entry.get('reason_for_update', ''))
        fields = [
            target,
            "world=" + world,
            "banned=" + ("1" if active else "0"),
            "bantype=" + ban_type
        ]
        if active and ban_entry.get('reset_timer', False):
            release_time = cls._banReleaseTime(ban_type)
            if release_time:
                fields.append("releasetime=" + release_time)
        fields.append("reason=" + reason)
        data = "GraalEngine,lister,setban," + ",".join(fields)
        payload = data.encode('latin-1')
        cls.sendPacket(cls.RC_TO_SERVER["PLI_SENDTEXT"], payload)
        cls.log("Setban text: {}".format(repr(data)), debug_only=True)

    @classmethod
    def _shouldSendBanSection(cls, ban_entry):
        if ban_entry.get('active', False):
            return True
        if str(ban_entry.get('ban_reason', '')).strip():
            return True
        time_remaining = str(ban_entry.get('time_remaining', '')).strip()
        if time_remaining and time_remaining != '-':
            return True
        if ban_entry.get('reset_timer', False):
            return True
        if str(ban_entry.get('reason_for_update', '')).strip():
            return True
        return False

    @classmethod
    def _normalizeBanSectionForCompare(cls, ban_entry):
        return {
            "active": bool(ban_entry.get('active', False)),
            "ban_reason": cls._banTypeName(ban_entry.get('ban_reason', '')),
            "time_remaining": str(ban_entry.get('time_remaining', '')).strip(),
            "reset_timer": bool(ban_entry.get('reset_timer', False)),
            "reason_for_update": str(ban_entry.get('reason_for_update', '')).strip()
        }

    @classmethod
    def _banSectionChanged(cls, section, ban_data, original_ban_data):
        if not original_ban_data:
            return cls._shouldSendBanSection(ban_data.get(section, {}))
        current = cls._normalizeBanSectionForCompare(ban_data.get(section, {}))
        original = cls._normalizeBanSectionForCompare(original_ban_data.get(section, {}))
        return current != original

    @classmethod
    def uploadSetBan(cls, account, ban_data, original_ban_data=None):
        computer_id = str(ban_data.get('computer_id', '')).strip()
        section_targets = [
            ('local', account, 'local'),
            ('global', account, 'all')
        ]
        if computer_id:
            section_targets.append(('computer', 'pc:' + computer_id, 'local'))
            section_targets.append(('global_computer', 'pc:' + computer_id, 'all'))
        for section, target, world in section_targets:
            ban_entry = ban_data.get(section, {})
            if not cls._banSectionChanged(section, ban_data, original_ban_data):
                continue
            cls._sendSetBan(account, target, world, ban_entry)
        cls.log("Uploaded ban data for: " + account, debug_only=True)

    @classmethod
    def uploadPlayerBan(cls, account, ban_data, original_ban_data=None):
        if not cls.authenticated:
            cls.logNotAuthenticated()
            return
        if cls.isNewProtocol:
            cls.uploadSetBan(account, ban_data, original_ban_data)
            return
        payload = bytearray()
        account_bytes = account.encode('latin-1')
        local_ban = ban_data.get('local', {})
        reason = str(local_ban.get('reason_for_update', '') or local_ban.get('ban_reason', '')).encode('latin-1')
        payload.append(len(account_bytes) + 32)
        payload.extend(account_bytes)
        payload.append((1 if local_ban.get('active', False) else 0) + 32)
        payload.extend(reason)
        cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERBANSET"], payload)
        cls.log("Uploaded ban data for: " + account, debug_only=True)

    @classmethod
    def sendPrivateMessage(cls, player_id, message):
        if cls.authenticated:
            payload = bytearray()
            payload.extend(writeGShort(1))
            payload.extend(writeGShort(player_id))
            message_commatext = gtokenize(message)
            payload.extend(message_commatext.encode('latin-1'))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_PRIVATEMESSAGE"], payload)
            cls.log("Sent PM to player ID {}: {}".format(player_id, message), debug_only=True)
    
    @classmethod
    def rightsToText(cls, rights_value, ip_range, folder_access):
        text = "IP Range: {}\n\n".format(ip_range)
        text += "# Rights (set to true/false):\n"
        for i, name in enumerate(cls.RIGHTS_NAMES):
            if name:
                has_right = (rights_value & (1 << i)) != 0
                text += "{}: {}\n".format(name, str(has_right).lower())
        text += "\nFolder Access:\n{}\n".format(folder_access)
        return text
    
    @classmethod
    def textToRights(cls, text):
        lines = text.split('\n')
        ip_range = ""
        folder_access_lines = []
        rights_value = 0
        in_folder_section = False
        for line in lines:
            if line.startswith("IP Range:"):
                ip_range = line.split(":", 1)[1].strip()
                in_folder_section = False
            elif line.startswith("Folder Access:"):
                first_folder = line.split(":", 1)[1].strip()
                if first_folder:
                    folder_access_lines.append(first_folder)
                in_folder_section = True
            elif line.startswith("#"):
                in_folder_section = False
            elif in_folder_section and line.strip():
                folder_access_lines.append(line.strip())
            elif not in_folder_section:
                for i, name in enumerate(cls.RIGHTS_NAMES):
                    if name and line.startswith(name + ":"):
                        value = line.split(":", 1)[1].strip().lower()
                        if value == "true":
                            rights_value |= (1 << i)
                        break
        folder_access = '\n'.join(folder_access_lines)
        return rights_value, ip_range, folder_access
    
    @classmethod
    def attributesToText(cls, properties):
        text = ""
        text += "[Stats]\n"
        text += "Account: {}\n".format(properties.get('account', ''))
        text += "Last IP: {}\n".format(properties.get('last_ip', ''))
        text += "Kills: {}\n".format(properties.get(27, 0))
        text += "Deaths: {}\n".format(properties.get(28, 0))
        text += "Online Seconds: {}\n".format(properties.get(29, 0))
        text += "Rating: {}\n".format(properties.get('rating', 0))
        text += "Rating Deviation: {}\n".format(properties.get('rating_dev', 0))
        text += "\n"
        text += "[Look]\n"
        text += "Head Image: {}\n".format(properties.get('head_image', 'head0.gif'))
        text += "Body Image: {}\n".format(properties.get('body_image', ''))
        text += "Animation: {}\n".format(properties.get(10, ''))
        colors = properties.get('colors', [0, 0, 0, 0, 0])
        text += "Skin Color: {}\n".format(cls.COLOR_NAMES[colors[0]] if colors[0] < len(cls.COLOR_NAMES) else colors[0])
        text += "Coat Color: {}\n".format(cls.COLOR_NAMES[colors[1]] if colors[1] < len(cls.COLOR_NAMES) else colors[1])
        text += "Sleeves Color: {}\n".format(cls.COLOR_NAMES[colors[2]] if colors[2] < len(cls.COLOR_NAMES) else colors[2])
        text += "Shoes Color: {}\n".format(cls.COLOR_NAMES[colors[3]] if colors[3] < len(cls.COLOR_NAMES) else colors[3])
        text += "Belt Color: {}\n".format(cls.COLOR_NAMES[colors[4]] if colors[4] < len(cls.COLOR_NAMES) else colors[4])
        text += "\n"
        text += "[Basic Attributes]\n"
        text += "Level: {}\n".format(properties.get(20, ''))
        text += "X: {}\n".format(int(properties.get(5, 0) / 2.0))
        text += "Y: {}\n".format(int(properties.get(6, 0) / 2.0))
        text += "Hearts: {}\n".format(properties.get(1, 0))
        text += "Full Hearts: {}\n".format(properties.get(2, 0))
        text += "MP: {}\n".format(properties.get(27, 0))
        text += "Gralats: {}\n".format(properties.get(30, 0))
        text += "Glove: {}\n".format(properties.get(17, 0))
        text += "Bombs: {}\n".format(properties.get(19, 0))
        text += "Arrows: {}\n".format(properties.get(4, 0))
        text += "Sword Power: {}\n".format(properties.get('sword_power', 0))
        text += "Sword Image: {}\n".format(properties.get('sword_image', ''))
        text += "Shield Power: {}\n".format(properties.get('shield_power', 0))
        text += "Shield Image: {}\n".format(properties.get('shield_image', ''))
        status = properties.get(18, 0)
        text += "Male: {}\n".format('true' if (status & 4) else 'false')
        text += "Weapons Enabled: {}\n".format('true' if (status & 16) else 'false')
        text += "Spin Attack: {}\n".format('true' if (status & 64) else 'false')
        text += "\n"
        text += "[Chests]\n"
        for chest in properties.get('chests', []):
            text += "{}\n".format(chest)
        text += "\n"
        text += "[Weapons]\n"
        for weapon in properties.get('weapons', []):
            text += "{}\n".format(weapon)
        text += "\n"
        text += "[Script Flags]\n"
        for flag in properties.get('flags', []):
            text += "{}\n".format(flag)
        return text

    @classmethod
    def textToAttributes(cls, text):
        properties = {}
        lines = text.split('\n')
        current_section = None
        chests = []
        weapons = []
        flags = []
        color_names_map = {v.lower(): k for k, v in enumerate(['White', 'Yellow', 'Orange', 'Pink', 'Red', 'Darkred', 'Lightgreen', 'Green', 'Darkgreen', 'Lightblue', 'Blue', 'Darkblue', 'Brown', 'Cynober', 'Purple', 'Darkpurple', 'Lightgray', 'Gray', 'Black', 'Transparent'])}
        colors = [0, 0, 0, 0, 0]
        status_bits = 0
        for line in lines:
            line = line.strip()
            if not line: continue
            if line.startswith('[') and line.endswith(']'):
                current_section = line[1:-1]
                continue
            if ':' in line:
                label, value = line.split(':', 1)
                label = label.strip()
                value = value.strip()
                try:
                    if label in cls.prop_map:
                        key, conv = cls.prop_map[label]
                        if isinstance(key, str) and key.startswith('status_'):
                            status_bits |= conv(value)
                        else:
                            properties[key] = conv(value)
                        cls.log("textToAttributes: label={}, value={}, key={}, result={}".format(label, value, key, properties.get(key, "N/A")), debug_only=True)
                    elif label in cls.color_map:
                        colors[cls.color_map[label]] = color_names_map.get(value.lower(), int(value) if value.isdigit() else 0)
                        cls.log("textToAttributes: color label={}, value={}, color_index={}, result={}".format(label, value, cls.color_map[label], colors[cls.color_map[label]]), debug_only=True)
                    elif label in cls.status_map and value.lower() == 'true':
                        status_bits |= cls.status_map[label]
                        cls.log("textToAttributes: status label={}, value={}, status_bits={}".format(label, value, status_bits), debug_only=True)
                except Exception as e:
                    cls.log("textToAttributes parse error: label={}, value={}, error={}".format(label, value, e), debug_only=True)
            elif current_section == 'Chests' and line:
                chests.append(line)
            elif current_section == 'Weapons' and line:
                weapons.append(line)
            elif current_section == 'Script Flags' and line:
                flags.append(line)
        properties['colors'] = colors
        properties[18] = status_bits
        properties['chests'] = chests
        properties['weapons'] = weapons
        properties['flags'] = flags
        return properties
    
    @classmethod
    def accountToText(cls, account_data):
        text = ""
        text += "Account name: {}\n".format(account_data.get('account', ''))
        text += "Password:\n"
        text += "E-mail address: {}\n".format(account_data.get('email', ''))
        text += "Admin level: {}\n".format(account_data.get('admin_level', ''))
        text += "Admin worlds: {}\n".format(account_data.get('admin_worlds', ''))
        text += "Banned: {}\n".format('true' if account_data.get('banned', False) else 'false')
        text += "Guest: {}\n".format('true' if account_data.get('guest', False) else 'false')
        ban_time = account_data.get('ban_time', 0)
        if ban_time > 0:
            from datetime import datetime
            ban_date = datetime.fromtimestamp(ban_time)
            text += "Ban Time: {}\n".format(ban_date.strftime('%a %b %d %H:%M:%S %Y'))
        else:
            text += "Ban Time: Wed Dec 31 18:00:00 1969\n"
        ban_reason = account_data.get('ban_reason', '')
        text += "Ban-Reason / Comments: {}\n".format(ban_reason)
        return text
    
    @classmethod
    def textToAccount(cls, text):
        account_data = {}
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("old email:"):
                account_data['old_email'] = line.split(":", 1)[1].strip() if ':' in line else ""
                continue
            if line.startswith("-") and "," in line:
                parts = line[1:].split(",", 1)
                account_data['changed_by'] = parts[0].strip()
                if len(parts) > 1:
                    account_data['change_date'] = parts[1].strip()
                continue
            if ':' in line:
                label, value = line.split(':', 1)
                label = label.strip()
                value = value.strip()
                if label == "Account name":
                    account_data['account'] = value
                elif label == "Password":
                    account_data['password'] = value
                elif label == "E-mail address":
                    account_data['email'] = value
                elif label == "Admin level":
                    account_data['admin_level'] = value
                elif label == "Admin worlds":
                    account_data['admin_worlds'] = value
                elif label == "Banned":
                    account_data['banned'] = value.lower() == 'true'
                elif label == "Guest":
                    account_data['guest'] = value.lower() == 'true'
                elif label == "Ban Time":
                    if value != "Wed Dec 31 18:00:00 1969":
                        try:
                            from datetime import datetime
                            account_data['ban_time'] = int(datetime.strptime(value, '%a %b %d %H:%M:%S %Y').timestamp())
                        except:
                            account_data['ban_time'] = 0
                    else:
                        account_data['ban_time'] = 0
                elif label == "Ban-Reason / Comments":
                    account_data['ban_reason'] = value
        return account_data
    
    @classmethod
    def textToProfile(cls, text, account):
        if account in cls.player_profiles:
            original_fields = cls.player_profiles[account]
            profile_fields = [original_fields[i] if i < len(original_fields) else "" for i in range(11)]
            original_server_extras = original_fields[11:] if len(original_fields) > 11 else []
        else:
            profile_fields = [""] * 11
            original_server_extras = []
        
        profile_fields[0] = account
        
        lines = text.split('\n')
        editable_field_map = {
            'Real Name': 1,
            'Age': 2,
            'Sex': 3,
            'Country': 4,
            'Messenger': 5,
            'E-Mail': 6,
            'Homepage': 7,
            'Fav. Hangout': 8,
            'Favourite Quote': 9
        }
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if line.startswith("Profile for"):
                continue
            if line == "Server Extras:":
                continue
            
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    label = parts[0].strip()
                    value = parts[1].strip()
                    
                    if label == "Level" or label == "Account" or label == "Online Time":
                        continue
                    if label in editable_field_map:
                        field_index = editable_field_map[label]
                        if field_index < len(profile_fields):
                            profile_fields[field_index] = value
        
        while len(profile_fields) < 11:
            profile_fields.append("")
        
        profile_fields[0] = account
        profile_fields.extend(original_server_extras)
        
        cls.log("textToProfile parsed fields: Account={}, Real Name={}, Age={}, Sex={}, Country={}, Messenger={}, E-Mail={}, Homepage={}, Fav. Hangout={}, Favourite Quote={}, Online Time={}".format(
            profile_fields[0], profile_fields[1], profile_fields[2], profile_fields[3], profile_fields[4], 
            profile_fields[5], profile_fields[6], profile_fields[7], profile_fields[8], profile_fields[9], profile_fields[10]
        ), debug_only=True)
        
        return profile_fields
    
    @classmethod
    def uploadPlayerRights(cls, account, rights_value, ip_range, folder_access):
        if cls.authenticated:
            payload = bytearray()
            account_bytes = account.encode('latin-1')
            payload.append(len(account_bytes) + 32)
            payload.extend(account_bytes)
            payload.extend(writeGInt5(rights_value))
            ip_bytes = ip_range.encode('latin-1')
            payload.append(len(ip_bytes) + 32)
            payload.extend(ip_bytes)
            folder_bytes = b""
            if folder_access:
                folder_commatext = gtokenize(folder_access)
                folder_bytes = folder_commatext.encode('latin-1')
            high = ((len(folder_bytes) >> 7) & 0xFF) + 32
            low = (len(folder_bytes) & 0x7F) + 32
            payload.extend(bytes([high, low]))
            payload.extend(folder_bytes)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERRIGHTSSET"], payload)
            cls.log("Updated rights for: " + account, debug_only=True)
    
    @classmethod
    def uploadPlayerAttributes(cls, account, properties):
        if cls.authenticated:
            props_payload = bytearray()
            if 1 in properties:
                props_payload.append(1 + 32)
                props_payload.append(int(properties[1]) + 32)
            if 2 in properties:
                props_payload.append(2 + 32)
                props_payload.append(int(float(properties[2]) * 2) + 32)
            if 3 in properties:
                props_payload.append(3 + 32)
                val = int(properties[3])
                props_payload.extend([(val >> 14) + 32, ((val >> 7) & 0x7F) + 32, (val & 0x7F) + 32])
            if 4 in properties:
                props_payload.append(4 + 32)
                props_payload.append(int(properties[4]) + 32)
            if 'x' in properties:
                props_payload.append(5 + 32)
                props_payload.append(int(float(properties['x']) * 2) + 32)
            if 'y' in properties:
                props_payload.append(6 + 32)
                props_payload.append(int(float(properties['y']) * 2) + 32)
            if 'sword_power' in properties and 'sword_image' in properties:
                props_payload.append(8 + 32)
                power = int(properties['sword_power'])
                img = properties['sword_image']
                if img and img.startswith('sword'):
                    base = img[5:-4]
                    try:
                        idx = int(base) if base.isdigit() else -1
                        if 1 <= idx <= 4:
                            props_payload.append(idx + 32)
                        else:
                            props_payload.append(min(max(10, power + 30), 50) + 32)
                            props_payload.append(len(img) + 32)
                            props_payload.extend(img.encode('latin-1'))
                    except:
                        props_payload.append(min(max(10, power + 30), 50) + 32)
                        props_payload.append(len(img) + 32)
                        props_payload.extend(img.encode('latin-1'))
                elif power == 0:
                    props_payload.append(32)
                else:
                    props_payload.append(min(max(10, power + 30), 50) + 32)
                    props_payload.append(len(img) + 32)
                    props_payload.extend(img.encode('latin-1'))
            if 'shield_power' in properties and 'shield_image' in properties:
                props_payload.append(9 + 32)
                power = int(properties['shield_power'])
                img = properties['shield_image']
                if img and img.startswith('shield'):
                    base = img[6:-4]
                    try:
                        idx = int(base) if base.isdigit() else -1
                        if 1 <= idx <= 3:
                            props_payload.append(idx + 32)
                        else:
                            props_payload.append(min(max(10, power + 10), 13) + 32)
                            props_payload.append(len(img) + 32)
                            props_payload.extend(img.encode('latin-1'))
                    except:
                        props_payload.append(min(max(10, power + 10), 13) + 32)
                        props_payload.append(len(img) + 32)
                        props_payload.extend(img.encode('latin-1'))
                elif power == 0:
                    props_payload.append(32)
                else:
                    props_payload.append(min(max(10, power + 10), 13) + 32)
                    props_payload.append(len(img) + 32)
                    props_payload.extend(img.encode('latin-1'))
            if 10 in properties:
                props_payload.append(10 + 32)
                val = str(properties[10])
                props_payload.append(len(val) + 32)
                props_payload.extend(val.encode('latin-1'))
            if 'head_image' in properties:
                props_payload.append(11 + 32)
                img = properties['head_image']
                if img and img.startswith('head'):
                    base = img[4:-4]
                    try:
                        idx = int(base) if base.isdigit() else -1
                        if idx >= 0 and idx < 100:
                            props_payload.append(idx + 32)
                        else:
                            props_payload.append(100 + len(img) + 32)
                            props_payload.extend(img.encode('latin-1'))
                    except:
                        props_payload.append(100 + len(img) + 32)
                        props_payload.extend(img.encode('latin-1'))
                elif img:
                    props_payload.append(100 + len(img) + 32)
                    props_payload.extend(img.encode('latin-1'))
                else:
                    props_payload.append(32)
            if 'colors' in properties:
                props_payload.append(13 + 32)
                for color in properties['colors']:
                    props_payload.append(int(color) + 32)
            if 15 in properties:
                props_payload.append(15 + 32)
                val = str(properties[15])
                props_payload.append(len(val) + 32)
                props_payload.extend(val.encode('latin-1'))
            if 16 in properties:
                props_payload.append(16 + 32)
                val = str(properties[16])
                props_payload.append(len(val) + 32)
                props_payload.extend(val.encode('latin-1'))
            if 18 in properties:
                props_payload.append(18 + 32)
                props_payload.append(int(properties[18]) + 32)
            if 21 in properties:
                props_payload.append(21 + 32)
                val = str(properties[21])
                props_payload.append(len(val) + 32)
                props_payload.extend(val.encode('latin-1'))
            if 26 in properties:
                props_payload.append(26 + 32)
                props_payload.append(int(properties[26]) + 32)
            if 27 in properties:
                props_payload.append(27 + 32)
                val = int(properties[27])
                props_payload.extend([(val >> 14) + 32, ((val >> 7) & 0x7F) + 32, (val & 0x7F) + 32])
            if 28 in properties:
                props_payload.append(28 + 32)
                val = int(properties[28])
                props_payload.extend([(val >> 14) + 32, ((val >> 7) & 0x7F) + 32, (val & 0x7F) + 32])
            if 29 in properties:
                props_payload.append(29 + 32)
                val = int(properties[29])
                props_payload.extend([(val >> 14) + 32, ((val >> 7) & 0x7F) + 32, (val & 0x7F) + 32])
            if 30 in properties:
                props_payload.append(30 + 32)
                val = int(properties[30])
                props_payload.extend([(val >> 14) + 32, ((val >> 7) & 0x7F) + 32, (val & 0x7F) + 32])
            if 17 in properties:
                props_payload.append(17 + 32)
                props_payload.append(int(properties[17]) + 32)
            if 19 in properties:
                props_payload.append(19 + 32)
                props_payload.append(int(properties[19]) + 32)
            if 21 in properties:
                props_payload.append(21 + 32)
                val = str(properties[21])
                props_payload.append(len(val) + 32)
                props_payload.extend(val.encode('latin-1'))
            if 'glove' in properties:
                props_payload.append(17 + 32)
                props_payload.append(int(properties['glove']) + 32)
            if 'bombs' in properties:
                props_payload.append(19 + 32)
                props_payload.append(int(properties['bombs']) + 32)
            if 'body_image' in properties:
                props_payload.append(53 + 32)
                img = properties['body_image']
                img_len = max(0, len(img))
                props_payload.append(img_len + 32)
                if img_len > 0:
                    props_payload.extend(img.encode('latin-1'))
            if 'rating' in properties and 'rating_dev' in properties:
                props_payload.append(36 + 32)
                rating = int(properties['rating'])
                rating_dev = int(properties['rating_dev'])
                byte1 = (rating >> 5) & 0xFF
                byte2 = ((rating & 0x1F) << 2) | ((rating_dev >> 7) & 0x03)
                byte3 = rating_dev & 0x7F
                props_payload.extend([byte1 + 32, byte2 + 32, byte3 + 32])
            payload = bytearray()
            account_bytes = account.encode('latin-1')
            payload.append(len(account_bytes) + 32)
            payload.extend(account_bytes)
            world_bytes = properties.get('world', '').encode('latin-1')
            payload.append(len(world_bytes) + 32)
            payload.extend(world_bytes)
            payload.append(len(props_payload) + 32)
            payload.extend(props_payload)
            flags = properties.get('flags', [])
            flag_count = len(flags)
            payload.extend([((flag_count >> 7) & 0xFF) + 32, (flag_count & 0x7F) + 32])
            for flag in flags:
                flag_bytes = flag.encode('latin-1')
                payload.append(len(flag_bytes) + 32)
                payload.extend(flag_bytes)
            chests = properties.get('chests', [])
            chest_count = len(chests)
            payload.extend([((chest_count >> 7) & 0xFF) + 32, (chest_count & 0x7F) + 32])
            for chest in chests:
                chest_bytes = chest.encode('latin-1')
                payload.append(len(chest_bytes) + 32)
                payload.extend(chest_bytes)
            weapons = properties.get('weapons', [])
            weapon_count = len(weapons)
            payload.append(weapon_count + 32)
            for weapon in weapons:
                weapon_bytes = weapon.encode('latin-1')
                payload.append(len(weapon_bytes) + 32)
                payload.extend(weapon_bytes)
            prop_keys = [k for k in properties.keys() if k not in ['flags', 'weapons', 'colors', 'chests', 'world']]
            prop_keys.sort(key=lambda x: (isinstance(x, str), x))
            props_str = ", ".join("{}={}".format(k, properties.get(k)) for k in prop_keys)
            cls.log("uploadPlayerAttributes: Account={}, World={}, Props=[{}], Flags={}, Weapons={}, Colors={}, Chest={}".format(
                account, properties.get('world', ''), props_str, properties.get('flags', []), 
                properties.get('weapons', []), properties.get('colors', []), properties.get('chests', [])
            ), debug_only=True)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERPROPSSET2"], payload)
            cls.log("Updated attributes for: " + account, debug_only=True)
    
    @classmethod
    def uploadPlayerComments(cls, account, comments):
        if cls.authenticated:
            payload = bytearray()
            account_bytes = account.encode('latin-1')
            payload.append(len(account_bytes) + 32)
            payload.extend(account_bytes)
            comments_commatext = gtokenize(comments)
            payload.extend(comments_commatext.encode('latin-1'))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERCOMMENTSSET"], payload)
            cls.log("Updated comments for: " + account, debug_only=True)
    
    @classmethod
    def uploadPlayerProfile(cls, account, profile_fields):
        if cls.authenticated:
            payload = bytearray()
            account_bytes = account.encode('latin-1')
            payload.append(len(account_bytes) + 32)
            payload.extend(account_bytes)
            for i in range(1, min(11, len(profile_fields))):
                field = profile_fields[i] if i < len(profile_fields) else ""
                field_bytes = field.encode('latin-1')
                payload.append(len(field_bytes) + 32)
                payload.extend(field_bytes)
            cls.log("uploadPlayerProfile sending fields: Account={}, Real Name={}, Age={}, Sex={}, Country={}, Messenger={}, E-Mail={}, Homepage={}, Fav. Hangout={}, Favourite Quote={}, Online Time={}".format(
                account, profile_fields[1] if len(profile_fields) > 1 else "", profile_fields[2] if len(profile_fields) > 2 else "",
                profile_fields[3] if len(profile_fields) > 3 else "", profile_fields[4] if len(profile_fields) > 4 else "",
                profile_fields[5] if len(profile_fields) > 5 else "", profile_fields[6] if len(profile_fields) > 6 else "",
                profile_fields[7] if len(profile_fields) > 7 else "", profile_fields[8] if len(profile_fields) > 8 else "",
                profile_fields[9] if len(profile_fields) > 9 else "", profile_fields[10] if len(profile_fields) > 10 else ""
            ), debug_only=True)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PROFILESET"], payload)
            cls.log("Updated profile for: " + account)
            cls.pending_player_profile_request = account
            cls.requestPlayerProfile(account)
    
    @classmethod
    def uploadAccount(cls, account, account_data):
        if cls.authenticated:
            cls.sendAccount(account_data, is_new=False, fallback_account=account)
            cls.log("Updated account data for: " + account, debug_only=True)

    @classmethod
    def addAccount(cls, account_data):
        if cls.authenticated:
            cls.sendAccount(account_data, is_new=True)
            cls.log("Added account: " + str(account_data.get('account', '')), debug_only=True)
            return True
        return False

    @classmethod
    def sendAccount(cls, account_data, is_new=False, fallback_account=""):
        payload = bytearray()
        account_name = str(account_data.get('account') or fallback_account or "")
        payload.extend(writeRcLenString(account_name))
        payload.extend(writeRcLenString(account_data.get('password', '')))
        payload.extend(writeRcLenString(account_data.get('email', '')))
        payload.append((1 if account_data.get('banned', False) else 0) + 32)
        payload.append((1 if account_data.get('guest', False) else 0) + 32)
        try:
            admin_level = int(account_data.get('admin_level', 0) or 0)
        except:
            admin_level = 0
        admin_level = max(0, min(0xdf, admin_level))
        payload.append(admin_level + 32)
        payload.extend(writeRcLenString(account_data.get('admin_worlds', '')))
        payload.extend(writeRcLenString(account_data.get('ban_reason', '')))
        opcode = cls.RC_TO_SERVER["PLI_RC_ACCOUNTADD"] if is_new else cls.RC_TO_SERVER["PLI_RC_ACCOUNTSET"]
        cls.sendPacket(opcode, payload)
    @classmethod
    def uploadServerConfig(cls, config_type, content):
        if config_type == "folderconfig":
            tokenized = gtokenize(content)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FOLDERCONFIGSET"], tokenized.encode('latin-1'))
            cls.log("Updated folder configuration", debug_only=True)
        elif config_type == "serverflags":
            lines = [line for line in content.split('\n') if line.strip()]
            high_byte = ((len(lines) >> 7) & 0xFF) + 32
            low_byte = (len(lines) & 0x7F) + 32
            payload = bytes([high_byte, low_byte])
            for line in lines:
                line = line[:223]
                payload += bytes([len(line) + 32]) + line.encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_SERVERFLAGSSET"], payload)
            cls.log("Updated server flags", debug_only=True)
        elif config_type == "serveroptions":
            tokenized = gtokenize(content)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_SERVEROPTIONSSET"], tokenized.encode('latin-1'))
            cls.log("Updated server options", debug_only=True)
    
    @classmethod
    def uploadNpcScript(cls, npc_id, npc_name, content):
        if cls.nc_authenticated:
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            payload.extend(gtokenize(content).encode('latin-1'))
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCSCRIPTSET"], payload)
            cls.log("Updated NPC script: {} (ID: {})".format(npc_name, npc_id), debug_only=True)
        else: cls.log("Not connected to NPC server")
    
    @classmethod
    def uploadClassScript(cls, class_name, content):
        if cls.nc_authenticated:
            payload = get1PlusTextNetString(class_name).encode('latin-1')
            payload += gtokenize(content).encode('latin-1')
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_CLASSADD"], payload)
            cls.log("Updated class script: " + class_name, debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def encodeNcScriptContent(cls, content):
        return (content or "").replace('\r', '').replace('\n', '§')

    @classmethod
    def deleteNpcScript(cls, npc_id, npc_name):
        if cls.nc_authenticated:
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCDELETE"], payload)
            cls.log("Deleted NPC script: {} (ID: {})".format(npc_name, npc_id), debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def resetNpc(cls, npc_id, npc_name):
        if cls.nc_authenticated:
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCRESET"], payload)
            cls.log("Reset NPC: {} (ID: {})".format(npc_name, npc_id), debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def deleteWeaponScript(cls, weapon_name):
        if cls.nc_authenticated:
            payload = weapon_name.encode('latin-1')
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_WEAPONDELETE"], payload)
            cls.log("Deleted weapon script: " + weapon_name, debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def deleteClassScript(cls, class_name):
        if cls.nc_authenticated:
            payload = class_name.encode('latin-1')
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_CLASSDELETE"], payload)
            cls.log("Deleted class script: " + class_name, debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def requestWeaponList(cls):
        if cls.nc_authenticated:
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_WEAPONLISTGET"], bytearray())
            cls.log("Requested weapon list", debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def requestWeaponScript(cls, weapon_name, callback=None):
        if cls.nc_authenticated:
            cls.pending_weapon_request = weapon_name
            cls.pending_weapon_callback = callback
            payload = weapon_name.encode('latin-1') + b'\n'
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_WEAPONGET"], payload)
            cls.log("Requesting weapon: " + weapon_name, debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def requestClassScript(cls, class_name, callback=None):
        if cls.nc_authenticated:
            cls.pending_class_request = class_name
            cls.pending_class_callback = callback
            payload = class_name.encode('latin-1') + b'\n'
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_CLASSEDIT"], payload)
            cls.log("Requesting class: " + class_name, debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def requestNpcScript(cls, npc_id, callback=None):
        if cls.nc_authenticated:
            cls.pending_npc_request = npc_id
            cls.pending_npc_callback = callback
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCSCRIPTGET"], payload)
            cls.log("Requesting NPC script for ID: " + str(npc_id), debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def requestNpcFlags(cls, npc_id):
        if cls.nc_authenticated:
            cls.pending_npc_flags_request = npc_id
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCFLAGSGET"], payload)
            cls.log("Requesting NPC flags for ID: " + str(npc_id), debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def requestNpcProps(cls, npc_id):
        if cls.nc_authenticated:
            cls.pending_npc_props_request = npc_id
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCGET"], payload)
            cls.log("Requesting NPC properties for ID: " + str(npc_id), debug_only=True)
        else: cls.log("Not connected to NPC server")
    
    @classmethod
    def requestPMServerPlayers(cls, server_name):
        if cls.authenticated:
            if server_name not in cls.pm_servers:
                cls.pm_servers.append(server_name)
                cls.pm_server_players[server_name] = []
            cls._requestPMServerPlayersNow(server_name)
            cls._startPMServerPolling(server_name)
            if cls.pending_pm_server_request == server_name:
                def timeout_handler():
                    if cls.pending_pm_server_request == server_name:
                        server_players = [p for p in cls.players if p.get('server') == server_name]
                        if not server_players:
                            window = sublime.active_window()
                            if window:
                                cmd = RcShowExplorerCommand(window)
                                cmd.showServerPlayers(server_name)
                sublime.set_timeout(timeout_handler, 3000)
        else: cls.log("Not authenticated - cannot request PM server players")
    
    @classmethod
    def _requestPMServerPlayersNow(cls, server_name):
        if cls.authenticated:
            data = "GraalEngine\npmserverplayers\n{}\n".format(server_name)
            payload = gtokenize(data).encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_REQUESTTEXT"], payload)
            cls.log("Requesting players from PM server: {}".format(server_name), debug_only=True)
    
    @classmethod
    def _startPMServerPolling(cls, server_name):
        if server_name in cls.pm_server_update_timers:
            pass
        def poll():
            if server_name in cls.pm_servers and cls.authenticated:
                cls._requestPMServerPlayersNow(server_name)
                cls.pm_server_update_timers[server_name] = sublime.set_timeout(poll, 5000)
        cls.pm_server_update_timers[server_name] = sublime.set_timeout(poll, 5000)
    
    @classmethod
    def _stopPMServerPolling(cls, server_name):
        if server_name in cls.pm_server_update_timers:
            del cls.pm_server_update_timers[server_name]
    
    @classmethod
    def removePMServer(cls, server_name):
        cls._stopPMServerPolling(server_name)
        if server_name in cls.pm_servers:
            cls.pm_servers.remove(server_name)
        if server_name in cls.pm_server_players:
            del cls.pm_server_players[server_name]
        external_ids_to_remove = []
        for ext_id, ext_player in cls.external_players.items():
            if ext_player.get('server') == server_name:
                external_ids_to_remove.append(ext_id)
        for ext_id in external_ids_to_remove:
            del cls.external_players[ext_id]
            for i, p in enumerate(cls.players):
                if p.get('id') == ext_id:
                    cls.players.pop(i)
                    break
        cls.log("Removed PM server: {}".format(server_name), debug_only=True)
        if cls.authenticated:
            data = "GraalEngine\npmunmapserver\n{}\n".format(server_name)
            payload = gtokenize(data).encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_REQUESTTEXT"], payload)
    
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
                                cmd = RcShowExplorerCommand(window)
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
                    'nickname': "{} (on {})".format(account_data['nickname'], server_name),
                    'level': '',
                    'server': server_name,
                    'external': True
                }
                cls.external_players[ext_id] = ext_player
                cls.players.append(ext_player)
                cls.log("Added external player: {} (on {})".format(account_data['nickname'], server_name), debug_only=True)
            else:
                ext_id = existing_accounts[account_lower]
                ext_player = cls.external_players.get(ext_id)
                if ext_player:
                    new_nickname = "{} (on {})".format(account_data['nickname'], server_name)
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
                        cls.log("Removed external player: {} (on {})".format(ext_player.get('nickname', ''), server_name), debug_only=True)
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
                            cmd = RcShowExplorerCommand(window)
                            cmd.showServerPlayers(server_name)
                        cls.pending_pm_server_request = None
                sublime.set_timeout(show_players, 500)

    @classmethod
    def uploadNpcFlags(cls, npc_id, flags):
        if cls.nc_authenticated:
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            payload.extend(gtokenize(flags).encode('latin-1'))
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCFLAGSSET"], payload)
            cls.log("Updated NPC flags for ID: " + str(npc_id), debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def warpNpc(cls, npc_id, level, x, y):
        if cls.nc_authenticated:
            high = ((npc_id >> 14) & 0xFF) + 32
            mid = ((npc_id >> 7) & 0x7F) + 32
            low = (npc_id & 0x7F) + 32
            payload = bytearray([high, mid, low])
            payload.append(writeGByte(int(x * 2)))
            payload.append(writeGByte(int(y * 2)))
            payload.extend(level.encode('latin-1'))
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_NPCWARP"], payload)
            cls.log("Warping NPC {} to {} ({}, {})".format(npc_id, level, x, y), debug_only=True)
        else: cls.log("Not connected to NPC server")

    @classmethod
    def warpPlayer(cls, player_id, level, x, y):
        if cls.authenticated:
            high_byte = (player_id >> 7) + 32
            low_byte = (player_id & 0x7F) + 32
            x_byte = int(x * 2) + 32
            y_byte = int(y * 2) + 32
            payload = bytearray([high_byte, low_byte, x_byte, y_byte])
            payload.extend(level.encode('latin-1'))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_WARPPLAYER"], payload)
            cls.log("Warped player {} to {} ({}, {})".format(player_id, level, x, y), debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def sendAdminMessage(cls, player_ids, message):
        if cls.authenticated:
            player_id = player_ids[0]
            high_byte = (player_id >> 7) + 32
            low_byte = (player_id & 0x7F) + 32
            payload = bytearray([high_byte, low_byte])
            payload.extend(message.encode('latin-1'))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PRIVADMINMESSAGE"], payload)
            cls.log("Sent admin message to player ID {}: {}".format(player_id, message), debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def resetPlayer(cls, account):
        if cls.authenticated:
            payload = account.encode('latin-1')
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERPROPSRESET"], payload)
            cls.log("Reset player attributes: " + account, debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def sendAdminMessageAll(cls, message):
        if cls.authenticated:
            payload = bytearray()
            message_bytes = message.encode('latin-1')
            payload.extend(message_bytes)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_ADMINMESSAGE"], payload)
            cls.log("Sent admin message to all players: {}".format(message), debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def sendToallMessage(cls, message):
        if cls.authenticated:
            message_bytes = message.encode('latin-1')
            payload = bytearray([len(message_bytes) + 32])
            payload.extend(message_bytes)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_TOALL"], payload)
            cls.logToalls("{}: {}".format(getSetting("nickname") or getSetting("account") or "You", message))
        else: cls.logNotAuthenticated()

    @classmethod
    def sendMassPm(cls, player_ids, message):
        if cls.authenticated:
            player_ids = player_ids[:0x6fff]
            num_players_high = (len(player_ids) >> 7) + 32
            num_players_low = (len(player_ids) & 0x7F) + 32
            payload = bytearray([num_players_high, num_players_low])
            for player_id in player_ids:
                high_byte = (player_id >> 7) + 32
                low_byte = (player_id & 0x7F) + 32
                payload.extend([high_byte, low_byte])
            payload.extend(gtokenize(message).encode('latin-1'))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_PRIVATEMESSAGE"], payload)
            cls.log("Sent mass PM to {} player(s): {}".format(len(player_ids), message))
        else: cls.logNotAuthenticated()

    @classmethod
    def requestServerOptions(cls):
        if cls.authenticated:
            cls.log("Requesting server options...", debug_only=True)
            cls.pending_server_options_request = True
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_SERVEROPTIONSGET"], bytearray())
        else: cls.logNotAuthenticated()

    @classmethod
    def requestFolderConfig(cls):
        if cls.authenticated:
            cls.pending_folder_config_request = True
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FOLDERCONFIGGET"], bytearray())
            cls.log("Requesting folder config...", debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def requestServerFlags(cls):
        if cls.authenticated:
            cls.pending_server_flags_request = True
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_SERVERFLAGSGET"], bytearray())
            cls.log("Requesting server flags...", debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def openFileBrowser(cls):
        if cls.authenticated:
            cls.expecting_folder_list = False 
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_START"], "")
            cls.log("Opening file browser...", debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def requestFolder(cls, folder_path):
        if cls.authenticated:
            cls.expecting_folder_list = False
            cls.folder_files = []
            cls.current_folder = folder_path
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_CD"], folder_path.encode('latin-1'))
            cls.logFileBrowser("Requesting folder: " + folder_path)
        else: cls.logNotAuthenticated()

    @classmethod
    def downloadFile(cls, filename):
        if cls.authenticated:
            cls.pending_file_download = filename
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_DOWN"], filename.encode('latin-1'))
    
    @classmethod
    def openFileExternally(cls, filename):
        if cls.authenticated:
            cls.pending_file_download = filename
            cls.open_after_download = False
            cls.external_open_requested = True
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_DOWN"], filename.encode('latin-1'))
            cls.logFileBrowser("Downloading file: " + filename)
        else: cls.logNotAuthenticated()

    @classmethod
    def openFileForEditing(cls, filename):
        if cls.authenticated:
            cls.open_after_download = True
            cls.pending_file_download = filename
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_DOWN"], filename.encode('latin-1'))
            cls.logFileBrowser("Opening file: " + filename)
        else: cls.logNotAuthenticated()

    @classmethod
    def uploadFile(cls, filename, content):
        if not cls.authenticated:
            cls.logNotAuthenticated()
            return
        if isinstance(content, str):
            content = content.encode('latin-1', errors='replace')
        filename = os.path.basename(filename.replace("\\", "/"))
        if not filename:
            cls.logFileBrowser("Upload failed: missing filename")
            return
        if len(filename) > 223:
            cls.logFileBrowser("Upload failed: filename is too long: " + filename)
            return
        name_bytes = filename.encode('latin-1', errors='replace')
        def send_upload_chunk(chunk):
            inner_payload = bytearray([cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_UP"] + 32])
            inner_payload.append(len(name_bytes) + 32)
            inner_payload.extend(name_bytes)
            inner_payload.extend(chunk)
            inner_payload.append(0x0a)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RAWDATA"], writeGInt3(len(inner_payload)))
            cls.protocol.sendRawBlock(cls.socket_connection, inner_payload)

        if len(content) <= cls.file_upload_chunk_size:
            send_upload_chunk(content)
            cls.logFileBrowser("Uploading file: {} ({} bytes)".format(filename, len(content)))
            return

        cls.pending_upload_filename = filename
        cls.pending_upload_total = len(content)
        cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_LARGEFILESTART"], name_bytes)
        offset = 0
        while offset < len(content):
            send_upload_chunk(content[offset:offset + cls.file_upload_chunk_size])
            offset += cls.file_upload_chunk_size
        cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_LARGEFILEEND"], name_bytes)
        cls.logFileBrowser("Uploading large file: {} ({} bytes)".format(filename, len(content)))

    @classmethod
    def uploadLocalFile(cls, local_path):
        if not cls.authenticated:
            cls.logNotAuthenticated()
            return
        if not cls.current_folder:
            cls.logFileBrowser("Upload failed: open a file browser folder first")
            sublime.error_message("Open a File Browser folder before uploading.")
            return
        try:
            with open(local_path, 'rb') as f:
                content = f.read()
        except Exception as e:
            cls.logFileBrowser("Upload failed: {}".format(str(e)))
            return
        filename = os.path.basename(local_path)
        cls.logFileBrowser("Upload target: {}{}".format(cls.current_folder, filename))
        cls.uploadFile(filename, content)

    @classmethod
    def deleteFile(cls, filename):
        if cls.authenticated:
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_DELETE"], filename.encode('latin-1'))
            cls.log("Deleting file: " + filename)
        else: cls.logNotAuthenticated()

    @classmethod
    def renameFile(cls, old_name, new_name):
        if cls.authenticated:
            payload = bytearray()
            payload.append(len(old_name) + 32)
            payload.extend(old_name.encode('latin-1'))
            payload.append(len(new_name) + 32)
            payload.extend(new_name.encode('latin-1'))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_RENAME"], payload)
            cls.log("Renaming file: {} -> {}".format(old_name, new_name))
        else: cls.logNotAuthenticated()

    @classmethod
    def closeFileBrowser(cls):
        if cls.authenticated:
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_FILEBROWSER_END"], bytearray())
            cls.log("Closing file browser", debug_only=True)
        else: cls.logNotAuthenticated()

    @classmethod
    def parseWeaponList(cls, payload):
        weapons = []
        offset = 0
        while offset < len(payload):
            if offset >= len(payload): break
            name_len = decodeGByte(payload[offset])
            offset += 1
            if offset + name_len > len(payload): break
            weapon_name = payload[offset:offset + name_len].decode('latin-1', errors='ignore')
            weapons.append(weapon_name)
            offset += name_len
        cls.weapons = sorted(weapons, key=sortKey)
        cls.log("Received {} weapons".format(len(weapons)), debug_only=True)
        return weapons
    
    @classmethod
    def _sortClasses(cls):
        cls.classes = sorted(cls.classes, key=sortKey)
        cls.class_sort_timer = None
        cls.class_batch_count = 0
        cls.log("Sorted {} classes".format(len(cls.classes)), debug_only=True)

    @classmethod
    def _sortNpcs(cls):
        cls.npcs = sorted(cls.npcs, key=lambda x: sortKey(x['name']))
        cls.npc_sort_timer = None
        cls.npc_batch_count = 0
        cls.log("Sorted {} NPCs".format(len(cls.npcs)), debug_only=True)

    @classmethod
    def uploadWeaponScript(cls, weapon_name, content):
        if cls.nc_authenticated:
            image_name = ""
            script_content = content
            if content.startswith("//#IMAGE:"):
                lines = content.split('\n', 2)
                if len(lines) >= 2:
                    image_name = lines[0][9:].strip()
                    script_content = '\n'.join(lines[1:]) if len(lines) > 1 else ""
            script_content = cls.encodeNcScriptContent(script_content)
            payload = get1PlusTextNetString(weapon_name).encode('latin-1')
            payload += get1PlusTextNetString(image_name).encode('latin-1')
            payload += script_content.encode('latin-1')
            cls.sendNcPacket(cls.NC_TO_SERVER["PLI_NC_WEAPONADD"], payload)
            cls.log("Updated weapon script: " + weapon_name, debug_only=True)
        else: cls.log("Not connected to NPC server")
    
    @classmethod
    def handleFileSave(cls, view):
        if not cls.authenticated: return False
        config_type = view.settings().get('rc_config_type')
        npc_id = view.settings().get('rc_npc_id')
        npc_name = view.settings().get('rc_npc_name')
        class_name = view.settings().get('rc_class_name')
        weapon_name = view.settings().get('rc_weapon_name')
        if not any([config_type, npc_name, class_name, weapon_name]): return False
        content = view.substr(sublime.Region(0, view.size()))
        try:
            if config_type: cls.uploadServerConfig(config_type, content)
            elif npc_name and npc_id is not None: cls.uploadNpcScript(npc_id, npc_name, content)
            elif class_name: cls.uploadClassScript(class_name, content)
            elif weapon_name: cls.uploadWeaponScript(weapon_name, content)
            return True
        except Exception as e:
            cls.log("Upload failed: " + str(e))
            return False
    
    @classmethod
    def listenForData(cls):
        buffer = bytearray()
        while cls.socket_connection:
            try:
                if cls.socket_connection is None: break
                data = cls.socket_connection.recv(1024)
                if not data:
                    cls.log("Connection closed by server")
                    break
                buffer.extend(data)
                while len(buffer) >= 2:
                    packet_length = struct.unpack('>H', buffer[:2])[0]
                    if len(buffer) < packet_length + 2: break
                    packet_data = buffer[2:2 + packet_length]
                    buffer = buffer[2 + packet_length:]
                    cls.processData(packet_data)
            except Exception as e:
                error_str = str(e)
                if not cls.switching_servers:
                    is_socket_error = False
                    if isinstance(e, OSError):
                        if hasattr(e, 'winerror') and e.winerror in [10038, 10053, 10054]:
                            is_socket_error = True
                        elif hasattr(e, 'errno') and e.errno in [10038, 10053, 10054]:
                            is_socket_error = True
                    if 'WinError' in error_str and any(code in error_str for code in ['10038', '10053', '10054']):
                        is_socket_error = True
                    if not is_socket_error:
                        cls.log("Error receiving data: " + error_str)
                break
        if cls.socket_connection:
            try: cls.socket_connection.close()
            except: pass
        cls.socket_connection = None
        cls.connected_server = None
        cls.updateChatViewName()
        cls.authenticated = False
        cls.clearCaches()
        if not cls.switching_servers:
            cls.log("Disconnected from server")
    
    @classmethod
    def listenNcData(cls):
        buffer = bytearray()
        while cls.nc_socket:
            try:
                if cls.nc_socket is None: break
                data = cls.nc_socket.recv(1024)
                if not data:
                    cls.log("NC connection closed by server")
                    break
                buffer.extend(data)
                while len(buffer) >= 2:
                    packet_length = struct.unpack('>H', buffer[:2])[0]
                    if len(buffer) < packet_length + 2: break
                    packet_data = buffer[2:2 + packet_length]
                    buffer = buffer[2 + packet_length:]
                    cls.processNcData(packet_data)
            except Exception as e:
                error_str = str(e)
                if not cls.switching_servers:
                    is_socket_error = False
                    if isinstance(e, OSError):
                        if hasattr(e, 'winerror') and e.winerror in [10038, 10053, 10054]:
                            is_socket_error = True
                        elif hasattr(e, 'errno') and e.errno in [10038, 10053, 10054]:
                            is_socket_error = True
                    if 'WinError' in error_str and any(code in error_str for code in ['10038', '10053', '10054']):
                        is_socket_error = True
                    if not is_socket_error:
                        cls.log("NC Error: " + error_str)
                break
        if cls.nc_socket:
            try: cls.nc_socket.close()
            except: pass
        cls.nc_socket = None
        cls.nc_authenticated = False
        if not cls.switching_servers:
            cls.log("Disconnected from NPC server")
    
    @classmethod
    def processData(cls, buf):
        if cls.protocol and cls.protocol.encryption_key is not None:
            try: buf = cls.protocol.decrypt(buf)
            except Exception as e:
                cls.log("Decryption error: " + str(e), debug_only=True)
                return
        if len(buf) > 2 and buf[0:2] == b'BZ':
            try:
                import bz2
                buf = bz2.decompress(buf)
                cls.log("Decompressed BZIP2 buffer to {} bytes".format(len(buf)), debug_only=True)
            except Exception as e:
                cls.log("BZIP2 decompression failed: {}".format(str(e)), debug_only=True)
        if len(buf) > 0:
            first_packet_id = buf[0] - 32
            cls.log("process_data: {} bytes, first packet ID: {}, raw byte: 0x{:02x}".format(len(buf), first_packet_id, buf[0]), debug_only=True)                
            #if len(payload) > 0 and payload[0] == 0x29: 
            #    payload = payload[1:]
        offset = 0
        while offset < len(buf):
            if buf[offset] == 132:
                if offset + 5 <= len(buf):
                    b0 = (buf[offset + 1] - 32) & 0x7F
                    b1 = (buf[offset + 2] - 32) & 0x7F
                    b2 = (buf[offset + 3] - 32) & 0x7F
                    raw_length = (b0 << 14) + (b1 << 7) + b2
                    if offset + 5 + raw_length <= len(buf):
                        raw_data = buf[offset + 5:offset + 5 + raw_length]
                        offset += 5 + raw_length
                        if len(raw_data) > 1 and raw_data[-1] == 0x0A:
                            raw_data = raw_data[:-1]
                        if len(raw_data) > 0 and raw_data[0] - 32 >= 0:
                            packet_id = raw_data[0] - 32
                            cls.processPacket(packet_id, raw_data[1:])
                        continue
                break
            idx = findTerminator(buf, offset)
            if idx == -1: break
            packet_data = buf[offset:idx]
            offset = idx + 1
            if len(packet_data) > 0:
                packet_id = packet_data[0] - 32
                cls.processPacket(packet_id, packet_data[1:])
    
    @classmethod
    def processNcData(cls, buf):
        try: buf = cls.nc_protocol.decrypt(buf)
        except: return
        offset = 0
        while offset < len(buf):
            idx = findTerminator(buf, offset)
            if idx == -1: break
            packet_data = buf[offset:idx]
            offset = idx + 1
            if len(packet_data) > 0:
                packet_id = packet_data[0] - 32
                packet_name = next((k for k, v in cls.SERVER_TO_NC.items() if v == packet_id), next((k for k, v in cls.SERVER_TO_RC.items() if v == packet_id), "UNKNOWN"))
                hex_data = ' '.join('{:02x}'.format(b) for b in packet_data[1:])
                decoded_data = ""
                if packet_id == cls.SERVER_TO_RC["PLO_SVI_SERVERINFO"] and len(packet_data) > 1:
                    try:
                        decoded_data = packet_data[1:].decode('latin-1', errors='ignore')
                        cls.log("NC pkt {} {} ({} bytes) [{}] {}".format(packet_id, packet_name, len(packet_data[1:]), hex_data, decoded_data), debug_only=True)
                    except:
                        cls.log("NC pkt {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(packet_data[1:]), hex_data), debug_only=True)
                else:
                    cls.log("NC pkt {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(packet_data[1:]), hex_data), debug_only=True)
                if packet_id in [cls.SERVER_TO_RC["PLO_UNKNOWN11"], cls.SERVER_TO_RC["PLO_RC_LOGIN"]]:
                    cls.nc_authenticated = True

                    if packet_id == cls.SERVER_TO_RC["PLO_RC_LOGIN"]:
                        time.sleep(0.3)
                        cls.requestWeaponList()
                elif packet_id == cls.SERVER_TO_RC["PLO_RC_CHAT"]:
                    message = packet_data[1:].decode('latin-1', errors='ignore')
                    message = message.replace(' of +', ' of ')
                    cls.logNc(message)
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_WEAPONLISTGET"]:
                    cls.parseWeaponList(packet_data[1:])
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_CLASSADD"]:
                    if len(packet_data) > 1:
                        class_name = packet_data[1:].decode('latin-1', errors='ignore').rstrip('\n')
                        if class_name and class_name not in cls.class_names:
                            cls.classes.append(class_name)
                            cls.class_names.add(class_name)
                            cls.class_batch_count += 1
                            if cls.class_batch_count == 1 or cls.class_batch_count >= 100:
                                if cls.class_sort_timer:
                                    try:
                                        sublime.cancel_timeout(cls.class_sort_timer)
                                    except:
                                        pass
                                cls.class_sort_timer = sublime.set_timeout(lambda: cls._sortClasses(), 1000)
                                if cls.class_batch_count >= 100:
                                    cls.class_batch_count = 0
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_CLASSDELETE"]:
                    if len(packet_data) > 1:
                        class_name = packet_data[1:].decode('latin-1', errors='ignore').rstrip('\n')
                        if class_name in cls.class_names:
                            cls.classes.remove(class_name)
                            cls.class_names.discard(class_name)
                            cls.log("Class deleted: " + class_name, debug_only=True)
                        if class_name in cls.class_scripts:
                            del cls.class_scripts[class_name]
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_WEAPONGET"]:
                    if cls.pending_weapon_request and len(packet_data) > 1:
                        data = packet_data[1:]
                        name_length = decodeGByte(data[0])
                        image_length = decodeGByte(data[1 + name_length])
                        script_start = 1 + name_length + 1 + image_length
                        encoded_script = data[script_start:]
                        script = ''.join(chr(b) if b != 0xa7 else '\n' for b in encoded_script)
                        cls.weapon_scripts[cls.pending_weapon_request] = script
                        cls.log("Received weapon script: " + cls.pending_weapon_request, debug_only=True)
                        weapon_name = cls.pending_weapon_request
                        callback = cls.pending_weapon_callback
                        cls.pending_weapon_request = None
                        cls.pending_weapon_callback = None
                        if callback:
                            sublime.set_timeout(lambda: callback(weapon_name), 0)
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_NPCATTRIBUTES"]:
                    if cls.pending_npc_props_request is not None and len(packet_data) > 1:
                        npc_id = cls.pending_npc_props_request
                        data = packet_data[1:]
                        comma_text = data.decode('latin-1', errors='ignore')
                        lines = gtokenizeReverse(comma_text).split('\n')
                        npc_level = None
                        npc_x = None
                        npc_y = None
                        for line in lines:
                            if '.level:' in line:
                                npc_level = line.split('.level:')[1].strip()
                            elif '.xprecise:' in line:
                                try: npc_x = float(line.split('.xprecise:')[1].strip())
                                except: pass
                            elif '.yprecise:' in line:
                                try: npc_y = float(line.split('.yprecise:')[1].strip())
                                except: pass
                        for npc in cls.npcs:
                            if npc['id'] == npc_id:
                                if npc_level: npc['level'] = npc_level
                                if npc_x is not None: npc['x'] = npc_x
                                if npc_y is not None: npc['y'] = npc_y
                                cls.log("Updated NPC {} properties: level={}, x={}, y={}".format(npc_id, npc_level, npc_x, npc_y))
                                break
                        cls.pending_npc_props_request = None
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_NPCADD"]:
                    if len(packet_data) >= 4:
                        data = packet_data[1:]
                        npc_id = decodeGInt3(data)
                        if npc_id in cls.npc_ids:
                            continue
                        offset = 3
                        npc_name = None
                        npc_level = None
                        npc_x = None
                        npc_y = None
                        while offset < len(data):
                            if offset >= len(data): break
                            prop_id = data[offset] - 32
                            offset += 1
                            if prop_id == 50:
                                if offset >= len(data): break
                                name_len = data[offset] - 32
                                offset += 1
                                if offset + name_len <= len(data):
                                    npc_name = data[offset:offset + name_len].decode('latin-1', errors='ignore')
                                    offset += name_len
                            elif prop_id == 20:
                                if offset >= len(data): break
                                level_len = data[offset] - 32
                                offset += 1
                                if offset + level_len <= len(data):
                                    npc_level = data[offset:offset + level_len].decode('latin-1', errors='ignore')
                                    offset += level_len
                            elif prop_id == 15:
                                if offset < len(data):
                                    npc_x = ((data[offset] - 32) / 2.0)
                                    offset += 1
                            elif prop_id == 16:
                                if offset < len(data):
                                    npc_y = ((data[offset] - 32) / 2.0)
                                    offset += 1
                            else:
                                if prop_id in [1, 4, 5, 6, 7, 17, 18, 19, 22, 26, 32, 33, 43, 44, 51, 53, 81]:
                                    offset += 1
                                elif prop_id in [2]:
                                    offset += 1
                                elif prop_id in [3, 27, 28, 29]:
                                    offset += 3
                                elif prop_id in [10, 12, 21, 35, 52, 75, 82] + list(range(37, 42)) + list(range(46, 50)) + list(range(54, 75)):
                                    if offset < len(data):
                                        str_len = data[offset] - 32
                                        offset += 1
                                        if str_len > 0 and offset + str_len <= len(data):
                                            offset += str_len
                                        else:
                                            break
                                else:
                                    break
                        if npc_name:
                            npc_data = {'id': npc_id, 'name': npc_name}
                            if npc_level: npc_data['level'] = npc_level
                            if npc_x is not None: npc_data['x'] = npc_x
                            if npc_y is not None: npc_data['y'] = npc_y
                            cls.npcs.append(npc_data)
                            cls.npc_ids.add(npc_id)
                            cls.npc_batch_count += 1
                            if cls.npc_batch_count == 1 or cls.npc_batch_count >= 100:
                                if cls.npc_sort_timer:
                                    try:
                                        sublime.cancel_timeout(cls.npc_sort_timer)
                                    except:
                                        pass
                                cls.npc_sort_timer = sublime.set_timeout(lambda: cls._sortNpcs(), 1000)
                                if cls.npc_batch_count >= 100:
                                    cls.npc_batch_count = 0
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_NPCDELETE"]:
                    if len(packet_data) >= 4:
                        data = packet_data[1:]
                        npc_id = decodeGInt3(data)
                        cls.npcs = [npc for npc in cls.npcs if npc['id'] != npc_id]
                        cls.npc_ids.discard(npc_id)
                        if npc_id in cls.npc_scripts:
                            del cls.npc_scripts[npc_id]
                        cls.log("NPC deleted: ID " + str(npc_id), debug_only=True)
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_CLASSGET"]:
                    if cls.pending_class_request and len(packet_data) > 1:
                        data = packet_data[1:]
                        name_length = decodeGByte(data[0])
                        tokenized_start = 1 + name_length
                        tokenized = data[tokenized_start:].decode('latin-1', errors='ignore')
                        script = gtokenizeReverse(tokenized)
                        cls.class_scripts[cls.pending_class_request] = script
                        cls.log("Received class script: " + cls.pending_class_request, debug_only=True)
                        class_name = cls.pending_class_request
                        callback = cls.pending_class_callback
                        cls.pending_class_request = None
                        cls.pending_class_callback = None
                        if callback:
                            sublime.set_timeout(lambda: callback(class_name), 0)
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_LEVELDUMP"]:
                    if cls.pending_local_npcs_request and len(packet_data) > 1:
                        tokenized = packet_data[1:].decode('latin-1', errors='ignore')
                        text = gtokenizeReverse(tokenized)
                        lines = text.split('\n') if text else []
                        title = "Local NPCs"
                        if cls.pending_local_npcs_request:
                            title += " - " + cls.pending_local_npcs_request
                        cls.openListView("local_npcs", title, lines)
                        cls.pending_local_npcs_request = None
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_NPCSCRIPT"]:
                    if cls.pending_npc_request is not None and len(packet_data) >= 4:
                        data = packet_data[1:]
                        npc_id = decodeGInt3(data)
                        if len(packet_data) > 4:
                            tokenized = data[3:].decode('latin-1', errors='ignore')
                            script = gtokenizeReverse(tokenized)
                        else:
                            script = ""
                        cls.npc_scripts[cls.pending_npc_request] = script
                        cls.log("Received NPC script for ID: " + str(npc_id), debug_only=True)
                        npc_id_received = cls.pending_npc_request
                        callback = cls.pending_npc_callback
                        cls.pending_npc_request = None
                        cls.pending_npc_callback = None
                        if callback:
                            npc_data = next((npc for npc in cls.npcs if npc['id'] == npc_id_received), {'id': npc_id_received, 'name': ''})
                            sublime.set_timeout(lambda: callback(npc_data), 0)
                    elif len(packet_data) > 4:
                        cls.log("Received packet #160 but no pending NPC request", debug_only=True)
                elif packet_id == cls.SERVER_TO_NC["PLO_NC_NPCFLAGS"]:
                    if cls.pending_npc_flags_request is not None and len(packet_data) >= 4:
                        data = packet_data[1:]
                        npc_id = decodeGInt3(data)
                        if len(data) > 3:
                            tokenized = data[3:].decode('latin-1', errors='ignore')
                            flags = gtokenizeReverse(tokenized)
                        else:
                            flags = ""
                        cls.npc_flags[npc_id] = flags
                        cls.log("Received NPC flags for ID: {} ({} bytes)".format(npc_id, len(flags) if flags else 0), debug_only=True)
                        requested_id = npc_id
                        cls.pending_npc_flags_request = None
                        def openFlags():
                            window = sublime.active_window()
                            if window:
                                npc_data = next((npc for npc in cls.npcs if npc['id'] == requested_id), {'id': requested_id, 'name': str(requested_id)})
                                RcShowExplorerCommand(window).editNpcFlags(npc_data, use_cached=True)
                        sublime.set_timeout(openFlags, 0)
                    elif len(packet_data) >= 4:
                        data = packet_data[1:]
                        npc_id = decodeGInt3(data)
                        tokenized = data[3:].decode('latin-1', errors='ignore') if len(data) > 3 else ""
                        cls.npc_flags[npc_id] = gtokenizeReverse(tokenized) if tokenized else ""
                        cls.log("Received packet #161 but no pending NPC flags request", debug_only=True)

    @classmethod
    def processPacket(cls, packet_id, payload):
        hex_preview = ' '.join('{:02x}'.format(b) for b in payload[:20]) if len(payload) > 0 else "(empty)"
        packet_name = next((k for k, v in cls.SERVER_TO_RC.items() if v == packet_id), "UNKNOWN")
        decoded_data = ""
        if packet_id == cls.SERVER_TO_RC["PLO_SVI_SERVERINFO"] and len(payload) > 0:
            try:
                decoded_data = payload.decode('latin-1', errors='ignore')
                cls.log("RECV PKT {} {} ({} bytes) [{}] {}".format(packet_id, packet_name, len(payload), hex_preview, decoded_data), debug_only=True)
            except:
                cls.log("RECV PKT {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(payload), hex_preview), debug_only=True)
        else:
            cls.log("RECV PKT {} {} ({} bytes) [{}]".format(packet_id, packet_name, len(payload), hex_preview), debug_only=True)
        if packet_id == cls.SERVER_TO_RC["PLO_RC_LOGIN"]:
            cls.log("Authentication successful!", debug_only=True)
            cls.authenticated = True
            cls.switching_servers = False
            cls.shown_not_authenticated = False
            cls.sendRcChat("/npc sublimerc_pystyle,5.2.2026")
            if not cls.has_set_nickname: cls.sendSetNickname()
            cls._requestServerList()
        elif packet_id == cls.SERVER_TO_RC["PLO_UNKNOWN190"]:
            cls.log("RC ready", debug_only=True)
            cls.requestBanTypes()
            cls.bootstrapIrcBridge()
        elif packet_id == cls.SERVER_TO_RC["PLO_PLAYERPROPS"] and len(payload) >= 2:
            player_id = ((payload[0] - 32) << 7) + (payload[1] - 32)
            player = next((p for p in cls.players if p.get('id') == player_id), None)
            if player and len(payload) > 2 and payload[2] - 32 == 0:
                nick_len = payload[3] - 32
                if 4 + nick_len <= len(payload):
                    player['nickname'] = payload[4:4 + nick_len].decode('latin-1', errors='ignore')
                    cls.log("{} nickname changed to: {}".format(player.get('account', 'Unknown'), player['nickname']), debug_only=True)
        elif packet_id == cls.SERVER_TO_RC["PLO_TOALL"] and len(payload) >= 3:
            player_id, message_len = ((payload[0] - 32) << 7) + (payload[1] - 32), payload[2] - 32
            if len(payload) >= 3 + message_len:
                message = payload[3:3 + message_len].decode('latin-1', errors='ignore')
                player = next((p for p in cls.players if p.get('id') == player_id), None)
                name = "{} ({})".format(player.get('nickname', 'Unknown'), player.get('account', 'Unknown')) if player else str(player_id)
                cls.logToalls("{}: {}".format(name, message))
        elif packet_id == cls.SERVER_TO_RC["PLO_FILESENDFAILED"]:
            message = payload.decode('latin-1', errors='ignore').strip()
            failed_file = cls.pending_file_download or message or "unknown file"
            cls.file_transfers.pop(failed_file, None)
            if cls.pending_file_download:
                basename = os.path.basename(cls.pending_file_download.replace("\\", "/"))
                cls.file_transfers.pop(basename, None)
            cls.pending_file_download = None
            cls.open_after_download = False
            cls.external_open_requested = False
            cls.logFileBrowser("Download failed: {}".format(failed_file))
            if message and message != failed_file:
                cls.logFileBrowser(message)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_ADMINMESSAGE"]:
            message = payload.decode('latin-1', errors='ignore')
            if message:
                for line in message.replace('\xa7', '\n').splitlines():
                    if line.strip():
                        cls.log(line)
        elif packet_id == cls.SERVER_TO_RC["PLO_EDITION_PACKET"]:
            message = payload.decode('latin-1', errors='ignore')
            cls.log("Disconnect message: " + message)
            cls.disconnect()
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_CHAT"]:
            message = payload.decode('latin-1', errors='ignore')
            message = message.replace(' of +', ' of ')
            if cls.handleRcControlMessage(message):
                pass
            else:
                cls.log(message)
            if cls.pending_account_request and "not authorized" in message.lower():
                cls.pending_account_request = None
        elif packet_id == cls.SERVER_TO_RC["PLO_NC_CONTROL"]:
            hex_data = ' '.join('{:02x}'.format(b) for b in payload[:50])
            cls.log("Packet #78 (echo): {}".format(hex_data))
        elif packet_id == cls.SERVER_TO_RC["PLO_NPCSERVERADDR"]:
            if len(payload) >= 2:
                npc_server_id = ((payload[0] - 32) << 7) + (payload[1] - 32) - 0x1020
                cls.npc_server_address = payload[2:].decode('latin-1', errors='ignore')
                cls.log("NPC Server address received: {}".format(cls.npc_server_address), debug_only=True)
                if not cls.nc_socket and not cls.nc_authenticated:
                    cls.log("Attempting to connect to NPC server...", debug_only=True)
                    cls.connectToNpcServer()
                else:
                    cls.log("Already connected/connecting to NPC server, ignoring duplicate")
            else:
                cls.log("Packet #79 too short: {} bytes".format(len(payload)))
        elif packet_id == cls.SERVER_TO_RC["PLO_SERVERTEXT"]:
            message = payload.decode('latin-1', errors='ignore')
            untokenized = gtokenizeReverse(message)
            parts = untokenized.split('\n')
            if len(parts) >= 3 and parts[0] == "GraalEngine" and parts[1] == "pmserverplayers":
                server_name = parts[2]
                player_data = '\n'.join(parts[3:]) if len(parts) > 3 else ""
                cls.updatePMPlayers(server_name, player_data)
            elif len(parts) >= 3 and parts[0] == "GraalEngine" and parts[1] == "lister" and parts[2] == "simpleserverlist":
                server_data_str = ','.join(parts[3:]) if len(parts) > 3 else ""
                servers = []
                server_entries = re.split(r',(?=(?:[^"]*"[^"]*")*[^"]*$)', server_data_str)
                i = 0
                while i < len(server_entries) - 2:
                    server_name = server_entries[i].strip().strip('"')
                    display_name = server_entries[i + 1].strip().strip('"')
                    try:
                        player_count = int(server_entries[i + 2].strip())
                    except:
                        i += 1
                        continue
                    
                    if not server_name or not display_name:
                        i += 1
                        continue
                    
                    emoji_map = {"P": "🪙", "H": "⏳", "3": "🕶️", "U": "🚧"}
                    display_name_clean = display_name
                    if len(display_name) > 2 and display_name[1] == ' ' and display_name[0] in emoji_map:
                        display_name_clean = display_name[2:]
                        display_name_with_emoji = "{} {}".format(emoji_map[display_name[0]], display_name_clean)
                    else:
                        display_name_with_emoji = "🌍 " + display_name_clean
                    
                    servers.append({
                        "name": display_name_with_emoji,
                        "display_name": display_name_clean,
                        "server_name": server_name,
                        "players": player_count,
                        "type": "lister"
                    })
                    i += 3
                
                if servers:
                    cls.servers = servers
                    cls.log("Received server list from listserver ({} servers)".format(len(servers)), debug_only=True)
                else:
                    cls.log("Received server list from listserver (empty list)", debug_only=True)
            elif len(parts) >= 3 and parts[0] == "GraalEngine" and parts[1] == "lister":
                command = parts[2]
                raw_hex = ' '.join('{:02x}'.format(b) for b in payload)
                cls.log("GraalEngine raw: hex=[{}] tokenized={!r} parts={!r}".format(raw_hex, message, parts), debug_only=True)
                if command == "bantypes":
                    cls.updateBanTypes(parts[3:])
                elif command == "ban" and len(parts) >= 5:
                    cls.handleBanResponse(parts)
                elif command == "staffactivity" and len(parts) >= 4:
                    cls.openListView("staffactivity", "Staff Activity", parts[4:], account=parts[3])
                elif command == "banhistory" and len(parts) >= 4:
                    rows = parts[4:] if len(parts) > 4 else ["No ban history entries returned."]
                    cls.openListView("banhistory", "Ban History", rows, account=parts[3])
                if cls.pending_player_ban_request:
                    cls.log("Pending ban request: {} ({})".format(cls.pending_player_ban_request, cls.pending_player_ban_request_id), debug_only=True)
            elif len(parts) >= 3 and parts[0] == "GraalEngine" and parts[1] == "irc":
                cls.handleIrcResponse(parts)
            elif len(parts) >= 1 and parts[0] == "GraalEngine":
                cls.log("Received GraalEngine response: {}".format(repr(untokenized)), debug_only=True)
        elif packet_id == cls.SERVER_TO_RC["PLO_ADDPLAYER"]:
            if len(payload) >= 2:
                player_id = ((payload[0] - 32) << 7) + (payload[1] - 32)
                offset = 2
                account_len = payload[offset] - 32
                offset += 1
                account = payload[offset:offset + account_len].decode('latin-1', errors='ignore')
                offset += account_len
                player_data = {'id': player_id, 'account': account, 'nickname': '', 'level': '', 'admin': False}
                while offset < len(payload):
                    if offset >= len(payload): break
                    prop_id = payload[offset] - 32
                    offset += 1
                    if prop_id == 0:
                        nick_len = payload[offset] - 32
                        offset += 1
                        if offset + nick_len <= len(payload):
                            try:
                                player_data['nickname'] = payload[offset:offset + nick_len].decode('utf-8', errors='ignore')
                            except:
                                player_data['nickname'] = payload[offset:offset + nick_len].decode('latin-1', errors='ignore')
                            offset += nick_len
                    elif prop_id == 20:
                        level_len = payload[offset] - 32
                        offset += 1
                        if offset + level_len <= len(payload):
                            player_data['level'] = payload[offset:offset + level_len].decode('latin-1', errors='ignore')
                            offset += level_len
                    elif prop_id == 1:
                        admin_val = payload[offset] - 32
                        player_data['admin'] = admin_val > 0
                        offset += 1
                    else: break
                if "(npcserver)" in account:
                    cls.npcserver_player_id = player_id
                    cls.log("Found npcserver with ID: {}".format(player_id), debug_only=True)
                    if not cls.npc_server_address:
                        cls.requestNpcServer()
                if player_id >= 16000:
                    nickname = player_data.get('nickname', '')
                    if account.startswith("irc:"):
                        channel = account[4:]
                        player_data['irc_channel'] = channel
                        player_data['external'] = True
                        cls.external_players[player_id] = player_data
                        cls.openIrcChannel(channel, focus=False)
                    elif "(on " in nickname:
                        server_name = nickname.split("(on ")[1].split(")")[0] if "(on " in nickname else None
                        if server_name:
                            if server_name not in cls.pm_servers:
                                cls.pm_servers.append(server_name)
                                cls.pm_server_players[server_name] = []
                                cls._startPMServerPolling(server_name)
                            player_data['server'] = server_name
                            player_data['external'] = True
                            cls.external_players[player_id] = player_data
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
                                                cmd = RcShowExplorerCommand(window)
                                                cmd.showServerPlayers(server_name)
                                            cls.pending_pm_server_request = None
                                    sublime.set_timeout(show_players, 500)
                existing = [p for p in cls.players if p['id'] == player_id]
                if not existing:
                    cls.players.append(player_data)
                    if player_data.get('server'):
                        for server in cls.servers:
                            if server.get('display_name') == player_data['server'] or server.get('server_name') == player_data['server']:
                                server['players'] = server.get('players', 0) + 1
                                break
                    nickname = player_data.get('nickname', '') or account
                    log_msg = "Player joined: {} ({})".format(nickname, account)
                    if player_id >= 16000 and player_data.get('server') and "(on " not in nickname:
                        log_msg += " (on {})".format(player_data['server'])
                    cls.log(log_msg, debug_only=True)
        elif packet_id == cls.SERVER_TO_RC["PLO_DELPLAYER"]:
            if len(payload) >= 2:
                player_id = ((payload[0] - 32) << 7) + (payload[1] - 32)
                removed = [p for p in cls.players if p['id'] == player_id]
                cls.players = [p for p in cls.players if p['id'] != player_id]
                if removed and removed[0].get('server'):
                    for server in cls.servers:
                        if server.get('display_name') == removed[0]['server'] or server.get('server_name') == removed[0]['server']:
                            server['players'] = max(0, server.get('players', 0) - 1)
                            break
                if player_id >= 16000 and player_id in cls.external_players:
                    del cls.external_players[player_id]
                if removed:
                    log_msg = "Player left: {} ({})".format(removed[0]['nickname'] or removed[0]['account'], removed[0]['account'])
                    if removed[0].get('server'):
                        log_msg += " (on {})".format(removed[0]['server'])
                    cls.log(log_msg, debug_only=True)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_SERVERFLAGSGET"]:   
            if len(payload) >= 2:
                num_flags = (payload[0] - 32) * 128 + (payload[1] - 32)
                offset = 2
                flags = []
                for i in range(num_flags):
                    if offset >= len(payload): break
                    flag_len = payload[offset] - 32
                    offset += 1
                    if offset + flag_len <= len(payload):
                        flag = payload[offset:offset + flag_len].decode('latin-1', errors='ignore')
                        flags.append(flag)
                        offset += flag_len
                cls.server_flags = '\n'.join(flags)
                cls.log("Received {} server flags".format(len(flags)), debug_only=True)
                if hasattr(cls, 'pending_server_flags_request') and cls.pending_server_flags_request:
                    cls.pending_server_flags_request = False
                    def openEditor():
                        window = sublime.active_window()
                        if window:
                            cmd = RcShowExplorerCommand(window)
                            cmd.editConfig("serverflags")
                    sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_SERVEROPTIONSGET"]:
            tokenized = payload.decode('latin-1', errors='ignore')
            cls.server_options = gtokenizeReverse(tokenized)
            cls.log("Received server options", debug_only=True)
            if cls.pending_server_options_request:
                cls.pending_server_options_request = False
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        cmd.editConfig("serveroptions")
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_PLAYERRIGHTSGET"]:
            if cls.pending_player_rights_request and len(payload) > 0:
                offset = 0
                account, offset = readLengthString(payload, offset)
                rights_value, offset = readGInt5(payload, offset)
                ip_range, offset = readLengthString(payload, offset)
                folder_access = ""
                if offset < len(payload):
                    folder_len, offset = readGShort(payload, offset)
                    folder_access = readCommaText(payload, offset, folder_len)
                cls.player_rights[cls.pending_player_rights_request] = {'rights': rights_value, 'ip': ip_range, 'folders': folder_access}
                cls.log("Received rights for: " + cls.pending_player_rights_request, debug_only=True)
                account = cls.pending_player_rights_request
                cls.pending_player_rights_request = None
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        cmd.editPlayerRights({'account': account})
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_PLAYERCOMMENTSGET"]:
            if cls.pending_player_comments_request:
                offset = 0
                account, offset = readLengthString(payload, offset)
                comments = readCommaText(payload, offset)
                cls.player_comments[cls.pending_player_comments_request] = comments
                cls.log("Received comments for: " + cls.pending_player_comments_request, debug_only=True)
                account = cls.pending_player_comments_request
                cls.pending_player_comments_request = None
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        cmd.editPlayerComments({'account': account})
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_PLAYERBANGET"]:
            hex_dump = ' '.join('{:02X}'.format(b) for b in payload)
            cls.log("PLO_RC_PLAYERBANGET (64) raw: {}".format(hex_dump), debug_only=True)
            if cls.pending_player_ban_request:
                ban_data = {}
                try:
                    offset = 0
                    account, offset = readLengthString(payload, offset)
                    ban_data['account'] = account
                    ban_data['computer_id'] = ''
                    for section in ('local', 'global', 'computer', 'global_computer'):
                        b = {}
                        b['active'] = ((payload[offset] - 32) == 1) if offset < len(payload) else False
                        offset += 1 if offset < len(payload) else 0
                        reason_len = max(0, payload[offset] - 32) if offset < len(payload) else 0
                        offset += 1 if offset < len(payload) else 0
                        b['ban_reason'] = payload[offset:min(offset + reason_len, len(payload))].decode('latin-1', errors='ignore')
                        offset = min(offset + reason_len, len(payload))
                        time_len = max(0, payload[offset] - 32) if offset < len(payload) else 0
                        offset += 1 if offset < len(payload) else 0
                        b['time_remaining'] = payload[offset:min(offset + time_len, len(payload))].decode('latin-1', errors='ignore') or '-'
                        offset = min(offset + time_len, len(payload))
                        b['reset_timer'] = ((payload[offset] - 32) == 1) if offset < len(payload) else False
                        offset += 1 if offset < len(payload) else 0
                        upd_len = max(0, payload[offset] - 32) if offset < len(payload) else 0
                        offset += 1 if offset < len(payload) else 0
                        b['reason_for_update'] = payload[offset:min(offset + upd_len, len(payload))].decode('latin-1', errors='ignore')
                        offset = min(offset + upd_len, len(payload))
                        ban_data[section] = b
                except Exception as e:
                    cls.log("Error parsing ban packet 64: {} | raw: {}".format(e, hex_dump))
                    ban_data.setdefault('account', cls.pending_player_ban_request)
                cls.player_bans[cls.pending_player_ban_request] = ban_data
                cls.log("Received ban data for: " + cls.pending_player_ban_request, debug_only=True)
                account = cls.pending_player_ban_request
                cls.pending_player_ban_request = None
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        cmd.editPlayerBan({'account': account, '_open_cached_ban': True})
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_PLAYERPROPSGET"]:
            if cls.pending_player_attrs_request and len(payload) > 4:
                offset = 0
                player_id = ((payload[0] - 32) << 7) + (payload[1] - 32)
                offset += 2
                account_len = payload[offset] - 32
                offset += 1
                account = payload[offset:offset + account_len].decode('latin-1', errors='ignore')
                offset += account_len
                world_len = payload[offset] - 32
                offset += 1
                world = payload[offset:offset + world_len].decode('latin-1', errors='ignore')
                offset += world_len
                props_len = payload[offset] - 32
                offset += 1
                properties = {'account': account, 'world': world}
                props_end = offset + props_len

                while offset < props_end and offset < len(payload):
                    prop_id = payload[offset] - 32
                    if offset + 1 < len(payload):
                        cls.log("prop_id={}, val={}".format(prop_id, payload[offset+1]), debug_only=True)
                    offset += 1
                    if prop_id == 0:
                        nick_len = payload[offset] - 32
                        offset += 1
                        properties['nickname'] = payload[offset:offset + nick_len].decode('latin-1', errors='ignore')
                        offset += nick_len
                    elif prop_id in [1, 4, 5, 6, 7, 17, 18, 19, 22, 26, 32, 33, 43, 44, 50, 51, 81]:
                        properties[prop_id] = payload[offset] - 32
                        offset += 1
                    elif prop_id == 53:
                        body_len = payload[offset] - 32
                        offset += 1
                        if body_len > 0 and offset + body_len <= len(payload):
                            properties['body_image'] = payload[offset:offset + body_len].decode('latin-1', errors='ignore')
                            offset += body_len
                        else:
                            properties['body_image'] = ""
                    elif prop_id in [2, 15, 16]:
                        properties[prop_id] = ((payload[offset] - 32) / 2.0)
                        offset += 1
                    elif prop_id in [3, 27, 28, 29]:
                        b0 = payload[offset] - 32
                        b1 = payload[offset+1] - 32
                        b2 = payload[offset+2] - 32
                        properties[prop_id] = (b0 << 14) + (b1 << 7) + b2
                        offset += 3
                    elif prop_id == 8:
                        power = payload[offset] - 32
                        offset += 1
                        if power >= 10:
                            if offset < len(payload):
                                img_len = payload[offset] - 32
                                offset += 1
                                if img_len > 0 and offset + img_len <= len(payload):
                                    img = payload[offset:offset + img_len].decode('latin-1', errors='ignore')
                                    properties['sword_power'] = power - 30
                                    properties['sword_image'] = img
                                    offset += img_len
                                else:
                                    properties['sword_power'] = power
                                    properties['sword_image'] = ""
                            else:
                                properties['sword_power'] = power
                                properties['sword_image'] = ""
                        elif power != 0:
                            properties['sword_power'] = power
                            properties['sword_image'] = "sword{}.gif".format(power)
                        else:
                            properties['sword_power'] = 0
                            properties['sword_image'] = ""
                    elif prop_id == 9:
                        power = payload[offset] - 32
                        offset += 1
                        if power >= 10:
                            if offset < len(payload):
                                img_len = payload[offset] - 32
                                offset += 1
                                if img_len > 0 and offset + img_len <= len(payload):
                                    img = payload[offset:offset + img_len].decode('latin-1', errors='ignore')
                                    properties['shield_power'] = power - 10
                                    properties['shield_image'] = img
                                    offset += img_len
                                else:
                                    properties['shield_power'] = power - 10
                                    properties['shield_image'] = ""
                            else:
                                properties['shield_power'] = power - 10
                                properties['shield_image'] = ""
                        elif power != 0:
                            properties['shield_power'] = power
                            properties['shield_image'] = "shield{}.gif".format(power)
                        else:
                            properties['shield_power'] = 0
                            properties['shield_image'] = ""
                    elif prop_id == 11:
                        head_len = payload[offset] - 32
                        offset += 1
                        if head_len > 0 and head_len < 100:
                            properties['head_image'] = "head{}.gif".format(head_len)
                        elif head_len >= 100 and offset + (head_len - 100) <= len(payload):
                            properties['head_image'] = payload[offset:offset + (head_len - 100)].decode('latin-1', errors='ignore')
                            offset += head_len - 100
                        else:
                            properties['head_image'] = "head0.gif"
                    elif prop_id == 13:
                        if offset + 5 <= len(payload):
                            properties['colors'] = [payload[offset + i] - 32 for i in range(5)]
                            offset += 5
                    elif prop_id in [10, 12, 20, 21, 35, 52, 75, 82] + list(range(37, 42)) + list(range(46, 50)) + list(range(54, 75)):
                        str_len = payload[offset] - 32
                        offset += 1
                        if str_len > 0 and offset + str_len <= len(payload):
                            properties[prop_id] = payload[offset:offset + str_len].decode('latin-1', errors='ignore')
                            offset += str_len
                        else:
                            properties[prop_id] = ""
                    elif prop_id == 30:
                        if offset + 5 <= len(payload):
                            b0 = (payload[offset] - 32) & 0xFF
                            b1 = (payload[offset+1] - 32) & 0xFF
                            b2 = (payload[offset+2] - 32) & 0xFF
                            b3 = (payload[offset+3] - 32) & 0xFF
                            b4 = (payload[offset+4] - 32) & 0xFF
                            ip_value = (b0 << 28) | (b1 << 21) | (b2 << 14) | (b3 << 7) | b4
                            properties['last_ip'] = "{}.{}.{}.{}".format(ip_value & 0xFF, (ip_value >> 8) & 0xFF, (ip_value >> 16) & 0xFF, (ip_value >> 24) & 0xFF)
                            offset += 5
                    elif prop_id == 36:
                        if offset + 3 <= len(payload):
                            byte1 = payload[offset] - 32
                            byte2 = payload[offset+1] - 32
                            byte3 = payload[offset+2] - 32
                            properties['rating'] = (byte1 << 5) + (byte2 >> 2)
                            properties['rating_dev'] = ((byte2 & 0x03) << 7) + byte3
                            offset += 3
                    elif prop_id == 45:
                        properties[prop_id] = (payload[offset] - 32) - 50
                        offset += 1
                    elif prop_id == 23:
                        if (payload[offset] - 32) > 0:
                            offset += 4
                        else:
                            offset += 1
                    elif prop_id == 24:
                        offset += 3
                    elif prop_id == 25:
                        offset += 2
                    elif prop_id in [31, 76]:
                        offset += 3
                    elif prop_id == 42:
                        offset += 4
                    else:
                        if offset < len(payload):
                            offset += 1

                flags = []
                if offset < len(payload) and offset + 2 <= len(payload):
                    flag_count = ((payload[offset] - 32) << 7) + (payload[offset+1] - 32)
                    offset += 2
                    for i in range(flag_count):
                        if offset >= len(payload): break
                        flag_len = payload[offset] - 32
                        offset += 1
                        if offset + flag_len <= len(payload):
                            flags.append(payload[offset:offset + flag_len].decode('latin-1', errors='ignore'))
                            offset += flag_len

                chests = []
                if offset < len(payload) and offset + 2 <= len(payload):
                    chest_count = ((payload[offset] - 32) << 7) + (payload[offset+1] - 32)
                    offset += 2
                    for i in range(chest_count):
                        if offset >= len(payload): break
                        chest_len = payload[offset] - 32
                        offset += 1
                        if offset + chest_len <= len(payload):
                            chests.append(payload[offset:offset + chest_len].decode('latin-1', errors='ignore'))
                            offset += chest_len

                weapons = []
                if offset < len(payload):
                    weapon_count = payload[offset] - 32
                    offset += 1
                    for i in range(weapon_count):
                        if offset >= len(payload): break
                        weapon_len = payload[offset] - 32
                        offset += 1
                        if offset + weapon_len <= len(payload):
                            weapons.append(payload[offset:offset + weapon_len].decode('latin-1', errors='ignore'))
                            offset += weapon_len

                properties['flags'] = flags
                properties['chests'] = chests
                properties['weapons'] = weapons
                account = cls.pending_player_attrs_request
                cls.player_attributes[account] = properties
                cls.log("Received attributes for: " + account)
                cls.pending_player_attrs_request = None
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        cmd.editPlayerAttributes({'account': account})
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_PROFILE"]:
            if cls.pending_player_profile_request and len(payload) > 0:
                offset = 0
                profile_fields = []
                while offset < len(payload):
                    field_len = payload[offset] - 32
                    offset += 1
                    if offset + field_len <= len(payload):
                        profile_fields.append(payload[offset:offset + field_len].decode('latin-1', errors='ignore'))
                        offset += field_len
                    else: break
                cls.player_profiles[cls.pending_player_profile_request] = profile_fields
                if len(profile_fields) >= 11:
                    cls.log("Received profile fields: Account={}, Real Name={}, Age={}, Sex={}, Country={}, Messenger={}, E-Mail={}, Homepage={}, Fav. Hangout={}, Favourite Quote={}, Online Time={}".format(
                        profile_fields[0] if len(profile_fields) > 0 else "", profile_fields[1] if len(profile_fields) > 1 else "",
                        profile_fields[2] if len(profile_fields) > 2 else "", profile_fields[3] if len(profile_fields) > 3 else "",
                        profile_fields[4] if len(profile_fields) > 4 else "", profile_fields[5] if len(profile_fields) > 5 else "",
                        profile_fields[6] if len(profile_fields) > 6 else "", profile_fields[7] if len(profile_fields) > 7 else "",
                        profile_fields[8] if len(profile_fields) > 8 else "", profile_fields[9] if len(profile_fields) > 9 else "",
                        profile_fields[10] if len(profile_fields) > 10 else ""
                    ), debug_only=True)
                cls.log("Received profile for: " + cls.pending_player_profile_request, debug_only=True)
                account = cls.pending_player_profile_request
                cls.pending_player_profile_request = None
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        player = {'account': account}
                        for p in cls.players:
                            if p.get('account') == account:
                                player = p
                                break
                        cmd.viewPlayerProfile(player)
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_ACCOUNTGET"]:
            if cls.pending_account_request:
                offset = 0
                account_info = {}
                requested_account = cls.pending_account_request
                if offset < len(payload):
                    account_len = payload[offset] - 32
                    offset += 1
                    if offset + account_len <= len(payload):
                        response_account = payload[offset:offset + account_len].decode('latin-1', errors='ignore')
                        account_info['account'] = response_account
                        offset += account_len
                        if response_account.lower() != requested_account.lower():
                            cls.log("Warning: Account response mismatch - requested '{}', got '{}'".format(requested_account, response_account))
                            cls.pending_account_request = None
                            return
                if offset < len(payload):
                    password_len = payload[offset] - 32
                    offset += 1
                    if password_len > 0 and offset + password_len <= len(payload):
                        account_info['password'] = payload[offset:offset + password_len].decode('latin-1', errors='ignore')
                        offset += password_len
                    else:
                        account_info['password'] = ''
                if offset < len(payload):
                    email_len = payload[offset] - 32
                    offset += 1
                    if offset + email_len <= len(payload):
                        account_info['email'] = payload[offset:offset + email_len].decode('latin-1', errors='ignore')
                        offset += email_len
                if offset < len(payload):
                    account_info['banned'] = (payload[offset] - 32) == 1
                    offset += 1
                if offset < len(payload):
                    account_info['guest'] = (payload[offset] - 32) == 1
                    offset += 1
                if offset < len(payload):
                    admin_level_val = payload[offset] - 32
                    account_info['admin_level'] = '' if admin_level_val == 0 else str(admin_level_val)
                    offset += 1
                if offset < len(payload):
                    admin_worlds_len = payload[offset] - 32
                    offset += 1
                    if offset + admin_worlds_len <= len(payload):
                        account_info['admin_worlds'] = payload[offset:offset + admin_worlds_len].decode('latin-1', errors='ignore')
                        offset += admin_worlds_len
                if offset < len(payload):
                    ban_length_len = payload[offset] - 32
                    offset += 1
                    if offset + ban_length_len <= len(payload):
                        ban_length = payload[offset:offset + ban_length_len].decode('latin-1', errors='ignore')
                        offset += ban_length_len
                        if ban_length and ban_length != "0" and ban_length != "Wed Dec 31 18:00:00 1969":
                            try:
                                from datetime import datetime
                                account_info['ban_time'] = int(datetime.strptime(ban_length, '%a %b %d %H:%M:%S %Y').timestamp())
                            except:
                                account_info['ban_time'] = 0
                        else:
                            account_info['ban_time'] = 0
                if offset < len(payload):
                    ban_reason_len = payload[offset] - 32
                    offset += 1
                    if offset + ban_reason_len <= len(payload):
                        ban_reason_tokenized = payload[offset:offset + ban_reason_len].decode('latin-1', errors='ignore')
                        account_info['ban_reason'] = gtokenizeReverse(ban_reason_tokenized)
                cls.player_accounts[cls.pending_account_request] = account_info
                cls.log("Received account data for: " + cls.pending_account_request, debug_only=True)
                account = cls.pending_account_request
                cls.pending_account_request = None
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        cmd.editAccount({'account': account})
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_ACCOUNTLISTGET"]:
            accounts = []
            offset = 0
            while offset < len(payload):
                try:
                    account, offset = readRcLenString(payload, offset)
                except:
                    break
                if account:
                    accounts.append(account)
            accounts.sort(key=lambda name: name.lower())
            cls.account_list = accounts
            cls.log("Received {} accounts".format(len(accounts)), debug_only=True)
            if cls.account_list_callback:
                callback = cls.account_list_callback
                cls.account_list_callback = None
                sublime.set_timeout(callback, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_FOLDERCONFIGGET"]:
            tokenized = payload.decode('latin-1', errors='ignore')
            cls.folder_config = gtokenizeReverse(tokenized)
            cls.log("Received folder config", debug_only=True)
            if cls.pending_folder_config_request:
                cls.pending_folder_config_request = False
                def openEditor():
                    window = sublime.active_window()
                    if window:
                        cmd = RcShowExplorerCommand(window)
                        cmd.editConfig("folderconfig")
                sublime.set_timeout(openEditor, 0)
        elif packet_id == cls.SERVER_TO_RC["PLO_NEWWORLDTIME"]:
            if len(payload) >= 4:
                b0 = (payload[0] - 32) & 0xFF
                b1 = (payload[1] - 32) & 0xFF
                b2 = (payload[2] - 32) & 0xFF
                b3 = (payload[3] - 32) & 0xFF
                world_time = (b0 << 21) | (b1 << 14) | (b2 << 7) | b3
                if not cls.ignore_world_time_debug:
                    cls.log("NEWWORLDTIME: {}".format(world_time), debug_only=True)
        elif packet_id == cls.SERVER_TO_RC["PLO_PRIVATEMESSAGE"]:
            if len(payload) >= 2:
                player_id = ((payload[0] - 32) << 7) + (payload[1] - 32)
                comma_pos = payload.find(ord(','))
                if comma_pos >= 0:
                    message = payload[comma_pos+1:].decode('latin-1', errors='ignore').rstrip(',')
                    sender = None
                    for p in cls.players:
                        if p.get('id') == player_id:
                            sender = p
                            break
                    if sender:
                        nickname = sender.get('nickname') or sender.get('account', 'Unknown')
                        account = sender.get('account', 'Unknown')
                        key = cls.recordPrivateMessage(player_id, nickname, account, message, incoming=True)
                        if not cls.private_messages.get(key, {}).get("last_refreshed_open_view"):
                            cls.logPrivateMessageReceived("{} ({})".format(nickname, account), key)
                    else:
                        key = cls.recordPrivateMessage(player_id, "player {}".format(player_id), "Unknown", message, incoming=True)
                        if not cls.private_messages.get(key, {}).get("last_refreshed_open_view"):
                            cls.logPrivateMessageReceived("player {}".format(player_id), key)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_FILEBROWSER_DIRLIST"]:
            folder_list = readCommaText(payload, 0)
            cls.folders = []
            for line in folder_list.split('\n'):
                if not line.strip(): continue
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    rights = parts[0]
                    pattern = parts[1]
                    cls.folders.append({'name': pattern, 'rights': rights, 'pattern': pattern})
            cls.logFileBrowser("Received {} folders".format(len(cls.folders)))
            if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                cls.log("Calling file_browser_callback", debug_only=True)
                sublime.set_timeout(cls.file_browser_callback, 0)
            else:
                cls.log("No file_browser_callback set (hasattr: {}, callback: {})".format(hasattr(cls, 'file_browser_callback'), getattr(cls, 'file_browser_callback', None)), debug_only=True)
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_FILEBROWSER_DIR"]:
            if len(payload) == 0: return
            if len(payload) == 1 and payload[0] == 0x20: # empty folder
                cls.folder_files = []
                if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                    sublime.set_timeout(cls.file_browser_callback, 0)
                return

            # Decompress if BZIP2
            if payload[:2] == b'Zh':
                import bz2
                payload = bytes([0x42]) + payload
                try:
                    payload = bz2.decompress(payload)
                    cls.log("BZIP2 decompressed to {} bytes".format(len(payload)), debug_only=True)
                except Exception as e:
                    cls.log("BZIP2 decompression failed: {}".format(str(e)), debug_only=True)
                    return
            # Decompress if GZIP
            elif payload[:2] == b'\x1f\x8b':
                try:
                    import gzip
                    payload = gzip.decompress(payload)
                    cls.log("GZIP decompressed to {} bytes".format(len(payload)), debug_only=True)
                except Exception as e:
                    cls.log("GZIP decompression failed: {}".format(str(e)), debug_only=True)
                    return
            # Handle Format.DYNAMIC (encrypted/compressed folder listings)
            else:
                first_byte = (payload[0] - 32) & 0xFF
                if first_byte <= 5:
                    original_payload_after_format = payload[1:]
                    potential_path_len = first_byte
                    is_plain_encoding = False
                    if potential_path_len > 0 and len(original_payload_after_format) >= potential_path_len:
                        potential_path = original_payload_after_format[:potential_path_len]
                        try:
                            path_str = potential_path.decode('latin-1', errors='strict')
                            if all(32 <= b <= 126 for b in potential_path) and ('/' in path_str or path_str.isalnum()):
                                is_plain_encoding = True
                                cls.log("Detected plain encoding (not Format.DYNAMIC): first_byte=0x{:02x} -> path_len={}, path='{}'".format(payload[0], potential_path_len, path_str), debug_only=True)
                        except:
                            pass
                    if is_plain_encoding:
                        format_type = None
                    else:
                        format_type = first_byte
                        cls.log("Format.DYNAMIC detected: type {}".format(format_type), debug_only=True)

                    if format_type is not None and format_type in [1, 3, 5]:
                        if cls.protocol and cls.protocol.encryption_key:
                            best_payload = None
                            best_rotations = None
                            for rotation_count in ([4, 8, 12, 16, 20, 24] if format_type == 5 else [12 if format_type == 1 else 4]):
                                try:
                                    mask = 0x04A80B38
                                    seed = cls.protocol.encryption_key
                                    MASK_ROTATION = 0x08088405
                                    rotations = rotation_count
                                    result = bytearray(original_payload_after_format)
                                    offset = 0
                                    while offset < 4 * rotations and offset < len(result):
                                        mask = (mask * MASK_ROTATION + seed) & 0xFFFFFFFF
                                        index = offset
                                        while index < len(result) and index < offset + 4:
                                            byte_mask = (mask >> (8 * (index % 4))) & 0xFF
                                            result[index] = original_payload_after_format[index] ^ byte_mask
                                            index += 1
                                        offset += 4
                                    test_payload = bytes(result)
                                    if len(test_payload) > 0:
                                        first_byte = test_payload[0]
                                        if first_byte >= 32 and first_byte <= 127:
                                            best_payload = test_payload
                                            best_rotations = rotations
                                            cls.log("Found valid unscrambling with {} rotations (first byte: 0x{:02x})".format(rotations, first_byte), debug_only=True)
                                            break
                                        elif (first_byte == 0x0a or first_byte == 0x0d) and len(test_payload) > 2:
                                            if test_payload[1:3] == b'BZ' or test_payload[1:3] == b'Zh':
                                                best_payload = test_payload
                                                best_rotations = rotations
                                                cls.log("Found newline+BZIP2 payload with {} rotations".format(rotations), debug_only=True)
                                                break
                                        elif (first_byte == 0x0a or first_byte == 0x0d) and best_payload is None:
                                            best_payload = test_payload
                                            best_rotations = rotations
                                            cls.log("Found newline-starting payload with {} rotations, keeping as fallback if no better found".format(rotations), debug_only=True)
                                except Exception as e:
                                    cls.log("Unscrambling with {} rotations failed: {}".format(rotations, str(e)), debug_only=True)
                            if best_payload is not None:
                                payload = best_payload
                                cls.log("Using unscrambled payload with {} rotations".format(best_rotations), debug_only=True)
                            else:
                                mask = 0x04A80B38
                                seed = cls.protocol.encryption_key
                                MASK_ROTATION = 0x08088405
                                rotations = 12 if format_type == 1 else 4
                                result = bytearray(original_payload_after_format)
                                offset = 0
                                while offset < 4 * rotations and offset < len(result):
                                    mask = (mask * MASK_ROTATION + seed) & 0xFFFFFFFF
                                    index = offset
                                    while index < len(result) and index < offset + 4:
                                        byte_mask = (mask >> (8 * (index % 4))) & 0xFF
                                        result[index] = original_payload_after_format[index] ^ byte_mask
                                        index += 1
                                    offset += 4
                                payload = bytes(result)
                                cls.log("Unscrambled with {} rotations (fallback)".format(rotations), debug_only=True)
                        else:
                            cls.log("Cannot unscramble: no encryption key", debug_only=True)

                    if format_type is not None and format_type in [2, 3]:
                        try:
                            payload = zlib.decompress(payload)
                            cls.log("ZLIB decompressed to {} bytes".format(len(payload)), debug_only=True)
                        except Exception as e:
                            cls.log("ZLIB decompression failed: {}".format(str(e)), debug_only=True)
                            return
                    elif format_type is not None and format_type in [4, 5]:
                        try:
                            import bz2
                            if len(payload) > 0 and (payload[0] == 0x0a or payload[0] == 0x0d):
                                temp_payload = payload[1:] if len(payload) > 1 else payload
                                if len(temp_payload) > 0 and (temp_payload[:2] == b'BZ' or temp_payload[:2] == b'Zh'):
                                    payload = bz2.decompress(b'B' + temp_payload if temp_payload[:2] == b'Zh' else temp_payload)
                                    cls.log("BZIP2 decompressed to {} bytes (after skipping newline)".format(len(payload)), debug_only=True)
                                else:
                                    raise Exception("No BZIP2 header after newline")
                            else:
                                payload = bz2.decompress(payload)
                                cls.log("BZIP2 decompressed to {} bytes".format(len(payload)), debug_only=True)
                        except Exception as e:
                            cls.log("BZIP2 decompression failed: {}".format(str(e)), debug_only=True)
                            if len(payload) > 0:
                                cls.log("First byte after unscrambling: {} (hex: 0x{:02x})".format(payload[0], payload[0]), debug_only=True)
                                if payload[0] >= 32 and payload[0] <= 127:
                                    cls.log("Unscrambled data appears valid, attempting to parse without BZIP2", debug_only=True)
                                else:
                                    cls.log("BZIP2 failed and first byte invalid, but continuing to parse in case data format differs for read-only folders", debug_only=True)
                            else:
                                cls.log("Empty payload after unscrambling, skipping", debug_only=True)
                                return

            if len(payload) > 0 and payload[0] == 132:
                b0 = (payload[1] - 32) & 0x7F
                b1 = (payload[2] - 32) & 0x7F
                b2 = (payload[3] - 32) & 0x7F
                length = (b0 << 14) + (b1 << 7) + b2
                payload = payload[5:5 + length]
                if len(payload) > 0 and payload[-1] == 0x0A:
                    payload = payload[:-1]
                cls.log("Unwrapped packet 100, inner packet is {} bytes".format(len(payload)))

            if len(payload) > 0 and payload[0] == 100:
                filename_bytes = payload[1:]
                null_pos = min([p for p in [filename_bytes.find(b'\x00'), filename_bytes.find(b'\n'), filename_bytes.find(b'\r')] if p != -1] + [len(filename_bytes)])
                filename = filename_bytes[:null_pos].decode('latin-1', errors='ignore').strip()
                cls.pending_file_download = filename
                content_offset = 1 + null_pos + 1
                remaining_payload = payload[content_offset:] if content_offset < len(payload) else b''

                if len(remaining_payload) > 1000:
                    if len(remaining_payload) > 0 and remaining_payload[0] == 134:
                        offset = 1
                        offset += 5
                        embed_fname_len = remaining_payload[offset] - 32
                        offset += 1
                        offset += embed_fname_len
                        actual_content = remaining_payload[offset:]
                    else:
                        fname_start = remaining_payload.find(filename.encode('latin-1'))
                        actual_content = remaining_payload[fname_start + len(filename):] if fname_start != -1 else remaining_payload
                    full_path = cls.pending_file_download if cls.pending_file_download else filename
                    cls.file_transfers[full_path] = {'buffer': bytearray(actual_content), 'size': 0, 'received': len(actual_content)}
                    cls.logFileBrowser("Bigfile transfer started: {}".format(filename))
                else:
                    cls.logFileBrowser("Bigfile transfer started: {}".format(filename))
                return

            if len(payload) > 0 and payload[0] == 134: 
                offset = 1
                b0 = (payload[offset] - 32) & 0xFF
                b1 = (payload[offset + 1] - 32) & 0xFF
                b2 = (payload[offset + 2] - 32) & 0xFF
                b3 = (payload[offset + 3] - 32) & 0xFF
                b4 = (payload[offset + 4] - 32) & 0xFF
                modified_timestamp = (b0 << 7) + b1
                modified_timestamp = (modified_timestamp << 7) + b2
                modified_timestamp = (modified_timestamp << 7) + b3
                modified_timestamp = (modified_timestamp << 7) + b4
                offset = 6
                header_filename_len = payload[offset] - 32
                offset += 1
                header_filename = payload[offset:offset + header_filename_len].decode('latin-1', errors='ignore')
                offset += header_filename_len
                file_content = payload[offset:]
                decoded_filename = header_filename.replace('%045', '-').replace('%047', '/')
                just_filename = decoded_filename.split('/')[-1]
                transfer_key = None
                if header_filename in cls.file_transfers:
                    transfer_key = header_filename
                elif just_filename in cls.file_transfers:
                    transfer_key = just_filename
                elif cls.pending_file_download and cls.pending_file_download in cls.file_transfers:
                    transfer_key = cls.pending_file_download

                if transfer_key:
                    cls.file_transfers[transfer_key]['buffer'].extend(file_content)
                    cls.file_transfers[transfer_key]['received'] += len(file_content)
                    received = cls.file_transfers[transfer_key]['received']
                    total = cls.file_transfers[transfer_key]['size']
                    cls.logFileBrowser("Received chunk: {}/{} bytes for {}".format(received, total, header_filename))
                    return

                cls.log("Downloaded: {} ({} bytes, modified={})".format(header_filename, len(payload) - offset, modified_timestamp))
                scripts_folder = getScriptsFolder()
                server_name = getCleanServerName(cls.connected_server['name']) if cls.connected_server else "unknown"
                current_folder = cls.current_folder if hasattr(cls, 'current_folder') and cls.current_folder else ""
                folder_path = current_folder.rstrip('/')
                if folder_path:
                    folder_path = sanitizePath(folder_path)
                modified_dir = os.path.join(scripts_folder, server_name, "modified", folder_path.replace('/', os.sep) if folder_path else "root")
                os.makedirs(modified_dir, exist_ok=True)
                file_path = os.path.join(modified_dir, just_filename)
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                original_dir = os.path.join(scripts_folder, server_name, "original", folder_path.replace('/', os.sep) if folder_path else "root")
                os.makedirs(original_dir, exist_ok=True)
                original_path = os.path.join(original_dir, just_filename)
                os.makedirs(os.path.dirname(original_path), exist_ok=True)

                if not os.path.exists(original_path):
                    with open(original_path, 'wb') as f:
                        f.write(file_content)
                    cls.log("Saved original: {}".format(original_path))

                with open(file_path, 'wb') as f:
                    f.write(file_content)

                cls.logFileBrowser("File saved: {}".format(file_path))
                if cls.pending_file_download and (header_filename == cls.pending_file_download or just_filename == cls.pending_file_download or cls.pending_file_download.endswith('/' + just_filename)):
                    cls.log("Checking if should open: open_after_download={}, external_open_requested={}".format(getattr(cls, 'open_after_download', False), getattr(cls, 'external_open_requested', False)), debug_only=True)
                    cls.pending_file_download = None
                    if hasattr(cls, 'external_open_requested') and cls.external_open_requested:
                        cls.external_open_requested = False
                        cls.logFileBrowser("Attempting to open file externally: {}".format(file_path))
                        try:
                            cls.openLocalFileExternally(file_path)
                            cls.watchExternalFile(file_path, header_filename)
                            cls.logFileBrowser("Opened file externally: {}".format(filename))
                        except Exception as e:
                            cls.logFileBrowser("Failed to open file externally: {}".format(str(e)))
                    elif hasattr(cls, 'open_after_download') and cls.open_after_download:
                        cls.open_after_download = False
                        view = sublime.active_window().open_file(file_path)
                        view.settings().set('rc_downloaded_file', header_filename)
                        if header_filename.lower().endswith('.txt'):
                            view.set_syntax_file("Packages/SublimeRC/gscript.sublime-syntax")
                        cls.logFileBrowser("Opened file for editing: {}".format(file_path))
                return

            oldprotocol_text_format = False
            if payload and len(payload) > 0 and payload[0] == 0x29:
                oldprotocol_text_format = True
                payload = payload[1:]
                cls.log("Detected old protocol text-based folder format", debug_only=True)
            if payload and len(payload) > 0 and (payload[0] == 0x0a or payload[0] == 0x0d):
                cls.log("Payload starts with newline (0x{:02x}), skipping and attempting to parse as text format".format(payload[0]), debug_only=True)
                while len(payload) > 0 and (payload[0] == 0x0a or payload[0] == 0x0d or payload[0] == 0x20):
                    payload = payload[1:]
                if len(payload) > 0 and payload.find(b' =/') != -1:
                    oldprotocol_text_format = True
                    cls.log("Detected text-based folder format after newline skip", debug_only=True)
            cls.log("Folder listing - First byte: {} (hex: 0x{:02x})".format(payload[0] if payload else 'empty', payload[0] if payload else 0), debug_only=True)
            try:
                if oldprotocol_text_format:
                    sep_pos = payload.find(b' =/')
                    if sep_pos == -1:
                        cls.folder_files = []
                        if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                            sublime.set_timeout(cls.file_browser_callback, 0)
                        return
                    folder_path = payload[:sep_pos].decode('latin-1', errors='ignore')
                    cls.current_folder = folder_path
                    cls.log("Folder (text format): {}".format(folder_path), debug_only=True)
                    cls.folder_files = []
                    offset = sep_pos + 3
                    while offset < len(payload):
                        quote_pos = payload.find(b'"', offset)
                        if quote_pos == -1: break
                        filename = payload[offset:quote_pos].decode('latin-1', errors='ignore')
                        offset = quote_pos + 1
                        if offset >= len(payload): break
                        rights_end = offset
                        while rights_end < len(payload) and payload[rights_end] not in [0x22, 0x20]:
                            rights_end += 1
                        if rights_end >= len(payload): break
                        rights = payload[offset:rights_end].decode('latin-1', errors='ignore').rstrip()
                        offset = rights_end
                        while offset < len(payload) and payload[offset] == 0x20:
                            offset += 1
                        if offset >= len(payload): break
                        cls.log("    DEBUG: filename='{}' rights='{}' offset={} next_byte=0x{:02x}".format(filename, rights, offset, payload[offset]), debug_only=True)
                        if offset + 10 > len(payload): break
                        b0,b1,b2,b3,b4 = payload[offset] - 32, payload[offset+1] - 32, payload[offset+2] - 32, payload[offset+3] - 32, payload[offset+4] - 32
                        size_val = (b0 << 7) + b1
                        size_val = (size_val << 7) + b2
                        size_val = (size_val << 7) + b3
                        size_val = (size_val << 7) + b4
                        offset += 5
                        b0,b1,b2,b3,b4 = payload[offset] - 32, payload[offset+1] - 32, payload[offset+2] - 32, payload[offset+3] - 32, payload[offset+4] - 32
                        last_change = (b0 << 7) + b1
                        last_change = (last_change << 7) + b2
                        last_change = (last_change << 7) + b3
                        last_change = (last_change << 7) + b4
                        offset += 5
                        is_directory = rights.startswith('d')
                        cls.folder_files.append({'path': filename, 'rights': rights, 'size': size_val, 'modified': last_change * 1000, 'is_directory': is_directory})
                        cls.log("  {}: {} ({}, {} bytes)".format("Dir" if is_directory else "File", filename, rights, size_val), debug_only=True)
                    cls.log("Folder contains {} items (text format)".format(len(cls.folder_files)), debug_only=True)
                    if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                        sublime.set_timeout(cls.file_browser_callback, 0)
                    return
                if cls.expecting_folder_list:
                    cls.expecting_folder_list = False
                    comma_text = payload.decode('latin-1', errors='ignore')
                    folder_text = gtokenizeReverse(comma_text)
                    lines = folder_text.split('\r\n') if '\r\n' in folder_text else folder_text.split('\n')
                    lines = [line.strip() for line in lines if line.strip()]
                    cls.folders = []
                    for line in lines:
                        parts = line.split(' ', 1)
                        if len(parts) == 2:
                            rights = parts[0]
                            pattern = parts[1]
                            folder_name = pattern.split('/')[0] if '/' in pattern else pattern.split('*')[0]
                            cls.folders.append({'name': folder_name, 'rights': rights, 'pattern': pattern})
                    if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                        sublime.set_timeout(cls.file_browser_callback, 0)
                    return
                offset = 0
                while offset < len(payload) and (payload[offset] == 0x0a or payload[offset] == 0x0d or payload[offset] == 0x20):
                    offset += 1
                if offset >= len(payload):
                    cls.log("Payload only contains whitespace/newlines, skipping", debug_only=True)
                    cls.folder_files = []
                    if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                        sublime.set_timeout(cls.file_browser_callback, 0)
                    return
                folder_path_len = payload[offset] - 32
                offset += 1
                cls.log("Folder path length: {} (from byte: 0x{:02x} at offset {})".format(folder_path_len, payload[offset-1] if offset > 0 else 0, offset-1), debug_only=True)
                if folder_path_len < 0 or folder_path_len > 255:
                    cls.log("Invalid folder path length: {}, attempting to find folder path manually".format(folder_path_len), debug_only=True)
                    sep_pos = payload.find(b' =/')
                    if sep_pos != -1:
                        cls.log("Found ' =/' separator, switching to text format parsing", debug_only=True)
                        folder_path = payload[:sep_pos].decode('latin-1', errors='ignore')
                        cls.current_folder = folder_path
                        cls.log("Folder (text format): {}".format(folder_path), debug_only=True)
                        cls.folder_files = []
                        offset = sep_pos + 3
                        while offset < len(payload):
                            quote_pos = payload.find(b'"', offset)
                            if quote_pos == -1: break
                            filename = payload[offset:quote_pos].decode('latin-1', errors='ignore')
                            offset = quote_pos + 1
                            if offset >= len(payload): break
                            rights_end = offset
                            while rights_end < len(payload) and payload[rights_end] not in [0x22, 0x20]:
                                rights_end += 1
                            if rights_end >= len(payload): break
                            rights = payload[offset:rights_end].decode('latin-1', errors='ignore').rstrip()
                            offset = rights_end
                            while offset < len(payload) and payload[offset] == 0x20:
                                offset += 1
                            if offset >= len(payload): break
                            if offset + 10 > len(payload): break
                            b0,b1,b2,b3,b4 = payload[offset] - 32, payload[offset+1] - 32, payload[offset+2] - 32, payload[offset+3] - 32, payload[offset+4] - 32
                            size_val = (b0 << 7) + b1
                            size_val = (size_val << 7) + b2
                            size_val = (size_val << 7) + b3
                            size_val = (size_val << 7) + b4
                            offset += 5
                            b0,b1,b2,b3,b4 = payload[offset] - 32, payload[offset+1] - 32, payload[offset+2] - 32, payload[offset+3] - 32, payload[offset+4] - 32
                            last_change = (b0 << 7) + b1
                            last_change = (last_change << 7) + b2
                            last_change = (last_change << 7) + b3
                            last_change = (last_change << 7) + b4
                            offset += 5
                            is_directory = rights.startswith('d')
                            cls.folder_files.append({'path': filename, 'rights': rights, 'size': size_val, 'modified': last_change * 1000, 'is_directory': is_directory})
                            cls.log("  {}: {} ({}, {} bytes)".format("Dir" if is_directory else "File", filename, rights, size_val), debug_only=True)
                        cls.log("Folder contains {} items (text format fallback)".format(len(cls.folder_files)), debug_only=True)
                        if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                            sublime.set_timeout(cls.file_browser_callback, 0)
                        return
                    else:
                        cls.log("Cannot determine folder format, skipping", debug_only=True)
                        cls.folder_files = []
                        if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                            sublime.set_timeout(cls.file_browser_callback, 0)
                        return
                folder_path = payload[offset:offset + folder_path_len].decode('latin-1', errors='ignore')
                cls.current_folder = folder_path
                offset += folder_path_len
                cls.log("Folder: {} (len={}, offset now: {})".format(folder_path, folder_path_len, offset), debug_only=True)
                cls.folder_files = []
                while offset < len(payload):
                    if offset + 2 > len(payload): break
                    msg_size = ((payload[offset] - 32) << 7) + (payload[offset + 1] - 32)
                    offset += 2
                    if msg_size <= 0 or offset >= len(payload): break
                    filename_len = payload[offset] - 32
                    filename_len_byte = payload[offset]
                    offset += 1
                    if offset + filename_len > len(payload): break
                    filename_bytes = payload[offset:offset + filename_len]
                    filename = filename_bytes.decode('latin-1', errors='ignore')
                    cls.log("  Filename: '{}' (len={}, len_byte=0x{:02x}, raw bytes: {})".format(filename, filename_len, filename_len_byte, ' '.join('{:02x}'.format(b) for b in filename_bytes[:min(20, len(filename_bytes))])), debug_only=True)
                    offset += filename_len
                    if offset >= len(payload): break
                    rights_len = payload[offset] - 32
                    offset += 1
                    if offset + rights_len > len(payload): break
                    rights = payload[offset:offset + rights_len].decode('latin-1', errors='ignore')
                    offset += rights_len
                    if offset + 10 > len(payload): break
                    # readLong = readInt32 + 1 byte (5 bytes total)
                    # readInt32 = readInt24 + 1, readInt24 = readInt16 + 1, readInt16 = 2 bytes
                    b0 = (payload[offset] - 32) & 0xFF
                    b1 = (payload[offset+1] - 32) & 0xFF
                    b2 = (payload[offset+2] - 32) & 0xFF
                    b3 = (payload[offset+3] - 32) & 0xFF
                    b4 = (payload[offset+4] - 32) & 0xFF
                    size_val = (b0 << 7) + b1
                    size_val = (size_val << 7) + b2
                    size_val = (size_val << 7) + b3
                    size_val = (size_val << 7) + b4
                    offset += 5
                    b0 = (payload[offset] - 32) & 0xFF
                    b1 = (payload[offset+1] - 32) & 0xFF
                    b2 = (payload[offset+2] - 32) & 0xFF
                    b3 = (payload[offset+3] - 32) & 0xFF
                    b4 = (payload[offset+4] - 32) & 0xFF
                    time_val = (b0 << 7) + b1
                    time_val = (time_val << 7) + b2
                    time_val = (time_val << 7) + b3
                    time_val = (time_val << 7) + b4
                    last_change = time_val * 1000
                    offset += 5
                    is_directory = rights.startswith('d')
                    cls.folder_files.append({'path': filename, 'rights': rights, 'size': size_val, 'modified': last_change, 'is_directory': is_directory})
                    cls.log("  {}: {} ({} bytes, {})".format("Dir" if is_directory else "File", filename, size_val, rights), debug_only=True)

                cls.log("Folder contains {} items".format(len(cls.folder_files)), debug_only=True)
                if hasattr(cls, 'file_browser_callback') and cls.file_browser_callback:
                    sublime.set_timeout(cls.file_browser_callback, 0)
            except Exception as e:
                cls.log("Failed to parse folder listing: {}".format(str(e)), debug_only=True)
                import traceback
                cls.log(traceback.format_exc())
        elif packet_id == cls.SERVER_TO_RC["PLO_RC_FILEBROWSER_MESSAGE"]:
            log_message = readCommaText(payload, 0)
            cls.logFileBrowserServerMessage(log_message)
        elif packet_id == cls.SERVER_TO_RC["PLO_LARGEFILESTART"]:
            basename = payload.decode('latin-1', errors='ignore')
            full_path = cls.pending_file_download if cls.pending_file_download else basename
            cls.file_transfers[full_path] = {'buffer': bytearray(), 'size': 0, 'received': 0}
            cls.log("Big file transfer started: {} (full path: {})".format(basename, full_path), debug_only=True)
        elif packet_id == cls.SERVER_TO_RC["PLO_LARGEFILESIZE"]:
            if len(payload) >= 5:
                b0 = (payload[0] - 32) & 0xFF
                b1 = (payload[1] - 32) & 0xFF
                b2 = (payload[2] - 32) & 0xFF
                b3 = (payload[3] - 32) & 0xFF
                b4 = (payload[4] - 32) & 0xFF
                file_size = (b0 << 7) + b1
                file_size = (file_size << 7) + b2
                file_size = (file_size << 7) + b3
                file_size = (file_size << 7) + b4
                for filename in cls.file_transfers:
                    if cls.file_transfers[filename]['size'] == 0:
                        cls.file_transfers[filename]['size'] = file_size
                        cls.log("Big file size: {} bytes".format(file_size), debug_only=True)
                        break
        elif packet_id == cls.SERVER_TO_RC["PLO_FILE"]:
            if len(payload) >= 6:
                b0 = (payload[0] - 32) & 0xFF
                b1 = (payload[1] - 32) & 0xFF
                b2 = (payload[2] - 32) & 0xFF
                b3 = (payload[3] - 32) & 0xFF
                b4 = (payload[4] - 32) & 0xFF
                modified_date = (b0 << 7) + b1
                modified_date = (modified_date << 7) + b2
                modified_date = (modified_date << 7) + b3
                modified_date = (modified_date << 7) + b4
                filename_len = payload[5] - 32
                filename = payload[6:6+filename_len].decode('latin-1', errors='ignore')
                content = payload[6+filename_len:]
                if filename in cls.file_transfers:
                    cls.file_transfers[filename]['buffer'].extend(content)
                    cls.file_transfers[filename]['received'] += len(content)
                    received = cls.file_transfers[filename]['received']
                    total = cls.file_transfers[filename]['size']
                    cls.logFileBrowser("Received chunk: {}/{} bytes for {}".format(received, total, filename))
                else:
                    scripts_folder = getScriptsFolder()
                    server_name = getCleanServerName(cls.connected_server['name']) if cls.connected_server else "unknown"
                    original_dir = os.path.join(scripts_folder, server_name, "original")
                    modified_dir = os.path.join(scripts_folder, server_name, "modified")
                    sanitized_filename = sanitizePath(filename)
                    original_path = os.path.join(original_dir, sanitized_filename.replace('/', os.sep))
                    modified_path = os.path.join(modified_dir, sanitized_filename.replace('/', os.sep))
                    os.makedirs(os.path.dirname(original_path), exist_ok=True)
                    os.makedirs(os.path.dirname(modified_path), exist_ok=True)

                    if not os.path.exists(original_path):
                        with open(original_path, 'wb') as f:
                            f.write(content)
                        os.utime(original_path, (modified_date, modified_date))

                    with open(modified_path, 'wb') as f:
                        f.write(content)
                    os.utime(modified_path, (modified_date, modified_date))
                    cls.logFileBrowser("File downloaded: {}".format(filename))

                    if hasattr(cls, 'external_open_requested') and cls.external_open_requested:
                        cls.external_open_requested = False
                        cls.logFileBrowser("Attempting to open file externally: {}".format(modified_path))
                        try:
                            cls.openLocalFileExternally(modified_path)
                            cls.watchExternalFile(modified_path, filename)
                            cls.logFileBrowser("Opened file externally: {}".format(os.path.basename(modified_path)))
                        except Exception as e:
                            cls.logFileBrowser("Failed to open externally: {}".format(str(e)))
                    elif hasattr(cls, 'open_after_download') and cls.open_after_download:
                        cls.open_after_download = False
                        view = sublime.active_window().open_file(modified_path)
                        view.settings().set('rc_downloaded_file', filename)
        elif packet_id == cls.SERVER_TO_RC["PLO_LARGEFILEEND"]:
            filename = payload.decode('latin-1', errors='ignore').rstrip('\n\x0a')
            cls.logFileBrowser("Bigfile transfer ended: {}".format(filename))

            transfer_key = None
            if cls.pending_file_download and cls.pending_file_download in cls.file_transfers:
                transfer_key = cls.pending_file_download
            elif filename in cls.file_transfers:
                transfer_key = filename

            if transfer_key and cls.file_transfers[transfer_key]['received'] > 0:
                scripts_folder = getScriptsFolder()
                server_name = getCleanServerName(cls.connected_server['name']) if cls.connected_server else "unknown"
                original_dir = os.path.join(scripts_folder, server_name, "original")
                modified_dir = os.path.join(scripts_folder, server_name, "modified")
                original_path = os.path.join(original_dir, transfer_key.replace('/', os.sep))
                modified_path = os.path.join(modified_dir, transfer_key.replace('/', os.sep))
                os.makedirs(os.path.dirname(original_path), exist_ok=True)
                os.makedirs(os.path.dirname(modified_path), exist_ok=True)
                content = bytes(cls.file_transfers[transfer_key]['buffer'])
                modified_date = time.time()

                if not os.path.exists(original_path):
                    with open(original_path, 'wb') as f:
                        f.write(content)
                    os.utime(original_path, (modified_date, modified_date))

                with open(modified_path, 'wb') as f:
                    f.write(content)
                os.utime(modified_path, (modified_date, modified_date))
                cls.logFileBrowser("File saved: {}".format(modified_path))
                if hasattr(cls, 'external_open_requested') and cls.external_open_requested:
                    cls.external_open_requested = False
                    cls.logFileBrowser("Attempting to open file externally: {}".format(modified_path))
                    try:
                        cls.openLocalFileExternally(modified_path)
                        cls.watchExternalFile(modified_path, transfer_key)
                        cls.logFileBrowser("Opened file externally: {}".format(os.path.basename(modified_path)))
                    except Exception as e:
                        cls.logFileBrowser("Failed to open externally: {}".format(str(e)))
                elif hasattr(cls, 'open_after_download') and cls.open_after_download:
                    cls.open_after_download = False
                    view = sublime.active_window().open_file(modified_path)
                    view.settings().set('rc_downloaded_file', transfer_key)
                    cls.logFileBrowser("Opened file for editing: {}".format(modified_path))

                del cls.file_transfers[transfer_key]

            cls.pending_file_download = None
    
    @classmethod
    def sendSetNickname(cls):
        try:
            nickname_payload = " " + get1PlusTextNetString(getSetting("nickname"))
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_PLAYERPROPSSET"], nickname_payload.encode('latin-1'))
            cls.has_set_nickname = True
            cls.log("Set nickname to: " + getSetting("nickname"), debug_only=True)
        except Exception as e: cls.log("Failed to set nickname: " + str(e))
    
    @classmethod
    def sendRcChat(cls, message):
        if not cls.authenticated:
            cls.log("Not connected - cannot send chat")
            return False
        try:
            if message.startswith('/'):
                parts = message.split(' ', 1)
                command = parts[0].lower()
                if command in ['/openacc', '/openaccount']:
                    account = parts[1].strip() if len(parts) > 1 and parts[1].strip() else getSetting("account")
                    cls.requestAccount(account)
                    return True
                elif command == '/openaccess':
                    account = parts[1].strip() if len(parts) > 1 and parts[1].strip() else getSetting("account")
                    if cls.isNewProtocol:
                        cls.requestPlayerBanByAccount(account)
                        return True
                    else:
                        cls.requestPlayerBan(account)
                        return True
                elif command == '/staffactivity':
                    account = parts[1].strip() if len(parts) > 1 and parts[1].strip() else getSetting("account")
                    cls.requestStaffActivity(account)
                    return True
                elif command == '/banhistory':
                    account = parts[1].strip() if len(parts) > 1 and parts[1].strip() else getSetting("account")
                    cls.requestBanHistory(account)
                    return True
                elif command in ('/ircjoin', '/joinirc'):
                    channel = parts[1].strip() if len(parts) > 1 and parts[1].strip() else "#graal"
                    cls.sendIrcText("join", channel)
                    return True
                elif command in ('/ircpart', '/partirc'):
                    channel = parts[1].strip() if len(parts) > 1 and parts[1].strip() else ""
                    if channel:
                        cls.sendIrcText("part", channel)
                    return True
                else:
                    account = parts[1] if len(parts) > 1 else getSetting("account")
                    cmd_map = {'/openrights': 'pending_player_rights_request', '/opencomments': 'pending_player_comments_request', '/open': 'pending_player_attrs_request', '/openprofile': 'pending_player_profile_request'}
                    if command in cmd_map:
                        setattr(cls, cmd_map[command], account)
                    else:
                        npc_command = command[1:].lower()
                        if npc_command in cls.npc_defined_commands:
                            message = "/npc " + message[1:]
            cls.sendPacket(cls.RC_TO_SERVER["PLI_RC_CHAT"], message.encode('latin-1'))
            return True
        except Exception as e:
            cls.log("Failed to send chat: " + str(e))
            return False

    @classmethod
    def _requestServerList(cls):
        if cls.authenticated:
            payload = "GraalEngine\nlister\nsimplelist\nall\n"
            tokenized = gtokenize(payload)
            cls.sendPacket(cls.RC_TO_SERVER["PLI_REQUESTTEXT"], tokenized.encode('latin-1'))
            cls.log("Requested server list from listserver", debug_only=True)

class RcRefreshServersCommand(sublime_plugin.WindowCommand):
    def run(self):
        if hasattr(GPlugin, 'current_listserver_config') and GPlugin.current_listserver_config:
            config = GPlugin.current_listserver_config
        else:
            config = getListserverConfigs()[0]
        sublime.status_message("Refreshing server list from {}...".format(config["name"]))
        threading.Thread(target=lambda: self.fetch(config), daemon=True).start()
    
    def fetch(self, config):
        servers = fetchServerList(config)
        if servers:
            GPlugin.current_listserver_config = config
            for server in servers:
                server['listserver_config'] = config
            GPlugin.servers = servers
            sublime.set_timeout(lambda: sublime.status_message("Fetched {} servers from {}".format(len(servers), config["name"])), 0)
        else: sublime.set_timeout(lambda: sublime.error_message("Failed to refresh server list from {}".format(config["name"])), 0)

class RcConnectServerCommand(sublime_plugin.WindowCommand):
    def run(self):
        listserver_configs = getListserverConfigs()
        if len(listserver_configs) == 1:
            self.fetchServersFromListserver(listserver_configs[0])
        else:
            config_names = [getListserverLabel(config) for config in listserver_configs]
            self.window.show_quick_panel(config_names, lambda index: self.onListserverChosen(index, listserver_configs))
    
    def onListserverChosen(self, index, configs):
        if index == -1: return
        self.fetchServersFromListserver(configs[index])
    
    def fetchServersFromListserver(self, config):
        GPlugin.current_listserver_config = config
        sublime.status_message("Fetching servers from {}...".format(config["name"]))
        threading.Thread(target=lambda: self.fetchAndShowServers(config), daemon=True).start()
    
    def fetchAndShowServers(self, config):
        servers = fetchServerList(config)
        if servers:
            for server in servers:
                server['listserver_config'] = config
            GPlugin.servers = servers
            sorted_servers = sorted(servers, key=lambda x: sortKey(x['name']))
            server_names = ["{} ({}:{}) - {} players".format(s['name'], s['ip'], s['port'], s.get('players', 0)) for s in sorted_servers]
            sublime.set_timeout(lambda: self.window.show_quick_panel(server_names, lambda index: self.onServerChosen(index, sorted_servers)), 0)
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
            err = str(e)
            sublime.set_timeout(lambda e=err: sublime.error_message("Connection error: {}".format(e)), 0)

class SublimeRCServerCommand(sublime_plugin.WindowCommand):
    def run(self, server_index=None):
        if not GPlugin.servers:
            sublime.status_message("Fetching server list...")
            threading.Thread(target=lambda: self.fetchAndConnect(server_index), daemon=True).start()
            return
        if server_index is None:
            server_names = []
            for s in GPlugin.servers:
                if 'ip' in s and 'port' in s:
                    if GPlugin.debug_mode:
                        server_names.append("{} ({}:{}) - {} players".format(s['name'], s['ip'], s['port'], s.get('players', 0)))
                    else:
                        server_names.append("{} - {} players".format(s['name'], s.get('players', 0)))
                else:
                    server_names.append("{} - {} players".format(s['name'], s.get('players', 0)))
            def onDone(index):
                if index >= 0:
                    server = GPlugin.servers[index]
                    if GPlugin.connectToServer(server):
                        sublime.status_message("Connected to " + server['name'])
                        self.window.run_command('rc_show_chat')
                    else: sublime.error_message("Failed to connect to " + server['name'])
            self.window.show_quick_panel(server_names, onDone)
        elif 0 <= server_index < len(GPlugin.servers):
            server = GPlugin.servers[server_index]
            if GPlugin.connectToServer(server):
                sublime.status_message("Connected to " + server['name'])
                self.window.run_command('rc_show_chat')
            else: sublime.error_message("Failed to connect to " + server['name'])
    def fetchAndConnect(self, server_index):
        GPlugin.servers = fetchServerList()
        if GPlugin.servers:
            sublime.set_timeout(lambda: self.run(server_index), 0)
        else:
            sublime.set_timeout(lambda: sublime.error_message("Failed to fetch server list"), 0)

class RcSetCredentialsCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current_account = settings.get("account", "")
        self.window.show_input_panel("Account:", current_account, self.onAccount, None, None)
    def onAccount(self, account):
        if not account:
            sublime.status_message("Credentials update cancelled")
            return
        self.account = account
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current_password = settings.get("password", "")
        self.window.show_input_panel("Password:", current_password, self.onPassword, None, None)
    def onPassword(self, password):
        if not password:
            sublime.status_message("Credentials update cancelled")
            return
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        settings.set("account", self.account)
        settings.set("password", password)
        sublime.save_settings("SublimeRC.sublime-settings")
        sublime.status_message("Credentials updated successfully")

class RcConnectNcCommand(sublime_plugin.WindowCommand):
    def run(self):
        if GPlugin.nc_authenticated:
            sublime.status_message("Already connected to NC server")
        elif GPlugin.npc_server_address:
            GPlugin.connectToNpcServer()
        else:
            GPlugin.requestNpcServer()
            sublime.status_message("Requesting NC server address...")
            
class RcSetNicknameCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current_nickname = settings.get("nickname", "")
        self.window.show_input_panel("Nickname:", current_nickname, self.onNickname, None, None)
    def onNickname(self, nickname):
        if not nickname: return
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        settings.set("nickname", nickname)
        sublime.save_settings("SublimeRC.sublime-settings")
        if GPlugin.authenticated:
            GPlugin.sendSetNickname()
            sublime.status_message("Nickname updated and sent to server")
        else:
            sublime.status_message("Nickname updated (will be sent on next connection)")

class RcSetListserverCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current_host = settings.get("listserver_host", "127.0.0.1")
        self.window.show_input_panel("Host:", current_host, self.onHost, None, None)
    def onHost(self, host):
        if not host: return
        self.host = host
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current_port = str(settings.get("listserver_port", 14922))
        self.window.show_input_panel("Port:", current_port, self.onPort, None, None)
    def onPort(self, port):
        if not port: return
        try:
            port_int = int(port)
            settings = sublime.load_settings("SublimeRC.sublime-settings")
            settings.set("listserver_host", self.host)
            settings.set("listserver_port", port_int)
            sublime.save_settings("SublimeRC.sublime-settings")
            sublime.status_message("Listserver settings updated")
        except ValueError:
            sublime.error_message("Invalid port number")

class RcSetScriptsFolderCommand(sublime_plugin.WindowCommand):
    def run(self):
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        current_folder = settings.get("scripts_folder", "C:\\SublimeRC")
        self.window.show_input_panel("Scripts Folder:", current_folder, self.onFolder, None, None)
    def onFolder(self, folder):
        if not folder: return
        settings = sublime.load_settings("SublimeRC.sublime-settings")
        settings.set("scripts_folder", folder)
        sublime.save_settings("SublimeRC.sublime-settings")
        sublime.status_message("Scripts folder updated")

class RcShowChatCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        GPlugin.ensureChatView(self.window or sublime.active_window(), focus=True)

class RcShowCompilerCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        GPlugin.ensureNcLogView(self.window or sublime.active_window(), focus=True)

class RcShowNcCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        GPlugin.ensureNcLogView(self.window or sublime.active_window(), focus=True)

class RcShowToallsCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        GPlugin.ensureToallsView(self.window or sublime.active_window(), focus=True)

class RcShowTerminalCommand(sublime_plugin.WindowCommand):
    def run(self, **kwargs):
        self.window.run_command("rc_show_chat")

class RcChatInsertCommand(sublime_plugin.TextCommand):
    def run(self, edit, characters):
        self.view.insert(edit, self.view.size(), characters)

class RcNoopCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        pass

class RcOpenPmAtPointCommand(sublime_plugin.TextCommand):
    def run(self, edit, event=None):
        if not self.view.settings().get("rc_chat_view"):
            return
        point = None
        if event and "x" in event and "y" in event:
            try:
                point = self.view.window_to_text((event["x"], event["y"]))
            except Exception:
                point = None
        if point is None:
            point = self.view.sel()[0].begin() if self.view.sel() else 0
        line_region = self.view.line(point)
        line = self.view.substr(line_region)
        match = re.match(r'^(\[[^\]]+\]\s+)([^:]{1,64})(:)\s+.+$', line)
        if not match:
            return
        name_start = line_region.begin() + len(match.group(1))
        name_end = name_start + len(match.group(2))
        if not (name_start <= point <= name_end):
            return
        player = GPlugin.findPlayerByChatName(match.group(2))
        if player:
            GPlugin.openPrivateMessageForPlayer(player)
        else:
            sublime.status_message("No connected RC found for: " + match.group(2))

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

class RcSaveConfigViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        config_type = self.view.settings().get("rc_config_type")
        if not config_type:
            return
        content = self.view.substr(sublime.Region(0, self.view.size()))
        config_file = self.view.settings().get("rc_config_file")
        if config_file:
            os.makedirs(os.path.dirname(config_file), exist_ok=True)
            with open(config_file, "w", encoding="utf-8") as f:
                f.write(content)
        GPlugin.uploadServerConfig(config_type, content)
        if config_type == "serverflags":
            GPlugin.server_flags = None
        elif config_type == "folderconfig":
            GPlugin.folder_config = None
        elif config_type == "serveroptions":
            GPlugin.server_options = None
        self.view.set_scratch(True)
        self.view.set_name(self.view.settings().get("rc_display_name") or self.view.name())
        self.view.run_command("mark_clean")
        sublime.status_message("Uploaded " + config_type)

class RcSaveBackedViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        backing_file = self.view.settings().get("rc_backing_file")
        if not backing_file:
            return
        content = self.view.substr(sublime.Region(0, self.view.size()))
        os.makedirs(os.path.dirname(backing_file), exist_ok=True)
        with open(backing_file, "w", encoding="utf-8") as f:
            f.write(content)
        npc_id = self.view.settings().get("rc_npc_id")
        npc_name = self.view.settings().get("rc_npc_name")
        class_name = self.view.settings().get("rc_class_name")
        weapon_name = self.view.settings().get("rc_weapon_name")
        player_account = self.view.settings().get("rc_player_account")
        player_data_type = self.view.settings().get("rc_player_data_type")
        is_npc_flags = self.view.settings().get("rc_npc_flags", False)
        was_deleted = self.view.settings().get("rc_was_deleted", False)
        if player_account and player_data_type:
            if player_data_type == 'rights':
                rights_value, ip_range, folder_access = GPlugin.textToRights(content)
                GPlugin.uploadPlayerRights(player_account, rights_value, ip_range, folder_access)
                sublime.status_message("Updated rights for: " + player_account)
            elif player_data_type == 'attributes':
                properties = GPlugin.textToAttributes(content)
                GPlugin.uploadPlayerAttributes(player_account, properties)
                sublime.status_message("Updated attributes for: " + player_account)
            elif player_data_type == 'comments':
                GPlugin.uploadPlayerComments(player_account, content)
                sublime.status_message("Updated comments for: " + player_account)
            elif player_data_type == 'account':
                account_data = GPlugin.textToAccount(content)
                GPlugin.uploadAccount(player_account, account_data)
                sublime.status_message("Updated account data for: " + player_account)
            elif player_data_type == 'profile':
                profile_fields = GPlugin.textToProfile(content, player_account)
                GPlugin.uploadPlayerProfile(player_account, profile_fields)
                sublime.status_message("Updated profile for: " + player_account)
            elif player_data_type == 'ban':
                ban_data = GPlugin.textToBan(content)
                original_ban_text = self.view.settings().get('rc_original_ban_text', '')
                original_ban_data = GPlugin.textToBan(original_ban_text) if original_ban_text else None
                GPlugin.uploadPlayerBan(player_account, ban_data, original_ban_data)
                self.view.settings().set('rc_original_ban_text', content)
                sublime.status_message("Updated ban data for: " + player_account)
        elif npc_id is not None and npc_name:
            if is_npc_flags:
                GPlugin.uploadNpcFlags(npc_id, content)
                sublime.status_message("Uploaded NPC flags: " + npc_name)
            else:
                GPlugin.uploadNpcScript(npc_id, npc_name, content)
                sublime.status_message("Uploaded NPC script: " + npc_name)
        elif class_name:
            if not content.strip():
                GPlugin.deleteClassScript(class_name)
                self.view.settings().set("rc_was_deleted", True)
                sublime.status_message("Deleted class script: " + class_name)
            else:
                GPlugin.uploadClassScript(class_name, content)
                self.view.settings().set("rc_was_deleted", False)
                sublime.status_message(("Restored" if was_deleted else "Uploaded") + " class script: " + class_name)
        elif weapon_name:
            if not content.strip():
                GPlugin.deleteWeaponScript(weapon_name)
                self.view.settings().set("rc_was_deleted", True)
                sublime.status_message("Deleted weapon script: " + weapon_name)
            else:
                GPlugin.uploadWeaponScript(weapon_name, content)
                self.view.settings().set("rc_was_deleted", False)
                sublime.status_message(("Restored" if was_deleted else "Uploaded") + " weapon script: " + weapon_name)
        self.view.set_scratch(True)
        self.view.set_name(self.view.settings().get("rc_display_name") or self.view.name())
        self.view.run_command("mark_clean")

class RcSavePlayerViewCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        player_file = self.view.settings().get("rc_player_file")
        player_account = self.view.settings().get("rc_player_account")
        player_data_type = self.view.settings().get("rc_player_data_type")
        if not player_file or not player_account or not player_data_type:
            return
        content = self.view.substr(sublime.Region(0, self.view.size()))
        display_file = self.view.file_name()
        try:
            if display_file:
                os.makedirs(os.path.dirname(display_file), exist_ok=True)
                with open(display_file, "w", encoding="utf-8") as f:
                    f.write(content)
            os.makedirs(os.path.dirname(player_file), exist_ok=True)
            with open(player_file, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            sublime.status_message("Failed to save player file: " + str(e))
            return
        if player_data_type == 'ban':
            ban_data = GPlugin.textToBan(content)
            original_ban_text = self.view.settings().get('rc_original_ban_text', '')
            original_ban_data = GPlugin.textToBan(original_ban_text) if original_ban_text else None
            GPlugin.uploadPlayerBan(player_account, ban_data, original_ban_data)
            self.view.settings().set('rc_original_ban_text', content)
            sublime.status_message("Updated ban data for: " + player_account)
        self.view.set_scratch(True)
        self.view.set_name(self.view.settings().get("rc_display_name") or self.view.name())
        self.view.run_command("mark_clean")

class RcSaveActiveBackedViewCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view:
            return
        if view.settings().get("rc_backing_file"):
            view.run_command("rc_save_backed_view")
        elif view.settings().get("rc_config_type"):
            view.run_command("rc_save_config_view")
        elif view.settings().get("rc_player_file"):
            view.run_command("rc_save_player_view")

class RcSaveAllBackedViewsCommand(sublime_plugin.WindowCommand):
    def run(self):
        for view in self.window.views():
            if not view.is_dirty():
                continue
            if view.settings().get("rc_backing_file"):
                view.run_command("rc_save_backed_view")
            elif view.settings().get("rc_config_type"):
                view.run_command("rc_save_config_view")
            elif view.settings().get("rc_player_file"):
                view.run_command("rc_save_player_view")

class RcChatAppendCommand(sublime_plugin.TextCommand):
    def run(self, edit, characters):
        content = self.view.substr(sublime.Region(0, self.view.size()))
        if content.startswith("> ["):
            self.view.erase(edit, sublime.Region(0, 2))
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

class RcSendCommandCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onDone(text):
            if text:
                GPlugin.sendRcChat(text)
                if not text.startswith('/'):
                    self.window.run_command("rc_show_chat")
        self.window.show_input_panel("RC Command:", "", onDone, None, None)

class RcOpenPmCommand(sublime_plugin.WindowCommand):
    def run(self):
        GPlugin.openNextPrivateMessageThread()

class RcOpenAllPmsCommand(sublime_plugin.WindowCommand):
    def run(self):
        GPlugin.openAllPrivateMessageThreads()

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

class RcReplyPmCommand(sublime_plugin.WindowCommand):
    def run(self):
        view = self.window.active_view()
        if not view:
            return
        player_id = view.settings().get("rc_pm_player_id")
        thread_key = view.settings().get("rc_pm_thread_key")
        label = view.settings().get("rc_pm_label", "PM")
        if player_id is None or not thread_key:
            sublime.error_message("Open a PM thread first.")
            return
        self.player_id = player_id
        self.thread_key = thread_key
        self.label = label
        self.window.show_input_panel("Reply to {}:".format(label), "", self.onMessage, None, None)

    def onMessage(self, message):
        if not message:
            return
        GPlugin.sendPrivateMessage(self.player_id, message)
        thread = GPlugin.private_messages.get(self.thread_key)
        if thread:
            GPlugin.recordPrivateMessage(self.player_id, thread.get("nickname"), thread.get("account"), message, incoming=False)
            GPlugin.openPrivateMessageThread(self.thread_key)
        sublime.status_message("Sent PM reply")

class RcDisconnectCommand(sublime_plugin.WindowCommand):
    def run(self):
        if GPlugin.socket_connection:
            GPlugin.switching_servers = True
            try: GPlugin.socket_connection.close()
            except: pass
            GPlugin.socket_connection = None
            GPlugin.connected_server = None
            GPlugin.updateChatViewName()
            GPlugin.authenticated = False
            GPlugin.clearCaches()
            if GPlugin.nc_socket:
                try: GPlugin.nc_socket.close()
                except: pass
                GPlugin.nc_socket = None
                GPlugin.nc_authenticated = False
            GPlugin.switching_servers = False
            GPlugin.log("Disconnected from server")
            sublime.status_message("Disconnected from server")
        else: sublime.status_message("Not connected to any server")

class SublimeRCNcCommand(sublime_plugin.WindowCommand):
    def run(self):
        if GPlugin.nc_authenticated:
            sublime.status_message("Already connected to NC server")
        elif GPlugin.npc_server_address:
            GPlugin.connectToNpcServer()
        else:
            GPlugin.requestNpcServer()
            sublime.status_message("Requesting NC server address...")

class RcDisconnectNcCommand(sublime_plugin.WindowCommand):
    def run(self):
        if GPlugin.nc_socket:
            try: GPlugin.nc_socket.close()
            except: pass
            GPlugin.nc_socket = None
            GPlugin.nc_authenticated = False
            GPlugin.log("Disconnected from NC server")
            sublime.status_message("Disconnected from NC server")
        else:
            sublime.status_message("Not connected to NC server")

class RcShowExplorerCommand(sublime_plugin.WindowCommand):
    def showNpcs(self):
        if not GPlugin.npcs:
            sublime.error_message("No NPCs available.")
            return
        npc_names = ["{} (ID: {})".format(npc['name'], npc['id']) for npc in GPlugin.npcs]
        def onDone(index):
            if index >= 0:
                npc_data = GPlugin.npcs[index]
                items = ["📝 Edit Script", "⚙️ Edit Flags", "🌀 Warp", "🔄 Reset", "🗑️ Delete"]
                def onChoice(choice_index):
                    if choice_index == 0:
                        self.editNpc(npc_data)
                    elif choice_index == 1:
                        self.editNpcFlags(npc_data)
                    elif choice_index == 2:
                        self.editNpcWarp(npc_data)
                    elif choice_index == 3:
                        if sublime.ok_cancel_dialog("Are you sure?", "Yes"):
                            GPlugin.resetNpc(npc_data['id'], npc_data['name'])
                            sublime.status_message("Reset NPC: {}".format(npc_data['name']))
                    elif choice_index == 4:
                        if sublime.ok_cancel_dialog("Delete NPC {}?".format(npc_data['name']), "Delete"):
                            GPlugin.deleteNpcScript(npc_data['id'], npc_data['name'])
                            sublime.status_message("Deleted NPC: {}".format(npc_data['name']))
                self.window.show_quick_panel(items, onChoice)
        self.window.show_quick_panel(npc_names, onDone)
    
    def showClasses(self):
        if not GPlugin.classes:
            sublime.error_message("No classes available.")
            return
        def onDone(index):
            if index >= 0: self.editClass(GPlugin.classes[index])
        self.window.show_quick_panel(GPlugin.classes, onDone)
    
    def showWeapons(self):
        if not GPlugin.weapons:
            if GPlugin.nc_authenticated:
                GPlugin.requestWeaponList()
            else: 
                sublime.error_message("Not connected to NPC server")
            return
        def onDone(index):
            if index >= 0: self.editWeapon(GPlugin.weapons[index])
        self.window.show_quick_panel(GPlugin.weapons, onDone)
    
    def showPlayers(self):
        rc_players = [p for p in GPlugin.players if not p.get('server') and not p.get('external')]
        if not rc_players:
            sublime.error_message("No RC players online")
            return
        sorted_players = sorted(rc_players, key=lambda x: x['nickname'] or x['account'])
        player_display = []
        for p in sorted_players:
            emoji = "🟠" if not p['level'] else "🟢"
            display = "{} {} ({}) (ID: {})".format(emoji, p['nickname'] or p['account'], p['account'], p['id'])
            display += " [RC]" if not p['level'] else " - {}".format(p['level'])
            player_display.append(display)
        def onDone(index):
            if index >= 0 and index < len(sorted_players):
                self.showPlayerMenu(sorted_players[index])
        self.window.show_quick_panel(player_display, onDone)
    
    def showGlobalChat(self):
        items = []
        if GPlugin.servers:
            sorted_servers = sorted(GPlugin.servers, key=lambda s: (
                0 if s.get('name') in GPlugin.recent_servers else 1,
                -GPlugin.recent_servers.index(s.get('name')) if s.get('name') in GPlugin.recent_servers else 0
            ))
            for server in sorted_servers:
                server_display = "{}".format(server.get('name', server.get('server_name', 'Unknown')))
                if 'players' in server:
                    server_display += " ({} players)".format(server['players'])
                items.append(server_display)
        def onDone(index):
            if index >= 0 and index < len(GPlugin.servers):
                sorted_servers = sorted(GPlugin.servers, key=lambda s: (
                    0 if s.get('name') in GPlugin.recent_servers else 1,
                    -GPlugin.recent_servers.index(s.get('name')) if s.get('name') in GPlugin.recent_servers else 0
                ))
                server = sorted_servers[index]
                server_name = server.get('name')
                if server_name and server_name not in GPlugin.recent_servers:
                    GPlugin.recent_servers.insert(0, server_name)
                    if len(GPlugin.recent_servers) > 10:
                        GPlugin.recent_servers.pop()
                elif server_name:
                    GPlugin.recent_servers.remove(server_name)
                    GPlugin.recent_servers.insert(0, server_name)
                display_name = server.get('display_name') or server.get('name', '')
                if display_name:
                    emoji_prefixes = ["🪙 ", "⏳ ", "🕶️ ", "🚧 ", "🌍 "]
                    for emoji_prefix in emoji_prefixes:
                        if display_name.startswith(emoji_prefix):
                            display_name = display_name[len(emoji_prefix):]
                            break
                if display_name:
                    GPlugin.pending_pm_server_request = server.get('name', display_name)
                    existing_players = [p for p in GPlugin.players if p.get('server') == display_name]
                    if existing_players:
                        self.showServerPlayers(display_name)
                    else:
                        GPlugin.requestPMServerPlayers(display_name)
                        sublime.status_message("Requesting players from {}...".format(server.get('name', display_name)))
        self.window.show_quick_panel(items, onDone)
    
    def showServerPlayers(self, server_name):
        server_players = [p for p in GPlugin.players if p.get('server') == server_name]
        if not server_players:
            GPlugin.requestPMServerPlayers(server_name)
            sublime.status_message("Requesting players from {}...".format(server_name))
            player_display = ["← Back", "(empty)"]
            def onDone(index):
                if index == 0:
                    self.showGlobalChat()
            self.window.show_quick_panel(player_display, onDone)
            return
        sorted_players = sorted(server_players, key=lambda x: x['nickname'] or x['account'])
        player_display = ["← Back"]
        for p in sorted_players:
            emoji = "🟠" if not p['level'] else "🟢"
            display = "{} {} ({}) (ID: {})".format(emoji, p['nickname'] or p['account'], p['account'], p['id'])
            if p.get('external') or p.get('server'):
                if p['level']:
                    display += " - {}".format(p['level'])
            else:
                display += " [RC]" if not p['level'] else " - {}".format(p['level'])
            player_display.append(display)
        def onDone(index):
            if index == 0:
                self.showGlobalChat()
            elif index > 0 and index - 1 < len(sorted_players):
                self.showPlayerMenu(sorted_players[index - 1])
        self.window.show_quick_panel(player_display, onDone)
    
    def addPMServer(self):
        def onDone(server_name):
            if server_name:
                GPlugin.requestPMServerPlayers(server_name)
                sublime.status_message("Added PM server: {}".format(server_name))
        self.window.show_input_panel("Server Name:", "", onDone, None, None)
    
    def removePMServer(self):
        if not GPlugin.pm_servers:
            sublime.error_message("No PM servers configured")
            return
        def onDone(index):
            if index >= 0:
                server_name = GPlugin.pm_servers[index]
                GPlugin.removePMServer(server_name)
                sublime.status_message("Removed PM server: {}".format(server_name))
        self.window.show_quick_panel(GPlugin.pm_servers, onDone)
    
    def showPlayerMenu(self, player):
        items = ["← Back", "🔒 Edit Rights", "⚙️ Edit Attributes", "💬 Edit Comments", "📝 Edit Account", "🚫 Edit Ban", "📜 Ban History", "📊 Staff Activity", "📨 Private Message", "🌀 Warp Player", "📢 Admin Message", "🔄 Reset Player", "❌ Disconnect Player", "🪪 Profile"]
        def onDone(index):
            if index == 0:
                server_name = player.get('server')
                if server_name:
                    self.showServerPlayers(server_name)
                else:
                    self.showPlayers()
            elif index == 1: self.editPlayerRights(player)
            elif index == 2: self.editPlayerAttributes(player)
            elif index == 3: self.editPlayerComments(player)
            elif index == 4: self.editAccount(player)
            elif index == 5: self.editPlayerBan(player)
            elif index == 6: self.showBanHistory(player)
            elif index == 7: self.showStaffActivity(player)
            elif index == 8: self.sendPrivateMessage(player)
            elif index == 9: self.warpPlayer(player)
            elif index == 10: self.sendAdminMessage(player)
            elif index == 11: self.resetPlayer(player)
            elif index == 12: self.disconnectPlayer(player)
            elif index == 13: self.viewPlayerProfile(player)
        self.window.show_quick_panel(items, onDone)
    
    def editPlayerRights(self, player):
        account = player['account']
        GPlugin.log("edit_player_rights: " + player['account'], debug_only=True)
        if account in GPlugin.player_rights:
            data = GPlugin.player_rights[account]
            text = GPlugin.rightsToText(data['rights'], data['ip'], data['folders'])
            self.openPlayerDataEditor(account, "rights", "🔒 Rights - " + account, text)
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player rights.")
                sublime.error_message("Not connected to server.")
            else:
                GPlugin.requestPlayerRights(account)
    
    def editPlayerAttributes(self, player):
        GPlugin.log("CALLED edit_player_attributes for: " + player['account'], debug_only=True)
        account = player['account']
        if account in GPlugin.player_attributes:
            properties = GPlugin.player_attributes[account]
            text = GPlugin.attributesToText(properties)
            self.openPlayerDataEditor(account, "attributes", "⚙ Attributes - " + account, text)
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player attributes.")
                sublime.error_message("Not connected to server.")
            else:
                GPlugin.requestPlayerAttributes(account)
    
    def editPlayerComments(self, player):
        GPlugin.log("CALLED edit_player_comments for: " + player['account'], debug_only=True)
        account = player['account']
        if account in GPlugin.player_comments:
            comments = GPlugin.player_comments[account]
            self.openPlayerDataEditor(account, "comments", "💬 Comments - " + account, comments)
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player comments.")
                sublime.error_message("Not connected to server.")
            else:
                GPlugin.requestPlayerComments(account)
    
    def editAccount(self, player):
        account = player['account'] if isinstance(player, dict) else player
        GPlugin.log("edit_account: " + account, debug_only=True)
        if account in GPlugin.player_accounts:
            account_data = GPlugin.player_accounts[account]
            text = GPlugin.accountToText(account_data)
            self.openPlayerDataEditor(account, "account", "🪪 Account - " + account, text)
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load account data.")
                sublime.error_message("Not connected to server.")
            else:
                GPlugin.requestAccount(account)
    
    def editPlayerBan(self, player):
        account = player['account'] if isinstance(player, dict) else player
        GPlugin.log("edit_player_ban: " + account, debug_only=True)
        open_cached = isinstance(player, dict) and player.get('_open_cached_ban')
        if open_cached and account in GPlugin.player_bans:
            self.openBanEditor(account, GPlugin.player_bans[account])
            return
        if isinstance(player, dict) and GPlugin.isNewProtocol and player.get('id') is not None:
            GPlugin.requestPlayerBanById(account, player.get('id'))
            return
        if not GPlugin.isNewProtocol:
            GPlugin.requestPlayerBanByAccount(account)
            return
        if account in GPlugin.player_bans:
            self.openBanEditor(account, GPlugin.player_bans[account])
        else:
            if not GPlugin.authenticated:
                sublime.error_message("Not connected to server.")
            else:
                GPlugin.requestPlayerBan(account)

    def openBanEditor(self, account, ban_data):
        text = GPlugin.banToText(ban_data)
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.connected_server['name']) if GPlugin.connected_server else "Unknown"
        player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
        os.makedirs(player_dir, exist_ok=True)
        ban_file = os.path.join(player_dir, urlEncodeFilename(account) + "_ban.goption")
        with open(ban_file, 'w', encoding='utf-8') as f:
            f.write(text)

        title = "🚫 Ban - " + account
        self.openBackedEditor(title, text, ban_file, "Packages/SublimeRC/goption.sublime-syntax", {
            'rc_player_account': account,
            'rc_player_data_type': 'ban',
            'rc_original_ban_text': text
        })

    def disconnectPlayer(self, player):
        def onReason(reason):
            if reason:
                GPlugin.disconnectPlayer(player['id'], reason)
                sublime.status_message("Disconnected {}".format(player['account']))
        self.window.show_input_panel("Disconnect Reason:", "", onReason, None, None)
    
    def sendPrivateMessage(self, player):
        def onMessage(message):
            if message:
                GPlugin.sendPrivateMessage(player['id'], message)
                sublime.status_message("Sent PM to {}".format(player['account']))
        self.window.show_input_panel("Private Message to {}:".format(player['nickname'] or player['account']), "", onMessage, None, None)

    def warpPlayer(self, player):
        current_level = player.get('level', 'onlinestartlocal.nw')
        def askLevel(level):
            if not level:
                level = current_level
            self.warp_level = level
            self.window.show_input_panel("X coordinate:", "30", askX, None, None)
        def askX(x):
            try:
                self.warp_x = float(x)
            except:
                self.warp_x = 30.0
            self.window.show_input_panel("Y coordinate:", "30", askY, None, None)
        def askY(y):
            try:
                self.warp_y = float(y)
            except:
                self.warp_y = 30.0
            GPlugin.warpPlayer(player['id'], self.warp_level, self.warp_x, self.warp_y)
            sublime.status_message("Warped {} to {} ({}, {})".format(player['account'], self.warp_level, self.warp_x, self.warp_y))
        self.window.show_input_panel("Level name:", current_level, askLevel, None, None)

    def sendAdminMessage(self, player):
        def onMessage(message):
            if message:
                GPlugin.sendAdminMessage([player['id']], message)
                sublime.status_message("Sent admin message to {}".format(player['account']))
        self.window.show_input_panel("Admin Message to {}:".format(player['nickname'] or player['account']), "", onMessage, None, None)

    def showBanHistory(self, player):
        if GPlugin.requestBanHistory(player['account']):
            sublime.status_message("Requested ban history for {}".format(player['account']))

    def showStaffActivity(self, player):
        if GPlugin.requestStaffActivity(player['account']):
            sublime.status_message("Requested staff activity for {}".format(player['account']))

    def resetPlayer(self, player):
        account = player['account']
        if sublime.ok_cancel_dialog("Reset player attributes for {}?".format(account), "Reset"):
            GPlugin.resetPlayer(account)
            sublime.status_message("Reset player attributes: {}".format(account))

    def viewPlayerProfile(self, player):
        account = player['account']
        if account in GPlugin.player_profiles:
            profile_fields = GPlugin.player_profiles[account]
            profile_text = "Profile for {}\n\n".format(account)
            field_names = ['Account', 'Real Name', 'Age', 'Sex', 'Country', 'Messenger', 'E-Mail', 'Homepage', 'Fav. Hangout', 'Favourite Quote', 'Online Time']
            for i in range(min(len(field_names), len(profile_fields))):
                if i == 10:
                    level = player.get('level', '')
                    profile_text += "Level: {}\n".format(level)
                profile_text += "{}: {}\n".format(field_names[i], profile_fields[i] if i < len(profile_fields) else "")
            if len(profile_fields) > 11:
                profile_text += "\nServer Extras:\n"
                for i in range(11, len(profile_fields)):
                    var = profile_fields[i]
                    if ':=' in var:
                        key, value = var.split(':=', 1)

                        if not value.strip():
                            value = 'none'
                        profile_text += "{}: {}\n".format(key, value)
                    else:
                        profile_text += "{}\n".format(var)
            self.openPlayerDataEditor(account, "profile", "🪪 Profile - " + account, profile_text)
        else:
            if not GPlugin.authenticated:
                GPlugin.log("Not connected to server. Cannot load player profile.")
                sublime.error_message("Not connected to server.")
            else:
                GPlugin.requestPlayerProfile(account)

    def browseFolder(self, folder):
        if folder.endswith('/'):
            subfiles = [folder + "file1.txt", folder + "file2.nw", folder + "subfolder/"]
            self.window.show_quick_panel(subfiles, None)
    
    def editConfig(self, config_type):
        config_map = {
            "serveroptions": GPlugin.server_options,
            "serverflags": GPlugin.server_flags,
            "folderconfig": GPlugin.folder_config
        }
        title_map = {
            "serveroptions": "⚙️ Server Options",
            "serverflags": "🚩 Server Flags",
            "folderconfig": "📁 Folder Config"
        }
        if config_map[config_type] is not None:
            script = config_map[config_type]
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            original_dir = os.path.join(scripts_folder, server_name, "original")
            modified_dir = os.path.join(scripts_folder, server_name, "modified")
            original_file = os.path.join(original_dir, config_type + ".goption")
            modified_file = os.path.join(modified_dir, config_type + ".goption")
            os.makedirs(original_dir, exist_ok=True)
            os.makedirs(modified_dir, exist_ok=True)
            if not os.path.exists(original_file):
                with open(original_file, 'w', encoding='utf-8') as f:
                    f.write(script)
            with open(modified_file, 'w', encoding='utf-8') as f:
                f.write(script)
            display_file = os.path.join(modified_dir, ".tabs", sanitizeDisplayFilename(title_map.get(config_type, config_type)))
            os.makedirs(os.path.dirname(display_file), exist_ok=True)
            with open(display_file, 'w', encoding='utf-8') as f:
                f.write(script)
            view = next((v for v in self.window.views() if v.settings().get("rc_config_type") == config_type), None)
            if not view:
                view = self.window.new_file()
            view.set_scratch(True)
            view.set_name(title_map.get(config_type, config_type))
            view.settings().set("rc_display_name", title_map.get(config_type, config_type))
            view.retarget(display_file)
            view.set_scratch(False)
            view.set_name(title_map.get(config_type, config_type))
            view.assign_syntax("Packages/SublimeRC/goption.sublime-syntax")
            view.settings().set("color_scheme", GOPTION_EDITOR_COLOR_SCHEME)
            view.settings().set('rc_config_type', config_type)
            view.settings().set('rc_config_file', modified_file)
            view.run_command("rc_replace_buffer_content", {"content": script, "read_only": False})
            view.run_command("mark_clean")
            self.window.focus_view(view)
            view.run_command("move_to", {"to": "bof"})
        else:
            if config_type == "serveroptions":
                GPlugin.requestServerOptions()
            elif config_type == "serverflags":
                GPlugin.requestServerFlags()
            elif config_type == "folderconfig":
                GPlugin.requestFolderConfig()

    def openBackedEditor(self, title, content, modified_file, syntax_file, settings):
        view = next((v for v in self.window.views() if v.settings().get("rc_backing_file") == modified_file), None)
        if not view:
            view = self.window.new_file()
            view.set_scratch(True)
        view.set_name(title)
        view.settings().set("rc_display_name", title)
        display_file = os.path.join(os.path.dirname(modified_file), ".tabs", sanitizeDisplayFilename(title))
        os.makedirs(os.path.dirname(display_file), exist_ok=True)
        with open(display_file, "w", encoding="utf-8") as f:
            f.write(content)
        view.retarget(display_file)
        view.set_scratch(False)
        view.set_name(title)
        view.assign_syntax(syntax_file)
        if syntax_file.endswith("gscript.sublime-syntax"):
            view.settings().set("color_scheme", GSCRIPT_EDITOR_COLOR_SCHEME)
        elif syntax_file.endswith("goption.sublime-syntax"):
            view.settings().set("color_scheme", GOPTION_EDITOR_COLOR_SCHEME)
        else:
            view.settings().erase("color_scheme")
        view.settings().set("rc_backing_file", modified_file)
        for key, value in settings.items():
            view.settings().set(key, value)
        view.run_command("rc_replace_buffer_content", {"content": content, "read_only": False})
        view.run_command("mark_clean")
        self.window.focus_view(view)
        view.run_command("move_to", {"to": "bof"})

    def openPlayerDataEditor(self, account, data_type, title, content, extension="goption", settings=None):
        scripts_folder = getScriptsFolder()
        server_name = getCleanServerName(GPlugin.connected_server['name']) if GPlugin.connected_server else "Unknown"
        player_dir = os.path.join(scripts_folder, server_name, "modified", "players")
        original_dir = os.path.join(scripts_folder, server_name, "original", "players")
        os.makedirs(player_dir, exist_ok=True)
        os.makedirs(original_dir, exist_ok=True)
        filename = "{}_{}.{}".format(urlEncodeFilename(account), data_type, extension)
        modified_file = os.path.join(player_dir, filename)
        original_file = os.path.join(original_dir, filename)
        if not os.path.exists(original_file):
            with open(original_file, "w", encoding="utf-8") as f:
                f.write(content)
        with open(modified_file, "w", encoding="utf-8") as f:
            f.write(content)
        view_settings = {
            "rc_player_account": account,
            "rc_player_data_type": data_type
        }
        if settings:
            view_settings.update(settings)
        self.openBackedEditor(title, content, modified_file, "Packages/SublimeRC/goption.sublime-syntax", view_settings)
    
    def editNpc(self, npc_data):
        npc_id = npc_data['id']
        npc_name = npc_data['name']
        if npc_id in GPlugin.npc_scripts:
            script = GPlugin.npc_scripts[npc_id]
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            encoded_name = urlEncodeFilename(npc_name)
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
            self.openBackedEditor("🤖 NPC - " + npc_name, script, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                "rc_npc_id": npc_id,
                "rc_npc_name": npc_name,
                "rc_original_content": script
            })
        else:
            if not GPlugin.nc_authenticated:
                GPlugin.log("Not connected to NPC server. Cannot load NPC script.")
                sublime.error_message("Not connected to NPC server.")
            else:
                def openEditor(npc):
                    script = GPlugin.npc_scripts.get(npc['id'], "")
                    scripts_folder = getScriptsFolder()
                    if GPlugin.connected_server:
                        server_name = getCleanServerName(GPlugin.connected_server['name'])
                    else:
                        server_name = "Unknown"
                    encoded_name = urlEncodeFilename(npc['name'])
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
                    self.openBackedEditor("🤖 NPC - " + npc['name'], script, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                        "rc_npc_id": npc['id'],
                        "rc_npc_name": npc['name'],
                        "rc_original_content": script,
                        "rc_was_deleted": False
                    })
                GPlugin.requestNpcScript(npc_id, openEditor)

    def editNpcFlags(self, npc_data, use_cached=False):
        npc_id = npc_data['id']
        npc_name = npc_data['name']
        if use_cached and npc_id in GPlugin.npc_flags:
            flags = GPlugin.npc_flags[npc_id]
            scripts_folder = getScriptsFolder()
            if GPlugin.connected_server:
                server_name = getCleanServerName(GPlugin.connected_server['name'])
            else:
                server_name = "Unknown"
            encoded_name = urlEncodeFilename(npc_name)
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
            self.openBackedEditor("🚩 NPC Flags - " + npc_name, flags, modified_file, "Packages/SublimeRC/goption.sublime-syntax", {
                "rc_npc_id": npc_id,
                "rc_npc_name": npc_name,
                "rc_npc_flags": True
            })
        else:
            if not GPlugin.nc_authenticated:
                GPlugin.log("Not connected to NPC server. Cannot load NPC flags.")
                sublime.error_message("Not connected to NPC server.")
            else:
                GPlugin.requestNpcFlags(npc_id)

    def editNpcWarp(self, npc_data):
        npc_id = npc_data['id']
        npc_name = npc_data['name']
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server.")
            return
        updated_npc = next((npc for npc in GPlugin.npcs if npc['id'] == npc_id), npc_data)
        current_level = updated_npc.get('level', '')
        current_x = str(updated_npc.get('x', '')) if updated_npc.get('x') is not None else ''
        current_y = str(updated_npc.get('y', '')) if updated_npc.get('y') is not None else ''
        if not current_level:
            GPlugin.requestNpcProps(npc_id)
            sublime.set_timeout(lambda: self.editNpcWarp(npc_data), 1000)
            return
        def askLevel(level):
            if not level: level = current_level
            self.warp_level = level
            self.window.show_input_panel("X coordinate:", current_x if current_x else "30", askX, None, None)
        def askX(x):
            try: self.warp_x = float(x) if x else 30.0
            except: self.warp_x = 30.0
            self.window.show_input_panel("Y coordinate:", current_y if current_y else "30", askY, None, None)
        def askY(y):
            try: self.warp_y = float(y) if y else 30.0
            except: self.warp_y = 30.0
            GPlugin.warpNpc(npc_id, self.warp_level, self.warp_x, self.warp_y)
            sublime.status_message("Warped {} to {} ({}, {})".format(npc_name, self.warp_level, self.warp_x, self.warp_y))
        self.window.show_input_panel("Level name:", current_level, askLevel, None, None)

    def editClass(self, class_name):
        if class_name in GPlugin.class_scripts:
            script = GPlugin.class_scripts[class_name]
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
            if not os.path.exists(original_file):
                with open(original_file, 'w', encoding='utf-8') as f:
                    f.write(script)
            with open(modified_file, 'w', encoding='utf-8') as f:
                f.write(script)
            self.openBackedEditor("🧩 Class - " + class_name, script, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                "rc_class_name": class_name,
                "rc_original_content": script,
                "rc_was_deleted": False
            })
        else:
            if not GPlugin.nc_authenticated:
                GPlugin.log("Not connected to NPC server. Cannot load class script.")
                sublime.error_message("Not connected to NPC server.")
            else:
                def openEditor(name):
                    script = GPlugin.class_scripts.get(name, "")
                    scripts_folder = getScriptsFolder()
                    if GPlugin.connected_server:
                        server_name = getCleanServerName(GPlugin.connected_server['name'])
                    else:
                        server_name = "Unknown"
                    encoded_name = urlEncodeFilename(name)
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
                    self.openBackedEditor("🧩 Class - " + name, script, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                        "rc_class_name": name,
                        "rc_original_content": script,
                        "rc_was_deleted": False
                    })
                GPlugin.requestClassScript(class_name, openEditor)

    def editWeapon(self, weapon_name):
        if weapon_name in GPlugin.weapon_scripts:
            script = GPlugin.weapon_scripts[weapon_name]
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
            if not os.path.exists(original_file):
                with open(original_file, 'w', encoding='utf-8') as f:
                    f.write(script)
            with open(modified_file, 'w', encoding='utf-8') as f:
                f.write(script)
            self.openBackedEditor("🗡 Weapon - " + weapon_name, script, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                "rc_weapon_name": weapon_name,
                "rc_original_content": script,
                "rc_was_deleted": False
            })
        else:
            if not GPlugin.nc_authenticated:
                GPlugin.log("Not connected to NPC server. Cannot load weapon script.")
                sublime.error_message("Not connected to NPC server.")
            else:
                def openEditor(name):
                    script = GPlugin.weapon_scripts.get(name, "")
                    scripts_folder = getScriptsFolder()
                    if GPlugin.connected_server:
                        server_name = getCleanServerName(GPlugin.connected_server['name'])
                    else:
                        server_name = "Unknown"
                    encoded_name = urlEncodeFilename(name)
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
                    self.openBackedEditor("🗡 Weapon - " + name, script, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                        "rc_weapon_name": name,
                        "rc_original_content": script,
                        "rc_was_deleted": False
                    })
                GPlugin.requestWeaponScript(weapon_name, openEditor)

class RcViewNpcAttributesCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).showNpcs()

class RcNewNpcCommand(sublime_plugin.WindowCommand):
    def run(self):
        def onDone(npc_name):
            if npc_name:
                view = self.window.new_file()
                view.set_name(npc_name + ".gscript")
                template = "function onCreated() {\n    setImg(\"npc1.png\");\n    setString(\"" + npc_name + "\");\n}\n"
                view.run_command('insert', {'characters': template})
                view.set_syntax_file("Packages/SublimeRC/gscript.sublime-syntax")
                view.settings().set('rc_npc_name', npc_name)
        self.window.show_input_panel("New NPC Name:", "", onDone, None, None)

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
            RcShowExplorerCommand(self.window).openBackedEditor("🗡 Weapon - " + weapon_name, template, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                "rc_weapon_name": weapon_name,
                "rc_original_content": template,
                "rc_was_deleted": False
            })
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
            RcShowExplorerCommand(self.window).openBackedEditor("🧩 Class - " + class_name, template, modified_file, "Packages/SublimeRC/gscript.sublime-syntax", {
                "rc_class_name": class_name,
                "rc_original_content": template,
                "rc_was_deleted": False
            })
            sublime.status_message("Created new class: " + class_name)
        self.window.show_input_panel("New Class Name:", "", onDone, None, None)

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
                RcShowExplorerCommand(self.window).editAccount({'account': account})
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
        data = {'admin_level': '0', 'admin_worlds': 'all', 'banned': False, 'guest': False, 'ban_reason': ''}
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
            self.window.show_input_panel("Banned? (0/1):", "0", askGuest, None, None)
        def askGuest(banned):
            data['banned'] = str(banned).strip().lower() in ('1', 'true', 'yes', 'y')
            self.window.show_input_panel("Guest? (0/1):", "0", askBanReason, None, None)
        def askBanReason(guest):
            data['guest'] = str(guest).strip().lower() in ('1', 'true', 'yes', 'y')
            self.window.show_input_panel("Ban reason/comments:", "", finish, None, None)
        def finish(ban_reason):
            data['ban_reason'] = ban_reason
            if GPlugin.addAccount(data):
                sublime.status_message("Added account: " + data['account'])
            else:
                sublime.error_message("Failed to add account")
        self.window.show_input_panel("Account name:", "", askPassword, None, None)

class RcCreateNpcOnServerCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.nc_authenticated:
            sublime.error_message("Not connected to NPC server. Use 'RC: Connect to NC' first.")
            return
        self.npc_data = {}
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
            fields = [
                self.npc_data["name"],
                str(self.npc_data["id"]),
                self.npc_data["type"],
                self.npc_data["scripter"],
                self.npc_data["level"],
                str(self.npc_data["x"]),
                str(self.npc_data["y"])
            ]
            GPlugin.log("Creating NPC: {}".format(",".join(fields)), debug_only=True)
            payload = gtokenize("\n".join(fields)).encode("latin-1")
            GPlugin.sendNcPacket(GPlugin.NC_TO_SERVER["PLI_NC_NPCADD"], payload)
            sublime.status_message("Created NPC: {} (ID: {})".format(self.npc_data['name'], self.npc_data['id']))
            npc_data = {'id': self.npc_data['id'], 'name': self.npc_data['name']}
            sublime.set_timeout(lambda: RcShowExplorerCommand(self.window).editNpc(npc_data), 1000)
        self.window.show_input_panel("NPC Name:", "", askName, None, None)

class RcShowPlayersCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).showPlayers()

class RcShowNpcsCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).showNpcs()

class RcLocalNpcsCommand(sublime_plugin.WindowCommand):
    def run(self):
        self.window.show_input_panel("Local NPCs:", "", self.onDone, None, None)

    def onDone(self, text):
        if GPlugin.requestLocalNpcs(text):
            sublime.status_message("Requested local NPCs")

class RcShowClassesCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).showClasses()

class RcShowWeaponsCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).showWeapons()

class RcShowGlobalChatCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).showGlobalChat()

class RcEditServerOptionsCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).editConfig("serveroptions")

class RcEditServerFlagsCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).editConfig("serverflags")

class RcEditFolderConfigCommand(sublime_plugin.WindowCommand):
    def run(self):
        RcShowExplorerCommand(self.window).editConfig("folderconfig")

class RcUploadFileCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if not GPlugin.current_folder:
            sublime.error_message("Open a File Browser folder before uploading.")
            return
        self.pickFiles()

    def pickFiles(self):
        try:
            sublime.open_dialog(self.onFilesSelected, [], None, True)
        except TypeError:
            try:
                sublime.open_dialog(self.onFileSelected)
            except Exception:
                self.window.show_input_panel("Local file path:", "", self.onPathEntered, None, None)
        except Exception:
            self.window.show_input_panel("Local file path:", "", self.onPathEntered, None, None)

    def onFileSelected(self, local_path):
        if local_path:
            GPlugin.uploadLocalFile(local_path)

    def onFilesSelected(self, local_paths):
        if not local_paths:
            return
        if isinstance(local_paths, str):
            local_paths = [local_paths]
        for local_path in local_paths:
            GPlugin.uploadLocalFile(local_path)

    def onPathEntered(self, local_path):
        if local_path:
            GPlugin.uploadLocalFile(local_path.strip().strip('"'))

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
            else:
                if GPlugin.folder_files:
                    GPlugin.log("No folder list from server, showing current directory files")
                    sublime.set_timeout(lambda: self.showFiles(), 100)
                else:
                    pass
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
            GPlugin.logFileBrowser("Requesting folder: {} (from pattern: {})".format(folder_path, selected['pattern']))
            GPlugin.requestFolder(folder_path)
            GPlugin.current_folder = folder_path
            sublime.set_timeout(lambda: self.showFiles(), 2000)

    def showFiles(self):
        GPlugin.log("folder_files count: {}".format(len(GPlugin.folder_files)), debug_only=True)
        if not GPlugin.folder_files:
            file_items = ["(empty)", "← Back to folders", "↻ Refresh"]
            def onEmptySelected(index):
                if index == 1:
                    sublime.set_timeout(lambda: self.showFolders(), 100)
                elif index == 2:
                    GPlugin.requestFolder(GPlugin.current_folder)
                    sublime.set_timeout(lambda: self.showFiles(), 1000)
            self.window.show_quick_panel(file_items, onEmptySelected)
            return
        directories = [f for f in GPlugin.folder_files if f.get('is_directory', False)]
        files = [f for f in GPlugin.folder_files if not f.get('is_directory', False)]
        file_items = ["📁 " + d['path'] for d in directories]
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
        self.selected_file = file_path
        options = ["📂 Open", "🔗 Open External", "⬇️ Download", "🗑️ Delete", "✏️ Rename", "← Back"]
        self.window.show_quick_panel(options, self.onActionSelected)

    def onActionSelected(self, index):
        if index == -1 or index == 5:
            sublime.set_timeout(lambda: self.showFiles(), 100)
            return
        if index == 0:
            GPlugin.openFileForEditing(self.selected_file)
        elif index == 1:
            GPlugin.openFileExternally(self.selected_file)
            return
        elif index == 2:
            GPlugin.downloadFile(self.selected_file)
        elif index == 3:
            if sublime.ok_cancel_dialog("Delete " + self.selected_file + "?", "Delete"):
                GPlugin.deleteFile(self.selected_file)
                sublime.set_timeout(lambda: self.showFiles(), 1000)
        elif index == 4:
            self.window.show_input_panel("New filename:", self.selected_file, self.onRename, None, None)

    def onRename(self, new_name):
        GPlugin.renameFile(self.selected_file, new_name)
        sublime.set_timeout(lambda: self.showFiles(), 1000)

class RcAdminMessageAllCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        self.window.show_input_panel("Admin Message to All Players:", "", self.onMessage, None, None)

    def onMessage(self, message):
        if message:
            GPlugin.sendAdminMessageAll(message)
            sublime.status_message("Sent admin message to all players")

class RcToallMessageCommand(sublime_plugin.WindowCommand):
    def run(self):
        GPlugin.ensureToallsView(self.window or sublime.active_window(), focus=True)

    def onMessage(self, message):
        if message:
            GPlugin.sendToallMessage(message)
            sublime.status_message("Sent to all message")

class RcMassPmCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        if not GPlugin.players:
            sublime.error_message("No players online")
            return
        self.window.show_input_panel("Mass PM to All Players:", "", self.onMessage, None, None)

    def onMessage(self, message):
        if message:
            player_ids = [p['id'] for p in GPlugin.players if p.get('id') is not None]
            GPlugin.sendMassPm(player_ids, message)
            sublime.status_message("Sent mass PM to {} players".format(len(player_ids)))

class RcOpenProfileCommand(sublime_plugin.WindowCommand):
    def run(self):
        if not GPlugin.authenticated:
            sublime.error_message("Not connected to server")
            return
        self.window.show_input_panel("Account Name:", "", self.onAccount, None, None)

    def onAccount(self, account):
        if not account: return
        player = None
        for p in GPlugin.players:
            if p.get('account', '').lower() == account.lower():
                player = p
                break
        if not player:
            player = {'account': account, 'nickname': account, 'level': '', 'id': 0}
        GPlugin.requestPlayerProfile(account)
        sublime.set_timeout(lambda: RcShowExplorerCommand(self.window).viewPlayerProfile(player), 500)

class RCScriptSaveListener(sublime_plugin.EventListener):
    def restore_display_name(self, view):
        display_name = view.settings().get("rc_display_name")
        if display_name:
            view.set_name(display_name)

    def is_chat_like_view(self, view):
        return view.settings().get("rc_chat_view") or view.settings().get("rc_pm_view") or view.settings().get("rc_irc_view") or view.settings().get("rc_file_browser_log_view") or view.settings().get("rc_toalls_view")

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

    def on_selection_modified(self, view):
        if view.settings().get("rc_chat_view") or view.settings().get("rc_file_browser_log_view"):
            if not view.sel():
                return
            point = view.sel()[0].begin()
            if view.settings().get("rc_chat_view"):
                links = GPlugin.pm_chat_links.get(view.id(), [])
                for start, end, key in links:
                    if start <= point <= end:
                        GPlugin.openPrivateMessageThread(key)
                        return
            links = GPlugin.find_result_links.get(view.id(), [])
            for start, end, filename in links:
                if start <= point <= end:
                    GPlugin.showFindResultActions(filename)
                    return

    def on_activated(self, view):
        self.restore_display_name(view)

    def on_load(self, view):
        self.restore_display_name(view)

    def on_window_command(self, window, command_name, args):
        if command_name == "save_all":
            if any(v.is_dirty() and (v.settings().get("rc_backing_file") or v.settings().get("rc_config_type") or v.settings().get("rc_player_file")) for v in window.views()):
                return ("rc_save_all_backed_views", {})
            return None
        if command_name not in ("save", "prompt_save_as", "save_as"):
            return None
        view = window.active_view()
        if view and (view.settings().get("rc_backing_file") or view.settings().get("rc_config_type") or view.settings().get("rc_player_file")):
            return ("rc_save_active_backed_view", {})
        return None

    def on_text_command(self, view, command_name, args):
        if view.settings().get("rc_backing_file") and command_name in ("save", "prompt_save_as", "save_as"):
            return ("rc_save_backed_view", {})
        if view.settings().get("rc_config_type") and command_name in ("save", "prompt_save_as", "save_as"):
            return ("rc_save_config_view", {})
        if view.settings().get("rc_player_file") and command_name in ("save", "prompt_save_as", "save_as"):
            return ("rc_save_player_view", {})
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
            if view.settings().get("rc_pm_view"):
                player_id = view.settings().get("rc_pm_player_id")
                thread_key = view.settings().get("rc_pm_thread_key")
                if player_id is not None and thread_key:
                    if message.lower() == "/clear":
                        GPlugin.clearPrivateMessageThread(thread_key)
                        sublime.status_message("Cleared PM history")
                    else:
                        GPlugin.sendPrivateMessage(player_id, message)
                        thread = GPlugin.private_messages.get(thread_key)
                        if thread:
                            GPlugin.recordPrivateMessage(player_id, thread.get("nickname"), thread.get("account"), message, incoming=False)
                else:
                    sublime.error_message("This PM tab is missing reply data.")
            elif view.settings().get("rc_irc_view"):
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
                else:
                    GPlugin.sendToallMessage(message)
            else:
                if message.lower() == "/clear":
                    view.run_command("rc_replace_buffer_content", {"content": "> ", "read_only": False})
                    sublime.status_message("Cleared RC Chat")
                else:
                    GPlugin.sendRcChat(message)
        return ("rc_noop", {})

    def on_post_save(self, view):
        view.erase_regions("sublimerc_compile_errors")
        view.erase_status("sublimerc_compile_error")
        display_name = view.settings().get("rc_display_name")
        if display_name:
            sublime.set_timeout(lambda: view.set_name(display_name), 0)
            sublime.set_timeout(lambda: view.set_name(display_name), 100)
            sublime.set_timeout(lambda: view.set_name(display_name), 500)
        file_path = view.file_name()
        if not file_path: return
        scripts_folder = getScriptsFolder()
        file_path_norm = os.path.normpath(file_path).lower()
        scripts_folder_norm = scripts_folder.lower()
        if "modified" not in file_path_norm or scripts_folder_norm not in file_path_norm: return
        npc_id = view.settings().get('rc_npc_id')
        npc_name = view.settings().get('rc_npc_name')
        class_name = view.settings().get('rc_class_name')
        weapon_name = view.settings().get('rc_weapon_name')
        config_type = view.settings().get('rc_config_type')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            sublime.status_message("Failed to read file: " + str(e))
            return
        backing_file = view.settings().get('rc_backing_file')
        if backing_file and os.path.normpath(backing_file) != os.path.normpath(file_path):
            try:
                os.makedirs(os.path.dirname(backing_file), exist_ok=True)
                with open(backing_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                sublime.status_message("Failed to update backing file: " + str(e))
                return
        config_file = view.settings().get('rc_config_file')
        if config_file and os.path.normpath(config_file) != os.path.normpath(file_path):
            try:
                os.makedirs(os.path.dirname(config_file), exist_ok=True)
                with open(config_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                sublime.status_message("Failed to update config file: " + str(e))
                return
        player_file = view.settings().get('rc_player_file')
        if player_file and os.path.normpath(player_file) != os.path.normpath(file_path):
            try:
                os.makedirs(os.path.dirname(player_file), exist_ok=True)
                with open(player_file, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                sublime.status_message("Failed to update player file: " + str(e))
                return
        is_empty = content.strip() == ""
        was_deleted = view.settings().get('rc_was_deleted', False)
        is_npc_flags = view.settings().get('rc_npc_flags', False)
        if npc_id is not None and npc_name:
            if is_npc_flags:
                GPlugin.uploadNpcFlags(npc_id, content)
                sublime.status_message("Uploaded NPC flags: " + npc_name)
            else:
                sublime.status_message("Uploaded NPC script: " + npc_name)
                GPlugin.uploadNpcScript(npc_id, npc_name, content)
        elif class_name:
            if is_empty:
                GPlugin.deleteClassScript(class_name)
                view.settings().set('rc_was_deleted', True)
                sublime.status_message("Deleted class script: " + class_name)
            else:
                if was_deleted:
                    GPlugin.log("Restoring class script: " + class_name, debug_only=True)
                    sublime.status_message("Restored class script: " + class_name)
                    view.settings().set('rc_was_deleted', False)
                else:
                    sublime.status_message("Uploaded class script: " + class_name)
                GPlugin.uploadClassScript(class_name, content)
        elif weapon_name:
            if is_empty:
                GPlugin.deleteWeaponScript(weapon_name)
                view.settings().set('rc_was_deleted', True)
                sublime.status_message("Deleted weapon script: " + weapon_name)
            else:
                if was_deleted:
                    GPlugin.log("Restoring weapon script: " + weapon_name, debug_only=True)
                    sublime.status_message("Restored weapon script: " + weapon_name)
                    view.settings().set('rc_was_deleted', False)
                else:
                    sublime.status_message("Uploaded weapon script: " + weapon_name)
                GPlugin.uploadWeaponScript(weapon_name, content)
        elif config_type:
            content = view.substr(sublime.Region(0, view.size()))
            GPlugin.uploadServerConfig(config_type, content)
            if config_type == "serverflags":
                GPlugin.server_flags = None
            elif config_type == "folderconfig":
                GPlugin.folder_config = None
            sublime.status_message("Uploaded " + config_type)
        else:
            downloaded_file = view.settings().get('rc_downloaded_file')
            if downloaded_file:
                content = view.substr(sublime.Region(0, view.size())).encode('latin-1', errors='ignore')
                GPlugin.uploadFile(downloaded_file, content)
                sublime.status_message("Uploaded: " + downloaded_file)
                return
            player_account = view.settings().get('rc_player_account')
            player_data_type = view.settings().get('rc_player_data_type')
            if player_account and player_data_type:
                if player_data_type == 'rights':
                    rights_value, ip_range, folder_access = GPlugin.textToRights(content)
                    GPlugin.uploadPlayerRights(player_account, rights_value, ip_range, folder_access)
                    sublime.status_message("Updated rights for: " + player_account)
                elif player_data_type == 'attributes':
                    properties = GPlugin.textToAttributes(content)
                    GPlugin.uploadPlayerAttributes(player_account, properties)
                    sublime.status_message("Updated attributes for: " + player_account)
                elif player_data_type == 'comments':
                    GPlugin.uploadPlayerComments(player_account, content)
                    sublime.status_message("Updated comments for: " + player_account)
                elif player_data_type == 'account':
                    account_data = GPlugin.textToAccount(content)
                    GPlugin.uploadAccount(player_account, account_data)
                    sublime.status_message("Updated account data for: " + player_account)
                elif player_data_type == 'profile':
                    profile_fields = GPlugin.textToProfile(content, player_account)
                    GPlugin.uploadPlayerProfile(player_account, profile_fields)
                    sublime.status_message("Updated profile for: " + player_account)
                elif player_data_type == 'ban':
                    ban_data = GPlugin.textToBan(content)
                    original_ban_text = view.settings().get('rc_original_ban_text', '')
                    original_ban_data = GPlugin.textToBan(original_ban_text) if original_ban_text else None
                    GPlugin.uploadPlayerBan(player_account, ban_data, original_ban_data)
                    view.settings().set('rc_original_ban_text', content)
                    sublime.status_message("Updated ban data for: " + player_account)

def createDefaultSettings():
    settings_path = os.path.join(sublime.packages_path(), 'User', 'SublimeRC.sublime-settings')
    if not os.path.exists(settings_path):
        default_scripts_folder = os.path.join(os.path.expanduser("~"), "SublimeRC").replace('\\', '/') if platform.system() != "Windows" else "C:/SublimeRC"
        template = """{{
    // Base folder where scripts will be saved
    // Original scripts are saved to: scripts_folder/original/SERVERNAME/[npcs|scripts|weapons]/
    // Modified scripts are saved to: scripts_folder/modified/SERVERNAME/[npcs|scripts|weapons]/
    "scripts_folder": "{}",
    // Account credentials
    "account": "username",
    "password": "password",
    "nickname": "username-sublime",
    // Listserver settings
    "listserver_host": "127.0.0.1",
    "listserver_port": 14922,
    // Compiler output location: "tab" routes into the NC tab, "panel" uses a bottom output panel
    "compiler_output_location": "tab",
    "compiler_panel_auto_show": true,
    // Route NPC-server packets/messages to a separate NC tab instead of RC Chat
    "separate_nc_messages": false
}}
""".format(default_scripts_folder)
        try:
            os.makedirs(os.path.dirname(settings_path), exist_ok=True)
            with open(settings_path, 'w', encoding='utf-8') as f:
                f.write(template)
            print('Created template SublimeRC.sublime-settings file')
            print('Please configure your account credentials in: Preferences > Package Settings > SublimeRC > Settings')
        except Exception as e:
            print('Failed to create settings template: ' + str(e))

def plugin_loaded():
    print("RC Plugin loaded")
    for window in sublime.windows():
        for view in window.views():
            scheme = view.settings().get("color_scheme", "")
            if scheme == "Packages/User/SublimeRC-gscript-editor.sublime-color-scheme":
                view.settings().set("color_scheme", GSCRIPT_EDITOR_COLOR_SCHEME)
            elif scheme == "Packages/User/SublimeRC-goption-editor.sublime-color-scheme":
                view.settings().set("color_scheme", GOPTION_EDITOR_COLOR_SCHEME)
    def fetchServers():
        listserver_configs = getListserverConfigs()
        config = listserver_configs[0] if listserver_configs else None
        if config:
            GPlugin.current_listserver_config = config
            servers = fetchServerList(config)
            if servers:
                for server in servers:
                    server['listserver_config'] = config
                GPlugin.servers = servers
                print("Fetched {} servers from {}".format(len(servers), config["name"]))
            else: print("Failed to fetch server list from {}".format(config["name"]))
        else: print("No listserver configurations found")
    threading.Thread(target=fetchServers, daemon=True).start()

def plugin_unloaded():
    if GPlugin.socket_connection:
        try: GPlugin.socket_connection.close()
        except: pass
    if GPlugin.nc_socket:
        try: GPlugin.nc_socket.close()
        except: pass
    print("RC Plugin unloaded")

def readGByte(payload, offset):
    return (payload[offset] - 32) & 0xFF, offset + 1

def readGShort(payload, offset):
    value = ((payload[offset] - 32) << 7) + (payload[offset+1] - 32)
    return value, offset + 2

def readGInt5(payload, offset):
    value = ((payload[offset] - 32) << 28)
    value += ((payload[offset+1] - 32) << 21)
    value += ((payload[offset+2] - 32) << 14)
    value += ((payload[offset+3] - 32) << 7)
    value += (payload[offset+4] - 32)
    return value, offset + 5

def readLengthString(payload, offset):
    length, offset = readGByte(payload, offset)
    string = payload[offset:offset + length].decode('latin-1', errors='ignore')
    return string, offset + length

def readRcLenString(payload, offset):
    if offset >= len(payload):
        return "", offset
    marker = payload[offset]
    offset += 1
    if marker == 0xff:
        length = min(0xdf, len(payload) - offset)
    else:
        length = max(0, marker - 32)
    string = payload[offset:offset + length].decode('latin-1', errors='ignore')
    return string, offset + length

def writeRcLenString(text):
    raw = str(text or "").encode('latin-1', errors='ignore')
    payload = bytearray()
    if len(raw) < 0xe0:
        payload.append(len(raw) + 32)
        payload.extend(raw)
    else:
        payload.append(0xff)
        payload.extend(raw[:0xdf])
    return payload

def readCommaText(payload, offset, length=None):
    if length is None:
        text = payload[offset:].decode('latin-1', errors='ignore')
    else:
        text = payload[offset:offset + length].decode('latin-1', errors='ignore')
    return gtokenizeReverse(text)

def writeGInt5(value):
    b = bytearray(5)
    b[0] = ((value >> 28) & 0x7F) + 32
    b[1] = ((value >> 21) & 0x7F) + 32
    b[2] = ((value >> 14) & 0x7F) + 32
    b[3] = ((value >> 7) & 0x7F) + 32
    b[4] = (value & 0x7F) + 32
    return b
