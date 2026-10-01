# pepper_robot_llm
Connecting pepper robot to a local llm running on a Mac using MLX

# Pepper voice loop

Local voice chat with a SoftBank Pepper (NAOqi 2.5). The robot only streams the front microphone and speaks. A Mac does pause detection, Whisper, and a local Qwen model.

## Layout

Pepper (Python 2.7) Mac (Python 3) pepper_mic.py pepper_whisper.py ALAudioDevice front mic --TCP:43000--> pause detection mlx-whisper LM Studio Qwen qicli ALAnimatedSpeech.say <-- SSH ----- reply ALMotion / ALAnimationPlayer <-- SSH ----- gesture

Pepper cannot run MLX Whisper or Qwen. Do not put the Mac script on the robot.

## Requirements

- Pepper on the same network as the Mac, NAOqi port 9559
- SSH as `nao` without a password prompt (`ssh-copy-id`)
- On the Mac: `ffmpeg`, `mlx-whisper`, `sounddevice` is not required for the robot mic, `openai`, `numpy`
- LM Studio server at `http://127.0.0.1:8080/v1`, thinking disabled for Qwen

```bash
python3 -m pip install mlx-whisper openai numpy
brew install ffmpeg
```
pepper_mic.py

Runs on the robot. Registers a NAOqi module, listens on 0.0.0.0:43000, and sends 16 kHz 16-bit PCM from the front mic after a client connects. It sends the banner READY first.

Start it with the system Python, not Python 3:

bash
export PYTHONPATH=/opt/aldebaran/lib/python2.7/site-packages
/usr/bin/python /home/nao/pepper_mic.py
Only one copy may run. A second copy fails in registerToBroker because the module name is already taken.

If the Mac disconnects, sendall must mark the client dead and return to accept(). Otherwise the next Mac run times out on port 43000.

pepper_whisper.py
Runs on the Mac. It connects to PEPPER_IP:43000, drops leftover PCM, waits for speech, stops after 1.8 s of silence (max 15 s), transcribes with mlx-community/whisper-large-v3-turbo, and sends the text to Qwen.

Speech goes back over SSH:
qicli call ALAnimatedSpeech.say "..."

Autonomous Life is disabled and the robot is woken up at startup so arm moves are not overridden.

Set PEPPER_IP to the address Pepper speaks when the chest button is pressed.

Gestures

The model does not emit joint angles. The script matches words in the user text and the reply:
| Words |	Action |
| :--- | :--- |
|hello, hi, hey, good morning	| right-arm wave via   ALMotion.setAngles |
| yes, okay, sure |	animations/Stand/Gestures/Yes_1 |
| no, nope | animations/Stand/Gestures/No_1 |

The gesture runs in a thread so speech is not delayed. GESTURE: wave only means the branch ran. If the arm does not move, print the qicli return code.

## Time and date

Qwen has no clock. If the transcript mentions time, date, today, or day, the Mac adds a line like Current time: Thursday, October 01, 2026, 12:08 PM before the chat request. The system prompt tells the model to speak that line and not invent a time. This is the Mac timezone, not Pepper's clock.

## Run order

On Pepper, wait until the log says waiting for Mac on port 43000.
Then start pepper_whisper.py on the Mac.
Speak after Speak now.
Starting the Mac first produces mic connect retry ... timed out.

## Run at Boot
/home/nao/naoqi/preferences/autoload.ini [python] is more reliable than [program] on NAOqi 2.5. launch_mic.py is the file to list there:
[python]
/home/nao/launch_mic.py

That launcher sets PYTHONPATH, kills any old pepper_mic.py, starts a new one, and repeats the kill-and-start every 30 minutes. Each restart drops the Mac socket until the new process is listening.

Do not start launch_mic.py and pepper_mic.py by hand at the same time.

## Notes:
- Built-in ALSpeechRecognition is a small closed vocabulary. This project does not use it.
- Mute is implicit: the Mac only reads audio while listening, but the robot keeps sending.
- The Mac reader thread must keep draining the socket during Qwen and speech, or Pepper's send buffer fills and the client drops.
- Qwen sometimes returns an empty content and puts the sentence in reasoning_content. The script uses whichever is non-empty and strips <think> tags.
