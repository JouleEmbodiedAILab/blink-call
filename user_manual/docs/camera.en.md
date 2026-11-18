# Camera

Camera settings select the camera used by the software and help keep the patient's face and both eyes clearly visible.

For ordinary use, keep **Local camera** selected. Other options are needed when multiple cameras are connected or staff are setting up a remote camera.

## Use a Local Camera

A local camera is connected to the current computer, such as a laptop's built-in camera or a USB camera.

Open:

**Settings → Camera → Choose camera source → Local camera**

After making changes, click **Save** and check the main screen.

## Select the Camera ID

The software starts with camera ID `0` by default. If no image appears:

1. Set the camera ID to `0`, save, and check the main screen.
2. If no image appears, try `1`, `2`, and `3` in order.
3. Click **Save** after each change, then check the main screen again.

Windows may list built-in, USB, infrared, and virtual cameras. Choose an ID that produces a normal color image on the main screen.

![Select a local, fallback, or remote camera](images/camera-settings.jpg)

!!! success "Signs of a Working Camera"
    The main screen continuously shows the patient, without camera-unavailable or reconnecting messages.

## Adjust the View

Adjust the camera or the patient's position until:

- The patient faces the camera.
- The full face and both eyes are in view.
- The eyes are not too close to the edges of the image.
- Hair, bedding, hands, or eyeglass frames do not cover the eyes.
- Lighting on the face is stable, without excessive darkness or strong backlighting.
- The patient can maintain the position naturally and comfortably.

If the view looks normal but the patient is not detected, see [The Patient's Face or Eyes Are Not Detected](troubleshooting.md#face-eyes-not-detected).

## Recovery After Disconnection

The software automatically tries to reconnect a local camera after a temporary disconnection.

If there is only one external camera:

1. Keep the software running.
2. Check the cable and reconnect the camera.
3. Wait for the reconnecting message to be replaced by the camera view.

A fallback camera does not need to be enabled in this situation.

## Use a Fallback Camera

If a laptop has both a built-in camera and an external camera, one can serve as the fallback.

1. Test both camera IDs separately and confirm that each produces a normal image.
2. Open **Settings → Camera** and select **Local camera**.
3. Enter the ID of the camera normally used as the primary camera.
4. Turn on **Enable fallback camera**.
5. Enter a fallback camera ID different from the primary ID.
6. Click **Save** and complete a test call.

If the primary camera remains unavailable, the software waits a few seconds and switches to the fallback. It keeps using the fallback while that camera works, even if the primary recovers, to prevent repeated switching. If the fallback also becomes unavailable, the software tries the primary again.

Do not use a virtual camera as the fallback. Check that the chosen device provides a usable image rather than an infrared feed.

## Use a Remote Camera (Advanced)

A remote camera is connected to another computer. Both computers must be on a network where they can reach each other. Staff familiar with network configuration should perform this setup.

On the computer connected to the camera:

1. Open **Settings → Camera**.
2. Under **Start local camera service**, choose the camera ID and service port.
3. Click **Start local camera service**.
4. Note the address and port shown on the main screen.

On the computer running blink recognition:

1. Open **Settings → Camera**.
2. Select **Remote camera**.
3. Enter the address and port shown by the camera-service computer.
4. Click **Save** and check the main screen.

If the main screen says the remote camera is unavailable, check the network, address, and port on both computers. Make sure the computer supplying the camera view is still running the service.

## The Camera Is Still Unavailable

See [No Camera Image](troubleshooting.md#camera-no-image). When reporting the problem, state whether you use a local, fallback, or remote camera and which camera IDs you have tried.
