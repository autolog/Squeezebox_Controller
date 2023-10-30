#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Smappee Controller © Autolog 2018-2022
#

import logging

# ============================== Custom Imports ===============================
try:
    import indigo  # noqa
except ImportError:
    pass

number = -1

debug_show_constants = False


def constant_id(constant_label) -> int:  # Auto increment constant id
    global number
    if debug_show_constants and number == -1:
        indigo.server.log("Smappee Controller Plugin internal Constant Name mapping ...", level=logging.DEBUG)
    number += 1
    if debug_show_constants:
        indigo.server.log(f"{number}: {constant_label}", level=logging.DEBUG)
    return number

# plugin Constants


try:
    # noinspection PyUnresolvedReferences
    import indigo
except ImportError:
    pass


CF_BUNDLE_IDENTIFIER = "com.indigodomo.indigoplugin.autologsqueezeboxcontroller"
ANNOUNCEMENTS_SUB_FOLDER = "autolog_squeezebox_announcements"
COVER_ART_SUB_FOLDER = "autolog_squeezebox_cover_art"

# noinspection Duplicates

PENDING = constant_id("PENDING")
YES = constant_id("YES")
NO = constant_id("NO")
SPEECH = constant_id("SPEECH")
REQUEST = constant_id("REQUEST")
INITIALISE = constant_id("INITIALISE")
SAVE_STATE = constant_id("SAVE_STATE")
PLAY = constant_id("SAVE_STATE")


ACTIVE = constant_id("ACTIVE")
ADDRESS = constant_id("ADDRESS")
ALBUM = constant_id("ARTIST")
ANNOUNCEMENT = constant_id("ANNOUNCEMENT")
ANNOUNCEMENT_PLAYLIST_NO_PLAY = constant_id("ANNOUNCEMENT_PLAYLIST_NO_PLAY")
ANNOUNCEMENT_PLAY_ACTIVE = constant_id("ANNOUNCEMENT_PLAY_ACTIVE")
ANNOUNCEMENT_PLAY_INITIALISED = constant_id("ANNOUNCEMENT_PLAY_INITIALISED")
ANNOUNCEMENT_UNIQUE_KEY = constant_id("ANNOUNCEMENT_UNIQUE_KEY")
API_VERSION = constant_id("API_VERSION")
APPEND = constant_id("APPEND")
ARTIST = constant_id("CONNECTED")
BASE_FOLDER = constant_id("BASE_FOLDER")
COMMAND_TO_SEND = constant_id("COMMAND_TO_SEND")
COMMUNICATE_WITH_SERVER = constant_id("COMMUNICATE_WITH_SERVER")
CONNECTED = constant_id("CONNECTED")
COVER_ART = constant_id("COVER_ART")
COVER_ART_FILE = constant_id("COVER_ART_FILE")
COVER_ART_FOLDER = constant_id("COVER_ART_FOLDER")
COVER_ART_NO_FILE = constant_id("COVER_ART_NO_FILE")
COVER_ART_NO_FILE_URL = constant_id("COVER_ART_NO_FILE_URL")
COVER_ART_URL = constant_id("COVER_ART_URL")
DATE_TIME_STARTED = constant_id("DATE_TIME_STARTED")
DURATION = constant_id("DURATION")
DURATION_UI = constant_id("DURATION_UI")
EDITED = constant_id("EDITED")
EVENT = constant_id("EVENT")
FILE = constant_id("FILE")
FILE_CHECK_OK = constant_id("FILE_CHECK_OK")
GENRE = constant_id("GENRE")
INDIGO_SERVER_ADDRESS = constant_id("INDIGO_SERVER_ADDRESS")
INITIALISED = constant_id("INITIALISED")
IP_ADDRESS = constant_id("IP_ADDRESS")
IP_ADDRESS_PORT = constant_id("IP_ADDRESS_PORT")
IP_ADDRESS_PORT_NAME = constant_id("IP_ADDRESS_PORT_NAME")
IS_SYNC_MASTER = constant_id("IS_SYNC_MASTER")
IS_SYNC_SLAVE = constant_id("CONNECTED")
KEEP_THREAD_ALIVE = constant_id("KEEP_THREAD_ALIVE")
LAST_SCAN = constant_id("LAST_SCAN")
LISTEN_NOTIFICATION = constant_id("LISTEN_NOTIFICATION")
LISTEN_TO_SERVER = constant_id("LISTEN_TO_SERVER")
MAC = constant_id("MAC")
MAINTAIN_SYNC = constant_id("IS_SYNC_SLAVE")
MASTER_PLAYER_ADDRESS = constant_id("MASTER_PLAYER_ADDRESS")
MASTER_PLAYER_ID = constant_id("MASTER_PLAYER_ID")
MASTER_PLAYER_NAME = constant_id("MASTER_PLAYER_NAME")
MODE = constant_id("MODE")
MODEL = constant_id("MODEL")
NAME = constant_id("NAME")
OPTION = constant_id("OPTION")
PATH = constant_id("PATH")
PLAYERS = constant_id("PLAYERS")
PLAYER_COUNT = constant_id("PLAYER_COUNT")
PLAYER_ID = constant_id("PLAYER_ID")
PLAYER_MAC = constant_id("PLAYER_MAC")
PLAYLIST_TRACKS_TOTAL = constant_id("PLAYLIST_TRACKS_TOTAL")
PLAYLIST_TRACKS_UI = constant_id("PLAYLIST_TRACKS_UI")
PLAYLIST_TRACK_NUMBER = constant_id("PLAYLIST_TRACK_NUMBER")
PLUGIN_DISPLAY_NAME = constant_id("PLUGIN_DISPLAY_NAME")
PLUGIN_ID = constant_id("PLUGIN_ID")
PLUGIN_INFO = constant_id("PLUGIN_INFO")
PLUGIN_INITIALIZED = constant_id("PLUGIN_INITIALIZED")
PLUGIN_PREFS_FOLDER = constant_id("PLUGIN_PREFS_FOLDER")
PLUGIN_VERSION = constant_id("PLUGIN_VERSION")
PORT = constant_id("PORT")
POWER = constant_id("POWER")
POWER_UI = constant_id("POWER_UI")
PREPEND = constant_id("PREPEND")
QUEUES = constant_id("QUEUES")
REMOTE_STREAM = constant_id("REMOTE_STREAM")
REPEAT = constant_id("REPEAT")
REPLY_TO_SEND = constant_id("REPLY_TO_SEND")
RETURNED_RESPONSE = constant_id("RETURNED_RESPONSE")
SAVED_MAINTAIN_SYNC = constant_id("SAVED_MAINTAIN_SYNC")
SAVED_MODE = constant_id("SAVED_MODE")
SAVED_POWER = constant_id("SAVED_POWER")
SAVED_REPEAT = constant_id("SAVED_REPEAT")
SAVED_SHUFFLE = constant_id("SAVED_SHUFFLE")
SAVED_TIME = constant_id("SAVED_TIME")
SAVED_VOLUME = constant_id("SAVED_VOLUME")
SERVERS = constant_id("SERVERS")
SERVER_ID = constant_id("SERVER_ID")
SERVER_NAME = constant_id("SERVER_NAME")
SHUFFLE = constant_id("SHUFFLE")
SLAVE_PLAYER_IDS = constant_id("SLAVE_PLAYER_IDS")
SONG_URL = constant_id("SONG_URL")
SPEECH_TEXT = constant_id("SPEECH_TEXT")
STATE = constant_id("STATE")
STATUS = constant_id("STATUS")
STEP = constant_id("STEP")
SYNC_MASTER_NUMBER_OF_SLAVES = constant_id("SYNC_MASTER_NUMBER_OF_SLAVES")
SYNC_MASTER_SLAVE_1_ADDRESS = constant_id("SYNC_MASTER_SLAVE_1_ADDRESS")
SYNC_MASTER_SLAVE_1_ID = constant_id("SYNC_MASTER_SLAVE_1_ID")
SYNC_MASTER_SLAVE_1_NAME = constant_id("SYNC_MASTER_SLAVE_1_NAME")
SYNC_MASTER_SLAVE_2_ADDRESS = constant_id("SYNC_MASTER_SLAVE_2_ADDRESS")
SYNC_MASTER_SLAVE_2_ID = constant_id("SYNC_MASTER_SLAVE_2_ID")
SYNC_MASTER_SLAVE_2_NAME = constant_id("SYNC_MASTER_SLAVE_2_NAME")
SYNC_MASTER_SLAVE_3_ADDRESS = constant_id("SYNC_MASTER_SLAVE_3_ADDRESS")
SYNC_MASTER_SLAVE_3_ID = constant_id("SYNC_MASTER_SLAVE_3_ID")
SYNC_MASTER_SLAVE_3_NAME = constant_id("SYNC_MASTER_SLAVE_3_NAME")
SYNC_MASTER_SLAVE_4_ADDRESS = constant_id("SYNC_MASTER_SLAVE_4_ADDRESS")
SYNC_MASTER_SLAVE_4_ID = constant_id("SYNC_MASTER_SLAVE_4_ID")
SYNC_MASTER_SLAVE_4_NAME = constant_id("SYNC_MASTER_SLAVE_4_NAME")
TEMPORARY_FOLDER = constant_id("TEMPORARY_FOLDER")
THREAD = constant_id("THREAD")
THREADS = constant_id("THREADS")
THREAD_ACTIVE = constant_id("THREAD_ACTIVE")
TIME = constant_id("TIME")
TIMERS = constant_id("TIMERS")
TITLE = constant_id("TITLE")
TOTAL_ALBUMS = constant_id("TOTAL_ALBUMS")
TOTAL_ARTISTS = constant_id("TOTAL_ARTISTS")
TOTAL_GENRES = constant_id("TOTAL_GENRES")
TOTAL_SONGS = constant_id("TOTAL_SONGS")
VERSION = constant_id("VERSION")
VOICE = constant_id("VOICE")
VOLUME = constant_id("VOLUME")

LOG_LEVEL_NOT_SET = 0
LOG_LEVEL_DEBUGGING = 10
LOG_LEVEL_STARLING_API = 15
LOG_LEVEL_INFO = 20
LOG_LEVEL_WARNING = 30
LOG_LEVEL_ERROR = 40
LOG_LEVEL_CRITICAL = 50

LOG_LEVEL_TRANSLATION = dict()
LOG_LEVEL_TRANSLATION[LOG_LEVEL_NOT_SET] = "Not Set"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_DEBUGGING] = "Debugging"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_STARLING_API] = "Starling API Logging"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_INFO] = "Info"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_WARNING] = "Warning"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_ERROR] = "Error"
LOG_LEVEL_TRANSLATION[LOG_LEVEL_CRITICAL] = "Critical"
