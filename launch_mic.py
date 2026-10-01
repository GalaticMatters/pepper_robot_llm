# -*- coding: utf-8 -*-
import os
import signal
import subprocess
import time

os.environ["PYTHONPATH"] = "/opt/aldebaran/lib/python2.7/site-packages"
log = open("/home/nao/launch_mic.log", "a")

def kill_old():
    subprocess.call(["pkill", "-f", "/home/nao/pepper_mic.py"])
    time.sleep(2)

def start():
    kill_old()
    log.write("start pepper_mic %s\n" % time.ctime())
    log.flush()
    return subprocess.Popen(
        ["/usr/bin/python", "/home/nao/pepper_mic.py"],
        stdout=open("/home/nao/pepper_mic.log", "a"),
        stderr=subprocess.STDOUT,
    )

p = start()
while True:
    time.sleep(1800)
    log.write("forced restart %s\n" % time.ctime())
    log.flush()
    p = start()
