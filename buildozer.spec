[app]
title = Light Speed
package.name = lightspeed
package.domain = org.lightspeed

source.dir = .
source.include_exts = py,png,jpg,kv,atlas

version = 1.0
requirements = python3==3.11.9,kivy,requests,certifi,charset-normalizer,idna,urllib3

orientation = portrait
fullscreen = 0

android.permissions = INTERNET
android.api = 33
android.minapi = 21
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
