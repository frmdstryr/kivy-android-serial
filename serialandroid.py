'''
Created on Dec 1, 2016

Kivy serial port driver for Android. 

A pyjnius port of usb-serial-for-android

License MIT

@author: frmdstryr@gmail.com
'''
from jnius import autoclass, cast
from serial.serialutil import SerialBase, SerialException, SerialTimeoutException

UsbConstants = autoclass('android.hardware.usb.UsbConstants')
Context = autoclass('org.kivy.android.PythonActivity')
ByteBuffer = autoclass('java.nio.ByteBuffer')
UsbRequest = autoclass('android.hardware.usb.UsbRequest')
PendingIntent = autoclass('android.app.PendingIntent')

import logging
log = logging.getLogger("kivy")

class CdcAcmSerialPort(SerialBase):
    """
    For this to work you must request permission using an intent
    filter:
    
    https://developer.android.com/guide/topics/connectivity/usb/host.html  
    
    """
    USB_RECIP_INTERFACE = 0x01
    USB_RT_ACM = UsbConstants.USB_TYPE_CLASS | USB_RECIP_INTERFACE

    SET_LINE_CODING = 0x20  # USB CDC 1.1 section 6.2
    GET_LINE_CODING = 0x21
    SET_CONTROL_LINE_STATE = 0x22
    SEND_BREAK = 0x23
    
    STOPBIT_MAP = {
            1:0,
            1.5:1,
            2:2,
    }
    PARITY_MAP = {
        'N':0,
        'O':1,
        'E':2,
        'M':3,
        'S':4
    }
    
    #: Use async reads required for build > jellybean
    ASYNC = False
    
    _requested_permission = False
    
    #: USB connection
    _connection = None
    
    #: Timeout for sync reads does ASYNC does NOT use a timeout, it blocks (seems stupid)
    DEFAULT_TIMEOUT = 1000
    
    def open(self):
        self.close()
        
        activity = cast('android.content.Context',Context.mActivity)
        manager = activity.getSystemService("usb")
        device = None
        log.info("UsbDevices: {}".format(manager.getDeviceList().values().toArray()))
        for device in manager.getDeviceList().values().toArray():
            if device:# and device.getDeviceName()==self.portstr:
                log.info("Found device {}".format(device.getDeviceName()))
                break
        if not device:
            raise SerialException("Device not present {}".format(self.portstr))
        
        connection = manager.openDevice(device)
        if not connection:
            #if not CdcAcmSerialPort._requested_permission:
            #    intent = PendingIntent()
            #    manager.requestPermission(device,intent)
            raise SerialException("Failed to open device!")
                
        log.info("UsbDevice connection made {}!".format(connection))
            
        self._device = device
        self._connection = connection
        
        if device.getInterfaceCount()==1:
            log.debug("device might be castrated ACM device, trying single interface logic")
            self._open_single_interface()
        else:
            log.debug("trying default interface logic") 
            self._open_interface()
        
        #: Check that all endpoints are good
        if None in [self._control_endpoint,
                        self._write_endpoint,
                        self._read_endpoint]:
            msg = "Could not establish all endpoints"
            log.debug(msg)
            raise SerialException(msg)
        
        return self.fd
    
    def _open_single_interface(self):
        self._control_interface = self._device.getInterface(0)
        log.debug("Control iface={}".format(self._control_interface))
        self._data_interface = self._device.getInterface(0)
        log.debug("Data iface={}".format(self._data_interface))
        
        if not self._connection.claimInterface(self._control_interface,True):
            raise SerialException("Could not claim shared control/data interface.")
        
        num_endpoints = self._control_interface.getEndpointCount()
        if num_endpoints < 3:
            msg = "not enough endpoints - need 3, got {}".format(num_endpoints)
            log.error(msg)
            raise SerialException(msg)
        
        for i in range(num_endpoints):
            ep = self._control_interface.getEndpoint(i)
            if ((ep.getDirection() == UsbConstants.USB_DIR_IN) and
                (ep.getType() == UsbConstants.USB_ENDPOINT_XFER_INT)):
                log.debug("Found controlling endpoint")
                self._control_endpoint = ep
            elif ((ep.getDirection() == UsbConstants.USB_DIR_IN) and
                (ep.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK)):
                log.debug("Found reading endpoint")
                self._read_endpoint = ep
            elif ((ep.getDirection() == UsbConstants.USB_DIR_OUT) and
                (ep.getType() == UsbConstants.USB_ENDPOINT_XFER_BULK)):
                log.debug("Found writing endpoint")
                self._write_endpoint = ep  
                
            if None not in [self._control_endpoint,
                        self._write_endpoint,
                        self._read_endpoint]:
                log.debug("Found all endpoints")
                break
        
    
    def _open_interface(self):
        device = self._device
        log.debug("claiming interfaces, count={}".format(
            device.getInterfaceCount()))
        
        self._control_interface = device.getInterface(0)
        log.debug("Control iface={}".format(self._control_interface))

        if not self._connection.claimInterface(self._control_interface, True):
            raise SerialException("Could not claim control interface")
        
        self._control_endpoint = self._control_interface.getEndpoint(0)
        log.debug("Control endpoint direction: {}".format(
            self._control_endpoint.getDirection()))
        
        log.debug("Claiming data interface.")
        self._data_interface = device.getInterface(1)
        log.debug("data iface={}".format(self._data_interface))
        
        if not self._connection.claimInterface(self._data_interface, True):
            raise SerialException("Could not claim data interface")
        
        self._read_endpoint = self._data_interface.getEndpoint(1)
        log.debug("Read endpoint direction: {}".format(
            self._read_endpoint.getDirection()))
        
        self._write_endpoint = self._data_interface.getEndpoint(0)
        log.debug("Write endpoint direction: {}".format(
            self._write_endpoint.getDirection()))
        
    def send_acm_control_message(self, request, value, buf=None):
        return self._connection.controlTransfer(
            self.USB_RT_ACM, request, value, 0, buf,
            0 if buf is None else len(buf),
            self._write_timeout
        )
        
    def close(self, *args, **kwargs):
        if self._connection:
            self._connection.close()
        self._connection = None
        
    def _reconfigure_port(self):
        msg = bytearray([self._baudrate & 0xff,
                         self._baudrate >> 8 & 0xff,
                         self._baudrate >> 16 & 0xff,
                         self._baudrate >> 24 & 0xff,
                         self.STOPBIT_MAP[self._stopbits],
                         self.PARITY_MAP[self._parity],
                         self._bytesize
                         ])
        #: Set line coding
        self.send_acm_control_message(self.SET_LINE_CODING, 0, msg)
        
        #: Set line state
        value = (0x2 if self._rts_state else 0) or (0x1 if self._dtr_state else 0)
        self.send_acm_control_message(self.SET_CONTROL_LINE_STATE, value)
    
    @property
    def fd(self):
        #: Warning... This does not seem to work with select :/
        return self._connection.getFileDescriptor()
    
    def reset_input_buffer(self):
        #: Not implemented
        pass
    
    def reset_output_buffer(self):
        #: Not implemented
        pass    
    
    def read(self, n):
        if self.ASYNC:
            data =  self._read_async(n)
        else:
            data = self._read_sync(n)
        log.info("AndroidSerial: read data={}, len={}".format(data,len(data)))
        return data
         
    def _read_async(self,n):
        #: Warning this blocks until data comes or the connection drops
        #: This should be done in an IO thread
        req = UsbRequest()
        try:
            req.initialize(self._connection,self._read_endpoint)
            buf = ByteBuffer.allocate(n)
            if not req.queue(buf,n):
                raise IOError("Error queuing request.")
            #: Warning this response is not necessarily from the above request
            #: see the docs
            resp = self._connection.requestWait()
             
            if resp is None:
                raise IOError("Null response")
            return str(bytearray(buf.array()[0:buf.position()]))
        finally:
            req.close()
        
    def _read_sync(self,n):
        buf = bytearray(n)
        
        timeout = int(self._timeout*1000 if self._timeout else self.DEFAULT_TIMEOUT)
        log.info("AndroidSerial: read start n={},timeout={}".format(n,timeout))
        num_read =  self._connection.bulkTransfer(self._read_endpoint,
                                                  buf,
                                                  n,
                                                  timeout)
        log.info("AndroidSerial: read done num_read={},buf={}".format(n,str(buf)))
        if num_read<0:
            raise SerialTimeoutException("Read timeout")
        elif num_read==0:
            return ''
        return str(buf[0:num_read])
            
    def write(self, data, buffer_size=16*1024):
        offset = 0
        timeout = int(self._write_timeout*1000 if self._write_timeout else self.DEFAULT_TIMEOUT)
        wrote = 0
        log.info("AndroidSerial: write data={}, timeout={}".format(timeout,data))
        while offset < len(data):
            n = min(len(data)-offset,buffer_size)
            buf = data[offset:offset+n]
            i = self._connection.bulkTransfer(self._write_endpoint,
                                              buf,
                                              n,
                                              timeout)
            if i<=0:
                raise IOError("Failed to write {}: {}".format(buf,i))
            offset +=n
            wrote += i
        log.info("AndroidSerial: wrote {}".format(wrote))
        return wrote
        



