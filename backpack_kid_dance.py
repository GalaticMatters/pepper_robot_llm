"""Backpack Kid floss for Pepper. pepper_whisper calls play() when the user says dance."""

import time

SPEED = 0.75
BEAT = 0.36
REPEATS = 4

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
]

# Hips sway one way while the arms swing the other, then they swap.
LEFT = [0.15, -0.30, 0.45, 0.30, -1.50, -0.50, 1.50, -0.12, 1.20, 0.30]
RIGHT = [-0.15, 0.30, 1.50, 0.12, -1.20, -0.30, 0.45, -0.30, 1.50, 0.50]
REST = [0.00, 0.00, 1.40, 0.12, -1.20, -0.40, 1.40, -0.12, 1.20, 0.40]


def _set_angles(names, angles, speed) -> str:
    name_list = "[" + ",".join('"%s"' % name for name in names) + "]"
    angle_list = "[" + ",".join("%.2f" % angle for angle in angles) + "]"
    return "qicli call ALMotion.setAngles '%s' '%s' %.2f" % (name_list, angle_list, speed)


def play(run) -> None:
    def step(cmd: str, pause: float) -> None:
        result = run(cmd)
        print("DANCE:", cmd, result.returncode)
        if result.stderr:
            print(result.stderr.strip())
        if pause:
            time.sleep(pause)

    step("qicli call ALMotion.wakeUp", 0.2)
    step("qicli call ALMotion.setStiffnesses Body 0.8", 0.1)
    step(_set_angles(["LHand", "RHand"], [0.70, 0.70], 0.50), 0.2)
    for _ in range(REPEATS):
        step(_set_angles(JOINTS, LEFT, SPEED), BEAT)
        step(_set_angles(JOINTS, RIGHT, SPEED), BEAT)
    step(_set_angles(JOINTS, REST, 0.40), 0.4)
