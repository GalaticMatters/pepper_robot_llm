"""Backpack Kid floss for Pepper. pepper_whisper calls play() when the user says dance."""

import base64

# Runs on the robot with NAOqi's Python 2.7. One call sets every joint together.
# qicli treats a quoted list as a string, so setAngles through qicli returns 1.
REMOTE = r"""
import time
from naoqi import ALProxy

SPEED = 0.75
BEAT = 0.36
REPEATS = 4
JOINTS = ["HipRoll", "HeadYaw", "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll"]
LEFT = [0.15, -0.30, 0.45, 0.30, -1.50, -0.50, 1.50, -0.12, 1.20, 0.30]
RIGHT = [-0.15, 0.30, 1.50, 0.12, -1.20, -0.30, 0.45, -0.30, 1.50, 0.50]
REST = [0.00, 0.00, 1.40, 0.12, -1.20, -0.40, 1.40, -0.12, 1.20, 0.40]

motion = ALProxy("ALMotion", "127.0.0.1", 9559)
motion.wakeUp()
motion.setStiffnesses("Body", 0.8)
motion.setAngles(["LHand", "RHand"], [0.7, 0.7], 0.5)
time.sleep(0.2)
for _ in range(REPEATS):
    motion.setAngles(JOINTS, LEFT, SPEED)
    time.sleep(BEAT)
    motion.setAngles(JOINTS, RIGHT, SPEED)
    time.sleep(BEAT)
motion.setAngles(JOINTS, REST, 0.4)
time.sleep(0.4)
print "dance done"
"""


def play(run) -> None:
    payload = base64.b64encode(REMOTE.encode("utf-8")).decode("ascii")
    cmd = (
        "PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages "
        "/usr/bin/python -c 'import base64; exec(base64.b64decode(\"%s\"))'"
        % payload
    )
    result = run(cmd)
    print("DANCE:", result.returncode)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
