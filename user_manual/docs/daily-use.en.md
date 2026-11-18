# Daily Use

After initial setup, open the software, check the camera and audio, then complete the configured blink sequence to trigger a call.

## Quick Checks Before Use

Before each use, have a family member or caregiver confirm that:

- `BlinkCall.exe` is open.
- The main screen continuously shows the camera view.
- The patient's face and both eyes are fully visible, clear, and uncovered.
- The top blink progress bar is visible.
- The computer speakers or Bluetooth speaker are connected and the volume is appropriate.

![Main screen with a clear camera view and top progress bar](images/home-main-window.jpg)

!!! tip
    Repeat a test call after replacing the camera, moving the computer, changing the patient's position, or adjusting the blink pattern.

## Trigger a Call

Complete the eye-open and eye-closed actions in the configured order.

The current default sequence is:

**Eyes open for 1.5 seconds → eyes closed for 1 second → eyes open for 1 second → eyes closed for 1.5 seconds.**

If you have customized the actions, follow **Blink sequence** in the settings.

## Understand the Top Progress Bar

The progress bar shows the required action and completion progress:

- Light green: eyes-open stage.
- Light yellow: eyes-closed stage.
- Dark green: completed progress.

Hold the current action until its stage finishes. Start the next stage within 3 seconds of finishing the previous one, or the whole sequence resets.

![Progress advances through eye-open and eye-closed actions](images/quick-start-call-alert.gif)

## After a Call Is Triggered

After the whole sequence finishes, the software plays the ringtone and displays the call alert.

With a fixed playback duration, the ringtone stops when the configured time is reached. With **Unlimited**, it continues until someone stops it.

To stop early, the patient or caregiver can click the red call alert button.

![Click the red call alert button to stop the ringtone early](images/quick-start-call-alert.jpg)

## During Use

- Keep hair, bedding, hands, and eyeglass frames away from the eyes.
- Check recognition again after a significant change in lighting or patient position.
- If the camera disconnects briefly, the software automatically tries to recover. Reconnect the device and wait for the view to return.
- The alert must be audible to the caregiver, especially across rooms or in noisy surroundings.
- If the sequence is tiring, adjust it with a caregiver's help rather than asking the patient to complete excessively long actions.

## Start Automatically and Use the System Tray

In **Settings → General**, enable **Start automatically when any user logs in** and save the settings. BlinkCall registers a Windows watchdog service that starts the app in each active user session and restarts it after an unexpected exit or forced termination. Enabling or disabling this feature requires administrator authorization. If BlinkCall is not already running as an administrator, Windows automatically displays an authorization prompt; approve it to apply the change.

After startup, BlinkCall remains available in the system tray. Closing the window hides it to the tray; right-click the tray icon to show the window again or exit the application.

To disable automatic startup, clear **Start automatically when any user logs in** and save the settings.

## A Call Did Not Trigger Normally

Check what the main screen shows:

- No image: see [No Camera Image](troubleshooting.md#camera-no-image).
- No face detected or invalid keypoints: see [The Patient's Face or Eyes Are Not Detected](troubleshooting.md#face-eyes-not-detected).
- Progress does not move or keeps resetting: see [Blink Progress Does Not Move or Keeps Resetting](troubleshooting.md#blink-progress).
- The call alert appears without sound: see [No Alert Sound](troubleshooting.md#no-sound).
