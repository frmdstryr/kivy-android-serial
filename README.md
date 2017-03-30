# kivy-android-serial

Android serial port driver (ACM) for Kivy based on usb-serial-for-android.

### Installing

1. In buildozer.spec add termios.so to the whitelist 
2. Include  pyserial and android in requirements
3. Add intent-filter.xml
4. Add device_filter.xml to your android res/xml/ folder
5. Add `<uses-feature android:name="android.hardware.usb.host" />` to your AndroidManifest.xml

```

# (list) python-for-android whitelist
android.p4a_whitelist = lib-dynload/termios.so

# (list) Application requirements
# comma seperated e.g. requirements = sqlite3,kivy
requirements = pyserial,android

# (str) XML file to include as an intent filters in <activity> tag
android.manifest.intent_filters = intent-filter.xml 
 
```

### Usage

Use like you would use `serial.Serial`.  A non-blocking implementation for use with twisted is included. 
