'''
Created on Jan 20, 2017

Intended to be used on android with
twisted's ThreadedSelect reactor.

License MIT

@author: frmdstryr@gmail.com
'''
from kvserial.driver import CdcAcmSerialPort
from serial.serialutil import SerialException, SerialTimeoutException
from twisted.internet.serialport import SerialPort as SerialBase
from twisted.internet.main import CONNECTION_DONE, CONNECTION_LOST
from twisted.internet.task import LoopingCall
from Queue import Queue, Empty

import logging
log = logging.getLogger("kivy")
    
class SerialPort(SerialBase):
    """ Does reading and writing in a thread
        since UsbDevice does not have a non-blocking
        usb (that I know of). 
    """
    _serialFactory = CdcAcmSerialPort
    
    def __init__(self,*args,**kwargs):
        self._rq = Queue()
        self._wq = Queue()
        self._io = LoopingCall(self._pollUsb)
        self._io.start(interval=0.1,now=True)
        super(SerialPort, self).__init__(*args,**kwargs)
        
    def _pollUsb(self):
        """ Since select does not work on the 
            Android UsbDevice, manually read and write.
        """
        if not hasattr(self,'_serial'):
            return # Not yet ready...
        from twisted.internet import reactor
        #: Do any pending io
        log.warning("_pollUsb..")
        reactor._sendToThread(self._ioThread)
        reactor.wakeUp()
        #: Force rw
        reactor._process_Notify([self],[self])
        
    def _ioThread(self):
        """ Read and Write from USB from a thread."""
        #: Read data
        log.warning("_ioThread..")
        buf = ''
        try:
            #: Do blocking read
            while True:
                buf += self._serial.read(8192)
        except SerialTimeoutException:
            pass
        except SerialException as e:
            log.warning("_ioThread: Error {}".format(e))
            self._io.stop()
            self._rq.put('')
            return
        if buf:
            self._rq.put(buf)
        
        #: Write the data
        try:
            data = self._wq.get_nowait()
            self._serial.write(data)
        except Empty:
            pass
        except IOError as e:
            log.warning("_ioThread: Error {}".format(e))
            self._io.stop()
            return
        log.warning("_ioThread done..")
    
    def writeSomeData(self, data):
        #: Put data in the write queue
        log.warning("_write some data..")
        self._wq.put(data)
        return len(data)
        
    def doRead(self):
        #: Get data from the read queue
        log.warning("_do read..")
        try:
            output = self._rq.get_nowait()
        except Empty as e:
            return
        if not output:
            return CONNECTION_DONE
        self.protocol.dataReceived(output)