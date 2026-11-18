# Troubleshooting

When something goes wrong, check the camera view and messages on the main screen, then follow the relevant steps below.

## Start with These Checks

1. Make sure the software is fully extracted and is not running inside the compressed package.
2. Make sure the model files have finished downloading.
3. Check that the camera view is continuous and clear, with the patient's face and both eyes fully visible.
4. Make sure **Settings → Blink Call → Enable blink call** is set to **On**.
5. Make sure the computer or Bluetooth speaker is not muted.

If the problem continues, find the matching situation below.

## The Software Will Not Open {#app-wont-open}

Check the following in order:

1. Fully extract the downloaded software package.
2. Open the extracted folder and double-click `BlinkCall.exe`.
3. Keep `BlinkCall.exe` together with the other files in the folder. Do not move or copy the executable on its own.
4. Download the package again, extract it to a new folder, and try again.

If the software still will not open, record the Windows version, software version, and any message on screen, then report the problem through [GitHub Issues](https://github.com/JouleEmbodiedAILab/blink-call/issues).

## Model Files Will Not Download {#model-download-failed}

If you see “Network connection timed out,” “Network connection failed,” “Failed to request model information,” or “Failed to download model files”:

1. Check that the computer can access the internet.
2. Close the download message and reopen **Settings → Blink Call**.
3. Click **Download/Update** again.
4. Wait for the entire download to finish. Do not close the software during the download.

After a successful download, the progress window closes and the settings are saved automatically. The main screen should no longer show the message that model files are missing.

If repeated attempts fail, record the complete error message and report it through [GitHub Issues](https://github.com/JouleEmbodiedAILab/blink-call/issues).

## No Camera Image {#camera-no-image}

If the main screen says the camera is not available:

1. Make sure the camera is connected properly.
2. Check that Windows allows desktop applications to access the camera.
3. Close meeting, streaming, or camera applications that may be using the device.
4. Open **Settings → Camera** and select **Local camera**.
5. Start with camera ID `0`. If no image appears, try `1`, `2`, and `3` in order.
6. After each change, click **Save** and check the main screen.

If the main screen says “Camera connection was lost. Reconnecting...,” check the cable, reconnect the camera, and wait for automatic recovery.

If you use both a laptop's built-in camera and an external camera, you can configure a fallback camera. See [Camera](camera.md).

## The Patient's Face or Eyes Are Not Detected {#face-eyes-not-detected}

The main screen may show:

- “No face detected.”
- “Failed to locate facial landmarks.”
- “Invalid facial keypoints. Please check the patient's pose or eye occlusion.”

Adjust the camera or the patient's position:

1. Have the patient face the camera.
2. Keep the full face and both eyes in view, away from the edges of the image.
3. Move hair, bedding, hands, or eyeglass frames away from the eyes.
4. Improve lighting on the face. Avoid a dark face or strong backlighting.
5. Keep the patient and camera steady and wait for recognition to recover.

## Blink Progress Does Not Move or Keeps Resetting {#blink-progress}

Check the following:

1. **Settings → Blink Call → Enable blink call** is set to **On**.
2. **Show top progress bar on home page** is set to **Show**.
3. The patient's face and both eyes can be recognized continuously.
4. Each eye-open or eye-closed action is held until the current stage is complete.
5. The next stage starts within 3 seconds of finishing the previous one.
6. The actions match **Settings → Blink Call → Blink sequence**.

Try restoring the default settings and testing the default sequence:

**Eyes open for 1.5 seconds → eyes closed for 1 second → eyes open for 1 second → eyes closed for 1.5 seconds.**

If the patient finds the current actions difficult, see [Blink Pattern](blink-pattern.md).

## The Sequence Finishes but No Call Is Triggered {#call-not-triggered}

1. Make sure the whole sequence finishes without the progress resetting midway.
2. Make sure **Enable blink call** is set to **On**.
3. Check that model files are not missing or damaged. You can check them again under **Download/Update model files**.
4. Click **Save**, return to the main screen, and test again.

If the main screen reports an inference error or says blink detection is not working, close and reopen the software. If the problem continues, record the message and report it.

## Calls Are Triggered Accidentally {#false-trigger}

- Avoid using only a very short eye-closed action, which may be confused with a natural blink.
- Increase the eye-closed duration slightly.
- Add one or two action steps to make the complete sequence easier to distinguish from natural blinking.
- Change one setting at a time and test several times after each change.
- Consider the patient's stamina and avoid making the sequence too long.

See [Blink Pattern](blink-pattern.md) for instructions.

## No Alert Sound {#no-sound}

1. Open **Settings → Blink Call**.
2. Make sure **Play call audio** is set to **On**.
3. Select a **Call audio file** and click **Preview**.
4. Increase **Audio volume** in the software.
5. Check the Windows volume and the speaker or Bluetooth speaker volume.
6. If using a Bluetooth speaker, make sure the computer is still connected to the correct playback device.
7. Save the settings and complete another test call.

If the preview works but a call produces no sound, check whether the blink sequence actually finished and the call alert appeared.

## Settings Have Become Confusing {#reset-settings}

Open **Settings → Others → Restore defaults**, confirm, and complete another test call.

Restoring defaults resets the blink pattern, camera, audio, and interface settings. It does not delete downloaded model files.

## Information to Include in a Report {#report-issue}

When reporting a problem through [GitHub Issues](https://github.com/JouleEmbodiedAILab/blink-call/issues), include:

- The Blink Call version.
- The Windows version.
- The actions taken before the problem occurred.
- What you expected and what actually happened.
- The complete message shown on the main screen.
- Screenshots that help explain the problem.

If staff need logs or a camera recording, they will explain how to obtain them. Recordings may contain the patient's face and surroundings. Obtain consent first and do not upload sensitive footage directly to a public issue.
