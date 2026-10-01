# -*- coding: utf-8 -*-
import socket
import sys
import threading
import time
import traceback
from naoqi import ALProxy, ALBroker, ALModule

LISTEN_PORT = 43000
SAMPLE_RATE = 16000

class SoundReceiver(ALModule):
    def __init__(self, name):
        ALModule.__init__(self, name)
        self.name = name
        self.lock = threading.Lock()
        self.client = None
        self.alive = False
        self.audio = ALProxy("ALAudioDevice")
        self.subscribed = False
        self.frames = 0

    def start_audio(self):
        if self.subscribed:
            return
        try:
            try:
                self.audio.setClientPreferences(self.name, SAMPLE_RATE, 3, 0)
            except Exception:
                print "front mic failed, trying all channels"
                self.audio.setClientPreferences(self.name, SAMPLE_RATE, 0, 0)
            self.audio.subscribe(self.name)
            self.subscribed = True
            print "mic subscribed as", self.name
        except Exception:
            traceback.print_exc()

    def stop_audio(self):
        if not self.subscribed:
            return
        try:
            self.audio.unsubscribe(self.name)
        except Exception:
            pass
        self.subscribed = False
        print "mic unsubscribed"

    def set_client(self, sock):
        with self.lock:
            old = self.client
            self.client = sock
            self.alive = sock is not None
        if old and old is not sock:
            try:
                old.close()
            except Exception:
                pass
    def processRemote(self, nbOfChannels, nbrOfSamplesByChannel, timestamp, buffer):
        self.frames += 1
        with self.lock:
            sock = self.client
        if sock is None:
            return
        try:
            sock.sendall(buffer)
        except Exception:
            print "client gone, waiting for Mac again"
            self.alive = False
            with self.lock:
                self.client = None
            try:
                sock.close()
            except Exception:
                pass

def serve():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", LISTEN_PORT))
    srv.listen(1)
    print "waiting for Mac on port", LISTEN_PORT
    while True:
        conn, addr = srv.accept()
        print "Mac connected", addr
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            conn.sendall("READY")
        except Exception:
            traceback.print_exc()
            continue
        SoundReceiver.set_client(conn)
        SoundReceiver.start_audio()
        try:
            while SoundReceiver.alive and SoundReceiver.client is conn:
                time.sleep(0.25)
        finally:
            print "Mac session ended"
            SoundReceiver.set_client(None)
            SoundReceiver.stop_audio()

if __name__ == "__main__":
    broker = ALBroker("micBroker", "0.0.0.0", 0, "127.0.0.1", 9559)
    global SoundReceiver
    SoundReceiver = SoundReceiver("SoundReceiver")
    t = threading.Thread(target=serve)
    t.setDaemon(True)
    t.start()
    print "pepper_mic running"
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        SoundReceiver.alive = False
        SoundReceiver.stop_audio()
        sys.exit(0)
