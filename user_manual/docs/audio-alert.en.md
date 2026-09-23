# Audio Alert

Audio alert settings determine whether sound is played after a call is triggered, which ringtone is used, how long the sound plays, and whether a short prompt sound is played after a blink sequence step is completed.

## Turn the Call Sound On or Off

Path:

Settings -> Blink Call -> Play Call Audio.

When enabled, the software plays an alert sound and shows the call alert screen after a call is triggered.

When disabled, the software will not play sound and will not show the call alert screen after a call is triggered.

If the software is used for daily calling, it is recommended to keep this enabled.

## Select a Ringtone

You can choose different ringtones under [Call Audio File].

## Blink Sequence Step Prompt Sound
![提示音](https://cdn.jsdelivr.net/gh/JouleEmbodiedAILab/blink-call@main/user_manual/docs/images/blink_sound.gif)
In [Blink Sequence], each action step can have [Sound Prompt] enabled or disabled.

When enabled, the software plays one short prompt sound after the patient completes the current eye-open or eye-closed step. This tells the patient that the current step is complete and they can continue with the next action.

When disabled, no short prompt sound is played after that step is completed.

This short prompt sound is separate from the ringtone played after a call is triggered. It is controlled by [Sound Prompt] for each action step.

## Preview the Ringtone

Click [Preview] to hear the selected ringtone before saving the settings.

## Adjust the Volume

You can adjust the call volume inside the software.

This changes the software volume for both the call ringtone and the blink sequence step prompt sound. It does not change the computer's system volume. Before daily use, make sure the computer or Bluetooth speaker volume is also set appropriately.

## Set the Playback Duration

You can set how long the sound plays after a call is triggered.

If you want the alert to continue until a family member manually stops it, choose [Infinite].

## Alert When the Camera or Face Is Missing

Turn on [Automatic Abnormality Alert] to set separate delays for a missing camera image and a face that cannot be detected. Both delays default to 5 minutes.

The alert uses the selected ringtone and software volume, and loops until the camera image or face detection recovers. Click the alert screen to silence it; it will not ring again until the current abnormal condition clears. This setting works independently of [Play Call Audio] and the normal call playback duration.

![Set playback duration](https://cdn.jsdelivr.net/gh/JouleEmbodiedAILab/blink-call@main/user_manual/docs/images/audio-alert-settings.jpg)
