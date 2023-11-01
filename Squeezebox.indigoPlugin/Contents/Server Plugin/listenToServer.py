#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Squeezebox Controller © Autolog 2023
#

# noinspection PyUnresolvedReferences
# ============================== Native Imports ===============================
import datetime
import socket
import sys
import threading
import traceback

# ============================== Custom Imports ===============================
try:
    import indigo  # noqa
except ImportError:
    pass

# ============================== Plugin Imports ===============================
from constants import *


# noinspection PyUnresolvedReferences,PyPep8Naming
class ThreadListenToServer(threading.Thread):

    # This class listens to the Squeezebox server

    def __init__(self, plugin_globals, dev_id):

        threading.Thread.__init__(self)

        self.globals = plugin_globals

        self.dev_id = dev_id
        self.host = self.globals[SERVERS][dev_id][IP_ADDRESS]
        self.port = self.globals[SERVERS][dev_id][PORT]
        self.name = indigo.devices[self.dev_id].description  # TODO - CHECK THIS ???

        self.listenLogger = logging.getLogger("Plugin.squeezeboxListen")

        self.threadStop = self.globals[THREADS][LISTEN_TO_SERVER][dev_id][EVENT]

    def exception_handler(self, exception_error_message, log_failing_statement):
        filename, line_number, method, statement = traceback.extract_tb(sys.exc_info()[2])[-1]
        module = filename.split("/")
        log_message = f"'{exception_error_message}' in module '{module[-1]}', method '{method}'"
        if log_failing_statement:
            log_message = f"{log_message}\n   Failing statement [line {line_number}]: '{statement}'"
        else:
            log_message = f"{log_message} at line {line_number}"
        self.listenLogger.error(log_message)

    def run(self):
        try:
            # keepThreadActive = True
            # while keepThreadActive:
            # self.listenLogger.error(f"listen Thread starting socket listen for {self.host}:{self.port} [{self.name}]")  # TODO: DEBUG

            self.squeezeboxListenSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # create a TCP socket
            self.squeezeboxListenSocket.connect((self.host, int(self.port)))  # connect to server on the port

            try:
                # self.listenLogger.error(f"Listen Thread initialised for {self.host}:{self.port} [{self.name}]")  # TODO: DEBUG
                self.squeezeboxListenSocket.settimeout(5)
                send_message_bytes = bytes("listen 1" + "\n", "utf-8")
                self.squeezeboxListenSocket.sendall(send_message_bytes)
                while self.globals[SERVERS][self.dev_id][KEEP_THREAD_ALIVE]:
                    loopTimeCheck = indigo.server.getTime()
                    try:
                        a = 1
                        b = a + 1
                        # self.listenLogger.debug("TIMEOUT LISTEN THREAD TEST")
                        for line in self.squeezeboxListenSocket.makefile("rbw"):
                            line = line.decode("utf-8")
                            self.globals[QUEUES][RETURNED_RESPONSE].put([self.dev_id, LISTEN_NOTIFICATION, line])
                            try:
                                self.listenLogger.error(f"{urllib.unquote(line.rstrip())}")
                            except:
                                pass
                        if len(self.line) < 10:
                            pass


                    except ConnectionError as exception_error:
                        self.exception_handler(exception_error, True)
                        break

                    except TimeoutError as exception_error:
                        loopTimeCheck = loopTimeCheck + datetime.timedelta(seconds=3)
                        if indigo.server.getTime() > loopTimeCheck:
                            # self.listenLogger.warning(f"Listen Thread detected Server [{self.name}] has timed out but will continue.")
                            continue
                        self.exception_handler(exception_error, True)
                        break

                    except Exception as exception_error:
                        self.exception_handler(exception_error, True)  # Log error and display failing statement
                        break

            except Exception as exception_error:
                self.exception_handler(exception_error, True)  # Log error and display failing statement

        except Exception as exception_error:
            exception_message = f"Listen Thread unable to start: {self.host}:{self.port} [{self.name}] [Reason = {exception_error}]"
            self.exception_handler(exception_message, True)  # Log error and display failing statement

        try:
            self.globals[SERVERS][self.dev_id][STATUS] = "unavailable"
            indigo.devices[self.dev_id].updateStateOnServer(key="status", value=self.globals[SERVERS][self.dev_id][STATUS])

            for dev in indigo.devices.iter(filter="self"):
                if dev.deviceTypeId == "squeezeboxPlayer" and dev.states["serverId"] == self.dev_id:  # dev_id is id of server
                    self.globals[PLAYERS][dev.id][POWER_UI] = "disconnected"
                    dev.updateStateOnServer(key="power", value=self.globals[PLAYERS][dev.id][POWER_UI])
                    dev.updateStateOnServer(key="state", value=self.globals[PLAYERS][dev.id][POWER_UI])
                    dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

            # time.sleep(15)
            # indigo.device.enable(self.dev_id, value=False)
            # indigo.device.enable(self.dev_id, value=True)

            self.listenLogger.debug(f"Listen Thread ended for {self.host}:{self.port} [{self.name}]")

        except Exception as exception_error:
            exception_message = f"Listen Thread unable to start: {self.host}:{self.port} [{self.name}] [Reason = {exception_error}]"
            self.exception_handler(exception_message, True)  # Log error and display failing statement

        self.globals[SERVERS][self.dev_id][KEEP_THREAD_ALIVE] = False

        # thread.exit()

