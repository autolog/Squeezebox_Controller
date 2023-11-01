#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Squeezebox Controller © Autolog 2023
#

# r = requests.get(url, json=data)
# result = r.json()["result"]

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import datetime
import socket
import sys
import threading
import traceback
import urllib.parse

# ============================== Custom Imports ===============================
try:
    import indigo  # noqa
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *


# noinspection PyUnresolvedReferences,PyPep8Naming
class ThreadCommunicateWithServer(threading.Thread):

    # This class communicates with the Squeezebox server

    def __init__(self, plugin_globals, dev_id):

        threading.Thread.__init__(self)

        self.globals = plugin_globals
        
        self.dev_id = dev_id
        self.host = self.globals[SERVERS][dev_id][IP_ADDRESS]
        self.port = self.globals[SERVERS][dev_id][PORT]
        self.name = indigo.devices[self.dev_id].description  # TODO - CHECK THIS ???

        self.communicateLogger = logging.getLogger("Plugin.squeezeboxCommunicate")

        self.threadStop = self.globals[THREADS][COMMUNICATE_WITH_SERVER][dev_id][EVENT]

        self.message_id = 0

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split("/")
        log_message = f"'{exception_error_message}' in module '{module[-1]}', method '{method}'"
        if log_failing_statement:
            log_message = f"{log_message}\n   Failing statement [line {line_number}]: '{statement}'"
        else:
            log_message = f"{log_message} at line {line_number}"
        self.communicateLogger.error(log_message)

    def run(self):
        try:
            # keepThreadActive = True
            # while keepThreadActive:

            print(f"HELLO WORLD: {self.globals[SERVERS][self.dev_id][KEEP_THREAD_ALIVE]}")

            try:
                self.communicateLogger.info(f"ThreadSqueezeboxServer creating socket for {self.name}: Host=[{self.host}], Port=[{self.port}]")
                self.squeezeboxReadWriteSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # create a TCP socket

                self.communicateLogger.info(f"ThreadSqueezeboxServer Starting socket connect for {self.name}: Host=[{self.host}], Port=[{self.port}]")
                self.squeezeboxReadWriteSocket.connect((self.host, int(self.port)))  # connect to server on the port
                self.squeezeboxReadWriteSocket.settimeout(20)

                self.communicateLogger.info(f"Communication Thread initialised for {self.name}: Host=[{self.host}], Port=[{self.port}]")

                self.globals[SERVERS][self.dev_id][KEEP_THREAD_ALIVE] = True
                while self.globals[SERVERS][self.dev_id][KEEP_THREAD_ALIVE]:
                    self.sendMessage = self.globals[QUEUES][COMMAND_TO_SEND][self.dev_id].get()
                    try:
                        if isinstance(self.sendMessage, list) and self.sendMessage[0] == "WAKEUP":
                            pass
                            # self.globals[TIMERS][COMMAND_TO_SEND][self.dev_id] = threading.Timer(5.0, signalWakeupQueues, [self.globals[QUEUES][COMMAND_TO_SEND][self.dev_id]])
                            # self.globals[TIMERS][COMMAND_TO_SEND][self.dev_id].start()
                        else:
                            testInstance = isinstance(self.sendMessage, list)
                            # self.communicateLogger.info(f"self.sendMessage [Type={type(self.sendMessage)}][{testInstance}] = {self.sendMessage}")

                            if isinstance(self.sendMessage, list):
                                self.sendMessage = self.sendMessage[0]

                            # self.sendMessage = f"{self.sendMessage.rstrip()} MSG:{self.message_id}"
                            # self.message_id += 1

                            # self.communicateLogger.error(f"Message sent to Server: {self.sendMessage}")  # TODO: DEBUG
                            send_message_bytes = bytes(self.sendMessage + "\n", "utf-8")
                            self.squeezeboxReadWriteSocket.sendall(send_message_bytes)
                            response_bytes = self.squeezeboxReadWriteSocket.recv(1024)
                            response_string = response_bytes.decode("utf-8")
                            while response_string[-1:] != "\n":
                                response_bytes = self.squeezeboxReadWriteSocket.recv(1024)
                                response_string = response_string + response_bytes.decode("utf-8")
                            self.response = response_string.strip()

                            # self.communicateLogger.info(f"RECEIVED SERVER RESPONSE Type/Length =  [{type(self.response)}]/[{len(self.response)}]")

                            # self.communicateLogger.info(f"RECEIVED SERVER RESPONSE = {urllib.parse.unquote(self.response.rstrip())}")

                            self.globals[QUEUES][RETURNED_RESPONSE].put([self.dev_id, REPLY_TO_SEND, self.response])

                    except socket.error as exception_error:
                        # TODO: SORT THIS OUT FOR PYTHON 3
                        if isinstance(exception_error.args, tuple):
                            if exception_error[0] == errno.EPIPE:
                                self.communicateLogger.error(f"Communication Thread detected Server [{self.name}] has disconnected.")
                            elif exception_error[0] == errno.ECONNRESET:
                                self.communicateLogger.error(f"Communication Thread detected Server [{self.name}] has reset connection.")
                            elif exception_error[0] == errno.ETIMEDOUT:
                                self.communicateLogger.error(f"Communication Thread detected Server [{self.name}] has timed out.")
                            else:
                                self.communicateLogger.error(f"Communication Thread detected error communicating with Server [{self.name}]. Has error code ='{exception_error[0]}'")
                        else:
                            self.exception_handler(exception_error, True)  # Log error and display failing statement
                        break
                    except Exception as exception_error:
                        self.exception_handler(exception_error, True)  # Log error and display failing statement
                        break

            except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

        except Exception as e:
            self.communicateLogger.error(f"Communication Thread unable to start: {self.host}:{self.port} [{self.name}] [Reason = {e}]")

        try:
            self.globals[SERVERS][self.dev_id][STATUS] = "unavailable"
            indigo.devices[self.dev_id].updateStateOnServer(key="status", value=self.globals[SERVERS][self.dev_id][STATUS])

            for dev in indigo.devices.iter(filter="self"):
                if dev.deviceTypeId == "squeezeboxPlayer" and dev.states["serverId"] == self.dev_id:  # dev_id is id of server
                    self.globals[PLAYERS][dev.id][POWER_UI] = "disconnected"
                    dev.updateStateOnServer(key="power", value=self.globals[PLAYERS][dev.id][POWER_UI])
                    dev.updateStateOnServer(key="state", value=self.globals[PLAYERS][dev.id][POWER_UI])
                    dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

            self.globals[SERVERS][self.dev_id][KEEP_THREAD_ALIVE] = False

            self.communicateLogger.error(f"Communication Thread ended for {self.host}:{self.port} [{self.name}]")

        except Exception as e:
            self.communicateLogger.error(f"Communication Thread unable to start: {self.host}:{self.port} [{self.name}] [Reason = {e}]")

            # thread.exit()

# http://192.168.1.8:9000/imageproxy/http%3A%2F%2Fstatic.qobuz.com%2Fimages%2Fcovers%2F95%2F34%2F0884463063495_600.jpg/image.jpg

# http://192.168.1.8:9000/imageproxy/http%3A%2F%2Fstatic.qobuz.com%2Fimages%2Fcovers%2F76%2F20%2F0822189012076_600.jpg/image.jpg

#                         imageproxy/http%3A%2F%2Fstatic.qobuz.com%2Fimages%2Fcovers%2F76%2F20%2F0822189012076_600.jpg/image_96x96_p.jpg

    # def squeezebox_api_call(self, is_post_api_call, api_url):
    #     try:
    #         error_code = None
    #         error_message_ui = ""
    #         try:
    #             status_code = -1
    #             if is_post_api_call:
    #                 post_data = dict()
    #                 post_data["id"] = 1
    #                 post_data["method"] = "slim.request"
    #                 post_data["params"] = parameter_list
    #                 headers = {"Content-type": "application/json;charset=UTF-8"}
    #                 reply = requests.post(api_url, headers=headers, data=post_data)
    #             else:
    #                 headers = {"Content-type": "application/json;charset=UTF-8"}
    #                 reply = requests.get(api_url, headers=headers)
    #             reply.raise_for_status()  # raise an HTTP error if one coccurred
    #             status_code = reply.status_code
    #             # print(f"Reply Status: {reply.status_code}, Text: {reply.text}")
    #             if status_code == 200:
    #                 pass
    #             # elif status_code == 400 or status_code == 401:
    #             #     error_details = reply.json()
    #             #     error_code = error_details["code"]
    #             #     error_message_ui = error_details["message"]
    #             # elif status_code == 404:
    #             #     error_code = "Not Found"
    #             #     error_message_ui = "Starling Hub not found"
    #             else:
    #                 error_code = "Unknown Error"
    #                 error_message_ui = f"unknown connection error: {status_code}"
    #         except requests.exceptions.HTTPError as error_message:
    #             error_code = "HTTP Error"
    #             error_message_ui = f"Access Smappee failed: {error_message}"
    #             # print(f"HTTP ERROR: {error_message}")
    #             if error_code != previous_status_message:
    #                 self.smappeeInterfaceLogger.error(error_message_ui)
    #             return False, [error_code, error_message_ui]
    #         except requests.exceptions.Timeout as error_message:
    #             error_code = "Timeout Error"
    #             error_message_ui = f"Access Smappee failed with a timeout error. Retrying . . ."
    #             if error_code != previous_status_message:
    #                 self.smappeeInterfaceLogger.error(error_message_ui)
    #             return False, [error_code, error_message_ui]
    #         except requests.exceptions.ConnectionError as error_message:
    #             error_code = "Connection Error"
    #             error_message_ui = f"Access Smappee failed with a connection error. Retrying . . ."
    #             if error_code != previous_status_message:
    #                 self.smappeeInterfaceLogger.error(error_message_ui)
    #             return False, [error_code, error_message_ui]
    #         except requests.exceptions.RequestException as error_message:
    #             error_code = "OOps: Unknown error"
    #             if error_code != previous_status_message:
    #                 error_message_ui = f"Access Smappee failed with an unknown error. Retrying . . ."
    #                 self.smappeeInterfaceLogger.info(error_message_ui)
    #             return False, [error_code, error_message_ui]
    #
    #         if status_code == 200:
    #             reply = reply.json()  # decode JSON
    #             # # Check Filter
    #             # if FILTERS in self.globals:
    #             #     if len(self.globals[FILTERS]) > 0 and self.globals[FILTERS] != ["-0-"]:
    #             #         self.nest_filter_log_processing(starling_hub_dev.id, starling_hub_dev.name, control_api, reply)
    #
    #             return_ok = True
    #             return return_ok, reply  # noqa [reply might be referenced before assignment]
    #
    #         else:
    #             # TODO: Sort this out!
    #             return_ok = False
    #             if error_message_ui is "":
    #                 self.smappeeInterfaceLogger.error(f"Error [{status_code}] accessing Smappee '{starling_hub_dev.name}': {error_code}")
    #             else:
    #                 self.smappeeInterfaceLogger.error(f"Error [{status_code}] accessing Smappee '{starling_hub_dev.name}': {error_code} - {error_message_ui}")
    #             return return_ok, [error_code, error_message_ui]
    #
    #     except Exception as exception_error:
    #         self.exception_handler(exception_error, True)  # Log error and display failing statement
    #         return False, [255, exception_error]
