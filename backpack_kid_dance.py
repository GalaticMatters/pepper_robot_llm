"""Pepper dances. pepper_whisper calls play() with what the user said.

Add a move by appending to MOVES: a name, the words that select it, how
stiff the body is, and a list of (pose, seconds). Poses use JOINTS, in order.
"dance" with no other name plays the next move in the list.
"""

import base64

JOINTS = [
    "HipRoll",
    "HeadYaw",
    "LShoulderPitch",
    "LShoulderRoll",
    "LElbowYaw",
    "LElbowRoll",
    "RShoulderPitch",
    "RShoulderRoll",
    "RElbowYaw",
    "RElbowRoll",
    "LHand",
    "RHand",
]

REST = [0.00, 0.00, 1.35, 0.12, -1.20, -0.40, 1.35, -0.12, 1.20, 0.40, 0.60, 0.60]

# Backpack Kid floss: hips one way, arms the other.
FLOSS_LEFT = [0.15, -0.25, 0.55, 0.25, -1.40, -0.45, 1.45, -0.12, 1.15, 0.30, 0.70, 0.70]
FLOSS_RIGHT = [-0.15, 0.25, 1.45, 0.12, -1.15, -0.30, 0.55, -0.25, 1.40, 0.45, 0.70, 0.70]

# Stiff robot: arms lock, then one side lifts.
ROBOT_OUT = [0.00, 0.00, 0.50, 0.35, -1.50, -1.10, 0.50, -0.35, 1.50, 1.10, 0.25, 0.25]
ROBOT_LEFT = [0.08, 0.45, -0.70, 0.25, -1.40, -0.90, 1.30, -0.15, 1.40, 0.70, 0.20, 0.20]
ROBOT_RIGHT = [-0.08, -0.45, 1.30, 0.15, -1.40, -0.70, -0.70, -0.25, 1.40, 0.90, 0.20, 0.20]

# Disco: one arm up, hips sway, then swap.
DISCO_LEFT = [0.18, -0.20, -0.50, 0.45, -1.20, -0.55, 1.40, -0.12, 1.20, 0.40, 0.90, 0.40]
DISCO_RIGHT = [-0.18, 0.20, 1.40, 0.12, -1.20, -0.40, -0.50, -0.45, 1.20, 0.55, 0.40, 0.90]

# Push the sky: both hands drop, then shove upward.
SKY_LOW = [0.00, 0.00, 0.70, 0.20, -1.30, -0.90, 0.70, -0.20, 1.30, 0.90, 0.85, 0.85]
SKY_UP = [0.00, 0.00, -1.15, 0.25, -1.20, -0.30, -1.15, -0.25, 1.20, 0.30, 1.00, 1.00]


def _floss():
    beat = 0.55
    steps = [(REST, 0.6), (FLOSS_LEFT, beat)]
    for _ in range(4):
        steps.append((FLOSS_RIGHT, beat))
        steps.append((FLOSS_LEFT, beat))
    steps.append((REST, beat))
    return steps


def _hold(pose, move, stay):
    return [(pose, move), (pose, stay)]


def _robot():
    steps = [(REST, 0.4)]
    steps += _hold(ROBOT_OUT, 0.35, 0.25)
    for _ in range(3):
        steps += _hold(ROBOT_LEFT, 0.28, 0.22)
        steps += _hold(ROBOT_RIGHT, 0.28, 0.22)
    steps += _hold(ROBOT_OUT, 0.28, 0.2)
    steps.append((REST, 0.5))
    return steps


def _disco():
    beat = 0.5
    steps = [(REST, 0.45)]
    for _ in range(4):
        steps.append((DISCO_LEFT, beat))
        steps.append((DISCO_RIGHT, beat))
    steps.append((REST, 0.5))
    return steps


def _sky():
    steps = [(REST, 0.4), (SKY_LOW, 0.35)]
    for _ in range(5):
        steps.append((SKY_UP, 0.32))
        steps.append((SKY_LOW, 0.38))
    steps.append((SKY_UP, 0.32))
    steps.append((REST, 0.55))
    return steps


# Right hand forward. RHand is the finger motor: 1 open, 0 closed.
# The hand opens at the side, the arm reaches while it stays open, then the fingers close.
SHAKE_OPEN = [0.00, 0.00, 1.35, 0.12, -1.20, -0.40, 1.35, -0.12, 1.20, 0.40, 0.60, 1.00]
SHAKE_OFFER = [0.00, -0.20, 1.35, 0.12, -1.20, -0.40, 0.40, -0.10, 1.10, 0.50, 0.60, 1.00]
SHAKE_GRIP = [0.00, -0.20, 1.35, 0.12, -1.20, -0.40, 0.40, -0.10, 1.10, 0.50, 0.60, 0.28]
SHAKE_UP = [0.00, -0.10, 1.35, 0.12, -1.20, -0.40, 0.15, -0.08, 1.00, 0.40, 0.60, 0.28]
SHAKE_DOWN = [0.00, -0.25, 1.35, 0.12, -1.20, -0.40, 0.55, -0.12, 1.20, 0.65, 0.60, 0.28]


def _shake():
    steps = [
        (REST, 0.30),
        (SHAKE_OPEN, 0.35),
        (SHAKE_OFFER, 0.85),
        (SHAKE_OFFER, 0.40),
        (SHAKE_GRIP, 0.40),
    ]
    for _ in range(4):
        steps.append((SHAKE_UP, 0.22))
        steps.append((SHAKE_DOWN, 0.22))
    steps.append((SHAKE_OFFER, 0.40))
    steps.append((REST, 0.55))
    return steps


# words are matched against what the user said. First match wins.
MOVES = [
    ("floss", ("floss", "backpack"), 0.6, _floss),
    ("robot", ("robot",), 0.85, _robot),
    ("disco", ("disco", "sway"), 0.55, _disco),
    ("sky", ("sky", "push the air", "push the sky"), 0.65, _sky),
    ("shake", ("shake", "handshake"), 0.5, _shake),
]

_next = 0

REMOTE = r"""
from naoqi import ALProxy
JOINTS = %s
STEPS = %s
STIFF = %s
motion = ALProxy("ALMotion", "127.0.0.1", 9559)
motion.wakeUp()
motion.setStiffnesses("Body", STIFF)
t = 0.0
times = []
angles = [[] for _ in JOINTS]
for pose, dt in STEPS:
    t += dt
    times.append(t)
    for i in range(len(JOINTS)):
        angles[i].append(pose[i])
time_lists = [times[:] for _ in JOINTS]
motion.angleInterpolation(JOINTS, angles, time_lists, True)
print "dance done"
"""


def matches(text: str) -> bool:
    said = text.lower()
    if "dance" in said:
        return True
    return _named(said) is not None


def _named(said: str):
    for name, words, _stiff, _steps in MOVES:
        if any(word in said for word in words):
            return name
    return None


def _choose(said: str):
    global _next
    name = _named(said)
    if name is None:
        name = MOVES[_next][0]
        _next = (_next + 1) % len(MOVES)
    for move in MOVES:
        if move[0] == name:
            return move
    return MOVES[0]


def play(run, text: str) -> str:
    name, _words, stiffness, steps_fn = _choose(text.lower())
    script = REMOTE % (repr(JOINTS), repr(steps_fn()), repr(stiffness))
    payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
    cmd = (
        "PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages "
        "/usr/bin/python -c 'import base64; exec(base64.b64decode(\"%s\"))'"
        % payload
    )
    result = run(cmd)
    print("DANCE:", name, result.returncode)
    if result.stdout:
        print(result.stdout.strip())
    if result.stderr:
        print(result.stderr.strip())
    return name
