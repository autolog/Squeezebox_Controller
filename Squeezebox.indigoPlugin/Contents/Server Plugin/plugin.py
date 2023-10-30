#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Squeezebox Controller © Autolog 2014-2023
#
# Requires Indigo 2022.2+ [Runs under Python 3]

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
from AppKit import NSSpeechSynthesizer
from Foundation import NSURL  # noqa: https://stackoverflow.com/a/23839976/2827397

import datetime
import errno
import os
import platform
import queue 
import shutil
import socket
import sys
import threading
import time
import traceback
import re
import urllib.parse  # TODO: Was urllib; Use requests instead?
from urllib.request import urlopen

# ============================== Custom Imports ===============================
try:
    import indigo  # noqa
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *
from communicateWithServer import ThreadCommunicateWithServer
from listenToServer import ThreadListenToServer


# noinspection PyTypeChecker
class Plugin(indigo.PluginBase):

    def __init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs):

        indigo.PluginBase.__init__(self, plugin_id, plugin_display_name, plugin_version, plugin_prefs)

        # Initialise dictionary to store plugin Globals
        self.globals = dict()

        # Initialise Indigo plugin info
        self.globals[PLUGIN_INFO] = dict()
        self.globals[PLUGIN_INFO][PLUGIN_ID] = plugin_id
        self.globals[PLUGIN_INFO][PLUGIN_DISPLAY_NAME] = plugin_display_name
        self.globals[PLUGIN_INFO][PLUGIN_VERSION] = plugin_version
        self.globals[PLUGIN_INFO][PATH] = indigo.server.getInstallFolderPath()
        self.globals[PLUGIN_INFO][API_VERSION] = indigo.server.apiVersion
        self.globals[PLUGIN_INFO][INDIGO_SERVER_ADDRESS] = indigo.server.address

        log_format = logging.Formatter("%(asctime)s.%(msecs)03d\t%(levelname)-12s\t%(name)s.%(funcName)-25s %(msg)s", datefmt="%Y-%m-%d %H:%M:%S")
        self.plugin_file_handler.setFormatter(log_format)
        self.plugin_file_handler.setLevel(LOG_LEVEL_INFO)  # Logging Level for plugin log file
        self.indigo_log_handler.setLevel(LOG_LEVEL_INFO)  # Logging level for Indigo Event Log

        self.logger = logging.getLogger("Plugin.Squeezebox")

        # self.globals[BASE_FOLDER] = "/Library/Application Support"  # Base Folder for Plugin data  # TODO: Change to Preferences Folder
        self.globals[PLUGIN_PREFS_FOLDER] = f"{self.globals[PLUGIN_INFO][PATH]}/Preferences/Plugins/{CF_BUNDLE_IDENTIFIER}"
        if not os.path.exists(self.globals[PLUGIN_PREFS_FOLDER]):
            self.mkdir_with_mode(self.globals[PLUGIN_PREFS_FOLDER])


        self.globals[COVER_ART] = dict()
        self.globals[COVER_ART][COVER_ART_NO_FILE] = ""
        self.globals[COVER_ART][COVER_ART_NO_FILE_URL] = ""

        self.globals[THREADS] = dict()
        self.globals[THREADS][COMMUNICATE_WITH_SERVER] = dict()
        self.globals[THREADS][LISTEN_TO_SERVER] = dict()

        self.globals[QUEUES] = dict()
        self.globals[QUEUES][RETURNED_RESPONSE] = ""  # Set-up in plugin start (a common returned response queue for all servers)
        self.globals[QUEUES][COMMAND_TO_SEND] = dict()  # There will be one "commandToSend" queue for each server - set-up in device start
        self.globals[QUEUES][ANNOUNCEMENT] = ""  # Set-up in plugin start (a common announcement queue for all servers)

        self.globals[TIMERS] = dict()
        self.globals[TIMERS][COMMAND_TO_SEND] = dict()

        self.globals[SERVERS] = dict()
        self.globals[PLAYERS] = dict()

        self.globals[ANNOUNCEMENT] = dict()
        self.globals[ANNOUNCEMENT][ACTIVE] = NO
        self.globals[ANNOUNCEMENT][STEP] = ""
        self.globals[ANNOUNCEMENT][FILE_CHECK_OK] = True
        self.globals[ANNOUNCEMENT][TEMPORARY_FOLDER] = ""

        self.validatePrefsConfigUi(plugin_prefs)  # Validate the Plugin Config before plugin initialisation

    def __del__(self):

        indigo.PluginBase.__del__(self)
    
    def display_plugin_information(self):
        try:
            def plugin_information_message():
                startup_message_ui = "Plugin Information:\n"
                startup_message_ui += f"{'':={'^'}80}\n"
                startup_message_ui += f"{'Plugin Name:':<30} {self.globals[PLUGIN_INFO][PLUGIN_DISPLAY_NAME]}\n"
                startup_message_ui += f"{'Plugin Version:':<30} {self.globals[PLUGIN_INFO][PLUGIN_VERSION]}\n"
                startup_message_ui += f"{'Plugin ID:':<30} {self.globals[PLUGIN_INFO][PLUGIN_ID]}\n"
                startup_message_ui += f"{'Indigo Version:':<30} {indigo.server.version}\n"
                startup_message_ui += f"{'Indigo License:':<30} {indigo.server.licenseStatus}\n"
                startup_message_ui += f"{'Indigo API Version:':<30} {indigo.server.apiVersion}\n"
                startup_message_ui += f"{'Architecture:':<30} {platform.machine()}\n"
                startup_message_ui += f"{'Python Version:':<30} {sys.version.split(' ')[0]}\n"
                startup_message_ui += f"{'Mac OS Version:':<30} {platform.mac_ver()[0]}\n"
                startup_message_ui += f"{'Plugin Process ID:':<30} {os.getpid()}\n"
                startup_message_ui += f"{'':={'^'}80}\n"
                return startup_message_ui

            self.logger.info(plugin_information_message())

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split("/")
        log_message = f"'{exception_error_message}' in module '{module[-1]}', method '{method}'"
        if log_failing_statement:
            log_message = log_message + f"\n   Failing statement [line {line_number}]: '{statement}'"
        else:
            log_message = log_message + f" at line {line_number}"
        self.logger.error(log_message)

    def mkdir_with_mode(self, directory):
        try:
            # Forces Read | Write on creation so that the plugin can delete the folder id required
            if not os.path.isdir(directory):
                oldmask = os.umask(000)
                os.makedirs(directory, 0o777)
                os.umask(oldmask)
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def startup(self):
        try:
            self.globals[COVER_ART][COVER_ART_NO_FILE] = str(f"{indigo.server.getInstallFolderPath()}/Plugins/Squeezebox.indigoPlugin/Contents/Resources/nocoverart.jpg")
            self.globals[COVER_ART][COVER_ART_NO_FILE_URL] = str(f"file://{self.globals[COVER_ART][COVER_ART_NO_FILE]}")
    
            self.globals[QUEUES][RETURNED_RESPONSE] = queue.Queue()  # noqa - For server responses and UI commands
    
            self.globals[QUEUES][ANNOUNCEMENT] = queue.Queue()  # noqa - For queued announcements (Announcements are queued when one is already active)
    
            self.signalWakeupQueues(self.globals[QUEUES][RETURNED_RESPONSE])
    
            self.deviceFolderName = "Squeezebox"
            if self.deviceFolderName not in indigo.devices.folders:
                self.deviceFolder = indigo.devices.folder.create(self.deviceFolderName)
            self.deviceFolderId = indigo.devices.folders.getId(self.deviceFolderName)
    
            indigo.devices.subscribeToChanges()
    
            self.logger.info("Autolog 'Squeezebox Controller' initialization complete")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def shutdown(self):

        self.logger.debug("shutdown called")

    def signalWakeupQueues(self, queueToWakeup):
        try:
            self.logger.debug(f"=================> signalWakeupQueues invoked for {queueToWakeup} <========================")
            queueToWakeup.put(["WAKEUP"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validatePrefsConfigUi(self, values_dict):
        try:
            self.globals[COVER_ART_FOLDER] = values_dict.get("coverArtFolder", self.globals[PLUGIN_PREFS_FOLDER])
            if self.globals[COVER_ART_FOLDER] == "":
                self.globals[COVER_ART_FOLDER] = self.globals[PLUGIN_PREFS_FOLDER]

            if not os.path.exists(self.globals[COVER_ART_FOLDER]):
                errorDict = indigo.Dict()
                errorDict["coverArtFolder"] = "Folder does not exist"
                errorDict["showAlertText"] = "Folder does not exist, please specify a valid folder."
                return False, values_dict, errorDict
    
            path = f"{self.globals[COVER_ART_FOLDER]}/{COVER_ART_SUB_FOLDER}"
            try:
                os.makedirs(path)
            except OSError as exception_error:
                if exception_error.errno != errno.EEXIST:
                    error_dict = indigo.Dict()
                    error_dict["coverArtFolder"] = f"Error creating '{path}' folder. Error = {exception_error}"
                    error_dict["showAlertText"] = "Error creating cover art autolog folder - please correct error."
                    return False, values_dict, error_dict

            values_dict["coverArtFolderResolved"] = path
            self.logger.info(f"Cover Art Folder: {path}")

            self.globals[ANNOUNCEMENT][TEMPORARY_FOLDER] = values_dict.get("announcementTempFolder", self.globals[PLUGIN_PREFS_FOLDER])
            if self.globals[ANNOUNCEMENT][TEMPORARY_FOLDER] == "":
                self.globals[ANNOUNCEMENT][TEMPORARY_FOLDER] = self.globals[PLUGIN_PREFS_FOLDER]
    
            if not os.path.exists(self.globals[ANNOUNCEMENT][TEMPORARY_FOLDER]):
                error_dict = indigo.Dict()
                error_dict["announcementTempFolder"] = "Folder does not exist"
                error_dict["showAlertText"] = "Folder does not exist, please specify a valid folder."
                return False, values_dict, error_dict
    
            try:
                path = f"{self.globals[ANNOUNCEMENT][TEMPORARY_FOLDER]}/{ANNOUNCEMENTS_SUB_FOLDER}"
                os.makedirs(path)
            except OSError as exception_error:
                if exception_error.errno != errno.EEXIST:
                    error_dict = indigo.Dict()
                    error_dict["announcementTempFolder"] = f"Error creating '{path}' folder. Error = {exception_error}"
                    error_dict["showAlertText"] = "Error creating temporary autolog folder - please correct error."
                    return False, values_dict, error_dict

            values_dict["announcementTempFolderResolved"] = path
            self.logger.info(f"Announcement Temp Folder: {path}")
    
            return True
        
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def runConcurrentThread(self):
        try:
            while True:
                returned_response = self.globals[QUEUES][RETURNED_RESPONSE].get()
                # self.logger.warning(f"Returned response: {returned_response}")
                try:
                    if returned_response[0] != "WAKEUP":
                        # self.logger.warning(f"RUN_CONCURRENT_THREAD - Returned response: {returned_response}")  # TODO: DEBUG
                        server_dev_id = returned_response[0]  # Indigo device id of Logitech Media Server
                        message_type = returned_response[1]  # LISTEN_NOTIFICATION | REPLY_TO_SEND
                        message = returned_response[2]  # Message received from Logitech Media Server
                        self.handleSqueezeboxServerResponse(indigo.devices[server_dev_id], message_type, message)
                    else:
                        if self.stopThread:
                            pass
                            # raise self.StopThread         # Plugin shutdown request.
                        else:
                            self.globals[TIMERS][RETURNED_RESPONSE] = threading.Timer(5.0, self.signalWakeupQueues, [self.globals[QUEUES][RETURNED_RESPONSE]])
                            self.globals[TIMERS][RETURNED_RESPONSE].start()

                except Exception as exception_error:
                    self.exception_handler(exception_error, True)  # Log error and display failing statement

        except self.StopThread:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _serverConnectedTest(self, dev, plugin_action):
        try:
            if dev is None:
                self.logger.error(f"'{plugin_action.description}' action ignored as Squeezebox Server to perform action is not specified.")
                return False
            elif dev.states["status"] != "connected":
                self.logger.error(f"'{plugin_action.description}' action ignored as Squeezebox Server '{dev.name}' is not available.")
                return False
            return True

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _playerConnectedTest(self, dev, pluginAction):
        try:
            if dev is None:
                self.logger.error(f"'{pluginAction.description}' action ignored as Squeezebox Player to perform action is not specified.")
                return False
            elif not dev.states["connected"]:
                self.logger.error(f"'{pluginAction.description}' action ignored as Squeezebox Player '{dev.name}' is disconnected.")
                return False
            return True

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processRefreshServerStatus(self, pluginAction, dev):  # Dev is a Squeezebox Server
        try:
            if self._serverConnectedTest(dev, pluginAction): 
                self.globals[QUEUES][COMMAND_TO_SEND][dev.id].put(["serverstatus 0 0 subscribe:0"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPowerOnAll(self, pluginAction, dev):  # Dev is a Squeezebox Server
        try:
            for selectedPlayerId in self.globals[PLAYERS]:
                self.logger.debug(f"Player [{selectedPlayerId}] has Mac Address '{self.globals[PLAYERS][selectedPlayerId][MAC]}'")
                if self.globals[PLAYERS][selectedPlayerId][POWER_UI] != "disconnected":   
                    self.globals[QUEUES][COMMAND_TO_SEND][dev.id].put([self.globals[PLAYERS][selectedPlayerId][MAC] + " power 1"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPowerOffAll(self, pluginAction, dev):  # Dev is a Squeezebox Server
        try:
            for selectedPlayerId in self.globals[PLAYERS]:
                self.logger.debug(f"Player [{selectedPlayerId}] has Mac Address '{self.globals[PLAYERS][selectedPlayerId][MAC]}'")
                if self.globals[PLAYERS][selectedPlayerId][POWER_UI] != "disconnected":
                    self.globals[QUEUES][COMMAND_TO_SEND][dev.id].put([self.globals[PLAYERS][selectedPlayerId][MAC] + " power 0"])
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPowerOn(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " power 1"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPowerOff(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " power 0"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPowerToggleOnOff(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " power"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPlay(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " play"])
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processStop(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " stop"])
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPause(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " pause"])
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processForward(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " button fwd"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processRewind(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " button rew"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processVolumeSet(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                volume = pluginAction.props.get("volumeSetValue")
                if self._validateVolume(volume):
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " mixer volume " + volume])
                else:
                    self.logger.error(f"Set volume of '{dev.name}' to value of '{volume}' is invalid")
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _validateVolume(self,volume):
        try:
            if volume.isdigit() and 0 <= int(volume) <= 100:
                return True, volume
            return False

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processVolumeIncrease(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                force = pluginAction.props.get("forceVolumeToMultipleOfIncrease", False)

                volumeIncreaseValue = pluginAction.props.get("volumeIncreaseValue", "5")
                if self._validateVolume(volumeIncreaseValue):
                    volumeIncreaseValue = int(volumeIncreaseValue)
                    volume = int(self.globals[PLAYERS][dev.id][VOLUME])

                    if force:
                        if volumeIncreaseValue > 0:
                            if (volume % volumeIncreaseValue) != 0:
                                volumeIncreaseValue = volumeIncreaseValue - (volume % volumeIncreaseValue)

                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " mixer volume +" + str(volumeIncreaseValue)])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processVolumeDecrease(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                force = pluginAction.props.get("forceVolumeToMultipleOfDecrease", False)

                volumeDecreaseValue = pluginAction.props.get("volumeDecreaseValue", "5")
                if self._validateVolume(volumeDecreaseValue):
                    volumeDecreaseValue = int(volumeDecreaseValue)
                    volume = int(self.globals[PLAYERS][dev.id][VOLUME])

                    if force and volumeDecreaseValue > 0:
                        if (volume % volumeDecreaseValue) != 0:
                            volumeDecreaseValue = (volume % volumeDecreaseValue)

                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " mixer volume -" + str(volumeDecreaseValue)])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processVolumeMute(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                if pluginAction.props.get("volumeMuteAll", False):
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " autologMixerMuteAll"])
                else:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " mixer muting 1"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processVolumeUnmute(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                if pluginAction.props.get("volumeUnmuteAll", False):
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " autologMixerUnmuteAll"])
                else:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " mixer muting 0"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processVolumeToggleMute(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                if pluginAction.props.get("volumeToggleMuteAll", False):
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " autologMixerToggleMuteAll"])
                else:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " mixer muting toggle"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPlayPreset(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " button playPreset_" + pluginAction.props.get("preset")])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPlayFavorite(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
               self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " favorites playlist play item_id:" + pluginAction.props.get("favorite")])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPlayPlaylist(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                if os.path.isfile(pluginAction.props.get("playlist")):
                    self.logger.info(f"Play Playlist ['{pluginAction.props.get('playlist')}'] requested for '{dev.name}'.")

                    self.playlistFile = str(pluginAction.props.get("playlist")).replace(" ", "%20")
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([
                        f"readdirectory 0 1 autologFunction:PlaylistCheck autologDevice:{str(dev.id)} folder:{os.path.dirname(self.playlistFile)} filter:{os.path.basename(self.playlistFile)}"])
                else:
                    self.logger.error(f"Play Playlist not actioned for '{dev.name}' as playlist ['{pluginAction.props.get('playlist')}'] not found.")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processClearPlaylist(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " playlist clear"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processShuffle(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                actionOptionShuffle = pluginAction.props.get("optionShuffle", "off")
                match actionOptionShuffle:
                    case "off":
                        optionShuffle = "0"
                    case "song":
                        optionShuffle = "1"
                    case "album":
                        optionShuffle = "2"
                    case "toggle":
                        optionShuffle = ""
                    case _:
                        optionShuffle = ""

                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " playlist shuffle " + optionShuffle])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processRepeat(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                actionOptionRepeat = pluginAction.props.get("optionRepeat", "off")
                match actionOptionRepeat:
                    case "off":
                        optionRepeat = "0"
                    case "song":
                        optionRepeat = "1"
                    case "playlist":
                        optionRepeat = "2"
                    case "toggle":
                        optionRepeat = ""
                    case _:
                        optionRepeat = ""
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([f"{self.globals[PLAYERS][dev.id][MAC]} playlist repeat {optionRepeat}"])  # noqa

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processResetAnnouncement(self, pluginAction, dev):  # Dev is a Squeezebox Server
        try:
            if self.globals[ANNOUNCEMENT][ACTIVE] != NO:
                self.globals[ANNOUNCEMENT][ACTIVE] = NO
                self.globals[ANNOUNCEMENT][INITIALISED] = False
                self.logger.info("Reset Announcement actioned")
            else:
                self.logger.info("Reset Announcement ignored as Play Announcement not currently in progress.")

            self.globals[QUEUES][ANNOUNCEMENT].queue.clear  # noqa

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processPlayAnnouncement(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            announcementUniqueKey = str(int(time.time()*1000))
            self.logger.debug(f"Unique Key = [{announcementUniqueKey}]")
            self.globals[ANNOUNCEMENT][announcementUniqueKey] = dict()

            if self._playerConnectedTest(dev, pluginAction):

                self.globals[ANNOUNCEMENT][announcementUniqueKey][OPTION] = pluginAction.props.get("optionAnnouncement")
                self.globals[ANNOUNCEMENT][announcementUniqueKey][VOLUME] = pluginAction.props.get("announcementVolume", "50")

                option = pluginAction.props.get("optionAnnouncement")
                match option:
                    case "file":
                        self.globals[ANNOUNCEMENT][announcementUniqueKey][OPTION] = FILE
                        self.globals[ANNOUNCEMENT][announcementUniqueKey][FILE] = str(pluginAction.props.get("announcementFile")).replace(" ", "%20")

                        if self.globals[ANNOUNCEMENT][ACTIVE] == NO:
                            self.globals[ANNOUNCEMENT][ACTIVE] = PENDING
                            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put(
                                [f"{self.globals[PLAYERS][dev.id][MAC]} autologAnnouncementRequest {announcementUniqueKey}"])
                        else:
                            self.logger.info(f"Announcement queued for '{indigo.devices[dev.id].name}' as a Play Announcement is currently in progress.")

                            self.globals[QUEUES][ANNOUNCEMENT].put(
                                [(self.globals[PLAYERS][dev.id][SERVER_ID], self.globals[PLAYERS][dev.id][MAC] + " autologAnnouncementRequest " + announcementUniqueKey)])

                    case _:  # Assume "speech"
                        self.globals[ANNOUNCEMENT][announcementUniqueKey][OPTION] = SPEECH

                        # perform variable / device substitution
                        textToSpeak = pluginAction.props.get("announcementText", "No speech text specified")
                        textToSpeakvalidation = self.substitute(textToSpeak, validateOnly=True)
                        if textToSpeakvalidation[0]:
                            self.globals[ANNOUNCEMENT][announcementUniqueKey][SPEECH_TEXT] = self.substitute(textToSpeak, validateOnly=False)
                        else:
                            self.logger.error(f"Announcement 'Text to Speak' ['{textToSpeak}'] has an error: [{textToSpeakvalidation[1]}]")
                            return

                        self.globals[ANNOUNCEMENT][announcementUniqueKey][VOICE] = pluginAction.props.get("announcementVoice")

                        self.logger.debug(f"speechText (Processed) = [{self.globals[ANNOUNCEMENT][announcementUniqueKey][SPEECH_TEXT]}]")

                        self.logger.debug(f"announcementPrepend = '{pluginAction.props.get('announcementPrepend')}', announcementAppend = '{pluginAction.props.get('announcementAppend')}'")

                        if pluginAction.props.get("announcementPrepend"):
                            self.logger.debug("announcementPrepend ACTIVE")
                            self.globals[ANNOUNCEMENT][announcementUniqueKey][PREPEND] = str(pluginAction.props.get("announcementPrependFile")).replace(" ", "%20")

                        if pluginAction.props.get("announcementAppend"):
                            self.logger.debug("announcementAppend ACTIVE")
                            self.globals[ANNOUNCEMENT][announcementUniqueKey][APPEND] = str(pluginAction.props.get("announcementAppendFile")).replace(" ", "%20")

                        if self.globals[ANNOUNCEMENT][ACTIVE] == NO:
                            self.globals[ANNOUNCEMENT][ACTIVE] = PENDING
                            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([(self.globals[PLAYERS][dev.id][MAC] + " autologAnnouncementRequest " + announcementUniqueKey)])
                        else:
                            self.logger.info(f"Announcement queued for '{indigo.devices[dev.id].name}' as a Play Announcement is currently in progress.")
                            self.globals[QUEUES][ANNOUNCEMENT].put([(self.globals[PLAYERS][dev.id][SERVER_ID], self.globals[PLAYERS][dev.id][MAC] + " autologAnnouncementRequest " + announcementUniqueKey)])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
                

    def processPlayerRawCommand(self, pluginAction, dev):  # Dev is a Squeezebox Player
        try:
            if self._playerConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.id][SERVER_ID]].put([self.globals[PLAYERS][dev.id][MAC] + " " + pluginAction.props.get("rawPlayerCommand")])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processServerRawCommand(self, pluginAction, dev):  # Dev is a Squeezebox Server
        try:
            if self._serverConnectedTest(dev, pluginAction):
                self.globals[QUEUES][COMMAND_TO_SEND][dev.id].put([pluginAction.props.get("rawServerCommand")])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def processSpeechVoiceGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        try:
            self.logger.debug(f"SQUEEZEBOX PLUGIN - processSpeechVoiceGenerator [valuesDict]=[{valuesDict}]")

            self.dictTest = []

            for appleVoice in NSSpeechSynthesizer.availableVoices():
                # self.logger.debug(f"NSSpeechSynthesizer.availableVoice[{type(appleVoice)}] = [{appleVoice}]")
                if appleVoice.rsplit(".", 1)[1] == "premium":
                    voiceName = str(f"{appleVoice.rsplit('.', 2)[1]} [Premium]")
                else:
                    voiceName = appleVoice.rsplit(".", 1)[1]


                self.dictTest.append((appleVoice, voiceName))

            # self.logger.debug(f"self.dictTest [Type: {type(self.dictTest)} ]: {self.dictTest}")

            myArray = self.dictTest
            return myArray

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validateActionConfigUi(self, valuesDict, typeId, actionId):
        try:
            self.logger.debug(f"validateActionConfigUi TypeId=[{str(typeId)}], ActionId=[{str(actionId)}] - {valuesDict}")

            if typeId == "volumeSet":
                volume = ""
                if "volumeSetValue" in valuesDict:
                    volume = valuesDict["volumeSetValue"]
                if self._validateVolume(volume):
                    return True
                errorDict = indigo.Dict()
                errorDict["volumeSetValue"] = "The value of this field must be between 0 to 100 inclusive."
                errorDict["showAlertText"] = "Invalid Volume Set Value specified."
                return (False, valuesDict, errorDict)

            if typeId == "volumeIncrease":
                volume = ""
                if "volumeIncreaseValue" in valuesDict:
                    volume = valuesDict["volumeIncreaseValue"]
                if self._validateVolume(volume):
                    return True
                errorDict = indigo.Dict()
                errorDict["volumeIncreaseValue"] = "The value of this field must be between 0 to 100 inclusive, though a number like 5 would be sensible."
                errorDict["showAlertText"] = "Invalid Volume Increase Value specified."
                return (False, valuesDict, errorDict)

            if typeId == "volumeDecrease":
                volume = ""
                if "volumeDecreaseValue" in valuesDict:
                    volume = valuesDict["volumeDecreaseValue"]
                if self._validateVolume(volume):
                    return True
                errorDict = indigo.Dict()
                errorDict["volumeDecreaseValue"] = "The value of this field must be between 0 to 100 inclusive, though a number like 5 would be sensible."
                errorDict["showAlertText"] = "Invalid Volume Decrease Value specified."
                return (False, valuesDict, errorDict)

            return True

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def handleSqueezeboxServerResponse(self, dev, processSqueezeboxFunction, responseFromSqueezeboxServer):
        try:
            response_items = responseFromSqueezeboxServer.split(" ")
            response_output = "Response From Squeezebox Server:\n"
            response_item_count = 0
            for response_item in response_items:
                response_item_count_ui = f"0{str(response_item_count)}"[-2:]
                response_item = urllib.parse.unquote(response_item)
                response_output += f"  {response_item_count_ui} {response_item}\n"
                response_item_count += 1  # For next response item
            response_output += "------------------"
            # self.logger.info(response_output)  # TODO: DEBUG

            try:
                response_keyword, response_keyword_2, response_data = responseFromSqueezeboxServer.split(" ", 2)
                response_keyword = urllib.parse.unquote(response_keyword)
                response_keyword_2 = urllib.parse.unquote(response_keyword_2)
            except ValueError:
                try:
                    response_data = ""
                    response_keyword, response_keyword_2 = responseFromSqueezeboxServer.split(" ", 1)
                    response_keyword = urllib.parse.unquote(response_keyword)
                    response_keyword_2 = urllib.parse.unquote(response_keyword_2)
                except ValueError:
                    response_keyword_2 = ""
                    response_keyword = responseFromSqueezeboxServer
                    response_keyword = urllib.parse.unquote(response_keyword)

            self.currentTime = indigo.server.getTime()

            self.responseFromSqueezeboxServer = urllib.parse.unquote(responseFromSqueezeboxServer)

            self.logger.debug(f"[{processSqueezeboxFunction}] {self.responseFromSqueezeboxServer.rstrip()}")

            self.serverResponse = self.responseFromSqueezeboxServer.split()

            self.serverResponseKeyword = self.serverResponse[0]
            try:
                self.serverResponseKeyword2 = self.serverResponse[1]
            except:
                self.serverResponseKeyword2 = ""
            self.logger.debug(f"HANDLE SERVER RESPONSE: KW1 = [{self.serverResponseKeyword}], KW2 = [{self.serverResponseKeyword2}]")

            #
            # Process response from server by analysing response and calling relevant handler
            #
            #   self.responseFromSqueezeboxServer  and self.serverResponse available to each handler (no need to pass as parameter)
            #

            match self.serverResponseKeyword:
                case "serverstatus":
                    self._handle_serverstatus(dev)  # dev = squeezebox server
                case "syncgroups":
                    self._handle_syncgroups(dev)  # dev = squeezebox server
                case "players":
                    self._handle_players(dev, response_items)  # dev = squeezebox server
                case "player":
                    if self.serverResponseKeyword2 == "id":
                        self._handle_player_id(dev)  # dev = squeezebox server
                case "readdirectory":
                    self._handle_readdirectory(dev)  # dev = squeezebox server
                case _:
                    if response_keyword[2:3] == ":":  # i.e. the response is something like "00:04:20:aa:bb:cc mode play" and is a response for a Player
                        self._handle_player(dev)  # dev = squeezebox server

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_serverstatus(self, dev):  # dev = squeezebox server
        try:
            self.globals[SERVERS][dev.id][STATUS] = "connected"
            dev.updateStateOnServer(key="status", value=self.globals[SERVERS][dev.id][STATUS])
            dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOn)

            self.responseToCommandServerstatus = re.findall(r"([^:]*:[^ ]*) *", self.responseFromSqueezeboxServer)  # Split the response into n times "AAAA : BBBB"

            for self.serverstatusResponseEntry in self.responseToCommandServerstatus:
                self.serverstatusResponseEntryElements = self.serverstatusResponseEntry.partition(":")

                match self.serverstatusResponseEntryElements[0]:
                    case "lastscan":
                        self.globals[SERVERS][dev.id][LAST_SCAN] = datetime.datetime.fromtimestamp(int(self.serverstatusResponseEntryElements[2])).strftime("%Y-%b-%d %H:%M:%S")
                        dev.updateStateOnServer(key="lastScan", value=self.globals[SERVERS][dev.id][LAST_SCAN])
                    case "version":
                        self.globals[SERVERS][dev.id][VERSION] = self.serverstatusResponseEntryElements[2]
                        dev.updateStateOnServer(key="version", value=self.globals[SERVERS][dev.id][VERSION])
                    case "info total albums":
                        self.globals[SERVERS][dev.id][TOTAL_ALBUMS] = self.serverstatusResponseEntryElements[2]
                        dev.updateStateOnServer(key="totalAlbums", value=self.globals[SERVERS][dev.id][TOTAL_ALBUMS])
                    case "info total artists":
                        self.globals[SERVERS][dev.id][TOTAL_ARTISTS] = self.serverstatusResponseEntryElements[2]
                        dev.updateStateOnServer(key="totalArtists", value=self.globals[SERVERS][dev.id][TOTAL_ARTISTS])
                    case "info total genres":
                        self.globals[SERVERS][dev.id][TOTAL_GENRES] = self.serverstatusResponseEntryElements[2]
                        dev.updateStateOnServer(key="totalGenres", value=self.globals[SERVERS][dev.id][TOTAL_GENRES])
                    case "info total songs":
                        self.globals[SERVERS][dev.id][TOTAL_SONGS] = self.serverstatusResponseEntryElements[2]
                        dev.updateStateOnServer(key="totalSongs", value=self.globals[SERVERS][dev.id][TOTAL_SONGS])
                    case "player count":
                        self.globals[SERVERS][dev.id][PLAYER_COUNT] = self.serverstatusResponseEntryElements[2]
                        loop = 0
                        while loop < int(self.serverstatusResponseEntryElements[2]):
                            self.globals[QUEUES][COMMAND_TO_SEND][dev.id].put(["players " + str(loop) +" 1"])
                            loop += 1

                self.logger.debug(
                    f"  = {self.serverstatusResponseEntry} [1={self.serverstatusResponseEntryElements[0]}] [2={self.serverstatusResponseEntryElements[1]}] [3={self.serverstatusResponseEntryElements[2]}]")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_syncgroups(self, dev):  # dev = squeezebox server
        try:
            self._playerRemoveSyncMaster()  # Set Sync master / slave off for all players

            for self.syncInfo in self.responseFromSqueezeboxServer.split("sync_"):
                if self.syncInfo[0:8] == "members:":
                    self.syncMembers = self.syncInfo[8:].split(",")
                    self.masterDevId = 0
                    for self.syncMember in self.syncMembers:
                        if self.masterDevId == 0:
                            self.masterMAC = self.syncMember.rstrip()
                            self.masterDevId = self._playerMACToDeviceId(self.syncMember.rstrip())
                            self.globals[PLAYERS][self.masterDevId][MASTER_PLAYER_ID] = 0
                            self.globals[PLAYERS][self.masterDevId][MASTER_PLAYER_ADDRESS] = ""

                            self.logger.debug(f"SyncMaster = '{self.syncMember}' = '{self.masterDevId}'")
                        else:
                            self.slaveDevId = self._playerMACToDeviceId(self.syncMember.rstrip())
                            self.globals[PLAYERS][self.slaveDevId ][MASTER_PLAYER_ID] = self.masterDevId
                            self.globals[PLAYERS][self.slaveDevId ][MASTER_PLAYER_ADDRESS] = self.masterMAC
                            self.globals[PLAYERS][self.slaveDevId ][SLAVE_PLAYER_IDS] = []
                            self.globals[PLAYERS][self.masterDevId][SLAVE_PLAYER_IDS].append(self.slaveDevId)

                            self.logger.debug(f"slavePlayerIds = '{self.globals[PLAYERS][self.masterDevId][SLAVE_PLAYER_IDS]}'")

            self._playerUpdateSync()

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_players(self, dev, response_items):  # dev = squeezebox server
        try:
            # self.logger.info(f"_HANDLE_PLAYERS:\n{self.responseFromSqueezeboxServer}\n")  # TODO: DEBUG
            playerInfo = dict()

            # for response_item in response_items:

            playerInfo[NAME] = "Not specified"
            playerInfo[MODEL] = "Unknown"
            playerInfo[IP_ADDRESS] = "Unknown"
            playerInfo[PORT] = "Unknown"
            playerInfo[POWER_UI] = "disconnected"
            playerInfo[PLAYER_ID] = "disconnected"

            self.serverResponsePlayersElementName = re.findall(r"(?<=name:)(.*) seq_no:", self.responseFromSqueezeboxServer)

            playerInfo[NAME] = self.serverResponsePlayersElementName[0]
    
            self.serverResponsePlayersElementModel = re.findall(r"(?<=model:)(.*) modelname:", self.responseFromSqueezeboxServer)
     
            playerInfo[MODEL] = self.serverResponsePlayersElementModel[0]
            match playerInfo[MODEL]:
                case "baby":
                    playerInfo[MODEL] = "Squeezebox Radio"
                case "boom":
                    playerInfo[MODEL] = "Squeezebox Boom"
                case "receiver":
                    playerInfo[MODEL] = "Squeezebox Receiver"
                case "fab4":
                    playerInfo[MODEL] = "Squeezebox Touch"
                case _:
                    playerInfo[MODEL] = f"Squeezebox Unknown: [{playerInfo[MODEL]}]"

            self.logger.debug(str(f"DISCONNECT DEBUG [MODEL]: {playerInfo[MODEL]}"))

            self.serverResponsePlayers = re.findall(r"([^:]*:[^ ]*) *", self.responseFromSqueezeboxServer.rstrip())

            for self.serverResponsePlayersEntry in self.serverResponsePlayers:
                self.logger.debug(str(f"DISCONNECT DEBUG [ENTRY]: {self.serverResponsePlayersEntry}"))
                self.serverResponsePlayersEntryElements = self.serverResponsePlayersEntry.partition(":")

                match self.serverResponsePlayersEntryElements[0]:
                    case "playerid":
                        playerInfo[PLAYER_ID] = self.serverResponsePlayersEntryElements[2]
                    case "ip":
                        self.serverStatusAddressElements = self.serverResponsePlayersEntryElements[2].partition(":")
                        playerInfo[IP_ADDRESS] = self.serverStatusAddressElements[0]
                        playerInfo[PORT] = self.serverStatusAddressElements[2]
                    case "connected":
                        self.logger.debug(f"DISCONNECT DEBUG [CONNECTED]: {self.serverResponsePlayersEntryElements[2]}")
                        if self.serverResponsePlayersEntryElements[2] == "1":
                            playerInfo[CONNECTED] = True  # Player is connected
                        else:
                            playerInfo[CONNECTED] = False  # Player is disconnected

            self.playerKnown = False
            for playerDev in indigo.devices.iter(filter="self"):
                if playerDev.address == playerInfo[PLAYER_ID]:
                    self.playerKnown = True
                    break

            if not self.playerKnown:
                self.logger.info(f"New player discovered with Address: [{playerInfo[PLAYER_ID]}] ... creating device ...")

                playerDev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                    address=playerInfo[PLAYER_ID],
                    name=playerInfo[NAME], 
                    description=playerInfo[MODEL],
                    pluginId=f"{CF_BUNDLE_IDENTIFIER}",
                    deviceTypeId="squeezeboxPlayer",
                    props={"mac":playerInfo[PLAYER_ID]},
                    folder=self.deviceFolderId)

                self.globals[PLAYERS][playerDev.id] = dict()

                key_value_list = list()
                self.deviceUpdateKeyValueList(False, playerDev, NAME, key_value_list, "name", playerInfo[NAME])
                self.deviceUpdateKeyValueList(False, playerDev, MODEL, key_value_list, "model", playerInfo[MODEL])
                self.deviceUpdateKeyValueList(False, playerDev, MAC, key_value_list, "mac", playerInfo[PLAYER_ID])
                self.deviceUpdateKeyValueList(True, playerDev, SERVER_ID, key_value_list, "serverId", dev.id)
                self.deviceUpdateKeyValueList(True, playerDev, SERVER_NAME, key_value_list, "serverName", dev.name)
                dev.updateStatesOnServer(key_value_list)

                # self.logger.debug(f"Calling deviceStartComm for device: {playerInfo[PLAYER_ID]}")
                self.deviceStartComm(playerDev)
                # self.logger.debug(f"Called deviceStartComm for device: {playerInfo[PLAYER_ID]}")
                self.logger.info(f"Newly discovered player with Address [{playerInfo[PLAYER_ID]}] has now been created.")

            else:
                self.deviceStateUpdate(True, playerDev, CONNECTED, "connected", playerInfo[CONNECTED])  # noqa
                if not playerInfo[CONNECTED]:
                    self.deviceStateUpdate(True, playerDev, POWER_UI, "powerUi", "disconnected")
                else:
                    self.deviceStateUpdate(True, playerDev, POWER_UI, "powerUi", "off")

                if not self.globals[PLAYERS][playerDev.id][CONNECTED]:
                    self.logger.info(f"Existing Player '{playerDev.name}' with address [{playerDev.address}] confirmed as disconnected from server '{dev.name}'")                    
                else:
                    self.logger.info(f"Existing Player '{playerDev.name}' with address [{playerDev.address}] confirmed as connected to server '{dev.name}'")

                self.deviceStateUpdate(True, playerDev, NAME, "name", playerInfo[NAME])
                self.deviceStateUpdate(True, playerDev, MODEL, "model", playerInfo[MODEL])
                self.deviceStateUpdate(True, playerDev, SERVER_ID, "serverId", dev.id)
                self.deviceStateUpdate(True, playerDev, SERVER_NAME, "serverName", dev.name)

                playerDevMac = playerDev.pluginProps["mac"]
                if playerDevMac == "":
                    playerDevProps = playerDev.pluginProps
                    playerDevProps[MAC] = playerInfo[PLAYER_ID]
                    playerDev.replacePluginPropsOnServer(playerDevProps)
                    self.deviceStateUpdate(True, playerDev, MAC, "mac", playerInfo[PLAYER_ID])

                # Update state of player connection / power    

            self.deviceStateUpdate(True, playerDev, IP_ADDRESS, "ipAddress", playerInfo[IP_ADDRESS])
            self.deviceStateUpdate(True, playerDev, PORT, "portAddress", playerInfo[PORT])


            self.deviceStateUpdate(True, playerDev, POWER_UI, "powerUi", playerInfo[POWER_UI])

            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put(["syncgroups ?"])

            self.deviceStateUpdateWithIcon(True, playerDev, STATE, "state", playerInfo[POWER_UI], indigo.kStateImageSel.PowerOff)

            try:
                shutil.copy2(self.globals[COVER_ART][COVER_ART_NO_FILE],self.globals[PLAYERS][playerDev.id][COVER_ART_FILE])
            except Exception as exception_error:
                self.logger.error(f"Cover Art Error - IN: {self.globals[COVER_ART][COVER_ART_NO_FILE]}")
                self.logger.error(f"Cover Art Error - OUT: {self.globals[PLAYERS][playerDev.id][COVER_ART_FILE]}")
                error_message = f"Cover Art Error - ERR: {exception_error}"
                self.exception_handler(error_message, True)  # Log error and display failing statement

            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " power ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " mode ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " artist ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " album ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " title ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " genre ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " duration ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " remote ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " playerpref volume ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " playerpref maintainSync ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " playlist index ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " playlist tracks ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " playlist repeat ?"])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerDev.id][SERVER_ID]].put([playerDev.address + " playlist shuffle ?"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_id(self, dev):  # dev = squeezebox server
        try:
            playerNumber = int(self.serverResponse[2])
            playerId = urllib.parse.unquote(self.serverResponse[3])

            playerKnown = False
            for playerDev in indigo.devices.iter(filter="self"):
                if playerDev.address == playerId:
                    playerKnown = True
                    self.logger.debug(f"Processing known player [{str(playerNumber)}]: '{playerId}'")
                    break
            if not playerKnown:
                playerName = "New Squeezebox Player"
                playerDescription = "New Squeezebox Player"
                playerModel = "unknown"
                playerDev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                    address=self.playerId,
                    name=playerName, 
                    description=playerDescription, 
                    pluginId=f"{CF_BUNDLE_IDENTIFIER}",
                    deviceTypeId="squeezeboxPlayer",
                    props={"mac":playerId},
                    folder=self.deviceFolderId)
                playerDev.updateStateOnServer(key="name", value=playerName)
                playerDev.updateStateOnServer(key="model", value=playerModel)
                playerDev.updateStateOnServer(key="serverId", value=dev.id)
                playerDev.updateStateOnServer(key="serverName", value=dev.name)

            self.playerIdQuoted = urllib.parse.quote(self.playerId)  # ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][dev.Id][SERVER_ID]].put([self.playerId + " status 0 999 tags:"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_readdirectory(self, dev):  # dev = squeezebox server
        try:
            self.logger.debug(f"READDIRECTORY = [{self.serverResponse[3]}] [{self.serverResponse[6]}]")

            self.readDirectory = []
            parts = re.split("(\w+:)", self.responseFromSqueezeboxServer)
            if parts[0]:
                self.readDirectory.append(parts[0].strip())
            groups = zip(*[parts[i+1::2] for i in range(2)])
            self.readDirectory.extend(["".join(group).strip() for group in groups])

            self.readDirectoryFunction = ""
            self.readDirectoryDevice = 0
            self.readDirectoryFolder = ""
            self.readDirectoryFilter = ""
            self.readDirectoryPath = ""
            self.readDirectoryCount = 0
            self.readDirectoryIsFolder = 0

            for self.readDirectoryEntry in self.readDirectory:
                self.readDirectoryEntryElements = self.readDirectoryEntry.partition(":")
                self.logger.debug(f"SELF.RD-ELEMENTS: [{self.readDirectoryEntryElements[0]}] [{self.readDirectoryEntryElements[1]}] [{self.readDirectoryEntryElements[2]}]")

                self.readDirectoryKeyword = self.readDirectoryEntryElements[0]
                self.readDirectoryValue = self.readDirectoryEntryElements[2].rstrip()

                match self.readDirectoryKeyword:
                    case "autologFunction":
                        self.readDirectoryFunction = self.readDirectoryValue
                    case "autologDevice":
                        self.readDirectoryDevice = self.readDirectoryValue
                    case "folder":
                        self.readDirectoryFolder = self.readDirectoryValue
                    case "filter":
                        self.readDirectoryFilter = self.readDirectoryValue
                    case "path":
                        self.readDirectoryPath = self.readDirectoryValue
                    case "count":
                        self.readDirectoryCount = self.readDirectoryValue
                    case "isfolder":
                        self.readDirectoryIsFolder = self.readDirectoryValue

            self.logger.debug(
                f"SELF.READDIRECTORY: Func=[{self.readDirectoryFunction}], Dev=[{'Unknown'}], Fol=[{self.readDirectoryFolder}], Fil=[{self.readDirectoryFilter}], Path=[{self.readDirectoryPath}], C=[{self.readDirectoryCount}], IsF=[{self.readDirectoryIsFolder}]")

            self.fileCount = self.serverResponse[6].partition(":")
            self.fileCheckModeDev = self.serverResponse[3].partition(":")
            self.logger.debug(f"SELF.FILECOUNT = [{self.readDirectoryCount}]")

            if self.readDirectoryFunction == "AnnouncementCheck":
                if self.readDirectoryCount == "1":
                    pass
                else:
                    self.globals[ANNOUNCEMENT][FILE_CHECK_OK] = False
                    self.logger.error(
                        f"Announcement File [{self.readDirectoryFolder}/{self.readDirectoryFilter}] not found. Play Announcement on '{indigo.devices[int(self.readDirectoryDevice)].name}' not actioned.")
            elif self.readDirectoryFunction == "PlaylistCheck":
                if self.readDirectoryCount == "1":
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][int(self.readDirectoryDevice)][SERVER_ID]].put([
                        self.globals[PLAYERS][int(self.readDirectoryDevice)][MAC] + " playlist play " + str(self.readDirectoryPath).replace(" ", "%20")])
                else:
                    self.logger.error(
                        f"Playlist File [{self.readDirectoryFolder}/{self.readDirectoryFilter}] not found. Play Playlist on '{indigo.devices[int(self.readDirectoryDevice)].name}' not actioned.")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player(self, devServer):  # dev = squeezebox server
        try:
            self.playerKnown = False
            for devPlayer in indigo.devices.iter(filter="self"):
                if devPlayer.address == self.serverResponseKeyword:
                    self.playerKnown = True
                    break

            if not self.playerKnown:
                self.logger.info(f"Now handling unknown player: [{self.serverResponseKeyword}]")
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put(["serverstatus 0 0 subscribe:0"])

                return

            self.replyPlayerMAC = self.serverResponseKeyword
            self.replyPlayerId = devPlayer.id  # noqa

            # Determine master (sync) player MAC and ID
            if self.globals[PLAYERS][self.replyPlayerId][MASTER_PLAYER_ADDRESS] != "":
                self.masterPlayerMAC = self.globals[PLAYERS][self.replyPlayerId][MASTER_PLAYER_ADDRESS]
                self.masterPlayerId = self.globals[PLAYERS][self.replyPlayerId][MASTER_PLAYER_ID]
            else:
                self.masterPlayerMAC = self.replyPlayerMAC
                self.masterPlayerId = self.replyPlayerId

            self._handle_player_detail(devServer,devPlayer)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail(self, devServer, devPlayer):
        try:
            match self.serverResponse[1]:
                case "sync":
                    self._handle_player_detail_sync(devServer, devPlayer)
                case "songinfo":
                    self._handle_player_detail_songinfo(devServer, devPlayer)
                case "favorites":
                    self._handle_player_detail_favorites(devServer, devPlayer)
                case "playlist":
                    match self.serverResponse[2]:
                        case "open":
                            self._handle_player_detail_playlist_open(devServer, devPlayer)
                        case "newsong":
                            self._handle_player_detail_playlist_newsong(devServer, devPlayer)
                        case "pause":
                            self._handle_player_detail_playlist_pause(devServer, devPlayer)
                        case "name":
                            self._handle_player_detail_playlist_name(devServer, devPlayer)
                        case "index":
                            self._handle_player_detail_playlist_index(devServer, devPlayer)
                        case "tracks":
                            self._handle_player_detail_playlist_tracks(devServer, devPlayer)
                        case "repeat":
                            self._handle_player_detail_playlist_repeat(devServer, devPlayer)
                        case "shuffle":
                            self._handle_player_detail_playlist_shuffle(devServer, devPlayer)
                        case "load_done":
                            self._handle_player_detail_playlist_load_done(devServer, devPlayer)
                        case "stop":
                            self._handle_player_detail_playlist_stop(devServer, devPlayer)
                case "pause":
                    self._handle_player_detail_pause(devServer, devPlayer)
                case "play":
                    self._handle_player_detail_play(devServer, devPlayer)
                case "prefset":
                    self._handle_player_detail_prefset(devServer, devPlayer)
                case "mixer":
                    self._handle_player_detail_mixer(devServer, devPlayer)
                case "playerpref":
                    self._handle_player_detail_playerpref(devServer, devPlayer)
                case "maintainSync":
                    self._handle_player_detail_maintainSync(devServer, devPlayer)
                case "artist":
                    self._handle_player_detail_artist(devServer, devPlayer)
                case "album":
                    self._handle_player_detail_album(devServer, devPlayer)
                case "title":
                    self._handle_player_detail_title(devServer, devPlayer)
                case "genre":
                    self._handle_player_detail_genre(devServer, devPlayer)
                case "duration":
                    self._handle_player_detail_duration(devServer, devPlayer)
                case "autologMixerMuteAll":
                    self._handle_player_detail_autologMixerMuteAll(devServer, devPlayer)
                case "autologMixerUnmuteAll":
                    self._handle_player_detail_autologMixerUnmuteAll(devServer, devPlayer)
                case "autologMixerToggleMuteAll":
                    self._handle_player_detail_autologMixerToggleMuteAll(devServer, devPlayer)
                case "remote":
                    self._handle_player_detail_remote(devServer, devPlayer)
                case "client":
                    self._handle_player_detail_client(devServer, devPlayer)
                case "autologAnnouncementRequest":
                    self._handle_player_detail_autologAnnouncementRequest(devServer, devPlayer)
                case "autologAnnouncementInitialise":
                    self._handle_player_detail_autologAnnouncementInitialise(devServer, devPlayer)
                case "power":
                    self._handle_player_detail_power(devServer, devPlayer)
                case "mode":
                    self._handle_player_detail_mode(devServer, devPlayer)
                case "time":
                    self._handle_player_detail_time(devServer, devPlayer)
                case "autologAnnouncementSaveState":
                    self._handle_player_detail_autologAnnouncementSaveState(devServer, devPlayer)
                case "autologAnnouncementPlay":
                    self._handle_player_detail_autologAnnouncementPlay(devServer, devPlayer)
                case "autologAnnouncementRestartPlaying":
                    self._handle_player_detail_autologAnnouncementRestartPlaying(devServer, devPlayer)
                case "autologAnnouncementEnded":
                    self._handle_player_detail_autologAnnouncementEnded(devServer, devPlayer)
                case _:
                    pass

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_sync(self, devServer, devPlayer):
        try:
            self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put(["syncgroups ?"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_songinfo(self, devServer, devPlayer):
        try:
            # artworkUrl = "00:04:20:29:46:b9 songinfo 0 100 url:pandora://495903246413988319.mp3 tags:aK id:-140590555861760 title:Timber artist:Pitbull artwork_url:http://cont-sv5-2.pandora.com/images/public/amz/0/8/5/7/800037580_500W_497H.jpg"

            artworkUrl = self.responseFromSqueezeboxServer.split("artwork_url:")
            if len(artworkUrl) == 2:
                artworkUrl = artworkUrl[1]  # i.e. artwork_url was found
            else:
                artworkUrl = str(f"music/current/cover.jpg?player={self.globals[PLAYERS][self.replyPlayerId][MAC]}")
            # artworkUrl = artworkUrl.split("artwork_url:")[1]
            # self.logger.debug(f"SONGINFO: 'artworkUrl' = {artworkUrl}")
            if artworkUrl[0:7] != "http://" and artworkUrl[0:8] != "https://":
                artworkUrl = f"http://{self.globals[SERVERS][devServer.id][IP_ADDRESS]}:9000/{artworkUrl}"

            # self.logger.debug(f"ARTWORKURL: 'artworkUrl' = {artworkUrl}")

            coverArtToRetrieve = urlopen(artworkUrl)
            coverArtFile = f"{self.globals[PLAYERS][self.replyPlayerId][COVER_ART_FOLDER]}/coverart.jpg"
            # self.logger.debug(f"COVERARTFILE: {coverArtFile}")

            localFile = open(coverArtFile, "wb")
            localFile.write(coverArtToRetrieve.read())
            localFile.close()

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_favorites(self, devServer, devPlayer):
        try:
            pass
            #     self.logger.info(f"FAVORITES = {self.serverResponse}")
            #     if self.serverResponse[2] == "playlist":  # favorites playlist
            #         self.logger.info("FAVORITES PLAYLIST")
            #         if self.serverResponse[3] == "play":  # favorites playlist play
            #             self.logger.info(f"FAVORITES PLAYLIST PLAY = {self.serverResponse[4]}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement


    def _handle_player_detail_playlist_open(self, devServer, devPlayer):
        try:
            songUrl = self.serverResponse[3]

            if (songUrl[0:7] == "file://" or songUrl[0:14] == "spotify:track:" or songUrl[0:10] == "pandora://"
                    or songUrl[0:8] == "qobuz://" or songUrl[0:9] == "deezer://" or songUrl[0:9] == "sirius://"):
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist open")
                for playerIdToProcess in playerIdsToProcess:
                    if self.globals[PLAYERS][playerIdToProcess][POWER_UI] != "disconnected":
                        self.deviceStateUpdate(True, devPlayer, SONG_URL, "songUrl", songUrl)
                        self.logger.debug(f"{devPlayer.name} is playing songUrl {songUrl}")

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_newsong(self, devServer, devPlayer):
        try:
            if self.globals[ANNOUNCEMENT][STEP] != "loaded":
                # self.logger.debug(f"NEWSONG: 'announcementStep' = {self.globals[ANNOUNCEMENT][STEP]}")
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " artist ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " album ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " title ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " genre ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " duration ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " remote ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " mode ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " playlist name ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " playlist index ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.masterPlayerMAC + " playlist tracks ?"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_pause(self, devServer, devPlayer):
        try:
            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist pause")

            for playerIdToProcess in playerIdsToProcess:
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerIdToProcess][SERVER_ID]].put([indigo.devices[playerIdToProcess].address + " mode ?"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_name(self, devServer, devPlayer):
        try:
            try:
                self.playlistName = self.serverResponse[3]
                self.playlistName = self.responseFromSqueezeboxServer.split("playlist name")[1]
            except:
                self.playlistName = ""

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist name")

            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][POWER_UI] != "disconnected":
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistName", value=self.playlistName)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_index(self, devServer, devPlayer):
        try:
            try:
                self.playlistIndex = self.serverResponse[3]
                self.playlistTrackNumber = str(int(self.playlistIndex) + 1)
            except:
                self.playlistIndex = "0"
                self.playlistTrackNumber = "1"

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist index")

            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][POWER_UI] != "disconnected":
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistIndex", value=self.playlistIndex)
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTrackNumber", value=self.playlistTrackNumber)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_tracks(self, devServer, devPlayer):
        try:
            self.playlistTracksTotal = self.serverResponse[3]

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist tracks")

            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][POWER_UI] != "disconnected":
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTracksTotal", value=self.playlistTracksTotal)
                    if self.playlistTracksTotal == "0":
                        indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTrackNumber", value="0")
                        tracksUi = ""
                    else:
                        tracksUi = f"{indigo.devices[playerIdToProcess].states['playlistTrackNumber']} of {self.playlistTracksTotal}"
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTracksUi", value=tracksUi)

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_repeat(self, devServer, devPlayer):
        try:
            if len(self.serverResponse) > 3:
                match self.serverResponse[3]:
                    case "0":
                        self.repeat = "off"
                    case "1":
                        self.repeat = "song"
                    case "2":
                        self.repeat = "playlist"
                    case _:
                        self.repeat = "?"
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist repeat")
                for playerIdToProcess in playerIdsToProcess:
                    self.globals[PLAYERS][playerIdToProcess][REPEAT] = self.serverResponse[3]
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="repeat", value=self.repeat)

            if self.globals[ANNOUNCEMENT][STEP] == "initialise":
                self.logger.debug(f"ACT=[initialise]: {indigo.devices[self.masterPlayerId].name}")
                if len(self.serverResponse) > 3:
                    self.globals[PLAYERS][self.masterPlayerId][SAVED_REPEAT] = self.serverResponse[3]
                else:
                    self.globals[PLAYERS][self.masterPlayerId][SAVED_REPEAT] = "?"

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_shuffle(self, devServer, devPlayer):
        try:
            if len(self.serverResponse) > 3:
                match self.serverResponse[3]:
                    case "0":
                        self.shuffle = "off"
                    case "1":
                        self.shuffle = "songs"
                    case "2":
                        self.shuffle = "albums"
                    case _:
                        self.shuffle = "?"
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist shuffle")
                for playerIdToProcess in playerIdsToProcess:
                    self.globals[PLAYERS][playerIdToProcess][SHUFFLE] = self.serverResponse[3]
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="shuffle", value=self.shuffle)

            if self.globals[ANNOUNCEMENT][STEP] == "initialise":
                self.logger.debug(f"ACT=[initialise]: {indigo.devices[self.masterPlayerId].name}")
                if len(self.serverResponse) > 3:
                    self.globals[PLAYERS][self.masterPlayerId][SAVED_SHUFFLE] = self.serverResponse[3]
                else:
                    self.globals[PLAYERS][self.masterPlayerId][SAVED_SHUFFLE] = "?"


        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_load_done(self, devServer, devPlayer):
        try:
            if self.globals[ANNOUNCEMENT][STEP] == "play":
                self.logger.debug(f"ACT=[play]: {indigo.devices[self.masterPlayerId].name}")
                self.globals[ANNOUNCEMENT][STEP] = "loaded"
                self.logger.debug(f"NXT=[loaded]: {indigo.devices[self.masterPlayerId].name}")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playlist_stop(self, devServer, devPlayer):
        try:
            # self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " mode ?")

            if self.globals[PLAYERS][self.replyPlayerId][POWER_UI] != "disconnected":
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist stop")

                for playerIdToProcess in playerIdsToProcess:
                    self.globals[PLAYERS][playerIdToProcess][MODE] = "stop"
                    stateDescription = "stopped"
                    indigo.devices[playerIdToProcess].updateStateOnServer(key="state", value=stateDescription)
                    stateImage = indigo.kStateImageSel.AvStopped
                    indigo.devices[self.replyPlayerId].updateStateImageOnServer(stateImage)

                if self.globals[ANNOUNCEMENT][STEP] == "loaded":
                    self.logger.debug(f"ACT=[loaded]: {indigo.devices[self.masterPlayerId].name}")
                    self.globals[ANNOUNCEMENT][STEP] = "stopped"
                    self.logger.debug(f"NXT=[stopped]: {indigo.devices[self.masterPlayerId].name}")

                    # reload saved playlist
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                        [self.replyPlayerMAC + " playlist resume autolog_" + str(self.masterPlayerId) + " wipePlaylist:1 noplay:1"])

                    #  + self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_PLAYLIST_NO_PLAY]

                    # for master sync player
                    #     if saved repeat != 0:
                    #         restore repeat
                    #     if saved shuffle != 0:
                    #         restore shuffle
                    #     if time != 0 and shuffle = 0:
                    #         restore time (seconds only)

                    if self.globals[PLAYERS][self.masterPlayerId][SAVED_REPEAT] != "0":
                        self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                            [self.masterPlayerMAC + " playlist repeat " + self.globals[PLAYERS][self.masterPlayerId][SAVED_REPEAT]])
                    if self.globals[PLAYERS][self.masterPlayerId][SAVED_SHUFFLE] != "0":
                        self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                            [self.masterPlayerMAC + " playlist shuffle " + self.globals[PLAYERS][self.masterPlayerId][SAVED_SHUFFLE]])
                    # if self.globals[PLAYERS][self.masterPlayerId][SAVED_TIME] !=  "0":
                    #     self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " time " + self.globals[PLAYERS][self.masterPlayerId][SAVED_TIME])
                    if self.globals[PLAYERS][self.masterPlayerId][SAVED_VOLUME] != self.globals[PLAYERS][self.masterPlayerId][VOLUME]:
                        self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                            [self.masterPlayerMAC + " mixer volume " + self.globals[PLAYERS][self.masterPlayerId][SAVED_VOLUME]])
                    if self.globals[PLAYERS][self.masterPlayerId][SAVED_MAINTAIN_SYNC] != self.globals[PLAYERS][self.masterPlayerId][MAINTAIN_SYNC]:
                        self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                            [self.masterPlayerMAC + " playerpref maintainSync " + self.globals[PLAYERS][self.masterPlayerId][SAVED_MAINTAIN_SYNC]])

                    # for each player (sync'd - master & slave)
                    #     if saved power is off:
                    #         turn off power

                    for slavePlayerId in self.globals[PLAYERS][self.masterPlayerId][SLAVE_PLAYER_IDS]:
                        if self.globals[PLAYERS][slavePlayerId][SAVED_VOLUME] != self.globals[PLAYERS][slavePlayerId][VOLUME]:
                            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put(
                                [self.globals[PLAYERS][slavePlayerId][MAC] + " mixer volume " + self.globals[PLAYERS][slavePlayerId][SAVED_VOLUME]])
                        if self.globals[PLAYERS][slavePlayerId][SAVED_MAINTAIN_SYNC] != self.globals[PLAYERS][slavePlayerId][MAINTAIN_SYNC]:
                            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put(
                                [self.globals[PLAYERS][slavePlayerId][MAC] + " playerpref maintainSync " + self.globals[PLAYERS][slavePlayerId][SAVED_MAINTAIN_SYNC]])

                        if self.globals[PLAYERS][slavePlayerId][SAVED_POWER] == "0":
                            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " power 0"])
                    if self.globals[PLAYERS][self.masterPlayerId][SAVED_POWER] == "0":
                        self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " power 0"])

                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " autologAnnouncementRestartPlaying"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_pause(self, devServer, devPlayer):
        try:
            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "pause")

            for playerIdToProcess in playerIdsToProcess:
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerIdToProcess][SERVER_ID]].put([indigo.devices[playerIdToProcess].address + " mode ?"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_play(self, devServer, devPlayer):
        try:
            self.logger.debug(f"NXT=[play]: {indigo.devices[self.masterPlayerId].name}")

            if self.globals[ANNOUNCEMENT][STEP] == "autologAnnouncementRestartPlaying":
                self.logger.debug(f"ACT=[autologAnnouncementRestartPlaying]: {indigo.devices[self.masterPlayerId].name}")
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "autologAnnouncementRestartPlaying")
                self.logger.debug(f"PLAYERIDSTOPROCESS: Len={len(playerIdsToProcess)}; {str(playerIdsToProcess)}")
                if self.globals[PLAYERS][self.masterPlayerId][SAVED_TIME] != "0":
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " pause"])
                    for playerIdToProcess in playerIdsToProcess:
                        mac = self._playerDeviceIdToMAC(playerIdToProcess)
                        self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerIdToProcess][SERVER_ID]].put([mac + " time " + self.globals[PLAYERS][self.masterPlayerId][SAVED_TIME]])
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " pause"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_prefset(self, devServer, devPlayer):
        try:
            if self.serverResponse[2] == "server":  # prefset server
                match self.serverResponse[3]:
                    case "volume":  # prefset server volume
                        self.globals[PLAYERS][self.replyPlayerId][VOLUME] = self.serverResponse[4]
                        indigo.devices[self.replyPlayerId].updateStateOnServer(key="volume", value=self.globals[PLAYERS][self.replyPlayerId][VOLUME])
                    case "power":  # prefset server power
                        pass
                    case "repeat":  # prefset server repeat
                        if len(self.serverResponse) > 4:
                            match self.serverResponse[4]:
                                case "0":
                                    self.repeat = "off"
                                case "1":
                                    self.repeat = "song"
                                case "2":
                                    self.repeat = "playlist"
                                case _:
                                    self.repeat = "?"
                        playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist repeat")
                        for playerIdToProcess in playerIdsToProcess:
                            self.globals[PLAYERS][playerIdToProcess][REPEAT] = self.repeat
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="repeat", value=self.repeat)

                        # if self.globals[ANNOUNCEMENT][STEP] == "autologAnnouncementInitialise":
                        #     if len(self.serverResponse) > 3:
                        #         self.globals[PLAYERS][self.masterPlayerId][SAVED_REPEAT] = self.serverResponse[3]
                        #     else:
                        #         self.globals[PLAYERS][self.masterPlayerId][SAVED_REPEAT] = "?"

                    case "shuffle":  # prefset server shuffle
                        if len(self.serverResponse) > 3:
                            match self.serverResponse[4]:
                                case "0":
                                    shuffle = "off"
                                case "1":
                                    shuffle = "songs"
                                case "2":
                                    shuffle = "albums"
                                case _:
                                    shuffle = "?"
                            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "playlist shuffle")
                            for playerIdToProcess in playerIdsToProcess:
                                self.deviceStateUpdate(True, devPlayer, SHUFFLE, "shuffle", shuffle)  # TODO: Check this is correct ???

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_mixer(self, devServer, devPlayer):
        try:
            if self.serverResponse[2] == "volume":  # mixer volume
                volume = self.serverResponse[3]
                # self.deviceStateUpdate(True,  devPlayer, "volume", volume)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_playerpref(self, devServer, devPlayer):
        try:
            if self.serverResponse[2] == "volume":  # playerpref volume
                volume = self.serverResponse[3]
                self.deviceStateUpdate(True, devPlayer, VOLUME, "volume", volume)

                if self.globals[ANNOUNCEMENT][STEP] == "initialise":
                    self.logger.debug(f"ACT=[initialise]: {indigo.devices[self.masterPlayerId].name}")
                    if len(self.serverResponse) > 3:
                        savedVolume = volume
                    else:
                        savedVolume = "?"
                    self.deviceStateUpdate(False, devPlayer, SAVED_VOLUME, "savedVolume", savedVolume)

            if self.serverResponse[2] == "maintainSync":  # playerpref maintainSync
                maintainSync = self.serverResponse[3]
                self.deviceStateUpdate(True, devPlayer, MAINTAIN_SYNC, "maintainSync", maintainSync)

                if self.globals[ANNOUNCEMENT][STEP] == "initialise":
                    self.logger.debug(f"ACT=[initialise]: {indigo.devices[self.masterPlayerId].name}")
                    if len(self.serverResponse) > 3:
                        savedMaintainSync = maintainSync
                    else:
                        savedMaintainSync = "?"
                    self.deviceStateUpdate(False, devPlayer, SAVED_MAINTAIN_SYNC, "savedMaintainSync", savedMaintainSync)


        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_maintainSync(self, devServer, devPlayer):
        try:
            pass
        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_artist(self, devServer, devPlayer):
        try:
            artistResponse = self.responseFromSqueezeboxServer.split(" ", 2)
            try:
                artist = artistResponse[2].rstrip()
            except:
                artist = ""

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "artist")
            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][CONNECTED]:
                    self.deviceStateUpdate(True, devPlayer, ARTIST, "artist", artist)

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_album(self, devServer, devPlayer):
        try:
            try:
                albumResponse = self.responseFromSqueezeboxServer.split(" ", 2)
                album = albumResponse[2].rstrip()
            except:
                album = ""

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "album")
            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][CONNECTED]:
                    self.deviceStateUpdate(True, devPlayer, ALBUM, "album", album)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_title(self, devServer, devPlayer):
        try:
            try:
                titleResponse = self.responseFromSqueezeboxServer.split(" ", 2)
                title = titleResponse[2].rstrip()
            except:
                title = ""

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "title")
            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][CONNECTED]:
                    self.deviceStateUpdate(True, devPlayer, TITLE, "title", title)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_genre(self, devServer, devPlayer):
        try:
            try:
                genreResponse = self.responseFromSqueezeboxServer.split(" ", 2)
                genre = genreResponse[2].rstrip()
            except:
                genre = ""

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "genre")
            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][CONNECTED]:
                    self.deviceStateUpdate(True, devPlayer, GENRE, "genre", genre)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_duration(self, devServer, devPlayer):
        try:
            durationUi = ""
            try:
                durationResponse = self.responseFromSqueezeboxServer.split(" ", 2)
                duration = durationResponse[2].rstrip()
                try:
                    m, s = divmod(float(duration), 60)
                    durationUi = str(f"{m:02d}:{s:02d}")
                except:
                    pass
            except:
                duration = ""

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "duration")
            for playerIdToProcess in playerIdsToProcess:
                if self.globals[PLAYERS][playerIdToProcess][CONNECTED]:
                    self.deviceStateUpdate(True, devPlayer, DURATION, "duration", duration)
                    self.deviceStateUpdate(True, devPlayer, DURATION_UI, "durationUi", durationUi)

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologMixerMuteAll(self, devServer, devPlayer):
        try:
            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "autologMixerMuteAll")
            for playerIdToProcess in playerIdsToProcess:
                mac = self._playerDeviceIdToMAC(playerIdToProcess)
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerIdToProcess][SERVER_ID]].put([f"{mac} mixer muting 1"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologMixerUnmuteAll(self, devServer, devPlayer):
        try:
            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "autologMixerUnmuteAll")
            for playerIdToProcess in playerIdsToProcess:
                mac = self._playerDeviceIdToMAC(playerIdToProcess)
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerIdToProcess][SERVER_ID]].put([f"{mac} mixer muting 0"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologMixerToggleMuteAll(self, devServer, devPlayer):
        try:
            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "autologMixerToggleMuteAll")
            for playerIdToProcess in playerIdsToProcess:
                mac = self._playerDeviceIdToMAC(playerIdToProcess)
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerIdToProcess][SERVER_ID]].put([f"{mac} mixer muting toggle"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_remote(self, devServer, devPlayer):
        try:
            try:
                remoteResponse = self.responseFromSqueezeboxServer.split(" ", 2)
                remoteStream = remoteResponse[2].rstrip()
            except:
                remoteStream = "0"

            if remoteStream == "1":
                remoteStream = "true"
                songUrl = self.globals[PLAYERS][self.replyPlayerId][SONG_URL]
                if songUrl != "":
                    mac = indigo.devices[self.replyPlayerId].address
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.replyPlayerId][SERVER_ID]].put([f"{mac} songinfo 0 100 url:{songUrl} tags:K"])
            else:
                remoteStream = "false"
                songUrl = self.globals[PLAYERS][self.replyPlayerId][SONG_URL]
                if songUrl != "":
                    mac = indigo.devices[self.replyPlayerId].address
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.replyPlayerId][SERVER_ID]].put([f"{mac} songinfo 0 100 url:{songUrl} tags:K"])

            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "remote")
            for playerIdToProcess in playerIdsToProcess:
                self.deviceStateUpdate(True, devPlayer, REMOTE_STREAM, "remoteStream", remoteStream)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_client(self, devServer, devPlayer):
        try:
            if self.serverResponse[2] == "new":  # client new
                self.connectingDevId = self._playerMACToDeviceId(self.serverResponse[0])
                if self.connectingDevId == 0:
                    self.logger.info(f"New Player [{self.serverResponse[0]}] detected.")
                else:
                    self.logger.info(f"{indigo.devices[self.connectingDevId].name} player [{self.serverResponse[0]}] connecting")
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put(["serverstatus 0 0 subscribe:-"])

            elif self.serverResponse[2] == "disconnect":  # client disconnect
                self.disconnectingDevId = self._playerMACToDeviceId(self.serverResponse[0])
                if self.disconnectingDevId == 0:
                    self.logger.info(f"Unknown player [{self.serverResponse[0]}] disconnecting")
                else:
                    self.logger.info(f"{indigo.devices[self.disconnectingDevId].name} player [{self.serverResponse[0]}] disconnecting")

                    self.globals[PLAYERS][self.disconnectingDevId][POWER_UI] = "disconnected"

                    # Reset any active announcements for known player

                    if self.globals[PLAYERS][self.disconnectingDevId][MASTER_PLAYER_ID] != 0:
                        self.masterPlayerId = self.globals[PLAYERS][self.disconnectingDevId][MASTER_PLAYER_ID]
                    else:
                        self.masterPlayerId = self.disconnectingDevId

                    self.globals[ANNOUNCEMENT][ACTIVE] = NO
                    self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_PLAY_INITIALISED] = False
                    self.logger.info(f"Reset Announcement actioned for {indigo.devices[self.disconnectingDevId].name} player [{self.serverResponse[0]}] as disconnected")
                    self.globals[QUEUES][ANNOUNCEMENT].queue.clear

                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put(["serverstatus 0 0 subscribe:-"])

            elif self.serverResponse[2] == "forget":  # client forget
                self.forgottenDevId = self._playerMACToDeviceId(self.serverResponse[0])
                if self.forgottenDevId == 0:
                    self.logger.info(f"Unknown player [{self.serverResponse[0]}] forgotten")
                else:
                    self.logger.info(f"{indigo.devices[self.forgottenDevId].name} player [{self.serverResponse[0]}] forgotten")
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put(["serverstatus 0 0 subscribe:-"])

            elif self.serverResponse[2] == "reconnect":  # client reconnect
                self.reconnectingDevId = self._playerMACToDeviceId(self.serverResponse[0])
                if self.reconnectingDevId == 0:
                    self.logger.info(f"Unknown player [{self.serverResponse[0]}] reconnecting")
                else:
                    self.logger.info(f"{indigo.devices[self.reconnectingDevId].name} player [{self.serverResponse[0]}] reconnecting")
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put(["serverstatus 0 0 subscribe:-"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologAnnouncementRequest(self, devServer, devPlayer):
        try:
            if self.globals[ANNOUNCEMENT][ACTIVE] == PENDING:
                self.globals[ANNOUNCEMENT][ACTIVE] = YES

                self.globals[ANNOUNCEMENT][STEP] = "request"
                self.logger.debug(f"NXT=[request]: {indigo.devices[self.masterPlayerId].name}")

                self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_UNIQUE_KEY] = self.serverResponse[2]
                announcementUniqueKey = self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_UNIQUE_KEY]

                self.globals[ANNOUNCEMENT][FILE_CHECK_OK] = True  # Assume file checks will be OK (Read Directory will set to False if not)
                if PREPEND in self.globals[ANNOUNCEMENT][announcementUniqueKey]:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([
                        f"readdirectory 0 1 autologFunction:AnnouncementCheck autologDevice:{str(self.masterPlayerId)} folder:{os.path.dirname(self.globals[ANNOUNCEMENT][announcementUniqueKey][PREPEND])} filter:{os.path.basename(self.globals[ANNOUNCEMENT][announcementUniqueKey][PREPEND])}"])

                if FILE in self.globals[ANNOUNCEMENT][announcementUniqueKey]:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([
                        f"readdirectory 0 1 autologFunction:AnnouncementCheck autologDevice:{str(self.masterPlayerId)} folder:{os.path.dirname(self.globals[ANNOUNCEMENT][announcementUniqueKey][FILE])} filter:{os.path.basename(self.globals[ANNOUNCEMENT][announcementUniqueKey][FILE])}"])

                if APPEND in self.globals[ANNOUNCEMENT][announcementUniqueKey]:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([
                        f"readdirectory 0 1 autologFunction:AnnouncementCheck autologDevice:{str(self.masterPlayerId)} folder:{os.path.dirname(self.globals[ANNOUNCEMENT][announcementUniqueKey][APPEND])} filter:{os.path.basename(self.globals[ANNOUNCEMENT][announcementUniqueKey][APPEND])}"])

                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([f"{self.masterPlayerMAC} autologAnnouncementInitialise"])


        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologAnnouncementInitialise(self, devServer, devPlayer):
        try:
            if not self.globals[ANNOUNCEMENT][FILE_CHECK_OK]:
                self.globals[ANNOUNCEMENT][ACTIVE] = NO
                self.logger.debug("Play Announcement Abandoned as file check failed")

            else:
                self.globals[ANNOUNCEMENT][STEP] = "initialise"
                self.logger.debug(f"NXT=[initialise]: {indigo.devices[self.masterPlayerId].name}")

                for slavePlayerId in self.globals[PLAYERS][self.masterPlayerId][SLAVE_PLAYER_IDS]:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " power ?"])
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " mode ?"])
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " playerpref volume ?"])
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " playerpref maintainSync ?"])

                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " power ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " mode ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playerpref volume ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playerpref maintainSync ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playlist repeat ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playlist shuffle ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " time ?"])
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " stop"])

                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " autologAnnouncementSaveState"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_power(self, devServer, devPlayer):
        try:
            if len(self.serverResponse) < 3:  # Check for Power Toggle - Need to query power to find power status
                self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([self.replyPlayerMAC + " power ?"])
            else:
                previousPower = self.globals[PLAYERS][devPlayer.id][POWER]  # Power setting before handling response

                power = self.serverResponse[2].rstrip()
                match power:
                    case "0":
                        powerUi = "off"
                    case "1":
                        powerUi = "on"
                    case _:
                        powerUi = "?"
                if not self.globals[PLAYERS][devPlayer.id][CONNECTED]:
                    powerUi = "disconnected"

                self.deviceStateUpdate(True, devPlayer, POWER, "power", power)
                self.deviceStateUpdate(True, devPlayer, POWER_UI, "powerUi", powerUi)

                if self.globals[ANNOUNCEMENT][STEP] == "initialise":
                    self.logger.debug(f"ACT=[initialise]: {indigo.devices[self.masterPlayerId].name}")
                    self.globals[PLAYERS][devPlayer.id][SAVED_POWER] = power

                if power != previousPower:
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][devPlayer.id][SERVER_ID]].put(["syncgroups ?"])

                    if self.globals[PLAYERS][devPlayer.id][POWER_UI] == "on" and self.globals[ANNOUNCEMENT][STEP] != "initialise":
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " autolog detected power on"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " mode ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " artist ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " album ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " title ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " genre ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " duration ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " remote ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " playerpref volume ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " playerpref maintainSync ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " playlist index ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " playlist tracks ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " playlist repeat ?"])
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " playlist shuffle ?"])
                    else:
                        self.globals[QUEUES][COMMAND_TO_SEND][devServer.id].put([devPlayer.address + " mode ?"])

                if power == "0" or not self.globals[PLAYERS][devPlayer.id][CONNECTED]:
                    try:
                        shutil.copy2(self.globals[COVER_ART][COVER_ART_NO_FILE], self.globals[PLAYERS][devPlayer.id][COVER_ART_FILE])
                    except Exception as exception_error:
                        self.logger.error(f"Cover Art Error - IN: {self.globals[COVER_ART][COVER_ART_NO_FILE]}")
                        self.logger.error(f"Cover Art Error - OUT: {self.globals[PLAYERS][devPlayer.id][COVER_ART_FILE]}")
                        error_message = f"Cover Art Error - ERR: {exception_error}"
                        self.exception_handler(error_message, True)  # Log error and display failing statement

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_mode(self, devServer, devPlayer):
        try:
            self.deviceStateUpdate(True, devPlayer, MODE, "mode", self.serverResponse[2])

            match self.globals[PLAYERS][devPlayer.id][MODE]:
                case "stop":
                    state = "stopped"
                case "pause":
                    state = "paused"
                case "play":
                    state = "playing"
                case _:
                    state = "unknown"

            if (self.globals[PLAYERS][devPlayer.id][POWER_UI] == "off") or (self.globals[PLAYERS][devPlayer.id][POWER_UI] == "disconnected"):
                state = self.globals[PLAYERS][devPlayer.id][POWER_UI]
                key_value_list = list()
                key_value_list.append({"key": "artist", "value": ""})
                key_value_list.append({"key": "album", "value": ""})
                key_value_list.append({"key": "title", "value": ""})
                key_value_list.append({"key": "genre", "value": ""})
                key_value_list.append({"key": "duration", "value": ""})
                key_value_list.append({"key": "remoteStream", "value": ""})
                key_value_list.append({"key": "playlistTrackNumber", "value": ""})
                key_value_list.append({"key": "playlistTracksTotal", "value": ""})
                key_value_list.append({"key": "playlistTracksUi", "value": ""})
                devPlayer.updateStatesOnServer(key_value_list)

            self.deviceStateUpdate(True, devPlayer, STATE, "state", state)

            match state:
                case "unknown":
                    stateImage = indigo.kStateImageSel.PowerOff
                case "stopped":
                    stateImage = indigo.kStateImageSel.AvStopped
                case "paused":
                    stateImage = indigo.kStateImageSel.AvPaused
                case "playing":
                    stateImage = indigo.kStateImageSel.AvPlaying
                case "off" | "disconnected":
                    stateImage = indigo.kStateImageSel.PowerOff
                case _:
                    stateImage = indigo.kStateImageSel.PowerOff

            indigo.devices[devPlayer.id].updateStateImageOnServer(stateImage)

            self.logger.debug("state image selector: " + str(indigo.devices[self.replyPlayerId].displayStateImageSel))

            if self.globals[ANNOUNCEMENT][STEP] == "initialise":
                self.logger.debug(f"ACT=[initialise]: {indigo.devices[self.masterPlayerId].name}")
                self.globals[PLAYERS][self.masterPlayerId][SAVED_MODE] = self.serverResponse[2]
                if self.globals[PLAYERS][self.masterPlayerId][SAVED_MODE] == "play":
                    self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_PLAYLIST_NO_PLAY] = "0"
                else:
                    self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_PLAYLIST_NO_PLAY] = "1"



        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_time(self, devServer, devPlayer):
        try:
            self.globals[PLAYERS][self.masterPlayerId][TIME] = self.serverResponse[2]
            if self.globals[ANNOUNCEMENT][STEP] == "initialise":
                self.logger.debug(f"ACT=[initialise]: {indigo.devices[self.masterPlayerId].name}")
                self.globals[PLAYERS][self.masterPlayerId][SAVED_TIME] = self.serverResponse[2].split(".")[0]

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologAnnouncementSaveState(self, devServer, devPlayer):
        try:
            self.globals[ANNOUNCEMENT][STEP] = "saveState"
            self.logger.debug(f"NXT=[saveState]: {indigo.devices[self.masterPlayerId].name}")

            for slavePlayerId in self.globals[PLAYERS][self.masterPlayerId][SLAVE_PLAYER_IDS]:
                # for each slave player

                if self.globals[PLAYERS][slavePlayerId][SAVED_POWER] == "0":
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " power 1"])

                if self.globals[PLAYERS][slavePlayerId][SAVED_MAINTAIN_SYNC] != "0":
                    self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " playerpref maintainSync 0"])

                # if self.globals[PLAYERS][slavePlayerId][SAVED_VOLUME != "50":
                #     self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][slavePlayerId][SERVER_ID]].put([self.globals[PLAYERS][slavePlayerId][MAC] + " mixer volume 50")  # FIX THIS !!!!!!

            if self.globals[PLAYERS][self.masterPlayerId][SAVED_MAINTAIN_SYNC] != "0":
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playerpref maintainSync 0"])

            # if saved repeat != 0
            #    turn repeat off
            if self.globals[PLAYERS][self.masterPlayerId][SAVED_REPEAT] != "0":
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playlist repeat 0"])

            # if saved shuffle != 0
            #     turn shuffle off
            if self.globals[PLAYERS][self.masterPlayerId][SAVED_SHUFFLE] != "0":
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playlist shuffle 0"])

            #  save playlist
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                [self.masterPlayerMAC + " playlist save autolog_" + str(self.masterPlayerId) + " silent:1"])

            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " autologAnnouncementPlay"])

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologAnnouncementPlay(self, devServer, devPlayer):
        try:
            self.globals[ANNOUNCEMENT][STEP] = "play"
            self.logger.debug(f"NXT=[play]: {indigo.devices[self.masterPlayerId].name}")

            announcementUniqueKey = self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_UNIQUE_KEY]

            # Set Volume
            playerIdsToProcess = self._playersToProcess(self.replyPlayerId, "autologAnnouncementPlay Volume")
            for playerIdToProcess in playerIdsToProcess:
                mac = self._playerDeviceIdToMAC(playerIdToProcess)
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][playerIdToProcess][SERVER_ID]].put([mac + " mixer volume " + self.globals[ANNOUNCEMENT][announcementUniqueKey][VOLUME]])

            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playlist clear"])

            if self.globals[ANNOUNCEMENT][announcementUniqueKey][OPTION] == "file":
                announcementFile = self.globals[ANNOUNCEMENT][announcementUniqueKey][FILE]
            else:
                try:
                    nssp = NSSpeechSynthesizer
                    announcementFile = str(f"{self.globals[ANNOUNCEMENT][TEMPORARY_FOLDER]}/{ANNOUNCEMENTS_SUB_FOLDER}/{str(indigo.devices[self.masterPlayerId].id)}/autologSpeech.aif")
                    indigo.server.log(f"announcementFile = {announcementFile}")
                    # announcementFile = "autologSpeech.aiff"
                    url = NSURL.fileURLWithPath_(announcementFile)  # TODO: SORT THIS OUT!
                    indigo.server.log(f"NSURL.fileURLWithPath_ = {url}")
                    # url = NSURL.fileURLWithPath_isDirectory_("~/Documents", announcementFile)
                    ve = nssp.alloc().init()
                    voice = self.globals[ANNOUNCEMENT][announcementUniqueKey][VOICE]  # e.g.
                    rate = 100
                    result = ve.setRate_(rate)
                    result = ve.setVoice_(voice)
                    result = ve.startSpeakingString_toURL_("Hello, How are you today, are you OK?", url)
                    speech_to_output = self.globals[ANNOUNCEMENT][announcementUniqueKey][SPEECH_TEXT]
                    result = ve.startSpeakingString_toURL_(speech_to_output, url)
                    time.sleep(1)

                except Exception as exception_error:
                    self.exception_handler(exception_error, True)  # Log error and display failing statement
                    return

            if "prepend" in self.globals[ANNOUNCEMENT][announcementUniqueKey]:
                self.logger.debug(f"announcementPrepend = '{self.globals[ANNOUNCEMENT][announcementUniqueKey][PREPEND]}'")
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                    [self.masterPlayerMAC + " playlist add " + self.globals[ANNOUNCEMENT][announcementUniqueKey][PREPEND]])

            self.logger.debug(f"announcementFile = '{announcementFile}'")
            announcementFile = urllib.parse.quote(announcementFile)
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " playlist add " + announcementFile])

            if "append" in self.globals[ANNOUNCEMENT][announcementUniqueKey]:
                self.logger.debug(f"announcementAppend = '{self.globals[ANNOUNCEMENT][announcementUniqueKey][APPEND]}'")
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(
                    [self.masterPlayerMAC + " playlist add " + self.globals[ANNOUNCEMENT][announcementUniqueKey][APPEND]])

            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " play"])

        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologAnnouncementRestartPlaying(self, devServer, devPlayer):
        try:
            self.globals[ANNOUNCEMENT][STEP] = "autologAnnouncementRestartPlaying"
            self.logger.debug(f"NXT=[autologAnnouncementRestartPlaying]: {indigo.devices[self.masterPlayerId].name}")

            if self.globals[PLAYERS][self.masterPlayerId][ANNOUNCEMENT_PLAYLIST_NO_PLAY] == "0" and self.globals[PLAYERS][self.masterPlayerId][SAVED_POWER] != 0:
                self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " play"])
                # if self.globals[PLAYERS][self.masterPlayerId][SAVED_TIME] !=  "0":
                #     self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put([self.masterPlayerMAC + " time " + self.globals[PLAYERS][self.masterPlayerId][SAVED_TIME])
            self.globals[QUEUES][COMMAND_TO_SEND][self.globals[PLAYERS][self.masterPlayerId][SERVER_ID]].put(self.masterPlayerMAC + " autologAnnouncementEnded")


        except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _handle_player_detail_autologAnnouncementEnded(self, devServer, devPlayer):
        try:
            self.globals[ANNOUNCEMENT][STEP] = "autologAnnouncementEnded"
            self.logger.debug(f"LAST STEP [autologAnnouncementEnded]: {indigo.devices[self.masterPlayerId].name}")
            self.globals[ANNOUNCEMENT][ACTIVE] = NO
            self.globals[ANNOUNCEMENT][STEP] = ""
            self.logger.debug("Play Announcement Ended")

            # clear any status as appropriate

            try:
                pass
                # pop next queued announcement (if any) otherwise an Empty exception is raised
                self.queuedAnnouncement = self.globals[QUEUES][ANNOUNCEMENT].get(False)

                self.logger.debug(f"self.queuedAnnouncement = ({self.queuedAnnouncement[0]},{self.queuedAnnouncement[1]})")

                self.globals[ANNOUNCEMENT][ACTIVE] = PENDING
                self.globals[QUEUES][COMMAND_TO_SEND][self.queuedAnnouncement[0]].put([self.queuedAnnouncement[1]])

            except queue.Empty:
                self.logger.debug("self.queuedAnnouncement = EMPTY")
                pass
                # handle queue empty

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _playersToProcess(self, devId, debugText):
        try:
            playerIdsToProcess = []
            if self.globals[PLAYERS][devId][MASTER_PLAYER_ID] != 0:
                masterPlayerId = self.globals[PLAYERS][devId][MASTER_PLAYER_ID]
                playerIdsToProcess.append(masterPlayerId)
                for slaveId in self.globals[PLAYERS][masterPlayerId][SLAVE_PLAYER_IDS]:
                    playerIdsToProcess.append(slaveId)
            elif self.globals[PLAYERS][devId][SLAVE_PLAYER_IDS] != []:
                playerIdsToProcess.append(devId)
                for slaveId in self.globals[PLAYERS][devId][SLAVE_PLAYER_IDS]:
                    playerIdsToProcess.append(slaveId)
            else:
                playerIdsToProcess.append(devId)

            self.logger.debug(f"_playersToProcess [{debugText}] = {playerIdsToProcess}")

            return playerIdsToProcess

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _playerMACToDeviceId(self, mac):
        try:
            deviceId = 0

            for playerDevId in self.globals[PLAYERS]:
                if mac == self.globals[PLAYERS][playerDevId][MAC]:
                    deviceId = playerDevId

            # self.logger.debug(f"PLAYER MAC ADDRESS [{mac}] IS DEVICE ID [{deviceId}]")

            return deviceId

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _playerDeviceIdToMAC(self, devId):
        try:
            mac = ""
            for playerDevId in self.globals[PLAYERS]:
                if playerDevId == devId:
                    mac = self.globals[PLAYERS][playerDevId][MAC]

            return mac

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _playerRemoveSyncMaster(self):
        try:
            for playerDevId in self.globals[PLAYERS]:
                self.globals[PLAYERS][playerDevId][MASTER_PLAYER_ADDRESS] = ""
                self.globals[PLAYERS][playerDevId][MASTER_PLAYER_ID] = 0
                self.globals[PLAYERS][playerDevId][SLAVE_PLAYER_IDS] = []

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def _playerUpdateSync(self):
        try:
            for playerDevId in self.globals[PLAYERS]:
                dev = indigo.devices[playerDevId]
                key_value_list = list()
                if len(self.globals[PLAYERS][playerDevId][SLAVE_PLAYER_IDS]) == 0:  # Check if the contains any entries and if not ...
                    key_value_list.append({"key": "isSyncMaster", "value": False})
                    key_value_list.append({"key": "syncMasterSlave_1_Id", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_1_Address", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_1_Name", "value": ""})
                    key_value_list.append({"key": "syncMasterSlave_2_Id", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_2_Address", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_2_Name", "value": ""})
                    key_value_list.append({"key": "syncMasterSlave_3_Id", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_3_Address", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_3_Name", "value": ""})
                    key_value_list.append({"key": "syncMasterSlave_4_Id", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_4_Address", "value": "None"})
                    key_value_list.append({"key": "syncMasterSlave_4_Name", "value": ""})
                    key_value_list.append({"key": "syncMasterNumberOfSlaves", "value": "0"})
                else:
                    key_value_list.append({"key": "isSyncMaster", "value": True})
                    slaveIds = ""
                    slaveAddresses = ""
                    slaveNames = ""
                    slaveLoopCount = 0
                    for slaveId in self.globals[PLAYERS][playerDevId][SLAVE_PLAYER_IDS]:
                        slaveLoopCount += 1
                        if slaveLoopCount < 5:  # Maximum number of 4 slaves to be recorded in master player devices (even though internally it handles more)
                            syncMasterSlave_N_Id = f"syncMasterSlave_{slaveLoopCount:d}_Id"
                            syncMasterSlave_N_Address = f"syncMasterSlave_{slaveLoopCount:d}_Address"
                            syncMasterSlave_N_Name= f"syncMasterSlave_{slaveLoopCount:d}_Name"

                            key_value_list.append({"key": syncMasterSlave_N_Id, "value": str(slaveId)})
                            key_value_list.append({"key": syncMasterSlave_N_Address, "value": self.globals[PLAYERS][slaveId][MAC]})
                            key_value_list.append({"key": syncMasterSlave_N_Name, "value": self.globals[PLAYERS][slaveId][NAME]})
 
                    key_value_list.append({"key": "syncMasterNumberOfSlaves", "value": str(slaveLoopCount)})

                if  self.globals[PLAYERS][playerDevId][MASTER_PLAYER_ID] == 0:
                    key_value_list.append({"key": "isSyncSlave", "value": False})
                    key_value_list.append({"key": "masterPlayerId", "value": "None"})
                    key_value_list.append({"key": "masterPlayerAddress", "value": "None"})
                    key_value_list.append({"key": "masterPlayername", "value": ""})
                else:
                    key_value_list.append({"key": "isSyncSlave", "value": True})
                    key_value_list.append({"key": "masterPlayerId", "value": str(self.globals[PLAYERS][playerDevId][MASTER_PLAYER_ID])})
                    key_value_list.append({"key": "masterPlayerAddress", "value": self.globals[PLAYERS][playerDevId][MASTER_PLAYER_ADDRESS]})
                    key_value_list.append({"key": "masterPlayername", "value": self.globals[PLAYERS][self.globals[PLAYERS][playerDevId][MASTER_PLAYER_ID]][NAME]})

                dev.updateStatesOnServer(key_value_list)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        try:
            self.currentTime = indigo.server.getTime()

            match typeId:
                case "squeezeboxServer":
                    # Validate Squeezebox Server
                    ipAddress = valuesDict.get("ipAddress", "")
                    try:
                        socket.inet_aton(ipAddress)
                        valid = True
                    except socket.error:
                        valid = False

                    if not valid:
                        errorDict = indigo.Dict()
                        errorDict["ipAddress"] = "Specify the Squeezebox Server IP Address"
                        errorDict["showAlertText"] = "Please specify the IP Address of the Squeezebox Server."
                        return False, valuesDict, errorDict
                case "squeezeboxPlayer":
                    # Validate Squeezebox Player
                    mac = valuesDict.get("mac", "")
                    if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", mac.lower()):
                       valid = True
                    else:
                        valid = False

                    if not valid:
                        errorDict = indigo.Dict()
                        errorDict["mac"] = "Specify Squeezebox Player MAC"
                        errorDict["showAlertText"] = "You must specify the MAC of the Squeezebox Player."
                        return False, valuesDict, errorDict

            return True, valuesDict

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceStartComm(self, dev):
        try:
            dev.stateListOrDisplayStateIdChanged()  # Ensure latest devices.xml is being used
            self.currentTime = indigo.server.getTime()

            devId = dev.id

            if dev.deviceTypeId == "squeezeboxServer":
                self.globals[SERVERS][devId] = dict()
                self.globals[SERVERS][devId][KEEP_THREAD_ALIVE] = True
                self.globals[SERVERS][devId][DATE_TIME_STARTED] = self.currentTime
                self.globals[SERVERS][devId][IP_ADDRESS] = dev.pluginProps["ipAddress"]
                self.globals[SERVERS][devId][PORT] = dev.pluginProps["port"]
                self.globals[SERVERS][devId][IP_ADDRESS_PORT] = f"{self.globals[SERVERS][devId][IP_ADDRESS]}:{self.globals[SERVERS][devId][PORT]}"
                self.globals[SERVERS][devId][IP_ADDRESS_PORT_NAME] = (self.globals[SERVERS][devId][IP_ADDRESS_PORT].replace(".", "-")).replace(":", "-")
                self.globals[SERVERS][devId][STATUS] = "starting"
                self.globals[SERVERS][devId][LAST_SCAN] = "?"
                self.globals[SERVERS][devId][PLAYER_MAC] = ""  # Used to handle specific player as result of subscribe (normally empty but used on connect)

                self.props = dev.pluginProps
                address = self.props.get("address", "")
                if address != self.globals[SERVERS][devId][IP_ADDRESS_PORT]:
                    self.props["address"] = self.globals[SERVERS][devId][IP_ADDRESS_PORT]
                    dev.replacePluginPropsOnServer(self.props)

                self.globals[QUEUES][COMMAND_TO_SEND][devId] = queue.Queue()  # set-up queue for each individual server

                self.signalWakeupQueues(self.globals[QUEUES][COMMAND_TO_SEND][devId])  # noqa

                self.globals[THREADS][COMMUNICATE_WITH_SERVER][devId] = dict()
                self.globals[THREADS][COMMUNICATE_WITH_SERVER][devId][EVENT] = threading.Event()
                self.globals[THREADS][COMMUNICATE_WITH_SERVER][devId][THREAD] = ThreadCommunicateWithServer(self.globals, devId)
                self.globals[THREADS][COMMUNICATE_WITH_SERVER][devId][THREAD].start()

                self.globals[THREADS][LISTEN_TO_SERVER][devId] = dict()
                self.globals[THREADS][LISTEN_TO_SERVER][devId][EVENT] = threading.Event()
                self.globals[THREADS][LISTEN_TO_SERVER][devId][THREAD] = ThreadListenToServer(self.globals, devId)
                self.globals[THREADS][LISTEN_TO_SERVER][devId][THREAD].start()

                dev.updateStateOnServer(key="status", value=self.globals[SERVERS][devId][STATUS])
                dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

                self.globals[QUEUES][COMMAND_TO_SEND][devId].put(["serverstatus 0 0 subscribe:-"])  # E.g. ["00:04:20:ab:cd:ef", ["playlist", "name", "?"]]

                self.logger.info(f"Started '{dev.name}': '{self.globals[SERVERS][devId][IP_ADDRESS]}'")
                self.logger.debug(f"SELF.SERVERS for '{dev.name}' = {self.globals[SERVERS][devId]}")

            elif dev.deviceTypeId == "squeezeboxPlayer":
                if dev.id not in self.globals[PLAYERS]:
                    self.globals[PLAYERS][dev.id] = dict()

                self.globals[PLAYERS][devId][NAME] = dev.name
                self.globals[PLAYERS][dev.id][MODEL] = indigo.devices[dev.id].states["model"]
                self.globals[PLAYERS][devId][MAC] = dev.address
                self.globals[PLAYERS][dev.id][SERVER_ID] = indigo.devices[dev.id].states["serverId"]
                self.globals[PLAYERS][dev.id][SERVER_NAME] = indigo.devices[dev.id].states["serverName"]

                self.logger.debug(f"MAC [{dev.name}] = '{self.globals[PLAYERS][devId][MAC]}'")

                key_value_list = list()

                self.deviceUpdateKeyValueList(False, dev, key_value_list, DATE_TIME_STARTED, "datetimeStarted", self.currentTime)
                self.deviceUpdateKeyValueList(False, dev, key_value_list, ANNOUNCEMENT_PLAY_ACTIVE, "announcementPlayActive", "NO")

                # self.deviceUpdateKeyValueList(False, dev, key_value_list, "name", dev.name)
                # self.deviceUpdateKeyValueList(False, dev, key_value_list, "mac", dev.pluginProps[MAC])  # MAC of Squeezebox Player

                self.deviceUpdateKeyValueList(False, dev, key_value_list, SAVED_POWER, "savedPower", "?")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, SAVED_MODE, "savedMode", "?")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, SAVED_REPEAT, "savedRepeat", "?")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, SAVED_SHUFFLE, "savedShuffle", "?")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, SAVED_VOLUME, "savedVolume", "?")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, SAVED_TIME, "savedTime", "0")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, SAVED_MAINTAIN_SYNC, "savedMaintainSync", "?")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, SONG_URL, "songUrl", "")

                self.deviceUpdateKeyValueList(True, dev, key_value_list, ALBUM, "album", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, ARTIST, "artist", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, CONNECTED, "connected", False)
                self.deviceUpdateKeyValueList(True, dev, key_value_list, DURATION, "duration", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, DURATION_UI, "durationUi", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, GENRE, "genre", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, IP_ADDRESS, "ipAddress", "Unknown")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, IS_SYNC_MASTER, "isSyncMaster", False)
                self.deviceUpdateKeyValueList(True, dev, key_value_list, IS_SYNC_SLAVE, "isSyncSlave", True)
                self.deviceUpdateKeyValueList(True, dev, key_value_list, MAINTAIN_SYNC, "maintainSync", "0")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, MASTER_PLAYER_ID, "masterPlayerId", 0)
                self.deviceUpdateKeyValueList(True, dev, key_value_list, MASTER_PLAYER_ADDRESS, "masterPlayerAddress", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, MASTER_PLAYER_NAME, "masterPlayername", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, MODE, "mode", "?")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, PORT, "portAddress", "Unknown")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, PLAYLIST_TRACK_NUMBER, "playlistTrackNumber", "?")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, PLAYLIST_TRACKS_TOTAL, "playlistTracksTotal", "?")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, PLAYLIST_TRACKS_UI, "playlistTracksUi", "?")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, POWER, "power", "0")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, POWER_UI, "powerUi", "disconnected")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, REMOTE_STREAM, "remoteStream", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, REPEAT, "repeat", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SHUFFLE, "shuffle", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, STATE, "state", "disconnected")
                self.deviceUpdateKeyValueList(False, dev, key_value_list, TIME, "time", "0")

                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_NUMBER_OF_SLAVES, "syncMasterNumberOfSlaves", "0")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_1_ID, "syncMasterSlave_1_Id", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_1_ADDRESS, "syncMasterSlave_1_Address", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_1_NAME, "syncMasterSlave_1_Name", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_2_ID, "syncMasterSlave_2_Id", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_2_ADDRESS, "syncMasterSlave_2_Address", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_2_NAME, "syncMasterSlave_2_Name", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_3_ID, "syncMasterSlave_3_Id", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_3_ADDRESS, "syncMasterSlave_3_Address", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_3_NAME, "syncMasterSlave_3_Name", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_4_ID, "syncMasterSlave_4_Id", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_4_ADDRESS, "syncMasterSlave_4_Address", "None")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, SYNC_MASTER_SLAVE_4_NAME, "syncMasterSlave_4_Name", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, TITLE, "title", "")
                self.deviceUpdateKeyValueList(True, dev, key_value_list, VOLUME, "volume", "0")

                dev.updateStatesOnServer(key_value_list)
                dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                
                try:
                    if self.globals[SERVERS][self.globals[PLAYERS][devId][SERVER_ID]]:
                        pass
                    self.logger.debug(f"Server Started before player '{dev.name}'")
                    self.globals[QUEUES][COMMAND_TO_SEND][devId].put(["serverstatus 0 0 subscribe:0"])          # CHECK THIS OUT - IS IT A BIT OTT?
                except Exception:
                    pass
                    self.logger.debug(f"Server Starting after player '{dev.name}'")

                self.logger.info(f"Started '{dev.name}': '{self.globals[PLAYERS][devId][MAC]}'")
                self.logger.debug(f"self.globals[PLAYERS] for '{dev.name}' = {self.globals[PLAYERS][devId]}")


                createCoverArtUrl = False
                path = ""  # Default = not found
                try:
                    self.deviceStateUpdate(False, dev, COVER_ART_FOLDER, "coverArtFolder", path)  # Default to not found
                    path = str(f"{self.globals[COVER_ART_FOLDER]}/{COVER_ART_SUB_FOLDER}/{str(dev.id)}")
                    # self.logger.debug(f"Cover art folder: {path}")
                    os.makedirs(path)
                    self.deviceStateUpdate(False, dev, COVER_ART_FOLDER, "coverArtFolder", path)
                    createCoverArtUrl = True
                except OSError as exception_error:
                    if exception_error.errno == errno.EEXIST:
                        self.deviceStateUpdate(False, dev, COVER_ART_FOLDER, "coverArtFolder", path)
                        createCoverArtUrl = True
                    else:
                        self.logger.error(f"Unable to create cover art folder: {path}")

                if createCoverArtUrl:
                    coverArtFile = str(f"{path}/{'coverart.jpg'}")
                    coverArtUrl = str(f"file://{coverArtFile}")
                    try:
                        shutil.copy2(self.globals[COVER_ART][COVER_ART_NO_FILE],coverArtFile)
                    except Exception as exception_error:
                        self.logger.error(f"Cover Art Error - IN: {self.globals[COVER_ART][COVER_ART_NO_FILE]}")
                        self.logger.error(f"Cover Art Error - OUT: {coverArtFile}")
                        error_message = f"Cover Art Error - ERR: {exception_error}"
                        self.exception_handler(error_message, True)  # Log error and display failing statement
                else:
                    coverArtFile = ""  # TODO: Set coverArtFile when not available; is empty correct?
                    coverArtUrl = "Not available"
                self.deviceStateUpdate(False, dev, COVER_ART_FILE, "coverArtFile", coverArtFile)  # Cover Art Url
                self.deviceStateUpdate(True, dev, COVER_ART_URL, "coverArtUrl", coverArtUrl)  # Cover Art Url

            else:
                self.logger.error(f"Squeezebox Invalid Device Type [{dev.deviceTypeId}]")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceUpdateKeyValueList(self, update_key_value_list, dev, key_value_list, internal_key, state_key, state_value):
        try:
            self.globals[PLAYERS][dev.id][internal_key] = state_value
            if update_key_value_list:
                key_value_list.append({"key": state_key, "value": state_value})

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceStateUpdate(self, updateServer, dev, internalKey, stateKey, stateValue):
        try:
            self.globals[PLAYERS][dev.id][internalKey] = stateValue
            if updateServer:
                dev.updateStateOnServer(key=stateKey, value=stateValue)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceStateUpdateWithIcon(self, updateServer, dev, internalKey, stateKey, stateValue, icon):
        try:
            self.deviceStateUpdate(updateServer, dev, internalKey, stateKey, stateValue)
            dev.updateStateImageOnServer(icon)

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement

    def deviceStopComm(self, dev):
        try:
            if dev.deviceTypeId == "squeezeboxServer":
                del self.globals[SERVERS][dev.id]
            elif dev.deviceTypeId == "squeezeboxPlayer":
                del self.globals[PLAYERS][dev.id]


            self.logger.info(f"Stopping '{dev.name}'")

        except Exception as exception_error:
            self.exception_handler(exception_error, True)  # Log error and display failing statement
