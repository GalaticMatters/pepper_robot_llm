"""Backpack Kid floss for Pepper. pepper_whisper calls play() when the user says dance."""

import base64

# Runs on the robot with NAOqi's Python 2.7.
# One angleInterpolation call keeps the hips and arms moving, instead of
# stopping at each pose the way setAngles does.
REMOTE = r"""
from naoqi import ALProxy

JOINTS = ["HipRoll", "HeadYaw", "LShoulderPitch", "LShoulderRoll", "LElbowYaw", "LElbowRoll", "RShoulderPitch", "RShoulderRoll", "RElbowYaw", "RElbowRoll", "LHand", "RHand"]
LEFT = [0.15, -0.25, 0.55, 0.25, -1.40, -0.45, 1.45, -0.12, 1.15, 0.30, 0.70, 0.70]
RIGHT = [-0.15, 0.25, 1.45, 0.12, -1.15, -0.30, 0.55, -0.25, 1.40, 0.45, 0.70, 0.70]
REST = [0.00, 0.00, 1.35, 0.12, -1.20, -0.40, 1.35, -0.12, 1.20, 0.40, 0.70, 0.70]
BEAT = 0.55
CYCLES = 4

poses = [REST, LEFT]
for _ in range(CYCLES):
    poses.append(RIGHT)
    poses.append(LEFT)
poses.append(REST)

times = []
t = 0.6
for _ in poses:
    times.append(t)
    t += BEAT

angles = []
time_lists = []
for joint in range(len(JOINTS)):
    angles.append([pose[joint] for pose in poses])
    time_lists.append(times[:])

motion = ALProxy("ALMotion", "127.0.0.1", 9559)
motion.wakeUp()
motion.setStiffnesses("Body", 0.6)
motion.angleInterpolation(JOINTS, angles, time_lists, True)
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
