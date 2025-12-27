[app]

# (str) Title of your application
title = Hospital Emergency

# (str) Package name
package.name = emergency_shield

# (str) Package domain (needed for android packaging)
package.domain = org.test

# (str) Source code where the main.py live
source.dir = .

# (list) Source files to include (let empty to include all the files)
source.include_exts = py,png,jpg,kv,atlas,html,css,js

# (str) Application versioning (method 1)
version = 0.1

# (list) Application requirements
# Yahan tere Flask ke saare modules hone chahiye
requirements = python3, kivy, flask, jinja2, werkzeug, itsdangerous, click, requests, markupsafe, chardet, idna, urllib3

# (str) Supported orientation (landscape, portrait or all)
orientation = portrait

# (list) Permissions
# Tere app ko Maps aur Net ke liye ye chahiye
android.permissions = INTERNET, ACCESS_FINE_LOCATION, ACCESS_COARSE_LOCATION

# (int) Android API to use (33 is stable for now)
android.api = 33

# (int) Minimum API your APK will support
android.minapi = 21

# (str) Android NDK version to use
android.ndk = 25b

# (bool) Use private storage for code (set to True)
android.private_storage = True

# (list) List of service to declare
# Isse app background mein bhi chalegi
# services = EmergencyService:service.py

[buildozer]

# (int) Log level (0 = error only, 1 = info, 2 = debug (with command output))
log_level = 2

# (int) Display warning if buildozer is run as root (0 = False, 1 = True)
warn_on_root = 1
