# First Use

This page is for family members or caregivers setting up the software for a patient for the first time. When finished, you should have a stable camera view and be able to trigger a test call with an audible alert.

## Quick Start Video {#quick-start-video}

Watch the demonstration before following the setup and test steps below. The video uses the Chinese interface and lasts about 2 minutes 22 seconds. The screenshots also show the Chinese interface.

<video controls playsinline preload="metadata" width="960" height="544" style="width: 100%; max-width: 960px; height: auto;" aria-label="First-time setup demonstration">
  <source src="../../images/quick_start.mp4" type="video/mp4">
  Your browser does not support embedded video.
</video>

If playback is unavailable, [open or download the video](images/quick_start.mp4).

## 1. Prepare the Equipment

Before starting, prepare:

- A Windows computer.
- A built-in camera or USB camera.
- Computer speakers or a Bluetooth speaker.
- An internet connection for the first model download.

Have the patient and caregiver complete the final test together.

## 2. Download and Extract the Software

Download the latest software package from any one of these links:

- [GitHub Latest Release](https://github.com/JouleEmbodiedAILab/blink-call/releases/latest)
- [Baidu Netdisk](https://pan.baidu.com/s/1Og8-TmnR_yIdsOA2_MHyiw?pwd=fk35)
- [Quark Netdisk](https://pan.quark.cn/s/e96254bb1153)

After downloading:

1. Find the software package.
2. Fully extract it to a fixed location.
3. Open the extracted folder.

Do not run the software directly inside the compressed package.

![Extract the software package in Windows](images/zip.jpg)

## 3. Open the Software

Double-click `BlinkCall.exe` in the extracted folder.

![Open the software by double-clicking BlinkCall.exe](images/app.jpg)

The software opens to the main screen. Once the model files and camera are ready, it shows the camera view and the blink progress bar at the top.

![Main screen with the camera view and top progress bar](images/home-main-window.jpg)

!!! tip "The Software Will Not Open?"
    Check that the software is fully extracted and run it from the extracted folder again. If it still will not open, see [The Software Will Not Open](troubleshooting.md#app-wont-open).

## 4. Download the Model Files

Model files must be downloaded before first use.

1. Click **Settings** at the top left of the main screen.
2. Select **Blink Call** on the left.
3. Find **Download/Update model files**.
4. Click **Download/Update** and wait for the download to finish.

![Download the model files](images/quick-start-download-model.gif)

!!! success "Signs of Success"
    After a successful download, the software automatically saves the settings, closes the settings window, and returns to the main screen. The message that model files are missing should no longer appear.

!!! warning "The Download Did Not Finish"
    If the software reports a network timeout, connection failure, or model download failure, check the connection and try again. See [Model Files Will Not Download](troubleshooting.md#model-download-failed) for details.

## 5. Allow Camera Access

If Windows asks for camera permission, allow access.

![Allow Blink Call to access the camera in Windows](images/authority.jpg)

If no prompt appears, continue to the next step. If there is still no image afterwards, check Windows camera privacy settings.

## 6. Select the Camera

By default, the software uses a local camera with camera ID `0`.

If no image appears on the main screen:

1. Open **Settings → Camera**.
2. Keep **Local camera** selected.
3. Set the camera ID to `0`, click **Save**, and check the main screen.
4. If there is still no image, try `1`, `2`, and `3` in order, saving after each change.

![Select the local camera ID](images/camera-settings.jpg)

!!! success "Signs of Success"
    The main screen continuously shows the camera view instead of a camera-unavailable or reconnecting message.

See [Camera](camera.md) if multiple cameras are connected or you need a fallback camera.

## 7. Adjust the Patient and Camera Position

Adjust the camera or the patient's position until:

- The patient faces the camera, with the full face and both eyes in view.
- Hair, bedding, hands, or eyeglass frames do not cover the eyes.
- Lighting is stable and the face is not too dark.
- The patient can maintain the position naturally and comfortably.

If the main screen reports that no face is detected, facial landmarks cannot be located, or facial keypoints are invalid, see [The Patient's Face or Eyes Are Not Detected](troubleshooting.md#face-eyes-not-detected).

## 8. Complete a Test Call

The current default sequence is:

**Eyes open for 1.5 seconds → eyes closed for 1 second → eyes open for 1 second → eyes closed for 1.5 seconds.**

During the test:

1. Watch the progress bar at the top of the main screen.
2. Hold each eye-open or eye-closed action until the current stage finishes.
3. Start the next stage within 3 seconds of completing the previous one.
4. After the whole sequence finishes, wait for the call alert and confirm that the ringtone can be heard.
5. Click the red call alert button to stop the ringtone early.

![Trigger and stop a call using the default blink sequence](images/quick-start-call-alert.gif)

!!! success "Test Complete"
    Initial setup is successful when all of the following are true:

    - The camera view is continuous and clear.
    - The top progress bar advances with eye-open and eye-closed actions.
    - The call alert appears after the sequence finishes.
    - The ringtone can be heard through the computer or Bluetooth speaker.
    - Clicking the red call alert button stops the ringtone.

If progress does not move, repeatedly resets, or the alert cannot be heard, see [Troubleshooting](troubleshooting.md).

## Next Steps

- Checks before daily use: [Daily Use](daily-use.md).
- Adjust actions for the patient: [Blink Pattern](blink-pattern.md).
- Adjust the ringtone and volume: [Audio Alert](audio-alert.md).
