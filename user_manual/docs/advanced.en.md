# Advanced Settings and Technical Support

This page covers language, appearance, and the recording, logging, and restore-default options used for troubleshooting. Recording and debug mode are usually unnecessary for daily calls.

## Switch Language

Open:

**Settings → General → Language**

Choose Chinese or English. Click **Save** to switch the interface to the selected language.

## Change Theme

Open:

**Settings → General → Theme**

Choose **Light** or **Dark**. This changes the appearance only and does not affect camera recognition or calling.

## Record Current Camera Data

This feature saves a recording of the current camera view to help developers or staff investigate recognition problems. It is not needed for ordinary daily use.

Open:

**Settings → Others → Record current camera data**

To record:

1. Set the maximum recording duration.
2. Select a local folder.
3. Click **Start recording**.
4. The software returns to the main screen and starts recording.
5. To finish early, click the stop-recording button on the main screen.

!!! warning "Protect Patient Privacy"
    A camera recording may contain the patient's face and surroundings. Obtain consent from the patient or guardian before recording or sharing. Do not upload sensitive footage directly to a public GitHub issue.

## Enable Debug Mode and Logs

Debug mode displays information about software operation. Enable it when staff need to examine recognition status or investigate a problem.

Open:

**Settings → Others → Debug mode**

To save the general debug log to a file:

1. Turn on **Debug mode**.
2. Set **Save to local** to **Yes**.
3. Choose the local log folder.
4. Click **Save** and repeat the actions until the problem occurs again.

When debug mode is enabled, the selected log folder also receives a separate `audio_status.log`. It records audio-output changes, the ringtone file and volume, load/play states, play requests, and stop events to help investigate a call that was triggered without sound. The file is rotated and keeps recent records.

After troubleshooting, you can turn off debug mode so technical information no longer remains on the main screen.

## Restore Defaults

If blink, camera, audio, or interface settings have become confusing, open:

**Settings → Others → Restore defaults**

After confirmation, the software restores the default configuration and closes the settings window.

Restoring defaults does not delete downloaded model files. It resets the blink pattern, camera ID, audio, interface, and other settings. Check the camera and complete a test call afterwards.

## Contact Staff or Developers

Read [Troubleshooting](troubleshooting.md) before submitting a report.

If the problem remains, report it through [GitHub Issues](https://github.com/JouleEmbodiedAILab/blink-call/issues) and include:

- The software version and Windows version.
- The actions taken before the problem occurred.
- The complete message shown on the main screen.
- What you expected and what actually happened.
- Screenshots without sensitive information.
- Logs, if staff specifically request them.

Do not publicly upload camera recordings unless staff confirm they are needed and explain a safe way to transfer them.
