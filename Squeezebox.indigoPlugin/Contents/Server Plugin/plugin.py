#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Squeezebox Controller © Autolog 2014-2015

from  AppKit import NSSpeechSynthesizer
import datetime
import errno
from Foundation import NSURL
import httplib
import inspect
import logging
from logging.handlers import TimedRotatingFileHandler
import operator
import os
from Queue import Queue as autologQueue
from Queue import Empty as autologQueueEmpty
import select
import shutil
import socket
import subprocess
import sys
import threading
import time
import traceback
import re
import urllib2



pluginGlobal = {}

pluginGlobal['baseFolder'] = '/Library/Application Support'  # Base Folder for Plugin data


pluginGlobal['autologger'] = ''

pluginGlobal['coverArt'] = {}
pluginGlobal['coverArt']['noCoverArtFile'] = ''
pluginGlobal['coverArt']['noCoverArtFileUrl'] = ''

pluginGlobal['threads'] = {}
pluginGlobal['threads']['communicateWithServer'] = {}
pluginGlobal['threads']['listenToServer'] = {}

pluginGlobal['queues'] = {}
pluginGlobal['queues']['returnedResponse'] = ''  # Set-up in plugin start (a common returned response queue for all servers)
pluginGlobal['queues']['commandToSend'] = {}  # There will be one 'commandToSend' queue for each server - set-up in device start
pluginGlobal['queues']['announcementQueue'] = ''  # Set-up in plugin start (a common announcement queue for all servers)

pluginGlobal['timers'] = {}
pluginGlobal['timers']['commandToSend'] = {}

pluginGlobal['servers'] = {}
pluginGlobal['players'] = {}

pluginGlobal['announcement'] = {}
pluginGlobal['announcement']['active'] = 'NO'
pluginGlobal['announcement']['step'] = ''
pluginGlobal['announcement']['fileCheckOK'] = True
pluginGlobal['announcement']['announcementTempFolder'] = ''

pluginGlobal['debug'] = {}
pluginGlobal['debug']['initialised']  = False  # Indicates whether the logging has been initailised and logging can be performed
pluginGlobal['debug']['active']       = False  # Indicates no debugging active if False else indicates at least one type of debug is active
pluginGlobal['debug']['detailed']     = False  # For detailed debugging
pluginGlobal['debug']['listen']       = False
pluginGlobal['debug']['methodTrace']  = False  # For displaying method invocations i.e. trace method
pluginGlobal['debug']['announcement'] = False
pluginGlobal['debug']['send']         = False
pluginGlobal['debug']['receive']      = False
pluginGlobal['debug']['response']     = False
pluginGlobal['debug']['threading']    = False

methodNameForTrace = lambda: inspect.stack()[1][3]

# Logging Types
ANNOUNCE = 1
DETAIL   = 2
ERROR    = 3
INFO     = 4
LISTEN   = 5
METHOD   = 6
SEND     = 7
RECEIVE  = 8
THREAD   = 9
RESPONSE = 10


def autolog(logType, message):
    global pluginGlobal

    if pluginGlobal['debug']['initialised'] == False:
        if logType == INFO: 
            indigo.server.log(message)
        elif logType == ERROR:
            indigo.server.log(message, isError=True)
        return

    if logType == INFO:
        logTime = datetime.datetime.now().strftime("%H:%M:%S")
        pluginGlobal['autologger'].debug(str('%s [INF]: %s' %(logTime, message)))
        indigo.server.log(message)
        return
    elif logType == ERROR:
        logTime = datetime.datetime.now().strftime("%H:%M:%S")
        pluginGlobal['autologger'].debug(str('%s [ERR]: %s' %(logTime, message)))
        indigo.server.log(message, isError=True)
        return
    else:
        if pluginGlobal['debug']['active']  == False:
            return

    logTime = datetime.datetime.now().strftime("%H:%M:%S")
        
    if logType == METHOD:
        if pluginGlobal['debug']['methodTrace']  == True:
            pluginGlobal['autologger'].debug(str('%s [MTH]: %s' %(logTime, message)))
    elif logType == DETAIL:
        if pluginGlobal['debug']['detailed']  == True:
            pluginGlobal['autologger'].debug(str('%s [DET]: %s' %(logTime, message)))
    elif logType == ANNOUNCE:
        if pluginGlobal['debug']['announcement']  == True:
            pluginGlobal['autologger'].debug(str('%s [ANN]: %s' %(logTime, message)))
    elif logType == SEND:
        if pluginGlobal['debug']['send']  == True:
            pluginGlobal['autologger'].debug(str('%s [SND]: %s' %(logTime, message)))
    elif logType == RECEIVE:
        if pluginGlobal['debug']['receive']  == True:
            pluginGlobal['autologger'].debug(str('%s [RCV]: %s' %(logTime, message)))
    elif logType == THREAD:
        if pluginGlobal['debug']['threading']  == True:
            pluginGlobal['autologger'].debug(str('%s [THR]: %s' %(logTime, message)))
    elif logType == LISTEN:
        if pluginGlobal['debug']['listen']  == True:
            pluginGlobal['autologger'].debug(str('%s [LIS]: %s' %(logTime, message)))
    elif logType == RESPONSE:
        if pluginGlobal['debug']['response']  == True:
            pluginGlobal['autologger'].debug(str('%s [HSR]: %s' %(logTime, message)))
    else:
        indigo.server.log(u'AUTOLOG LOGGING - INVALID TYPE: %s' % (logType), isError=True)
        indigo.server.log(message, isError=True)


def signalWakeupQueues(queueToWakeup):
    global pluginGlobal
 
    try:
        autolog(DETAIL, '=================> signalWakeupQueues invoked for %s <========================' % queueToWakeup)

        queueToWakeup.put(['WAKEUP'])

    except StandardError, e:
        # autolog(ERROR, u"StandardError detected for '%s' with function '%s'. Line '%s' has error='%s'" % (indigo.devices[self.process[0]].name, self.process[1], sys.exc_traceback.tb_lineno, e))   
        autolog(ERROR, u"StandardError detected in signalWakeupQueues.  Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   


class communicateWithServerThread(threading.Thread):

    def __init__(self, _devId, _host, _port):
        global pluginGlobal

        threading.Thread.__init__(self)

        self.devId = _devId
        self.host = _host
        self.port = int(_port)
        self.name = indigo.devices[self.devId].description

        autolog(THREAD, u"Initialising Communication Thread for %s:%d [%s]" % (self.host, self.port, self.name))  
  
    def run(self):
        global pluginGlobal
        autolog(METHOD, u"METHOD TRACE [communicateWithServerThread]: %s" %  (methodNameForTrace()))  

        try:
            autolog(THREAD, u"ThreadSqueezeboxServer creating socket for %s: Host=[%s], Port=[%d]" % (self.name, self.host, self.port))   
            self.squeezeboxReadWriteSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    # create a TCP socket

            autolog(THREAD, u"ThreadSqueezeboxServer Starting socket connect for %s: Host=[%s], Port=[%d]" % (self.name, self.host, self.port))   
            self.squeezeboxReadWriteSocket.connect((self.host, self.port)) # connect to server on the port
            # self.squeezeboxReadWriteSocket.settimeout(5)

            try:
                autolog(THREAD, u"Communication Thread initialised for %s: Host=[%s], Port=[%d]" % (self.name, self.host, self.port))  
   
                while pluginGlobal['servers'][self.devId]['keepThreadAlive']:

                    self.sendMessage = pluginGlobal['queues']['commandToSend'][self.devId].get()
                    try:
                        if isinstance(self.sendMessage, list) and self.sendMessage[0] == 'WAKEUP':
                            pluginGlobal['timers']['commandToSend'][self.devId] = threading.Timer(5.0, signalWakeupQueues, [pluginGlobal['queues']['commandToSend'][self.devId]])
                            pluginGlobal['timers']['commandToSend'][self.devId].start()
                        else:
                            testInstance = isinstance(self.sendMessage, tuple)
                            autolog(DETAIL, u"self.sendMessage [Type=%s][%s] = %s" % (type(self.sendMessage), testInstance, self.sendMessage))

                            if isinstance(self.sendMessage, tuple):
                                self.sendMessage = self.sendMessage[0]
                            self.sendMessage = self.sendMessage.rstrip()    

                            autolog(SEND, u"%s" % (self.sendMessage))

                            self.squeezeboxReadWriteSocket.sendall(self.sendMessage + '\n')
                            self.response = self.squeezeboxReadWriteSocket.recv(1024)
                            while self.response[-1:] != "\n":
                                self.response = self.response + self.squeezeboxReadWriteSocket.recv(1024)
                            self.response = self.response.decode('utf-8').strip()

                            autolog(DETAIL, u"RECEIVED SERVER RESPONSE Type/Length =  [%s]/[%s]" % (type(self.response), len(self.response)))

                            autolog(RECEIVE, u"%s" % (urllib2.unquote(self.response.rstrip())))

                            pluginGlobal['queues']['returnedResponse'].put([self.devId, 'REPLY-TO-SEND', self.response])

                    except socket.error, e:
                        if isinstance(e.args, tuple):
                            if e[0] == errno.EPIPE:
                                autolog(ERROR, u"Communication Thread detected Server [%s] has disconnected." % (self.name))
                            elif e[0] == errno.ECONNRESET:
                                autolog(ERROR, u"Communication Thread detected Server [%s] has reset connection." % (self.name))
                            elif e[0] == errno.ETIMEDOUT:
                                autolog(ERROR, u"Communication Thread detected Server [%s] has timed out." % (self.name))
                            else:
                                autolog(ERROR, u"Communication Thread detected error communicating with Server [%s]. Line '%s' has error code ='%s'" % (self.name, sys.exc_traceback.tb_lineno, e[0]))
                        else:
                            autolog(ERROR, u"Communication Thread detected socket error. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
                        break   
                    except StandardError, e:
                        autolog(ERROR, u"Communication Thread detected StandardError. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
                        break   


            except StandardError, e:
                autolog(ERROR, u"Communication Thread detected error. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   

        except Exception, e:
            autolog(ERROR, u"Communication Thread unable to start: %s:%d [%s] [Reason = %s]" % (self.host, self.port, self.name, e))

        try:
            pluginGlobal['servers'][self.devId]['status'] = 'unavailable'
            indigo.devices[self.devId].updateStateOnServer(key="status", value=pluginGlobal['servers'][self.devId]['status'])

            for dev in indigo.devices.iter(filter="self"):
                if dev.deviceTypeId == "squeezeboxPlayer" and dev.states['serverId'] == self.devId:  # devID is id of server
                    pluginGlobal['players'][dev.id]['powerUi'] = 'disconnected'
                    dev.updateStateOnServer(key="power",  value=pluginGlobal['players'][dev.id]['powerUi'])
                    dev.updateStateOnServer(key="state",  value=pluginGlobal['players'][dev.id]['powerUi'])
                    if float(indigo.server.apiVersion) >= 1.18:
                        dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

            pluginGlobal['servers'][self.devId]['keepThreadAlive'] = False

            autolog(ERROR, u"Communication Thread ended for %s:%d [%s]" % (self.host, self.port, self.name)) 

        except Exception, e:
            autolog(ERROR, u"Communication Thread unable to start: %s:%d [%s] [Reason = %s]" % (self.host, self.port, self.name, e))   
    

        thread.exit()


# http://192.168.1.8:9000/imageproxy/http%3A%2F%2Fstatic.qobuz.com%2Fimages%2Fcovers%2F95%2F34%2F0884463063495_600.jpg/image.jpg

# http://192.168.1.8:9000/imageproxy/http%3A%2F%2Fstatic.qobuz.com%2Fimages%2Fcovers%2F76%2F20%2F0822189012076_600.jpg/image.jpg

#                         imageproxy/http%3A%2F%2Fstatic.qobuz.com%2Fimages%2Fcovers%2F76%2F20%2F0822189012076_600.jpg/image_96x96_p.jpg

class listenToServerThread(threading.Thread):

    def __init__(self, _devId, _host, _port):
        global pluginGlobal

        threading.Thread.__init__(self)

        self.devId = _devId
        self.host = _host
        self.port = int(_port)
        self.name = indigo.devices[self.devId].description

        autolog(THREAD, u"Initialising Listen Thread for %s:%s [%s]" % (self.host, self.port, self.name))   

  
    def run(self):
        global pluginGlobal
        autolog(METHOD, u"METHOD TRACE [listenToServerThread]: %s" %  (methodNameForTrace()))  

        try:
            autolog(THREAD, u"listen Thread starting socket listen for %s:%d [%s]" % (self.host, self.port, self.name))     

            self.squeezeboxListenSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)    # create a TCP socket
            self.squeezeboxListenSocket.connect((self.host, self.port)) # connect to server on the port

            try:
                autolog(THREAD, u"Listen Thread initialised for %s:%d [%s]" % (self.host, self.port, self.name))    
                self.squeezeboxListenSocket.settimeout(5)
                self.squeezeboxListenSocket.sendall("listen 1" + '\n')
                while pluginGlobal['servers'][self.devId]['keepThreadAlive']:
                    try:
                        loopTimeCheck = indigo.server.getTime()
                        # autolog(THREAD, u"TIMEOUT LISTEN THREAD TEST")
                        for self.line in self.squeezeboxListenSocket.makefile('r'):
                            self.line = self.line.encode('ascii','replace')
                            pluginGlobal['queues']['returnedResponse'].put([self.devId, 'LISTEN-NOTIFICATION', self.line])
                            try:
                                autolog(LISTEN, u"%s" % (urllib2.unquote(self.line.rstrip())))
                            except:
                                pass
                        if len(self.line) < 10:
                            pass  

                    except socket.error, e:
                        if isinstance(e.args, tuple):
                            if e[0] == errno.EPIPE:
                                autolog(ERROR, u"Listen Thread detected Server [%s] disconnected." % (self.name))   
                            elif e[0] == errno.ECONNRESET:
                                autolog(ERROR, u"Listen Thread detected Server [%s] has reset connection." % (self.name))
                            elif e[0] == 'timed out':
                                loopTimeCheck = loopTimeCheck + datetime.timedelta(seconds=3)
                                if indigo.server.getTime() > loopTimeCheck:
                                    # autolog(THREAD, u"Listen Thread detected Server [%s] has timed out but will continue." % (self.name))
                                    continue
                                autolog(ERROR, u"Listen Thread detected Server [%s] has timed out." % (self.name))
                            else:
                                autolog(ERROR, u"Listen Thread detected error communicating with Server [%s]. Line '%s' has error = '%s'" % (self.name, sys.exc_traceback.tb_lineno, e[0]))
                        else:
                            autolog(ERROR, u"Listen Thread detected socket error. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
                        break   
                    except Exception, e:
                        autolog(ERROR, u"Listen Thread detected StandardError. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))
                        break   

            except Exception, e:
                autolog(ERROR, u"listen Thread starting ERROR: %s:%d [Line: %s, Exception = %s]" % (self.host, self.port, sys.exc_traceback.tb_lineno, e))

        except Exception, e:
            autolog(ERROR, u"Listen Thread unable to start: %s:%d [%s] [Reason = %s]" % (self.host, self.port, self.name, e))   

        try:
            pluginGlobal['servers'][self.devId]['status'] = 'unavailable'
            indigo.devices[self.devId].updateStateOnServer(key="status", value=pluginGlobal['servers'][self.devId]['status'])

            for dev in indigo.devices.iter(filter="self"):
                if dev.deviceTypeId == "squeezeboxPlayer" and dev.states['serverId'] == self.devId:  # devID is id of server
                    pluginGlobal['players'][dev.id]['powerUi'] = 'disconnected'
                    dev.updateStateOnServer(key="power",  value=pluginGlobal['players'][dev.id]['powerUi'])
                    dev.updateStateOnServer(key="state",  value=pluginGlobal['players'][dev.id]['powerUi'])
                    if float(indigo.server.apiVersion) >= 1.18:
                        dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

            # time.sleep(15)
            # indigo.device.enable(self.devId, value=False)
            # indigo.device.enable(self.devId, value=True)

            autolog(ERROR, u"Listen Thread ended for %s:%d [%s]" % (self.host, self.port, self.name))     

        except Exception, e:
            autolog(ERROR, u"Listen Thread unable to start: %s:%d [%s] [Reason = %s]" % (self.host, self.port, self.name, e))   

        pluginGlobal['servers'][self.devId]['keepThreadAlive'] = False

        thread.exit()   


class Plugin(indigo.PluginBase):

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):

        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        self.validatePrefsConfigUi(pluginPrefs)  # Validate the Plugin Config before plugin initialisation


    def __del__(self):

        indigo.PluginBase.__del__(self)


    def startup(self):
        global pluginGlobal
        # autolog(METHOD, u"%s" %  (methodNameForTrace()))

        pluginGlobal['coverArt']['noCoverArtFile'] = str('%s/Plugins/Squeezebox.indigoPlugin/Contents/Resources/nocoverart.jpg' %(indigo.server.getInstallFolderPath()))
        pluginGlobal['coverArt']['noCoverArtFileUrl'] = str('file://%s' %(pluginGlobal['coverArt']['noCoverArtFile']))

        pluginGlobal['queues']['returnedResponse'] = autologQueue()  # For server responses and UI commands

        pluginGlobal['queues']['announcementQueue'] = autologQueue()  # For queued announcements (Announcements are queued when one is already active)

        signalWakeupQueues(pluginGlobal['queues']['returnedResponse'])

        pluginGlobal['debug']['detailed']         = bool(self.pluginPrefs.get("debugDetailed", False))  # For detailed debugging
        pluginGlobal['debug']['listen']           = bool(self.pluginPrefs.get("debugListen", False))
        pluginGlobal['debug']['methodTrace']      = bool(self.pluginPrefs.get("debugMethodTrace", False))  # For displaying method invocations i.e. trace method
        pluginGlobal['debug']['announcement']     = bool(self.pluginPrefs.get("debugPlayAnnouncement", False))
        pluginGlobal['debug']['send']             = bool(self.pluginPrefs.get("debugSend", False))
        pluginGlobal['debug']['receive']          = bool(self.pluginPrefs.get("debugReceive", False))
        pluginGlobal['debug']['threading']        = bool(self.pluginPrefs.get("debugThreading", False))
        pluginGlobal['debug']['response']         = bool(self.pluginPrefs.get("debugResponse", False))

        pluginGlobal['debug']['active'] = pluginGlobal['debug']['detailed'] or pluginGlobal['debug']['listen'] or pluginGlobal['debug']['methodTrace'] or pluginGlobal['debug']['announcement'] or pluginGlobal['debug']['send'] or pluginGlobal['debug']['receive'] or pluginGlobal['debug']['threading'] or pluginGlobal['debug']['response']

        self.validateDeviceFlag = {}
        self.validateActionFlag = {}

        self.deviceFolderName = "Squeezebox"
        if (self.deviceFolderName not in indigo.devices.folders):
            self.deviceFolder = indigo.devices.folder.create(self.deviceFolderName)
        self.deviceFolderId = indigo.devices.folders.getId(self.deviceFolderName)

        debugFile = str('%s/%s' %(pluginGlobal['debug']['debugFolder'], 'autolog/squeezebox/debug/debug.txt'))
        pluginGlobal['autologger'] = logging.getLogger(debugFile)
        pluginGlobal['autologger'].setLevel(logging.DEBUG)
        handler = TimedRotatingFileHandler(debugFile, when="midnight", interval=1, backupCount=6)
        pluginGlobal['autologger'].addHandler(handler)

        pluginGlobal['debug']['initialised'] = True

        indigo.devices.subscribeToChanges()

        autolog(INFO, u"Autolog 'Squeezebox Controller' initialization complete")

    def shutdown(self):

        autolog(DETAIL, u"shutdown called")


    def validatePrefsConfigUi(self, valuesDict):
        global pluginGlobal
#        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        pluginGlobal['coverArtFolder'] = valuesDict.get("coverArtFolder", pluginGlobal['baseFolder'])

        if not os.path.exists(pluginGlobal['coverArtFolder']):
            errorDict = indigo.Dict()
            errorDict["coverArtFolder"] = "Folder doesn't exist"
            errorDict["showAlertText"] = "Folder doesn't exist, please specify a valid folder."
            return (False, valuesDict, errorDict)

        try:
            path = str('%s/%s' %(pluginGlobal['coverArtFolder'], 'autolog/squeezebox'))
            os.makedirs(path)
        except OSError, e:
            if e.errno != errno.EEXIST:
                errorDict = indigo.Dict()
                errorDict["coverArtFolder"] = str("Error creating '%s' folder. Error = %s" % (path, e))
                errorDict["showAlertText"] = "Error creating cover art autolog folder - please correct error."
                return (False, valuesDict, errorDict)


        pluginGlobal['announcement']['announcementTempFolder'] = valuesDict.get("announcementTempFolder", pluginGlobal['baseFolder'])

        if not os.path.exists(pluginGlobal['announcement']['announcementTempFolder']):
            errorDict = indigo.Dict()
            errorDict["announcementTempFolder"] = "Folder doesn't exist"
            errorDict["showAlertText"] = "Folder doesn't exist, please specify a valid folder."
            return (False, valuesDict, errorDict)

        try:
            path = str('%s/%s' %(pluginGlobal['announcement']['announcementTempFolder'], 'autolog/squeezebox'))
            os.makedirs(path)
        except OSError, e:
            if e.errno != errno.EEXIST:
                errorDict = indigo.Dict()
                errorDict["announcementTempFolder"] = str("Error creating '%s' folder. Error = %s" % (path, e))
                errorDict["showAlertText"] = "Error creating temporary autolog folder - please correct error."
                return (False, valuesDict, errorDict)

        pluginGlobal['debug']['debugFolder'] = valuesDict.get("debugFolder", pluginGlobal['baseFolder'])

        if not os.path.exists(pluginGlobal['debug']['debugFolder']):
            errorDict = indigo.Dict()
            errorDict["debugFolder"] = "Folder doesn't exist"
            errorDict["showAlertText"] = "Folder doesn't exist, please specify a valid folder."
            return (False, valuesDict, errorDict)

        try:
            path = str('%s/%s' %(pluginGlobal['debug']['debugFolder'], 'autolog/squeezebox/debug'))
            os.makedirs(path)
        except OSError, e:
            if e.errno != errno.EEXIST:
                errorDict = indigo.Dict()
                errorDict["debugFolder"] = str("Error creating '%s' folder. Error = %s" % (path, e))
                errorDict["showAlertText"] = "Error creating debug folder - please correct error."
                return (False, valuesDict, errorDict)

        pluginGlobal['debug']['detailed']     = bool(valuesDict.get("debugDetailed", False))
        pluginGlobal['debug']['listen']       = bool(valuesDict.get("debugListen", False))
        pluginGlobal['debug']['methodTrace']  = bool(valuesDict.get("debugMethodTrace", False))  # For displaying method invocations i.e. trace method
        pluginGlobal['debug']['announcement'] = bool(valuesDict.get("debugPlayAnnouncement", False))
        pluginGlobal['debug']['send']         = bool(valuesDict.get("debugSend", False))
        pluginGlobal['debug']['receive']      = bool(valuesDict.get("debugReceive", False))
        pluginGlobal['debug']['threading']    = bool(valuesDict.get("debugThreading", False))
        pluginGlobal['debug']['response']     = bool(valuesDict.get("debugResponse", False))

        pluginGlobal['debug']['active'] = pluginGlobal['debug']['detailed'] or pluginGlobal['debug']['listen'] or pluginGlobal['debug']['methodTrace'] or pluginGlobal['debug']['announcement'] or pluginGlobal['debug']['send'] or pluginGlobal['debug']['receive'] or pluginGlobal['debug']['threading'] or pluginGlobal['debug']['response']

        if pluginGlobal['debug']['active'] == False:
            autolog(INFO, u"No debug logging requested")
        else:
            debugTypes = []
            if pluginGlobal['debug']['detailed'] == True:
                debugTypes.append('Detailed')
            if pluginGlobal['debug']['listen'] == True:
                debugTypes.append('Listen')
            if pluginGlobal['debug']['methodTrace'] == True:
                debugTypes.append('Method Trace')
            if pluginGlobal['debug']['announcement'] == True:
                debugTypes.append('Announcement')
            if pluginGlobal['debug']['send'] == True:
                debugTypes.append('Send')
            if pluginGlobal['debug']['receive'] == True:
                debugTypes.append('Receive')
            if pluginGlobal['debug']['threading'] == True:
                debugTypes.append('Threading')
            if pluginGlobal['debug']['response'] == True:
                debugTypes.append('Response')

            loop = 0
            message = ''
            for debugType in debugTypes:
                if loop == 0:
                    message = message + debugType
                else:
                    message = message + ', ' + debugType
                loop += 1

            autolog(INFO, u"Debug logging active for debug types: %s" % (message))  

        return True


    # def runConcurrentThread(self):
    #     global pluginGlobal
    #     autolog(METHOD, u"%s" %  (methodNameForTrace()))  

    #     try:
    #         while True:
    #             try:
    #                 self.process = pluginGlobal['queues']['returnedResponse'].get(True,1)
    #                 # autolog(DETAIL, u"QUEUE GET = %s" % (self.process))
    #                 try:   
    #                     self.handleSqueezeboxServerResponse(indigo.devices[self.process[0]], self.process[1], self.process[2])
    #                     if pluginGlobal['queues']['returnedResponse'].qsize() == 0:
    #                         pluginGlobal['timers']['returnedResponse'] = threading.Timer(5.0, signalWorker, [pluginGlobal['queues']['returnedResponse']])

    #                 except StandardError, e:
    #                     autolog(ERROR, u"StandardError detected for '%s' with function '%s'. Line '%s' has error='%s'" % (indigo.devices[self.process[0]].name, self.process[1], sys.exc_traceback.tb_lineno, e))   
    #             except autologQueueEmpty:
    #                 pass
    #                 # autolog(DETAIL, u"Queue EMPTY")
    #                 if self.stopThread:
    #                     raise self.StopThread         # Plugin shutdown request.
    #     except self.StopThread:
    #         pass    # Optionally catch the StopThread exception and do any needed cleanup.
    #         # autolog(DETAIL, u"self.StopThread DETECTED")   


    def runConcurrentThread(self):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        try:
            while True:
                self.process = pluginGlobal['queues']['returnedResponse'].get()
                try:
                    if self.process[0] != 'WAKEUP':   
                        self.handleSqueezeboxServerResponse(indigo.devices[self.process[0]], self.process[1], self.process[2])
                    else:
                        if self.stopThread:
                            raise self.StopThread         # Plugin shutdown request.
                        else:
                            pluginGlobal['timers']['returnedResponse'] = threading.Timer(5.0, signalWakeupQueues, [pluginGlobal['queues']['returnedResponse']])
                            pluginGlobal['timers']['returnedResponse'].start()

                except StandardError, e:
                    autolog(ERROR, u"StandardError detected. Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))   
        except self.StopThread:
            pass


    def validateActionConfigUi(self, valuesDict, typeId, actionId):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        self.validateActionFlag[actionId] = {}

        self.validateActionFlag.clear()

        return (True, valuesDict)

    def _serverConnectedTest(self, dev, pluginAction):    
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if dev == None:
            autolog(ERROR, u"'%s' action ignored as Squeezebox Server to perform action isn't specified." % (pluginAction.description))
            return False
        elif dev.states['status'] != 'connected':
            autolog(ERROR, u"'%s' action ignored as Squeezebox Server '%s' is not available." % (pluginAction.description, dev.name))
            return False

        return True


    def _playerConnectedTest(self, dev, pluginAction):    
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        if dev == None:
            autolog(ERROR, u"'%s' action ignored as Squeezebox Player to perform action isn't specified." % (pluginAction.description))
            return False
        elif dev.states['connected'] == False:
            autolog(ERROR, u"'%s' action ignored as Squeezebox Player '%s' is disconnected." % (pluginAction.description, dev.name))
            return False

        return True


    def processRefreshServerStatus(self, pluginAction, dev):  # Dev is a Squeezebox Server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        if self._serverConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][dev.id].put("serverstatus 0 0 subscribe:0")


    def processPowerOnAll(self, pluginAction, dev):  # Dev is a Squeezebox Server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        for selectedPlayerId in pluginGlobal['players']:
            autolog(DETAIL, "Player [%s] has Mac Address '%s'" % (selectedPlayerId, pluginGlobal['players'][selectedPlayerId]['mac']))
            if pluginGlobal['players'][selectedPlayerId]['powerUi'] != "disconnected":   
                pluginGlobal['queues']['commandToSend'][dev.id].put(pluginGlobal['players'][selectedPlayerId]['mac'] + " power 1")


    def processPowerOffAll(self, pluginAction, dev):  # Dev is a Squeezebox Server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        for selectedPlayerId in pluginGlobal['players']:
            autolog(DETAIL, "Player [%s] has Mac Address '%s'" % (selectedPlayerId, pluginGlobal['players'][selectedPlayerId]['mac']))
            if pluginGlobal['players'][selectedPlayerId]['powerUi'] != "disconnected":   
                pluginGlobal['queues']['commandToSend'][dev.id].put(pluginGlobal['players'][selectedPlayerId]['mac'] + " power 0")


    def processPowerOn(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " power 1")


    def processPowerOff(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " power 0")


    def processPowerToggleOnOff(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " power")


    def processPlay(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " play")
 

    def processStop(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " stop")


    def processPause(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " pause")


    def processForward(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " button fwd")


    def processRewind(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " button rew")


    def processVolumeSet(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        if self._playerConnectedTest(dev, pluginAction): 
            volume = pluginAction.props.get("volumeSetValue")
            if self._validateVolume(volume):  
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " mixer volume " + volume)
            else:
                autolog(ERROR, u"Set volume of '%s' to value of '%s' is invalid" % (dev.name, volume),isError=True)


    def _validateVolume(self,volume):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        if volume.isdigit() and int(volume) >= 0 and int(volume) <= 100:
            return (True, volume)

        return (False)

    def processVolumeIncrease(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            force = pluginAction.props.get("forceVolumeToMultipleOfIncrease", False)

            volumeIncreaseValue = pluginAction.props.get("volumeIncreaseValue", "5")
            if self._validateVolume(volumeIncreaseValue):  
                volumeIncreaseValue = int(volumeIncreaseValue)
                volume = int(pluginGlobal['players'][dev.id]['volume']) 

                if force == True and volumeIncreaseValue > 0:
                    if (volume % volumeIncreaseValue) != 0:
                        volumeIncreaseValue = volumeIncreaseValue - (volume % volumeIncreaseValue)

                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " mixer volume +" + str(volumeIncreaseValue))


    def processVolumeDecrease(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            force = pluginAction.props.get("forceVolumeToMultipleOfDecrease", False)

            volumeDecreaseValue = pluginAction.props.get("volumeDecreaseValue", "5")
            if self._validateVolume(volumeDecreaseValue):  
                volumeDecreaseValue = int(volumeDecreaseValue)
                volume = int(pluginGlobal['players'][dev.id]['volume']) 

                if force == True and volumeDecreaseValue > 0:
                    if (volume % volumeDecreaseValue) != 0:
                        volumeDecreaseValue = (volume % volumeDecreaseValue)

                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " mixer volume -" + str(volumeDecreaseValue))


    def processVolumeMute(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction):
            if pluginAction.props.get("volumeMuteAll", False):
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " autologMixerMuteAll")
            else:
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " mixer muting 1")


    def processVolumeUnmute(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction):
            if pluginAction.props.get("volumeUnmuteAll", False):
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " autologMixerUnmuteAll")
            else:
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " mixer muting 0")


    def processVolumeToggleMute(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction):
            if pluginAction.props.get("volumeToggleMuteAll", False):
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " autologMixerToggleMuteAll")
            else:
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " mixer muting toggle")

    def processPlayPreset(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " button playPreset_" + pluginAction.props.get("preset"))


    def processPlayFavorite(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " favorites playlist play item_id:" + pluginAction.props.get("favorite"))


    def processPlayPlaylist(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            if os.path.isfile(pluginAction.props.get("playlist")):
                autolog(INFO, "Play Playlist ['%s'] requested for '%s'." % (pluginAction.props.get("playlist"), dev.name))

                self.playlistFile = str(pluginAction.props.get("playlist")).replace(' ','%20')
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put("readdirectory 0 1 autologFunction:PlaylistCheck autologDevice:%s folder:%s filter:%s" % (str(dev.id), os.path.dirname(self.playlistFile), os.path.basename(self.playlistFile)))
            else:
                autolog(ERROR, "Play Playlist not actioned for '%s' as playlist ['%s'] not found." % (dev.name, pluginAction.props.get("playlist")))


    def processClearPlaylist(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction):
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " playlist clear")

    def processShuffle(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction):
            actionOptionShuffle = pluginAction.props.get('optionShuffle','off')
            if actionOptionShuffle == 'off':
                optionShuffle = '0'
            elif actionOptionShuffle == 'song':
                optionShuffle = '1'
            elif actionOptionShuffle == 'album':
                optionShuffle = '2'
            elif actionOptionShuffle == 'toggle':
                optionShuffle = ''
            else:
                optionShuffle = ''

            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " playlist shuffle " + optionShuffle)


    def processRepeat(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction):
            actionOptionRepeat = pluginAction.props.get('optionRepeat','off')
            if actionOptionRepeat == 'off':
                optionRepeat = '0'
            elif actionOptionRepeat == 'song':
                optionRepeat = '1'
            elif actionOptionRepeat == 'playlist':
                optionRepeat = '2'
            elif actionOptionRepeat == 'toggle':
                optionRepeat = ''
            else:
                optionRepeat = ''
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " playlist repeat " + optionRepeat)


    def processResetAnnouncement(self, pluginAction, dev):  # Dev is a Squeezebox Server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if pluginGlobal['announcement']['active'] != 'NO':
            pluginGlobal['announcement']['active'] = 'NO'
            pluginGlobal['announcement']['Initialised'] = False 
            autolog(INFO, "Reset Announcement actioned")
        else:
            autolog(INFO, "Reset Announcement ignored as Play Announcement not currently in progress.")

        pluginGlobal['queues']['announcementQueue'].queue.clear
 

    def processPlayAnnouncement(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        announcementUniqueKey = str(int(time.time()*1000))
        autolog(ANNOUNCE, "Unique Key = [%s]" % (announcementUniqueKey))
        pluginGlobal['announcement'][announcementUniqueKey] = {}

        if self._playerConnectedTest(dev, pluginAction): 

            pluginGlobal['announcement'][announcementUniqueKey]['option'] = pluginAction.props.get("optionAnnouncement")
            pluginGlobal['announcement'][announcementUniqueKey]['volume'] = pluginAction.props.get("announcementVolume","50")
  
            if pluginGlobal['announcement'][announcementUniqueKey]['option'] == 'file':
                pluginGlobal['announcement'][announcementUniqueKey]['file'] = str(pluginAction.props.get("announcementFile")).replace(' ','%20')

                if pluginGlobal['announcement']['active'] == 'NO':
                    pluginGlobal['announcement']['active'] = 'PENDING'
                    # pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey)
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey)
                else:
                    autolog(INFO, "Announcement queued for '%s' as a Play Announcement is currently in progress." % (indigo.devices[dev.id].name))

                    # pluginGlobal['queues']['announcementQueue'].put((pluginGlobal['players'][dev.id]['serverId'], pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey))
                    pluginGlobal['queues']['announcementQueue'].put((pluginGlobal['players'][dev.id]['serverId'], pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey))

            elif pluginGlobal['announcement'][announcementUniqueKey]['option'] == 'speech':
                # perform variable / device substitution
                textToSpeak = pluginAction.props.get("announcementText", "No speech text specified")
                textToSpeakvalidation = self.substitute(textToSpeak, validateOnly=True)
                if textToSpeakvalidation[0] == True:
                    pluginGlobal['announcement'][announcementUniqueKey]['speechText'] = self.substitute(textToSpeak, validateOnly=False)
                else:
                    autolog(ERROR, "Announcement 'Text to Speak' ['%s'] has an error: [%s]" % (textToSpeak, textToSpeakvalidation[1]))
                    return

                pluginGlobal['announcement'][announcementUniqueKey]['voice'] = pluginAction.props.get("announcementVoice")

                autolog(ANNOUNCE, "speechText (Processed) = [%s]" % (pluginGlobal['announcement'][announcementUniqueKey]['speechText']))

                autolog(ANNOUNCE, "announcementPrepend = '%s', announcementAppend = '%s'" % (pluginAction.props.get("announcementPrepend"), pluginAction.props.get("announcementAppend")))

                if pluginAction.props.get("announcementPrepend") == True:
                    autolog(ANNOUNCE, "announcementPrepend ACTIVE")
                    pluginGlobal['announcement'][announcementUniqueKey]['prepend'] = str(pluginAction.props.get("announcementPrependFile")).replace(' ','%20')

                if pluginAction.props.get("announcementAppend") == True:
                    autolog(ANNOUNCE, "announcementAppend ACTIVE")
                    pluginGlobal['announcement'][announcementUniqueKey]['append'] = str(pluginAction.props.get("announcementAppendFile")).replace(' ','%20')

                if pluginGlobal['announcement']['active'] == 'NO':
                    pluginGlobal['announcement']['active'] = 'PENDING'
                    # pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put((pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey))
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put((pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey))
                else:
                    autolog(INFO, "Announcement queued for '%s' as a Play Announcement is currently in progress." % (indigo.devices[dev.id].name))
                    # pluginGlobal['queues']['announcementQueue'].put((pluginGlobal['players'][dev.id]['serverId'], pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey))
                    pluginGlobal['queues']['announcementQueue'].put((pluginGlobal['players'][dev.id]['serverId'], pluginGlobal['players'][dev.id]['mac'] + " autologAnnouncementRequest " + announcementUniqueKey))
                

    def processPlayerRawCommand(self, pluginAction, dev):  # Dev is a Squeezebox Player
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._playerConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.id]['serverId']].put(pluginGlobal['players'][dev.id]['mac'] + " " + pluginAction.props.get("rawPlayerCommand"))


    def processServerRawCommand(self, pluginAction, dev):  # Dev is a Squeezebox Server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if self._serverConnectedTest(dev, pluginAction): 
            pluginGlobal['queues']['commandToSend'][dev.id].put(pluginAction.props.get("rawServerCommand"))
 

    def processSpeechVoiceGenerator(self, filter="", valuesDict=None, typeId="", targetId=0):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        autolog(DETAIL, u"SQUEEZEBOX PLUGIN - processSpeechVoiceGenerator [valuesDict]=[%s]" % (valuesDict)) 

        self.dictTest = []

        for appleVoice in NSSpeechSynthesizer.availableVoices():
            # autolog(DETAIL, u'NSSpeechSynthesizer.availableVoice[%s] = [%s]' % (type(appleVoice), appleVoice))
            if appleVoice.rsplit('.', 1)[1] == 'premium':
                voiceName = str("%s [Premium]" % (appleVoice.rsplit('.', 2)[1]))
            else:
                voiceName = appleVoice.rsplit('.', 1)[1]


            self.dictTest.append((appleVoice, voiceName))

        # autolog(DETAIL, "self.dictTest [Type: %s ]: %s" % (type(self.dictTest),self.dictTest))

        myArray = self.dictTest
        return myArray


    def validateActionConfigUi(self, valuesDict, typeId, actionId):
        autolog(ANNOUNCE, u"validateActionConfigUi TypeId=[%s], ActionId=[%s] - %s" %  (str(typeId), str(actionId), valuesDict))  

        if typeId == 'volumeSet':
            volume = ''
            if 'volumeSetValue' in valuesDict:
                volume = valuesDict['volumeSetValue']
            if self._validateVolume(volume):
                return True
            errorDict = indigo.Dict()
            errorDict["volumeSetValue"] = "The value of this field must be between 0 to 100 inclusive."
            errorDict["showAlertText"] = "Invalid Volume Set Value specified."
            return (False, valuesDict, errorDict)

        if typeId == 'volumeIncrease':
            volume = ''
            if 'volumeIncreaseValue' in valuesDict:
                volume = valuesDict['volumeIncreaseValue']
            if self._validateVolume(volume):
                return True
            errorDict = indigo.Dict()
            errorDict["volumeIncreaseValue"] = "The value of this field must be between 0 to 100 inclusive, though a number like 5 would be sensible."
            errorDict["showAlertText"] = "Invalid Volume Increase Value specified."
            return (False, valuesDict, errorDict)

        if typeId == 'volumeDecrease':
            volume = ''
            if 'volumeDecreaseValue' in valuesDict:
                volume = valuesDict['volumeDecreaseValue']
            if self._validateVolume(volume):
                return True
            errorDict = indigo.Dict()
            errorDict["volumeDecreaseValue"] = "The value of this field must be between 0 to 100 inclusive, though a number like 5 would be sensible."
            errorDict["showAlertText"] = "Invalid Volume Decrease Value specified."
            return (False, valuesDict, errorDict)


        return True

    def handleSqueezeboxServerResponse(self, dev, processSqueezeboxFunction, responseFromSqueezeboxServer):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        try:
            self.currentTime = indigo.server.getTime()

            self.responseFromSqueezeboxServer = urllib2.unquote(responseFromSqueezeboxServer)

            autolog(RESPONSE, "[%s] %s" % (processSqueezeboxFunction[0:3], self.responseFromSqueezeboxServer.rstrip()))

            self.serverResponse = self.responseFromSqueezeboxServer.split()

            self.serverResponseKeyword = self.serverResponse[0]
            try:
                self.serverResponseKeyword2 = self.serverResponse[1]
            except:
                self.serverResponseKeyword2 = ''
            autolog(DETAIL, "HANDLE SERVER RESPONSE: KW1 = [%s], KW2 = [%s]" % (self.serverResponseKeyword, self.serverResponseKeyword2))

            #
            # Process response from server by analysing response and calling relevant handler
            #
            #   self.responseFromSqueezeboxServer  and self.serverResponse available to each handler (no need to pass as parameter)
            #

            if self.serverResponseKeyword == "serverstatus":
                self._handle_serverstatus(dev)  # dev = squeezebox server

            elif self.serverResponseKeyword == "syncgroups":
                self._handle_syncgroups(dev)  # dev = squeezebox server

            elif self.serverResponseKeyword == "players":
                self._handle_players(dev)  # dev = squeezebox server

            elif self.serverResponseKeyword == "player":
                if self.serverResponseKeyword2 == "id":
                    self._handle_player_id(dev)  # dev = squeezebox server

            elif self.serverResponseKeyword == "readdirectory":
                self._handle_readdirectory(dev)  # dev = squeezebox server

            elif self.serverResponseKeyword[2:3] == ":":  # i.e. the response is something like '00:04:20:aa:bb:cc mode play' and is a response for a Player
                self._handle_player(dev)  # dev = squeezebox server

        except StandardError, e:
            autolog(ERROR, u"StandardError detected for '%s' with function '%s'. Line '%s' has error='%s'" % (indigo.devices[self.process[0]].name, self.process[1], sys.exc_traceback.tb_lineno, e))   


    def _handle_serverstatus(self, dev):  # dev = squeezebox server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:  
            pluginGlobal['servers'][dev.id]['status'] = 'connected'
            dev.updateStateOnServer(key="status", value=pluginGlobal['servers'][dev.id]['status'])

            if float(indigo.server.apiVersion) >= 1.18:
                dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOn)


            self.responseToCommandServerstatus = re.findall(r'([^:]*:[^ ]*) *', self.responseFromSqueezeboxServer)  # Split the response into n times 'AAAA : BBBB'

            for self.serverstatusResponseEntry in self.responseToCommandServerstatus:
                self.serverstatusResponseEntryElements = self.serverstatusResponseEntry.partition(":")

                if self.serverstatusResponseEntryElements[0] == "lastscan":
                    pluginGlobal['servers'][dev.id]['lastScan'] = datetime.datetime.fromtimestamp(int(self.serverstatusResponseEntryElements[2])).strftime('%Y-%b-%d %H:%M:%S')
                    dev.updateStateOnServer(key="lastScan", value=pluginGlobal['servers'][dev.id]['lastScan'])
                elif self.serverstatusResponseEntryElements[0] == "version":
                    pluginGlobal['servers'][dev.id]['version'] = self.serverstatusResponseEntryElements[2]
                    dev.updateStateOnServer(key="version", value=pluginGlobal['servers'][dev.id]['version'])
                elif self.serverstatusResponseEntryElements[0] == "info total albums":
                    pluginGlobal['servers'][dev.id]['totalAlbums'] = self.serverstatusResponseEntryElements[2]
                    dev.updateStateOnServer(key="totalAlbums", value=pluginGlobal['servers'][dev.id]['totalAlbums'])
                elif self.serverstatusResponseEntryElements[0] == "info total artists":
                    pluginGlobal['servers'][dev.id]['totalArtists'] = self.serverstatusResponseEntryElements[2]
                    dev.updateStateOnServer(key="totalArtists", value=pluginGlobal['servers'][dev.id]['totalArtists'])
                elif self.serverstatusResponseEntryElements[0] == "info total genres":
                    pluginGlobal['servers'][dev.id]['totalGenres'] = self.serverstatusResponseEntryElements[2]
                    dev.updateStateOnServer(key="totalGenres", value=pluginGlobal['servers'][dev.id]['totalGenres'])
                elif self.serverstatusResponseEntryElements[0] == "info total songs":
                    pluginGlobal['servers'][dev.id]['totalSongs'] = self.serverstatusResponseEntryElements[2]
                    dev.updateStateOnServer(key="totalSongs", value=pluginGlobal['servers'][dev.id]['totalSongs'])
                elif self.serverstatusResponseEntryElements[0] == "player count":
                    pluginGlobal['servers'][dev.id]['playerCount'] = self.serverstatusResponseEntryElements[2]
                    self.loop = 0
                    while self.loop < int(self.serverstatusResponseEntryElements[2]):
                        pluginGlobal['queues']['commandToSend'][dev.id].put("players " + str(self.loop) +" 1")
                        self.loop += 1

                autolog(DETAIL, "  = %s [1=%s] [2=%s] [3=%s]" % (self.serverstatusResponseEntry,self.serverstatusResponseEntryElements[0],self.serverstatusResponseEntryElements[1],self.serverstatusResponseEntryElements[2]))

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _handle_syncgroups(self, dev):  # dev = squeezebox server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

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
                            pluginGlobal['players'][self.masterDevId]['masterPlayerId'] = 0
                            pluginGlobal['players'][self.masterDevId]['masterPlayerAddress'] = ''

                            autolog(ANNOUNCE, "SyncMaster = '%s' = '%s'" % (self.syncMember, self.masterDevId))
                        else:
                            self.slaveDevId = self._playerMACToDeviceId(self.syncMember.rstrip())
                            pluginGlobal['players'][self.slaveDevId ]['masterPlayerId'] = self.masterDevId
                            pluginGlobal['players'][self.slaveDevId ]['masterPlayerAddress'] = self.masterMAC
                            pluginGlobal['players'][self.slaveDevId ]['slavePlayerIds'] = []
                            pluginGlobal['players'][self.masterDevId]['slavePlayerIds'].append(self.slaveDevId)

                            autolog(ANNOUNCE, "slavePlayerIds = '%s'" % (pluginGlobal['players'][self.masterDevId]['slavePlayerIds']))

            self._playerUpdateSync()

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _handle_players(self, dev):  # dev = squeezebox server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:
            playerInfo = {}
            playerInfo['name']        = "Not specified"
            playerInfo['model']       = "Unknown"
            playerInfo['ipAddress']   = "Unknown"
            playerInfo['portAddress'] = "Unknown"
            playerInfo['powerUi']     = 'disconnected'
            playerInfo['playerid']    = 'disconnected'

            self.serverResponsePlayersElementName = re.findall(r'(?<=name:)(.*) model:', self.responseFromSqueezeboxServer)

            playerInfo['name'] = self.serverResponsePlayersElementName[0]
    
            self.serverResponsePlayersElementModel = re.findall(r'(?<=model:)(.*) isplayer:', self.responseFromSqueezeboxServer)
     
            playerInfo['model'] = self.serverResponsePlayersElementModel[0]
            if playerInfo['model'] == 'baby':
                playerInfo['model'] = 'Squeezebox Radio'
            elif playerInfo['model'] == 'boom':
                playerInfo['model'] = 'Squeezebox Boom'
            elif playerInfo['model'] == 'receiver':
                playerInfo['model'] = 'Squeezebox Receiver'
            elif playerInfo['model'] == 'fab4':
                playerInfo['model'] = 'Squeezebox Touch'

            autolog(DETAIL, str('DISCONNECT DEBUG [MODEL]: %s' % (playerInfo['model'])))


            self.serverResponsePlayers = re.findall(r'([^:]*:[^ ]*) *', self.responseFromSqueezeboxServer.rstrip())

            for self.serverResponsePlayersEntry in self.serverResponsePlayers:
                autolog(DETAIL, str('DISCONNECT DEBUG [ENTRY]: %s' % (self.serverResponsePlayersEntry)))
                self.serverResponsePlayersEntryElements = self.serverResponsePlayersEntry.partition(":")
                if self.serverResponsePlayersEntryElements[0] == 'playerid':
                    playerInfo['playerid'] = self.serverResponsePlayersEntryElements[2]
                elif self.serverResponsePlayersEntryElements[0] == 'ip':
                    self.serverStatusAddressElements = self.serverResponsePlayersEntryElements[2].partition(":")
                    playerInfo['ipAddress'] = self.serverStatusAddressElements[0]
                    playerInfo['portAddress'] = self.serverStatusAddressElements[2]
                elif self.serverResponsePlayersEntryElements[0] == "connected":
                    autolog(DETAIL, str('DISCONNECT DEBUG [CONNECTED]: %s' % (self.serverResponsePlayersEntryElements[2])))
                    if self.serverResponsePlayersEntryElements[2] == '1':
                        playerInfo['connected'] = True  # Player is connected
                    else:
                        playerInfo['connected'] = False  # Player is disconnected

            self.playerKnown = False
            for playerDev in indigo.devices.iter(filter="self"):
                if playerDev.address == playerInfo['playerid']:
                    self.playerKnown = True
                    break

            if self.playerKnown == False:
                autolog(INFO, "New player discovered with Address: [%s] ... creating device ..." % (playerInfo['playerid']))

                playerDev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                    address=playerInfo['playerid'],
                    name=playerInfo['name'], 
                    description=playerInfo['model'], 
                    pluginId="com.indigodomo.indigoplugin.autologsqueezeboxcontroller",
                    deviceTypeId="squeezeboxPlayer",
                    props={"mac":playerInfo['playerid']},
                    folder=self.deviceFolderId)
                pluginGlobal['players'][playerDev.id] = {}
                self.deviceStateUpdate(False, playerDev, 'name', playerInfo['name'])
                self.deviceStateUpdate(False, playerDev, 'model', playerInfo['model'])
                self.deviceStateUpdate(False, playerDev, 'mac', playerInfo['playerid'])
                self.deviceStateUpdate(True, playerDev, 'serverId', dev.id)
                self.deviceStateUpdate(True, playerDev, 'serverName', dev.name)
                 # autolog(DETAIL, "Calling deviceStartComm for device: %s" % (playerInfo['playerid']))
                self.deviceStartComm(playerDev)
                # autolog(DETAIL, "Called deviceStartComm for device: %s" % (playerInfo['playerid']))
                autolog(INFO, "Newly discovered player with Address [%s] has now been created." % (playerInfo['playerid']))

            else:
                self.deviceStateUpdate(True, playerDev, 'connected', playerInfo['connected'])
                if playerInfo['connected'] == False:
                    self.deviceStateUpdate(True, playerDev, 'powerUi', 'disconnected')
                else:
                    self.deviceStateUpdate(True, playerDev, 'powerUi', 'off')

                if pluginGlobal['players'][playerDev.id]['connected'] == False:
                    autolog(INFO, "Existing Player '%s' with address [%s] confirmed as disconnected from server '%s'" % (playerDev.name, playerDev.address, dev.name))                    
                else:
                    autolog(INFO, "Existing Player '%s' with address [%s] confirmed as connected to server '%s'" % (playerDev.name, playerDev.address, dev.name))

                self.deviceStateUpdate(True, playerDev, 'name', playerInfo['name'])
                self.deviceStateUpdate(True, playerDev, 'model', playerInfo['model'])
                self.deviceStateUpdate(True, playerDev, 'serverId', dev.id)
                self.deviceStateUpdate(True, playerDev, 'serverName', dev.name)

                playerDevMac = playerDev.pluginProps['mac']
                if playerDevMac == '':
                    playerDevProps = playerDev.pluginProps
                    playerDevProps['mac'] = playerInfo['playerid']
                    playerDev.replacePluginPropsOnServer(playerDevProps)
                    self.deviceStateUpdate(True, playerDev, 'mac', playerInfo['playerid'])

                # Update state of player connection / power    

            self.deviceStateUpdate(True, playerDev, 'ipAddress', playerInfo['ipAddress'])
            self.deviceStateUpdate(True, playerDev, 'portAddress', playerInfo['portAddress'])


            self.deviceStateUpdate(True, playerDev, 'powerUi', playerInfo['powerUi'])

            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put("syncgroups ?")

            self.deviceStateUpdateWithIcon(True, playerDev, 'state', playerInfo['powerUi'], indigo.kStateImageSel.PowerOff)


            try:
                shutil.copy2(pluginGlobal['coverArt']['noCoverArtFile'],pluginGlobal['players'][playerDev.id]['coverArtFile'])
            except StandardError, e:
                indigo.server.log(u'Cover Art Error -  IN: %s' % (pluginGlobal['coverArt']['noCoverArtFile']), isError=True)
                indigo.server.log(u'Cover Art Error -  OUT: %s' % (pluginGlobal['players'][playerDev.id]['coverArtFile']), isError=True)
                indigo.server.log(u'Cover Art Error -  ERR: %s' % (e), isError=True)
 


            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " power ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " mode ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " artist ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " album ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " title ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " genre ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " duration ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " remote ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " playerpref volume ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " playerpref maintainSync ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " playlist index ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " playlist tracks ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " playlist repeat ?")
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerDev.id]['serverId']].put(playerDev.address + " playlist shuffle ?")

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _handle_player_id(self, dev):  # dev = squeezebox server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:
            playerNumber = int(self.serverResponse[2])
            playerId = urllib2.unquote(self.serverResponse[3])

            playerKnown = False
            for playerDev in indigo.devices.iter(filter="self"):
                if playerDev.address == playerId:
                    playerKnown = True
                    autolog(DETAIL, "Processing known player [%s]: '%s'" % (str(playerNumber), playerId))
                    break
            if playerKnown == False:
                playerName = 'New Squeezebox Player'
                playerDescription = 'New Squeezebox Player'
                playerModel = 'unknown'
                playerDev = indigo.device.create(protocol=indigo.kProtocol.Plugin,
                    address=self.playerId,
                    name=playerName, 
                    description=playerDescription, 
                    pluginId="com.indigodomo.indigoplugin.autologsqueezeboxcontroller",
                    deviceTypeId="squeezeboxPlayer",
                    props={"mac":playerId},
                    folder=self.deviceFolderId)
                playerDev.updateStateOnServer(key="name", value=playerName)
                playerDev.updateStateOnServer(key="model", value=playerModel)
                playerDev.updateStateOnServer(key="serverId",  value=dev.id)
                playerDev.updateStateOnServer(key="serverName",  value=dev.name)

            self.playerIdQuoted = urllib2.quote(self.playerId)  # ££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££££
            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][dev.Id]['serverId']].put(self.playerId + " status 0 999 tags:")

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _handle_readdirectory(self, dev):  # dev = squeezebox server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:
            autolog(ANNOUNCE, "READDIRECTORY = [%s] [%s]" % (self.serverResponse[3], self.serverResponse[6]))

            self.readDirectory = []
            parts = re.split("(\w+:)", self.responseFromSqueezeboxServer)
            if parts[0]:
                self.readDirectory.append(parts[0].strip())
            groups = zip(*[parts[i+1::2] for i in range(2)])
            self.readDirectory.extend(["".join(group).strip() for group in groups])

            self.readDirectoryFunction = ''
            self.readDirectoryDevice = 0
            self.readDirectoryFolder = ''
            self.readDirectoryFilter = ''
            self.readDirectoryPath = ''
            self.readDirectoryCount = 0
            self.readDirectoryIsFolder = 0

            for self.readDirectoryEntry in self.readDirectory:
                self.readDirectoryEntryElements = self.readDirectoryEntry.partition(":")
                autolog(ANNOUNCE, "SELF.RD-ELEMENTS: [%s] [%s] [%s]" % (self.readDirectoryEntryElements[0],self.readDirectoryEntryElements[1],self.readDirectoryEntryElements[2]))

                self.readDirectoryKeyword = self.readDirectoryEntryElements[0]
                self.readDirectoryValue = self.readDirectoryEntryElements[2].rstrip()

                if self.readDirectoryKeyword == "autologFunction":
                    self.readDirectoryFunction = self.readDirectoryValue
                elif self.readDirectoryKeyword == "autologDevice":
                    self.readDirectoryDevice = self.readDirectoryValue
                elif self.readDirectoryKeyword == "folder":
                    self.readDirectoryFolder = self.readDirectoryValue
                elif self.readDirectoryKeyword == "filter":
                    self.readDirectoryFilter = self.readDirectoryValue
                elif self.readDirectoryKeyword == "path":
                    self.readDirectoryPath = self.readDirectoryValue
                elif self.readDirectoryKeyword == "count":
                    self.readDirectoryCount = self.readDirectoryValue
                elif self.readDirectoryKeyword == "isfolder":
                    self.readDirectoryIsFolder = self.readDirectoryValue

            autolog(ANNOUNCE, "SELF.READDIRECTORY: Func=[%s], Dev=[%s], Fol=[%s], Fil=[%s], Path=[%s], C=[%s], IsF=[%s]" % (self.readDirectoryFunction, 'Unknown', self.readDirectoryFolder, self.readDirectoryFilter, self.readDirectoryPath, self.readDirectoryCount, self.readDirectoryIsFolder))

            self.fileCount = self.serverResponse[6].partition(":")
            self.fileCheckModeDev = self.serverResponse[3].partition(":")
            autolog(ANNOUNCE, "SELF.FILECOUNT = [%s]" % (self.readDirectoryCount))

            if self.readDirectoryFunction == 'AnnouncementCheck':
                if self.readDirectoryCount == '1':
                    pass
                else:
                    pluginGlobal['announcement']['fileCheckOK'] = False
                    autolog(ERROR, "Announcement File [%s/%s] not found. Play Announcement on '%s' not actioned." % (self.readDirectoryFolder, self.readDirectoryFilter, indigo.devices[int(self.readDirectoryDevice)].name))
            elif self.readDirectoryFunction == 'PlaylistCheck':
                if self.readDirectoryCount == '1':
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][int(self.readDirectoryDevice)]['serverId']].put(pluginGlobal['players'][int(self.readDirectoryDevice)]['mac'] + " playlist play " + str(self.readDirectoryPath).replace(' ','%20'))
                else:
                    autolog(ERROR, "Playlist File [%s/%s] not found. Play Playlist on '%s' not actioned." % (self.readDirectoryFolder, self.readDirectoryFilter, indigo.devices[int(self.readDirectoryDevice)].name))

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _handle_player(self, devServer):  # dev = squeezebox server
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:
            self.playerKnown = False
            for devPlayer in indigo.devices.iter(filter="self"):
                if devPlayer.address == self.serverResponseKeyword:
                    self.playerKnown = True
                    break

            if self.playerKnown == False:
                autolog(INFO, u"Now handling unknown player: [%s]" %  (self.serverResponseKeyword))
                pluginGlobal['queues']['commandToSend'][devServer.id].put("serverstatus 0 0 subscribe:0")

                return

            self.replyPlayerMAC = self.serverResponseKeyword
            self.replyPlayerId = devPlayer.id

            # Determine master (sync) player MAC and ID
            if pluginGlobal['players'][self.replyPlayerId]['masterPlayerAddress'] != "":
                self.masterPlayerMAC = pluginGlobal['players'][self.replyPlayerId]['masterPlayerAddress']
                self.masterPlayerId = pluginGlobal['players'][self.replyPlayerId]['masterPlayerId']
            else:
                self.masterPlayerMAC = self.replyPlayerMAC
                self.masterPlayerId = self.replyPlayerId

            self._handle_player_detail(devServer,devPlayer)


        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _handle_player_detail(self, devServer, devPlayer):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:
            # Check if a sync change has been detected in which case request a syncgroups update
            if self.serverResponse[1] == 'sync':  # SYNC  
                pluginGlobal['queues']['commandToSend'][devServer.id].put("syncgroups ?")

            if self.serverResponse[1] == "songinfo":  # songinfo
                # artworkUrl = '00:04:20:29:46:b9 songinfo 0 100 url:pandora://495903246413988319.mp3 tags:aK id:-140590555861760 title:Timber artist:Pitbull artwork_url:http://cont-sv5-2.pandora.com/images/public/amz/0/8/5/7/800037580_500W_497H.jpg'

                artworkUrl = self.responseFromSqueezeboxServer.split('artwork_url:')
                if len(artworkUrl) == 2:
                    artworkUrl = artworkUrl[1]  # i.e. artwork_url was found
                else:
                    artworkUrl = str('music/current/cover.jpg?player=%s' % (pluginGlobal['players'][self.replyPlayerId]['mac']))
                # artworkUrl = artworkUrl.split('artwork_url:')[1]
                # autolog(DETAIL, u"SONGINFO: 'artworkUrl' = %s" % (artworkUrl))
                if artworkUrl[0:7] != 'http://' and artworkUrl[0:8] != 'https://':
                    artworkUrl = str('http://%s:9000/%s' % (pluginGlobal['servers'][devServer.id]['ipAddress'], artworkUrl)) 

                #autolog(DETAIL, u"ARTWORKURL: 'artworkUrl' = %s" % (artworkUrl))

                coverArtToRetrieve = urllib2.urlopen(artworkUrl)
                coverArtFile = str('%s/coverart.jpg' % (pluginGlobal['players'][self.replyPlayerId]['coverArtFolder']))
                #autolog(DETAIL, u"COVERARTFILE: %s" % (coverArtFile))

                localFile = open(coverArtFile, 'wb')
                localFile.write(coverArtToRetrieve.read())
                localFile.close()

            # elif self.serverResponse[1] == "favorites":  # favorites
            #     indigo.server.log(u'FAVORITES = %s' % (self.serverResponse))
            #     if self.serverResponse[2] == "playlist":  # favorites playlist
            #         indigo.server.log(u'FAVORITES PLAYLIST')
            #         if self.serverResponse[3] == "play":  # favorites playlist play
            #             indigo.server.log(u'FAVORITES PLAYLIST PLAY = %s' % (self.serverResponse[4]))









            elif self.serverResponse[1] == "playlist":  # playlist
                if self.serverResponse[2] == "open":  # playlist open
                    songUrl = self.serverResponse[3]

                    if songUrl[0:7] == 'file://' or songUrl[0:14] == 'spotify:track:' or songUrl[0:10] == 'pandora://' or songUrl[0:8] == 'qobuz://' or songUrl[0:9] == 'deezer://' or songUrl[0:9] == 'sirius://':
                        playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist open')
                        for playerIdToProcess in playerIdsToProcess:
                            if pluginGlobal['players'][playerIdToProcess]['powerUi'] != 'disconnected':
                                self.deviceStateUpdate(True,  devPlayer, 'songUrl', songUrl)
                                autolog(ANNOUNCE,u'%s is playing songUrl %s' % (devPlayer.name, songUrl))

                if self.serverResponse[2] == "newsong":  # playlist newsong
                    if pluginGlobal['announcement']['step'] != "loaded":
                        # autolog(ANNOUNCE, u"NEWSONG: 'announcementStep' = %s" % (pluginGlobal['announcement']['step']))
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " artist ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " album ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " title ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " genre ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " duration ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " remote ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " mode ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " playlist name ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " playlist index ?")
                        pluginGlobal['queues']['commandToSend'][devServer.id].put(self.masterPlayerMAC + " playlist tracks ?")

                elif self.serverResponse[2] == "pause":  # playlist pause
                    playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist pause')

                    for playerIdToProcess in playerIdsToProcess:
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerIdToProcess]['serverId']].put(indigo.devices[playerIdToProcess].address + " mode ?")

                elif self.serverResponse[2] == "name":  # playlist name
                    try:
                        self.playlistName = self.serverResponse[3]
                        self.playlistName = self.responseFromSqueezeboxServer.split('playlist name')[1]
                    except:
                        self.playlistName = ''

                    playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist name')

                    for playerIdToProcess in playerIdsToProcess:
                        if pluginGlobal['players'][playerIdToProcess]['powerUi'] != 'disconnected':
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistName", value=self.playlistName)

                elif self.serverResponse[2] == "index":  # playlist index
                    try:
                        self.playlistIndex = self.serverResponse[3]
                        self.playlistTrackNumber = str(int(self.playlistIndex) + 1)
                    except:
                        self.playlistIndex = '0'
                        self.playlistTrackNumber = '1'

                    playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist index')

                    for playerIdToProcess in playerIdsToProcess:
                        if pluginGlobal['players'][playerIdToProcess]['powerUi'] != 'disconnected':
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistIndex", value=self.playlistIndex)
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTrackNumber", value=self.playlistTrackNumber)

                elif self.serverResponse[2] == "tracks":  # playlist tracks
                    self.playlistTracksTotal = self.serverResponse[3]

                    playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist tracks')

                    for playerIdToProcess in playerIdsToProcess:
                        if pluginGlobal['players'][playerIdToProcess]['powerUi'] != 'disconnected':
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTracksTotal", value=self.playlistTracksTotal)
                            if self.playlistTracksTotal =='0':
                                indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTrackNumber", value='0')
                                tracksUi = ''
                            else:
                                tracksUi = str('%s of %s' % (indigo.devices[playerIdToProcess].states['playlistTrackNumber'], self.playlistTracksTotal))
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="playlistTracksUi", value=tracksUi)

                elif self.serverResponse[2] == "repeat":  # playlist repeat
                    if len(self.serverResponse) > 3:
                        self.repeat = '?'
                        if self.serverResponse[3] == '0':
                            self.repeat = 'off'
                        elif self.serverResponse[3] == '1':
                            self.repeat = 'song' 
                        elif self.serverResponse[3] == '2':
                            self.repeat = 'playlist'
                        playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist repeat')
                        for playerIdToProcess in playerIdsToProcess:
                            pluginGlobal['players'][playerIdToProcess]['repeat'] = self.serverResponse[3]
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="repeat", value=self.repeat)

                    if pluginGlobal['announcement']['step'] == "initialise":
                        autolog(ANNOUNCE, "ACT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))
                        if len(self.serverResponse) > 3:
                            pluginGlobal['players'][self.masterPlayerId]['savedRepeat'] = self.serverResponse[3]
                        else:
                            pluginGlobal['players'][self.masterPlayerId]['savedRepeat'] = '?'

                elif self.serverResponse[2] == "shuffle":  # playlist shuffle
                    if len(self.serverResponse) > 3:
                        self.shuffle = '?'
                        if self.serverResponse[3] == '0':
                            self.shuffle = 'off'
                        elif self.serverResponse[3] == '1':
                            self.shuffle = 'songs' 
                        elif self.serverResponse[3] == '2':
                            self.shuffle = 'albums'
                        playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist shuffle')
                        for playerIdToProcess in playerIdsToProcess:
                            pluginGlobal['players'][playerIdToProcess]['shuffle'] = self.serverResponse[3]
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="shuffle", value=self.shuffle)

                    if pluginGlobal['announcement']['step'] == "initialise":
                        autolog(ANNOUNCE, "ACT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))
                        if len(self.serverResponse) > 3:
                            pluginGlobal['players'][self.masterPlayerId]['savedShuffle'] = self.serverResponse[3]
                        else:
                            pluginGlobal['players'][self.masterPlayerId]['savedShuffle'] = '?'

                elif self.serverResponse[2] == "load_done":  # playlist load_done
                    if pluginGlobal['announcement']['step'] == "play":
                        autolog(ANNOUNCE, "ACT=[play]: %s" % (indigo.devices[self.masterPlayerId].name))
                        pluginGlobal['announcement']['step'] = "loaded"
                        autolog(ANNOUNCE, "NXT=[loaded]: %s" % (indigo.devices[self.masterPlayerId].name))

                elif self.serverResponse[2] == "stop":  # playlist stop
                    # pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " mode ?")

                    if pluginGlobal['players'][self.replyPlayerId]['powerUi'] != 'disconnected':
                        playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist stop')

                        for playerIdToProcess in playerIdsToProcess:
                            pluginGlobal['players'][playerIdToProcess]['mode'] = 'stop'
                            stateDescription = 'stopped'
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="state", value=stateDescription)
                            if float(indigo.server.apiVersion) >= 1.18:
                                stateImage = indigo.kStateImageSel.AvStopped
                                indigo.devices[self.replyPlayerId].updateStateImageOnServer(stateImage)

                        if pluginGlobal['announcement']['step'] == "loaded":
                            autolog(ANNOUNCE, "ACT=[loaded]: %s" % (indigo.devices[self.masterPlayerId].name))
                            pluginGlobal['announcement']['step'] = "stopped"
                            autolog(ANNOUNCE, "NXT=[stopped]: %s" % (indigo.devices[self.masterPlayerId].name))

                            # reload saved playlist
                            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.replyPlayerMAC + " playlist resume autolog_" + str(self.masterPlayerId) + " wipePlaylist:1 noplay:1")

                            #  + pluginGlobal['players'][self.masterPlayerId]['announcementPlaylistNoplay']

                            # for master sync player
                            #     if saved repeat != 0:
                            #         restore repeat
                            #     if saved shuffle != 0:
                            #         restore shuffle
                            #     if time != 0 and shuffle = 0:
                            #         restore time (seconds only)

                            if pluginGlobal['players'][self.masterPlayerId]['savedRepeat'] != "0":
                                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist repeat " + pluginGlobal['players'][self.masterPlayerId]['savedRepeat'])
                            if pluginGlobal['players'][self.masterPlayerId]['savedShuffle'] != "0":
                                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist shuffle " + pluginGlobal['players'][self.masterPlayerId]['savedShuffle'])
                            # if pluginGlobal['players'][self.masterPlayerId]['savedTime'] !=  "0":
                            #     pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " time " + pluginGlobal['players'][self.masterPlayerId]['savedTime'])
                            if pluginGlobal['players'][self.masterPlayerId]['savedVolume'] != pluginGlobal['players'][self.masterPlayerId]['volume']:
                                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " mixer volume " + pluginGlobal['players'][self.masterPlayerId]['savedVolume'])
                            if pluginGlobal['players'][self.masterPlayerId]['savedMaintainSync'] != pluginGlobal['players'][self.masterPlayerId]['maintainSync']:
                                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playerpref maintainSync " + pluginGlobal['players'][self.masterPlayerId]['savedMaintainSync'])

                            # for each player (sync'd - master & slave) '
                            #     if saved power is off:
                            #         turn off power

                            for slavePlayerId in pluginGlobal['players'][self.masterPlayerId]['slavePlayerIds']:
                                if pluginGlobal['players'][slavePlayerId]['savedVolume'] != pluginGlobal['players'][slavePlayerId]['volume']:
                                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " mixer volume " + pluginGlobal['players'][slavePlayerId]['savedVolume'])
                                if pluginGlobal['players'][slavePlayerId]['savedMaintainSync'] != pluginGlobal['players'][slavePlayerId]['maintainSync']:
                                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " playerpref maintainSync " + pluginGlobal['players'][slavePlayerId]['savedMaintainSync'])
                                    
                                if pluginGlobal['players'][slavePlayerId]['savedPower'] == "0":
                                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " power 0")
                            if pluginGlobal['players'][self.masterPlayerId]['savedPower'] == "0":
                                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " power 0")

                            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " autologAnnouncementRestartPlaying")

            elif self.serverResponse[1] == "pause":  # pause
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'pause')

                for playerIdToProcess in playerIdsToProcess:
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerIdToProcess]['serverId']].put(indigo.devices[playerIdToProcess].address + " mode ?")

            elif self.serverResponse[1] == "play":  # play

                autolog(ANNOUNCE, "NXT=[play]: %s" % (indigo.devices[self.masterPlayerId].name))

                if pluginGlobal['announcement']['step'] == "autologAnnouncementRestartPlaying":
                    autolog(ANNOUNCE, "ACT=[autologAnnouncementRestartPlaying]: %s" % (indigo.devices[self.masterPlayerId].name))
                    playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'autologAnnouncementRestartPlaying')
                    autolog(DETAIL, u'PLAYERIDSTOPROCESS: Len=%s; %s' % (len(playerIdsToProcess), str(playerIdsToProcess)))
                    if pluginGlobal['players'][self.masterPlayerId]['savedTime'] !=  "0":
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " pause")
                        for playerIdToProcess in playerIdsToProcess:
                            mac = self._playerDeviceIdToMAC(playerIdToProcess)
                            pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerIdToProcess]['serverId']].put(mac + " time " + pluginGlobal['players'][self.masterPlayerId]['savedTime'])
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " pause")




            elif self.serverResponse[1] == "prefset":  # prefset
                if self.serverResponse[2] == "server":  # prefset server
                    if self.serverResponse[3] == "volume":  # prefset server volume
                        pluginGlobal['players'][self.replyPlayerId]['volume'] = self.serverResponse[4]
                        indigo.devices[self.replyPlayerId].updateStateOnServer(key="volume", value=pluginGlobal['players'][self.replyPlayerId]['volume'])
                    elif self.serverResponse[3] == "power":  # prefset server power
                        pass
                    elif self.serverResponse[3] == "repeat":  # prefset server repeat
                        self.repeat = '?'
                        if len(self.serverResponse) > 4:
                            if self.serverResponse[4] == '0':
                                self.repeat = 'off'
                            elif self.serverResponse[4] == '1':
                                self.repeat = 'song' 
                            elif self.serverResponse[4] == '2':
                                self.repeat = 'playlist'
                        playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist repeat')
                        for playerIdToProcess in playerIdsToProcess:
                            pluginGlobal['players'][playerIdToProcess]['repeat'] = self.repeat
                            indigo.devices[playerIdToProcess].updateStateOnServer(key="repeat", value=self.repeat)

                        # if pluginGlobal['announcement']['step'] == "autologAnnouncementInitialise":
                        #     if len(self.serverResponse) > 3:
                        #         pluginGlobal['players'][self.masterPlayerId]['savedRepeat'] = self.serverResponse[3]
                        #     else:
                        #         pluginGlobal['players'][self.masterPlayerId]['savedRepeat'] = '?'

                    elif self.serverResponse[3] == "shuffle":  # prefset server shuffle
                        shuffle = '?'
                        if len(self.serverResponse) > 3:
                            if self.serverResponse[4] == '0':
                                shuffle = 'off'
                            elif self.serverResponse[4] == '1':
                                shuffle = 'songs' 
                            elif self.serverResponse[4] == '2':
                                shuffle = 'albums'
                        playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'playlist shuffle')
                        for playerIdToProcess in playerIdsToProcess:
                            self.deviceStateUpdate(True,  devPlayer, 'shuffle', shuffle)

 
            elif self.serverResponse[1] == "mixer":  # mixer
                if self.serverResponse[2] == "volume":  # mixer volume
                    volume = self.serverResponse[3]
                    # self.deviceStateUpdate(True,  devPlayer, 'volume', volume)

            elif self.serverResponse[1] == "playerpref":  # playerpref

                if self.serverResponse[2] == "volume":  # playerpref volume
                    volume = self.serverResponse[3]
                    self.deviceStateUpdate(True,  devPlayer, 'volume', volume)

                    if pluginGlobal['announcement']['step'] == "initialise":
                        autolog(ANNOUNCE, "ACT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))
                        if len(self.serverResponse) > 3:
                            savedVolume = volume
                        else:
                            savedVolume = '?'
                        self.deviceStateUpdate(False,  devPlayer, 'savedVolume', savedVolume)

                if self.serverResponse[2] == "maintainSync":  # playerpref maintainSync
                    maintainSync = self.serverResponse[3]
                    self.deviceStateUpdate(True,  devPlayer, 'maintainSync', maintainSync)

                    if pluginGlobal['announcement']['step'] == "initialise":
                        autolog(ANNOUNCE, "ACT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))
                        if len(self.serverResponse) > 3:
                            savedMaintainSync = maintainSync
                        else:
                            savedMaintainSync = '?'
                        self.deviceStateUpdate(False,  devPlayer, 'savedMaintainSync', savedMaintainSync)

            elif self.serverResponse[1] == "artist":  # artist
                artistResponse = self.responseFromSqueezeboxServer.split(' ', 2)
                try:  
                    artist = artistResponse[2].rstrip()
                except:
                    artist = ''

                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'artist')
                for playerIdToProcess in playerIdsToProcess:
                    if pluginGlobal['players'][playerIdToProcess]['connected'] == True:
                        self.deviceStateUpdate(True,  devPlayer, 'artist', artist)

            elif self.serverResponse[1] == "album":  # album
                try:  
                    albumResponse = self.responseFromSqueezeboxServer.split(' ', 2)
                    album = albumResponse[2].rstrip()
                except:
                    album = ''

                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'album')
                for playerIdToProcess in playerIdsToProcess:
                    if pluginGlobal['players'][playerIdToProcess]['connected'] == True:
                        self.deviceStateUpdate(True,  devPlayer, 'album', album)

            elif self.serverResponse[1] == "title":  # title
                try:  
                    titleResponse = self.responseFromSqueezeboxServer.split(' ', 2)
                    title = titleResponse[2].rstrip() 
                except:
                    title = ''

                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'title')
                for playerIdToProcess in playerIdsToProcess:
                    if pluginGlobal['players'][playerIdToProcess]['connected'] == True:
                        self.deviceStateUpdate(True,  devPlayer, 'title', title)

            elif self.serverResponse[1] == "genre":  # genre
                try: 
                    genreResponse = self.responseFromSqueezeboxServer.split(' ', 2)
                    genre = genreResponse[2].rstrip()
                except:
                    genre = ''

                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'genre')
                for playerIdToProcess in playerIdsToProcess:
                    if pluginGlobal['players'][playerIdToProcess]['connected'] == True:
                        self.deviceStateUpdate(True,  devPlayer, 'genre', genre)

            elif self.serverResponse[1] == "duration":  # duration
                durationUi = ''
                try:  
                    durationResponse = self.responseFromSqueezeboxServer.split(' ', 2)
                    duration = durationResponse[2].rstrip()
                    try:
                        m, s = divmod(float(duration), 60)
                        durationUi = str("%02d:%02d" % (m,s))
                    except:
                        pass
                except:
                    duration = ''

                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'duration')
                for playerIdToProcess in playerIdsToProcess:
                    if pluginGlobal['players'][playerIdToProcess]['connected'] == True:
                        self.deviceStateUpdate(True,  devPlayer, 'duration', duration)
                        self.deviceStateUpdate(True,  devPlayer, 'durationUi', durationUi)


            elif self.serverResponse[1] == "autologMixerMuteAll":  # autologMixerMuteAll
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'autologMixerMuteAll')
                for playerIdToProcess in playerIdsToProcess:
                    mac = self._playerDeviceIdToMAC(playerIdToProcess)
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerIdToProcess]['serverId']].put(mac + " mixer muting 1")

            elif self.serverResponse[1] == "autologMixerUnmuteAll":  # autologMixerUnmuteAll
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'autologMixerUnmuteAll')
                for playerIdToProcess in playerIdsToProcess:
                    mac = self._playerDeviceIdToMAC(playerIdToProcess)
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerIdToProcess]['serverId']].put(mac + " mixer muting 0")

            elif self.serverResponse[1] == "autologMixerToggleMuteAll":  # autologMixerToggleMuteAll
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'autologMixerToggleMuteAll')
                for playerIdToProcess in playerIdsToProcess:
                    mac = self._playerDeviceIdToMAC(playerIdToProcess)
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerIdToProcess]['serverId']].put(mac + " mixer muting toggle")

            elif self.serverResponse[1] == "remote":  # remote
                try:  
                    remoteResponse = self.responseFromSqueezeboxServer.split(' ', 2)
                    remoteStream = remoteResponse[2].rstrip()
                except:
                    remoteStream = '0'

                if remoteStream == '1':
                    remoteStream = 'true'
                    songUrl = pluginGlobal['players'][self.replyPlayerId]['songUrl']
                    if songUrl != '':
                        mac = indigo.devices[self.replyPlayerId].address
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.replyPlayerId]['serverId']].put(mac + str(" songinfo 0 100 url:%s tags:K" % (songUrl)))
                else:
                    remoteStream = 'false'
                    songUrl = pluginGlobal['players'][self.replyPlayerId]['songUrl']
                    if songUrl != '':
                        mac = indigo.devices[self.replyPlayerId].address
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.replyPlayerId]['serverId']].put(mac + str(" songinfo 0 100 url:%s tags:K" % (songUrl)))

                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'remote')
                for playerIdToProcess in playerIdsToProcess:
                    self.deviceStateUpdate(True,  devPlayer, 'remoteStream', remoteStream)




            # check if a player connecting / disconnecting / reconnecting
            elif self.serverResponse[1] == "client":  # client
                if self.serverResponse[2] == "new":  # client new
                    self.connectingDevId = self._playerMACToDeviceId(self.serverResponse[0])
                    if self.connectingDevId == 0:
                        autolog(INFO, "New Player [%s] detected." % (self.serverResponse[0]))
                    else:
                        autolog(INFO, "%s player [%s] connecting" % (indigo.devices[self.connectingDevId].name, self.serverResponse[0]))
                    pluginGlobal['queues']['commandToSend'][devServer.id].put("serverstatus 0 0 subscribe:-")

                elif self.serverResponse[2] == "disconnect":  # client disconnect
                    self.disconnectingDevId = self._playerMACToDeviceId(self.serverResponse[0])
                    if self.disconnectingDevId == 0:
                        autolog(INFO, "Unknown player [%s] disconnecting" % (self.serverResponse[0]))
                    else:
                        autolog(INFO, "%s player [%s] disconnecting" % (indigo.devices[self.disconnectingDevId].name, self.serverResponse[0]))

                        pluginGlobal['players'][self.disconnectingDevId]['powerUi'] = 'disconnected'

                        # Reset any active announcements for known player

                        if pluginGlobal['players'][self.disconnectingDevId]['masterPlayerId'] != 0:
                            self.masterPlayerId = pluginGlobal['players'][self.disconnectingDevId]['masterPlayerId']
                        else:
                            self.masterPlayerId = self.disconnectingDevId

                        pluginGlobal['announcement']['active'] = 'NO'
                        pluginGlobal['players'][self.masterPlayerId]['announcementPlayInitialised'] = False
                        autolog(INFO, "Reset Announcement actioned for %s player [%s] as disconnected" % (indigo.devices[self.disconnectingDevId].name, self.serverResponse[0]))
                        pluginGlobal['queues']['announcementQueue'].queue.clear

                    pluginGlobal['queues']['commandToSend'][devServer.id].put("serverstatus 0 0 subscribe:-")

                elif self.serverResponse[2] == "forget":  # client forget
                    self.forgottenDevId = self._playerMACToDeviceId(self.serverResponse[0])
                    if self.forgottenDevId == 0:
                        autolog(INFO, "Unknown player [%s] forgotten" % (self.serverResponse[0]))
                    else:
                        autolog(INFO, "%s player [%s] forgotten" % (indigo.devices[self.forgottenDevId].name, self.serverResponse[0]))
                    pluginGlobal['queues']['commandToSend'][devServer.id].put("serverstatus 0 0 subscribe:-")

                elif self.serverResponse[2] == "reconnect":  # client reconnect
                    self.reconnectingDevId = self._playerMACToDeviceId(self.serverResponse[0])
                    if self.reconnectingDevId == 0:
                        autolog(INFO, "Unknown player [%s] reconnecting" % (self.serverResponse[0]))
                    else:
                        autolog(INFO, "%s player [%s] reconnecting" % (indigo.devices[self.reconnectingDevId].name, self.serverResponse[0]))
                    pluginGlobal['queues']['commandToSend'][devServer.id].put("serverstatus 0 0 subscribe:-")


            # check if request for an autolog announcement
            elif self.serverResponse[1] == "autologAnnouncementRequest":  # autologAnnouncementRequest
                if pluginGlobal['announcement']['active'] == 'PENDING':
                    pluginGlobal['announcement']['active'] = 'YES'

                    pluginGlobal['announcement']['step'] = "request"
                    autolog(ANNOUNCE, "NXT=[request]: %s" % (indigo.devices[self.masterPlayerId].name))

                    pluginGlobal['players'][self.masterPlayerId]['announcementUniqueKey'] = self.serverResponse[2]
                    announcementUniqueKey = pluginGlobal['players'][self.masterPlayerId]['announcementUniqueKey']
 
                    pluginGlobal['announcement']['fileCheckOK'] = True  # Assume file checks will be OK (Read Directory will set to False if not)
                    if 'prepend' in pluginGlobal['announcement'][announcementUniqueKey]:
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put("readdirectory 0 1 autologFunction:AnnouncementCheck autologDevice:%s folder:%s filter:%s" % (str(self.masterPlayerId), os.path.dirname(pluginGlobal['announcement'][announcementUniqueKey]['prepend']), os.path.basename(pluginGlobal['announcement'][announcementUniqueKey]['prepend'])))

                    if 'file' in pluginGlobal['announcement'][announcementUniqueKey]:
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put("readdirectory 0 1 autologFunction:AnnouncementCheck autologDevice:%s folder:%s filter:%s" % (str(self.masterPlayerId), os.path.dirname(pluginGlobal['announcement'][announcementUniqueKey]['file']), os.path.basename(pluginGlobal['announcement'][announcementUniqueKey]['file'])))

                    if 'append' in pluginGlobal['announcement'][announcementUniqueKey]:
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put("readdirectory 0 1 autologFunction:AnnouncementCheck autologDevice:%s folder:%s filter:%s" % (str(self.masterPlayerId), os.path.dirname(pluginGlobal['announcement'][announcementUniqueKey]['append']), os.path.basename(pluginGlobal['announcement'][announcementUniqueKey]['append'])))

                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " autologAnnouncementInitialise")

            elif self.serverResponse[1] == "autologAnnouncementInitialise":  # autologAnnouncementInitialise
                if pluginGlobal['announcement']['fileCheckOK'] == False:
                    pluginGlobal['announcement']['active'] = 'NO'
                    autolog(ANNOUNCE, u"Play Announcement Abandoned as file check failed")

                else:
                    pluginGlobal['announcement']['step'] = "initialise"
                    autolog(ANNOUNCE, "NXT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))

                    for slavePlayerId in pluginGlobal['players'][self.masterPlayerId]['slavePlayerIds']:
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " power ?")
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " mode ?")
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " playerpref volume ?")
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " playerpref maintainSync ?")

                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " power ?")
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " mode ?")
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playerpref volume ?")
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playerpref maintainSync ?")
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist repeat ?")
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist shuffle ?")
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " time ?")
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " stop")

                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " autologAnnouncementSaveState")

            elif self.serverResponse[1] == "power":  # power
                if len(self.serverResponse) < 3:  # Check for Power Toggle - Need to query power to find power status
                    pluginGlobal['queues']['commandToSend'][devServer.id].put(self.replyPlayerMAC + " power ?")
                else:
                    previousPower = pluginGlobal['players'][devPlayer.id]['power']  # Power setting before handling response

                    power = self.serverResponse[2].rstrip()
                    powerUi = '?'
                    if power == '0':
                        powerUi = 'off'
                    elif power == '1':
                        powerUi = 'on'
                    if pluginGlobal['players'][devPlayer.id]['connected'] == False:
                        powerUi = 'disconnected'

                    self.deviceStateUpdate(True,  devPlayer, 'power', power)
                    self.deviceStateUpdate(True,  devPlayer, 'powerUi', powerUi)

                    if pluginGlobal['announcement']['step'] == "initialise":
                        autolog(ANNOUNCE, "ACT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))
                        pluginGlobal['players'][devPlayer.id]['savedPower'] = power

                    if power != previousPower:

                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][devPlayer.id]['serverId']].put("syncgroups ?")

                        if pluginGlobal['players'][devPlayer.id]['powerUi'] == 'on' and pluginGlobal['announcement']['step'] != "initialise":
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " autolog detected power on")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " mode ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " artist ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " album ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " title ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " genre ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " duration ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " remote ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " playerpref volume ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " playerpref maintainSync ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " playlist index ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " playlist tracks ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " playlist repeat ?")
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " playlist shuffle ?")
                        else:
                            pluginGlobal['queues']['commandToSend'][devServer.id].put(devPlayer.address + " mode ?")

                    if power == '0' or pluginGlobal['players'][devPlayer.id]['connected'] == False:
                        try:
                            shutil.copy2(pluginGlobal['coverArt']['noCoverArtFile'],pluginGlobal['players'][devPlayer.id]['coverArtFile'])
                        except StandardError, e:
                            indigo.server.log(u'Cover Art Error -  IN: %s' % (pluginGlobal['coverArt']['noCoverArtFile']), isError=True)
                            indigo.server.log(u'Cover Art Error -  OUT: %s' % (pluginGlobal['players'][devPlayer.id]['coverArtFile']), isError=True)
                            indigo.server.log(u'Cover Art Error -  ERR: %s' % (e), isError=True)


            elif self.serverResponse[1] == "mode":  # mode

                self.deviceStateUpdate(True,  devPlayer, 'mode', self.serverResponse[2])

                state = 'unknown'
                if pluginGlobal['players'][devPlayer.id]['mode'] == 'stop':
                    state = 'stopped'
                elif pluginGlobal['players'][devPlayer.id]['mode'] == 'pause':
                    state = 'paused'
                elif pluginGlobal['players'][devPlayer.id]['mode'] == 'play':
                    state = 'playing'
                if (pluginGlobal['players'][devPlayer.id]['powerUi'] == 'off') or (pluginGlobal['players'][devPlayer.id]['powerUi'] == 'disconnected'):
                    state = pluginGlobal['players'][devPlayer.id]['powerUi']
                    indigo.devices[devPlayer.id].updateStateOnServer(key="artist", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="album", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="title", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="genre", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="duration", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="remoteStream", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="playlistTrackNumber", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="playlistTracksTotal", value='')
                    indigo.devices[devPlayer.id].updateStateOnServer(key="playlistTracksUi", value='')

                self.deviceStateUpdate(True,  devPlayer, 'state', state)

                if float(indigo.server.apiVersion) >= 1.18:
                    stateImage = indigo.kStateImageSel.Auto
                    if state == 'unknown':
                        stateImage = indigo.kStateImageSel.PowerOff
                    elif state == 'stopped':
                        stateImage = indigo.kStateImageSel.AvStopped
                    elif state == 'paused':
                        stateImage = indigo.kStateImageSel.AvPaused
                    elif state == 'playing':
                        stateImage = indigo.kStateImageSel.AvPlaying
                    elif state == 'off' or state == 'disconnected':
                        stateImage = indigo.kStateImageSel.PowerOff
                    else:
                        stateImage = indigo.kStateImageSel.PowerOff

                    indigo.devices[devPlayer.id].updateStateImageOnServer(stateImage)


                    autolog(DETAIL, "state image selector: " + str(indigo.devices[self.replyPlayerId].displayStateImageSel))

                if pluginGlobal['announcement']['step'] == "initialise":
                    autolog(ANNOUNCE, "ACT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))
                    pluginGlobal['players'][self.masterPlayerId]['savedMode'] = self.serverResponse[2]
                    if pluginGlobal['players'][self.masterPlayerId]['savedMode'] == 'play':
                        pluginGlobal['players'][self.masterPlayerId]['announcementPlaylistNoplay'] = '0'
                    else:
                       pluginGlobal['players'][self.masterPlayerId]['announcementPlaylistNoplay'] = '1'

            elif self.serverResponse[1] == "time":  # time
                pluginGlobal['players'][self.masterPlayerId]['time'] = self.serverResponse[2]
                if pluginGlobal['announcement']['step'] == "initialise":
                    autolog(ANNOUNCE, "ACT=[initialise]: %s" % (indigo.devices[self.masterPlayerId].name))
                    pluginGlobal['players'][self.masterPlayerId]['savedTime'] = self.serverResponse[2].split('.')[0]

            elif self.serverResponse[1] == "autologAnnouncementSaveState":  # autologAnnouncementSaveState
                pluginGlobal['announcement']['step'] = "saveState"
                autolog(ANNOUNCE, "NXT=[saveState]: %s" % (indigo.devices[self.masterPlayerId].name))


                for slavePlayerId in pluginGlobal['players'][self.masterPlayerId]['slavePlayerIds']:
                # for each slave player

                    if pluginGlobal['players'][slavePlayerId]['savedPower'] == "0":
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " power 1")

                    if pluginGlobal['players'][slavePlayerId]['savedMaintainSync'] != "0":
                        pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " playerpref maintainSync 0")

                    # if pluginGlobal['players'][slavePlayerId]['savedVolume'] != "50":
                    #     pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][slavePlayerId]['serverId']].put(pluginGlobal['players'][slavePlayerId]['mac'] + " mixer volume 50")  # FIX THIS !!!!!!

                if pluginGlobal['players'][self.masterPlayerId]['savedMaintainSync'] != "0":
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playerpref maintainSync 0")

                # if saved repeat != 0
                #    turn repeat off
                if pluginGlobal['players'][self.masterPlayerId]['savedRepeat'] != "0":
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist repeat 0")

                # if saved shuffle != 0 
                #     turn shuffle off
                if pluginGlobal['players'][self.masterPlayerId]['savedShuffle'] != "0":
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist shuffle 0")

                #  save playlist
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist save autolog_" + str(self.masterPlayerId) + " silent:1")

                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " autologAnnouncementPlay")

            elif self.serverResponse[1] == "autologAnnouncementPlay":  # autologAnnouncementPlay

                pluginGlobal['announcement']['step'] = "play"
                autolog(ANNOUNCE, "NXT=[play]: %s" % (indigo.devices[self.masterPlayerId].name))

                announcementUniqueKey = pluginGlobal['players'][self.masterPlayerId]['announcementUniqueKey']

                # Set Volume
                playerIdsToProcess = self._playersToProcess(self.replyPlayerId, 'autologAnnouncementPlay Volume')
                for playerIdToProcess in playerIdsToProcess:
                    mac = self._playerDeviceIdToMAC(playerIdToProcess)
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][playerIdToProcess]['serverId']].put(mac + " mixer volume " + pluginGlobal['announcement'][announcementUniqueKey]['volume'] )


                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist clear")

                if pluginGlobal['announcement'][announcementUniqueKey]['option'] == 'file':
                    announcementFile = pluginGlobal['announcement'][announcementUniqueKey]['file']
                else:
                    try:
                        nssp = NSSpeechSynthesizer
                        announcementFile = str('%s/%s/%s/%s' %(pluginGlobal['announcement']['announcementTempFolder'], 'autolog/squeezebox', str(indigo.devices[self.masterPlayerId].id), 'autologSpeech.aiff'))

                        url = NSURL.fileURLWithPath_(announcementFile)
                        ve = nssp.alloc().init()
                        voice = pluginGlobal['announcement'][announcementUniqueKey]['voice']
                        ve.setVoice_(voice)
                        ve.startSpeakingString_toURL_(pluginGlobal['announcement'][announcementUniqueKey]['speechText'], url)

                    except Exception, e:
                        autolog(ERROR, u"ANNOUNCEMENT SPEECH ERROR detected for '%s'. Line '%s' has error='%s'" % (indigo.devices[self.process[0]].name, sys.exc_traceback.tb_lineno, e))   
                        return    

                if 'prepend' in pluginGlobal['announcement'][announcementUniqueKey]:
                    autolog(ANNOUNCE, "announcementPrepend = '%s'" % (pluginGlobal['announcement'][announcementUniqueKey]['prepend']))
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist add " + pluginGlobal['announcement'][announcementUniqueKey]['prepend'])

                autolog(ANNOUNCE, "announcementFile = '%s'" % (announcementFile))
                announcementFile = urllib2.quote(announcementFile)
                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist add " + announcementFile)

                if 'append' in pluginGlobal['announcement'][announcementUniqueKey]:
                    autolog(ANNOUNCE, "announcementAppend = '%s'" % (pluginGlobal['announcement'][announcementUniqueKey]['append']))
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " playlist add " + pluginGlobal['announcement'][announcementUniqueKey]['append'])

                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " play")

            elif self.serverResponse[1] == "autologAnnouncementRestartPlaying":  # autologAnnouncementRestartPlaying
                pluginGlobal['announcement']['step'] = 'autologAnnouncementRestartPlaying'
                autolog(ANNOUNCE, "NXT=[autologAnnouncementRestartPlaying]: %s" % (indigo.devices[self.masterPlayerId].name))

                if pluginGlobal['players'][self.masterPlayerId]['announcementPlaylistNoplay'] == '0' and pluginGlobal['players'][self.masterPlayerId]['savedPower'] != 0:
                    pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " play")
                    # if pluginGlobal['players'][self.masterPlayerId]['savedTime'] !=  "0":
                    #     pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " time " + pluginGlobal['players'][self.masterPlayerId]['savedTime'])

                pluginGlobal['queues']['commandToSend'][pluginGlobal['players'][self.masterPlayerId]['serverId']].put(self.masterPlayerMAC + " autologAnnouncementEnded")


            elif self.serverResponse[1] == "autologAnnouncementEnded":  # autologAnnouncementEnded
                pluginGlobal['announcement']['step'] = 'autologAnnouncementEnded'
                autolog(ANNOUNCE, "LAST STEP [autologAnnouncementEnded]: %s" % (indigo.devices[self.masterPlayerId].name))
                pluginGlobal['announcement']['active'] = 'NO'
                pluginGlobal['announcement']['step'] = ''
                autolog(ANNOUNCE, u"Play Announcement Ended")

                # clear any status as appropriate

                try:
                    pass
                    # pop next queued announcement (if any) otherwise an Empty exception is raised 
                    self.queuedAnnouncement = pluginGlobal['queues']['announcementQueue'].get(False)
                    
                    autolog(ANNOUNCE, "self.queuedAnnouncement = (%s,%s)" % (self.queuedAnnouncement[0],self.queuedAnnouncement[1]))

                    pluginGlobal['announcement']['active'] = 'PENDING'
                    pluginGlobal['queues']['commandToSend'][self.queuedAnnouncement[0]].put(self.queuedAnnouncement[1])


                except autologQueueEmpty:
                    autolog(ANNOUNCE, "self.queuedAnnouncement = EMPTY")
                    pass
                    # handle queue empty

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _handle_EXAMPLE(self):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:
            pass

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))


    def _playersToProcess(self, devId, debugText):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        playerIdsToProcess = []
        if pluginGlobal['players'][devId]['masterPlayerId'] != 0:
            masterPlayerId = pluginGlobal['players'][devId]['masterPlayerId']
            playerIdsToProcess.append(masterPlayerId)
            for slaveId in pluginGlobal['players'][masterPlayerId]['slavePlayerIds']:
                playerIdsToProcess.append(slaveId)
        elif pluginGlobal['players'][devId]['slavePlayerIds'] != []:
            playerIdsToProcess.append(devId)
            for slaveId in pluginGlobal['players'][devId]['slavePlayerIds']:
                playerIdsToProcess.append(slaveId)
        else:
            playerIdsToProcess.append(devId)

        autolog(DETAIL, u'_playersToProcess [%s] = %s' % (debugText, playerIdsToProcess))

        return playerIdsToProcess


    def _playerMACToDeviceId(self, mac):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        deviceId = 0

        for playerDevId in pluginGlobal['players']:
            if mac == pluginGlobal['players'][playerDevId]['mac']:
                deviceId = playerDevId

        #autolog(DETAIL, u"PLAYER MAC ADDRESS [%s] IS DEVICE ID [%s]" % (mac, deviceId)) 

        return deviceId

    def _playerDeviceIdToMAC(self, devId):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        mac = ''
        for playerDevId in pluginGlobal['players']:
            if playerDevId == devId:
                mac = pluginGlobal['players'][playerDevId]['mac']

        return mac

    def _playerRemoveSyncMaster(self):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        for playerDevId in pluginGlobal['players']:
            pluginGlobal['players'][playerDevId]['masterPlayerAddress'] = ""
            pluginGlobal['players'][playerDevId]['masterPlayerId'] = 0
            pluginGlobal['players'][playerDevId]['slavePlayerIds'] = []


    def _playerUpdateSync(self):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))

        try:
            for playerDevId in pluginGlobal['players']:
                dev = indigo.devices[playerDevId]
                if pluginGlobal['players'][playerDevId]['slavePlayerIds'] == []:



                    indigo.devices[playerDevId].updateStateOnServer(key="isSyncMaster",  value=False)
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_1_Id",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_1_Address",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_1_Name",  value='')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_2_Id",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_2_Address",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_2_Name",  value='')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_3_Id",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_3_Address",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_3_Name",  value='')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_4_Id",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_4_Address",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterSlave_4_Name",  value='')
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterNumberOfSlaves",  value='0')
                else:
                    indigo.devices[playerDevId].updateStateOnServer(key="isSyncMaster",  value=True)
                    slaveIds = ''
                    slaveAddresses = ''
                    slaveNames = ''
                    slaveLoopCount = 0
                    for slaveId in pluginGlobal['players'][playerDevId]['slavePlayerIds']:
                        slaveLoopCount += 1
                        if slaveLoopCount < 5:  # Maximum number of 4 slaves to be recorded in master player devices (even though internally it handles more)

                            syncMasterSlave_N_Id = str('syncMasterSlave_%d_Id' % (slaveLoopCount))
                            syncMasterSlave_N_Address = str('syncMasterSlave_%d_Address' % (slaveLoopCount))
                            syncMasterSlave_N_Name= str('syncMasterSlave_%d_Name' % (slaveLoopCount))

                            indigo.devices[playerDevId].updateStateOnServer(key=syncMasterSlave_N_Id,  value=str(slaveId))
                            indigo.devices[playerDevId].updateStateOnServer(key=syncMasterSlave_N_Address,  value=pluginGlobal['players'][slaveId]['mac'])
                            indigo.devices[playerDevId].updateStateOnServer(key=syncMasterSlave_N_Name,  value=pluginGlobal['players'][slaveId]['name'])
 
                    indigo.devices[playerDevId].updateStateOnServer(key="syncMasterNumberOfSlaves",  value=str(slaveLoopCount))

                if  pluginGlobal['players'][playerDevId]['masterPlayerId'] == 0:
                    indigo.devices[playerDevId].updateStateOnServer(key="isSyncSlave",  value=False)
                    indigo.devices[playerDevId].updateStateOnServer(key="masterPlayerId",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="masterPlayerAddress",  value='None')
                    indigo.devices[playerDevId].updateStateOnServer(key="masterPlayername",  value='')
                else:
                    indigo.devices[playerDevId].updateStateOnServer(key="isSyncSlave",  value=True)
                    indigo.devices[playerDevId].updateStateOnServer(key="masterPlayerId",  value=str(pluginGlobal['players'][playerDevId]['masterPlayerId']))
                    indigo.devices[playerDevId].updateStateOnServer(key="masterPlayerAddress",  value=pluginGlobal['players'][playerDevId]['masterPlayerAddress'])
                    indigo.devices[playerDevId].updateStateOnServer(key="masterPlayername",  value=pluginGlobal['players'][pluginGlobal['players'][playerDevId]['masterPlayerId']]['name'])

        except Exception, e:
            autolog(ERROR, u"StandardError detected: Line '%s' has error='%s'" % (sys.exc_traceback.tb_lineno, e))



    def validateDeviceConfigUi(self, valuesDict, typeId, devId):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        self.validateDeviceFlag[devId] = {}
        self.validateDeviceFlag[devId]["edited"] = False

        self.currentTime = indigo.server.getTime()
 
        if typeId == "squeezeboxServer":
            # Validate Squeezebox Server
            self.validateDeviceFlag[devId]['ipAddress'] = ""
            try:
                if "ipAddress" in valuesDict:
                    self.validateDeviceFlag[devId]['ipAddress'] = valuesDict["ipAddress"]
                try:
                    socket.socket.inet_aton(self.validateDeviceFlag[devId]['ipAddress'])
                except socket.error:
                    self.validateDeviceFlag[devId]['ipAddress'] = ""

            except:
                pass

            if self.validateDeviceFlag[devId]['ipAddress'] == "":
                errorDict = indigo.Dict()
                errorDict["ipAddress"] = "Specify the Squeezebox Server IP Address"
                errorDict["showAlertText"] = "Please specify the IP Address of the Squeezebox Server."
                return (False, valuesDict, errorDict)
        else:
            # Validate Squeezebox Player
            self.validateDeviceFlag[devId]['mac'] = ""
            try:
                if "mac" in valuesDict:
                    self.validateDeviceFlag[devId]['mac'] = valuesDict["mac"]
                if re.match("[0-9a-f]{2}([-:])[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", self.validateDeviceFlag[devId]['mac'].lower()):
                   pass
                else:
                    self.validateDeviceFlag[devId]['mac'] = ""
            except:
                pass

            if self.validateDeviceFlag[devId]['mac'] == "":
                errorDict = indigo.Dict()
                errorDict["mac"] = "Specify Squeezebox Player MAC"
                errorDict["showAlertText"] = "You must specify the MAC of the Squeezebox Player."
                return (False, valuesDict, errorDict)

        self.validateDeviceFlag[devId]["edited"] = True

        return (True, valuesDict)


    def deviceStartComm(self, dev):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        dev.stateListOrDisplayStateIdChanged()  # Ensure latest devices.xml is being used

        try:
            self.currentTime = indigo.server.getTime()

            devId = dev.id

            self.validateDeviceFlag[devId] = {}
            self.validateDeviceFlag[devId]["edited"] = False

            if dev.deviceTypeId == "squeezeboxServer":

                pluginGlobal['servers'][devId] = {}
                pluginGlobal['servers'][devId]['keepThreadAlive'] = True
                pluginGlobal['servers'][devId]['datetimeStarted'] = self.currentTime
                pluginGlobal['servers'][devId]['ipAddress'] = dev.pluginProps['ipAddress']
                pluginGlobal['servers'][devId]['port'] = dev.pluginProps['port']
                pluginGlobal['servers'][devId]['ipAddressPort'] = dev.pluginProps['ipAddress'] + ":" + dev.pluginProps['port']
                pluginGlobal['servers'][devId]['ipAddressPortName'] = (pluginGlobal['servers'][devId]['ipAddressPort'].replace('.','-')).replace(':','-')
                pluginGlobal['servers'][devId]['status'] = 'starting'
                pluginGlobal['servers'][devId]['lastScan'] = "?"
                pluginGlobal['servers'][devId]['playersMAC'] = ""  # Used to handle specific player as result of subscribe (normally empty but used on connect)

                self.props = dev.pluginProps
                self.props['address'] = pluginGlobal['servers'][devId]['ipAddressPort']
                dev.replacePluginPropsOnServer(self.props)

                pluginGlobal['queues']['commandToSend'][devId] = autologQueue()  # set-up queue for each individual server

                signalWakeupQueues(pluginGlobal['queues']['commandToSend'][devId])

                pluginGlobal['threads']['communicateWithServer'][devId] = communicateWithServerThread(devId, pluginGlobal['servers'][devId]['ipAddress'], pluginGlobal['servers'][devId]['port'])
                pluginGlobal['threads']['communicateWithServer'][devId].start()

                pluginGlobal['threads']['listenToServer'][devId] = listenToServerThread(devId, pluginGlobal['servers'][devId]['ipAddress'], pluginGlobal['servers'][devId]['port'])
                pluginGlobal['threads']['listenToServer'][devId].start()

                dev.updateStateOnServer(key="status", value=pluginGlobal['servers'][devId]['status'])
                if float(indigo.server.apiVersion) >= 1.18:
                    dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)

                pluginGlobal['queues']['commandToSend'][devId].put("serverstatus 0 0 subscribe:-")

                autolog(INFO, u"Started '%s': '%s'" % (dev.name, pluginGlobal['servers'][devId]['ipAddress']))
                autolog(DETAIL, u"SELF.SERVERS for '%s' = %s" % (dev.name, pluginGlobal['servers'][devId]))

            elif dev.deviceTypeId == "squeezeboxPlayer":
                if dev.id not in pluginGlobal['players']:
                    pluginGlobal['players'][dev.id] = {}

                pluginGlobal['players'][devId]['name'] = dev.name
                self.deviceStateGet(dev, 'model')
                pluginGlobal['players'][devId]['mac'] = dev.address
                self.deviceStateGet(dev, 'serverId')
                self.deviceStateGet(dev, 'serverName')

                autolog(DETAIL, u"MAC [%s] = '%s'" % (dev.name, pluginGlobal['players'][devId]['mac']))

                self.deviceStateUpdate(False, dev, 'datetimeStarted', self.currentTime)


                self.deviceStateUpdate(False, dev, 'announcementPlayActive', 'NO')
                #  self.deviceStateUpdate(False, dev, 'name', dev.name)
                #  self.deviceStateUpdate(False, dev, 'mac', dev.pluginProps['mac'])  # MAC of Squeezebox Player

                self.deviceStateUpdate(False, dev, 'savedPower', '?')
                self.deviceStateUpdate(False, dev, 'savedMode','?')
                self.deviceStateUpdate(False, dev, 'savedRepeat', '?')
                self.deviceStateUpdate(False, dev, 'savedShuffle', '?')
                self.deviceStateUpdate(False, dev, 'savedVolume', '?')
                self.deviceStateUpdate(False, dev, 'savedTime', '0')
                self.deviceStateUpdate(False, dev, 'savedMaintainSync', '?')

                self.deviceStateUpdate(False, dev, 'songUrl', '')
                self.deviceStateUpdate(True,  dev, 'album', '')
                self.deviceStateUpdate(True,  dev, 'artist', '')
                self.deviceStateUpdate(True,  dev, 'connected', False)
                self.deviceStateUpdate(True,  dev, 'duration', '')
                self.deviceStateUpdate(True,  dev, 'durationUi', '')
                self.deviceStateUpdate(True,  dev, 'genre', '')
                self.deviceStateUpdate(True,  dev, 'ipAddress', 'Unknown')
                self.deviceStateUpdate(True,  dev, 'isSyncMaster', False)
                self.deviceStateUpdate(True,  dev, 'isSyncSlave', True)
                self.deviceStateUpdate(True,  dev, 'maintainSync', '0')
                self.deviceStateUpdate(True,  dev, 'masterPlayerId', 0)
                self.deviceStateUpdate(True,  dev, 'masterPlayerAddress', '')
                self.deviceStateUpdate(True,  dev, 'masterPlayername', '')
                self.deviceStateUpdate(True,  dev, 'mode', '?')
                self.deviceStateUpdate(True,  dev, 'portAddress', 'Unknown')
                self.deviceStateUpdate(True,  dev, 'playlistTrackNumber', '?')
                self.deviceStateUpdate(True,  dev, 'playlistTracksTotal', '?')
                self.deviceStateUpdate(True,  dev, 'playlistTracksUi', '?')
                self.deviceStateUpdate(True,  dev, 'power', '0')
                self.deviceStateUpdate(True,  dev, 'powerUi', 'disconnected')
                self.deviceStateUpdate(True,  dev, 'remoteStream', '')
                self.deviceStateUpdate(True,  dev, 'repeat', '')
                self.deviceStateUpdate(True,  dev, 'shuffle', '')
                self.deviceStateUpdate(True,  dev, 'state', 'disconnected')
                self.deviceStateUpdate(False, dev, 'time', '0')

                self.deviceStateUpdate(True,  dev, 'syncMasterNumberOfSlaves', '0')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_1_Id', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_1_Address', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_1_Name', '')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_2_Id', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_2_Address', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_2_Name', '')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_3_Id', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_3_Address', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_3_Name', '')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_4_Id', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_4_Address', 'None')
                self.deviceStateUpdate(True,  dev, 'syncMasterSlave_4_Name', '')
                self.deviceStateUpdate(True,  dev, 'title', '')
                self.deviceStateUpdate(True,  dev, 'volume', '0')

                if float(indigo.server.apiVersion) >= 1.18:
                    dev.updateStateImageOnServer(indigo.kStateImageSel.PowerOff)
                
                try:
                    if pluginGlobal['servers'][pluginGlobal['players'][devId]['serverId']]:
                        pass
                    autolog(DETAIL, u"Server Started before player '%s'" % (dev.name))
                    pluginGlobal['queues']['commandToSend'][devId].put("serverstatus 0 0 subscribe:0")          # CHECK THIS OUT - IS IT A BIT OTT?
                except StandardError:
                    pass
                    autolog(DETAIL, u"Server Starting after player '%s'" % (dev.name))

                autolog(INFO, u"Started '%s': '%s'" % (dev.name, pluginGlobal['players'][devId]['mac']))
                autolog(DETAIL, u"pluginGlobal['players'] for '%s' = %s" % (dev.name, pluginGlobal['players'][devId]))


                createCoverArtUrl = False
                try:
                    self.deviceStateUpdate(False,  dev, 'coverArtFolder', '')  # Default to not found
                    path = str('%s/%s/%s' %(pluginGlobal['coverArtFolder'], 'autolog/squeezebox', str(dev.id)))
                    #autolog(DETAIL, u'Cover art folder: %s' % (path))
                    os.makedirs(path)
                    self.deviceStateUpdate(False,  dev, 'coverArtFolder', path)
                    createCoverArtUrl = True
                except OSError, e:
                    if e.errno == errno.EEXIST:
                        self.deviceStateUpdate(False,  dev, 'coverArtFolder', path)
                        createCoverArtUrl = True
                    else:
                        autolog(ERROR, u'Unable to create cover art folder: %s' % (path))

                if createCoverArtUrl == True:
                    coverArtFile = str('%s/%s' % (path, 'coverart.jpg'))
                    coverArtUrl = str('file://%s' % (coverArtFile))
                    try:
                        shutil.copy2(pluginGlobal['coverArt']['noCoverArtFile'],coverArtFile)
                    except StandardError, e:
                        indigo.server.log(u'Cover Art Error -  IN: %s' % (pluginGlobal['coverArt']['noCoverArtFile']), isError=True)
                        indigo.server.log(u'Cover Art Error - OUT: %s' % (coverArtFile), isError=True)
                        indigo.server.log(u'Cover Art Error - ERR: %s' % (e), isError=True)
                        pass
                else:
                    coverArtUrl = 'Not available'
                self.deviceStateUpdate(False,  dev, 'coverArtFile', coverArtFile)  # Cover Art Url
                self.deviceStateUpdate(True,  dev, 'coverArtUrl', coverArtUrl)  # Cover Art Url

            else:
                autolog(ERROR, "Squeezebox Invalid Device Type [%s]" % (dev.deviceTypeId))

        except StandardError, e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            autolog(ERROR, u"deviceStartComm: StandardError detected for '%s' at line '%s' = %s" % (dev.name, exc_tb.tb_lineno,  e))  

    def deviceStateGet(self, dev, stateKey):  

        pluginGlobal['players'][dev.id][stateKey] = indigo.devices[dev.id].states[stateKey]


    def deviceStateUpdate(self, updateServer, dev, stateKey, stateValue):  

        pluginGlobal['players'][dev.id][stateKey] = stateValue
        if updateServer == True:
            dev.updateStateOnServer(key=stateKey, value=stateValue)


    def deviceStateUpdateWithIcon(self, updateServer, dev, stateKey, stateValue, icon):
        self.deviceStateUpdate(True, dev, stateKey, stateValue)  
        if float(indigo.server.apiVersion) >= 1.18:
            dev.updateStateImageOnServer(icon)   

 
    def deviceStopComm(self, dev):
        global pluginGlobal
        autolog(METHOD, u"%s" %  (methodNameForTrace()))  

        if dev.deviceTypeId == "squeezeboxServer":
            del pluginGlobal['servers'][dev.id]
        elif dev.deviceTypeId == "squeezeboxPlayer":
            del pluginGlobal['players'][dev.id]

 
        autolog(INFO, "Stopping '%s'" % (dev.name))


