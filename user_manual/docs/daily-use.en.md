# Daily Use

After the first-time setup is complete, daily use only requires opening the software, checking the camera view, and completing the configured blink sequence to trigger a call.

## Open the Software

Before each use, double-click `BlinkCall.exe` and confirm that the main screen shows the camera view.

![Main window](https://cdn.jsdelivr.net/gh/JouleEmbodiedAILab/blink-call@main/user_manual/docs/images/home-main-window.jpg)

## Make Sure Both Eyes Are Clearly Visible

Make sure both of the patient's eyes appear fully in the camera view. The eyes should not be covered by hair, bedding, hands, eyeglass frames, or other objects.

## Trigger a Call with the Blink Sequence

Open and close the eyes in order according to the current blink sequence.

The default sequence is:

Eyes open for 1.5 seconds -> eyes closed for 1 second -> eyes open for 1 second -> eyes closed for 1.5 seconds.

## Watch the Top Progress Bar

The progress bar at the top shows the completion status of the current blink action.

- Light green: eyes-open stage.
- Light yellow: eyes-closed stage.
- Dark green: current completed progress.

During each stage, keep the current eye-open or eye-closed state until that stage is complete. After finishing one stage, start the next stage within 3 seconds, or the progress will reset.

![Blink call](https://cdn.jsdelivr.net/gh/JouleEmbodiedAILab/blink-call@main/user_manual/docs/images/quick-start-call-alert.gif)

## Stop the Call Alert

After the call is triggered, the software will play an alert sound and show the call alert screen.

To stop it early, click the stop button on the call alert screen.

![Blink call](https://cdn.jsdelivr.net/gh/JouleEmbodiedAILab/blink-call@main/user_manual/docs/images/quick-start-call-alert.jpg)

## Start Automatically and Use the System Tray

The packaged Windows app enables **Start automatically when any user logs in** by default. On first launch, BlinkCall requests Windows administrator approval to register its watchdog service. The service starts the app in each active user session and restarts it after an unexpected exit or forced termination. Before approving the prompt, place the app in a fixed location that all users can read but ordinary users cannot modify. Each user's settings are stored in that user's Windows application data directory.

After startup, BlinkCall remains available in the system tray. Closing the window hides it to the tray; right-click the tray icon to show the window again or exit the application.

To disable automatic startup, clear **Start automatically when any user logs in** under **Settings → General** and save. Windows requests administrator approval again. This switch applies to every user of the computer. On the first launch after upgrading, an older disabled setting is migrated to the new enabled default; a later manual choice to disable it is retained.
