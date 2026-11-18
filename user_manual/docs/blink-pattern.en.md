# Blink Pattern

Blink pattern settings determine the order of eye-open and eye-closed actions needed to trigger a call alert.

Use the default settings until the first test succeeds. When adjusting them, change one setting at a time and test again after saving.

## Open the Settings

Open:

**Settings → Blink Call**

Make sure **Enable blink call** is set to **On**. Keep **Show top progress bar on home page** set to **Show** so the patient and caregiver can follow the actions.

## What Is a Blink Sequence?

A blink sequence is a series of eye-open and eye-closed actions. The software recognizes them in the configured order and triggers a call only after the complete sequence finishes.

The current default sequence is:

**Eyes open for 1.5 seconds → eyes closed for 1 second → eyes open for 1 second → eyes closed for 1.5 seconds.**

These actions last longer than a natural blink, which helps reduce accidental calls.

![Complete the blink sequence to trigger a call](images/quick-start-call-alert.gif)

## Change Actions and Durations

Each row under **Blink sequence** is one action step:

- Choose **Open eyes** or **Close eyes**.
- Set the duration from 0.5 to 5 seconds.
- **Sound prompt** determines whether a short cue plays when the step finishes.

Click **Save**, return to the main screen, and complete a test call.

![Set the action, duration, and sound prompt for each step](images/blink-pattern-settings.jpg)

## Add or Remove Steps

- Click **Add step** to append an action to the sequence.
- Click **Remove** on the right of a step to delete it.
- At least one step must remain.

More steps usually make the sequence harder to confuse with natural blinking, but also take more time and effort to complete.

![Add and remove blink sequence steps](images/blink-pattern-settings.gif)

## Adjust for the Patient

| Situation | What to try |
| --- | --- |
| Closing the eyes is difficult | Shorten the eye-closed duration without making it easy to confuse with natural blinking |
| The alert sounds without an intentional call | Increase the eye-closed duration or add one or two action steps |
| Progress often resets midway | Shorten difficult steps and make sure the next step starts within 3 seconds |
| The complete sequence is too tiring | Shorten durations or reduce the number of steps |
| The patient does not know when to move on | Enable **Sound prompt** for the relevant steps |

## A Suggested Adjustment Process

1. Record or remember the current settings.
2. Adjust only one step or duration at a time.
3. Click **Save** and return to the main screen.
4. Have the patient test several times while comfortable.
5. Check both ease of completion and accidental triggering.
6. Use the settings for daily calls after finding a suitable sequence.

!!! warning
    Do not make actions excessively long just to reduce accidental calls. The patient's ability to complete them reliably and comfortably matters more than adding steps.

## Problems After Adjusting

- Progress does not move or keeps resetting: see [Blink Progress Does Not Move or Keeps Resetting](troubleshooting.md#blink-progress).
- Accidental calls: see [Calls Are Triggered Accidentally](troubleshooting.md#false-trigger).
- The settings are no longer clear: use **Settings → Others → Restore defaults**, then test again.
