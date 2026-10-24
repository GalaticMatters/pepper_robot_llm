# -*- coding: utf-8 -*-
import array
import socket
import struct
import sys
import threading
import time
import traceback
from naoqi import ALProxy, ALBroker, ALModule

LISTEN_PORT = 43000
SAMPLE_RATE = 16000
# Channel config 0 is all four head mics, interleaved. 3 is the front mic only.
ALL_MICS = 0
FRONT_MIC = 3


def mix_mics(buffer, nb_of_channels, samples_per_channel, hold_channel):
    """Return mono 16-bit PCM and the channel to keep next time.

    Opposite mics cancel if they are added raw. Channels much quieter than
    the loudest one are left out. The rest are shifted into agreement and
    averaged, so a voice at the side is not thrown away.
    """
    if nb_of_channels <= 1:
        return buffer, 0
    count = samples_per_channel * nb_of_channels
    raw = buffer[:count * 2]
    vals = struct.unpack("<%dh" % count, raw)
    channels = [vals[c::nb_of_channels] for c in range(nb_of_channels)]
    energy = []
    for ch in channels:
        energy.append(sum(v * v for v in ch))
    best = 0
    for c in range(1, nb_of_channels):
        if energy[c] > energy[best]:
            best = c
    if hold_channel is not None and energy[best] < energy[hold_channel] * 1.5:
        best = hold_channel
    loud = energy[best]
    keep = []
    for c in range(nb_of_channels):
        if energy[c] * 4 >= loud:
            keep.append(c)
    ref = channels[best]
    mixed = [0] * samples_per_channel
    for c in keep:
        src = channels[c]
        lag = 0
        if c != best:
            lag = _best_lag(ref, src, 4)
        for i in range(samples_per_channel):
            j = i + lag
            if 0 <= j < samples_per_channel:
                mixed[i] += src[j]
    scale = len(keep)
    out = array.array("h")
    for v in mixed:
        v //= scale
        if v > 32767:
            v = 32767
        elif v < -32768:
            v = -32768
        out.append(v)
    return out.tostring(), best


def _best_lag(ref, src, limit):
    best_lag = 0
    best_score = None
    n = len(ref)
    for lag in range(-limit, limit + 1):
        score = 0
        if lag >= 0:
            for i in range(n - lag):
                score += ref[i] * src[i + lag]
        else:
            for i in range(-lag, n):
                score += ref[i] * src[i + lag]
        if best_score is None or score > best_score:
            best_score = score
            best_lag = lag
    return best_lag

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
        self.mic_choice = None
        self.reported = False

    def start_audio(self):
        if self.subscribed:
            return
        try:
            try:
                self.audio.setClientPreferences(self.name, SAMPLE_RATE, ALL_MICS, 0)
                print "mic mode: all four"
            except Exception:
                print "all mics failed, using front"
                self.audio.setClientPreferences(self.name, SAMPLE_RATE, FRONT_MIC, 0)
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
        if not self.reported:
            self.reported = True
            print "audio channels", nbOfChannels, "samples", nbrOfSamplesByChannel
        try:
            mono, chosen = mix_mics(buffer, nbOfChannels, nbrOfSamplesByChannel, self.mic_choice)
        except Exception:
            traceback.print_exc()
            mono = buffer
            chosen = self.mic_choice
        if chosen != self.mic_choice:
            print "using mic", chosen
            self.mic_choice = chosen
        with self.lock:
            sock = self.client
        if sock is None:
            return
        try:
            sock.sendall(mono)
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
