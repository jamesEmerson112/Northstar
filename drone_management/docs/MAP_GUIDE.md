# How to Use the Drone Map

This guide shows you how to use the drone dashboard and map. You don't need to know any computer code — just follow along.

## Open the dashboard

Open this address in your web browser (Chrome works best):

http://localhost:8000

You'll see a big map and a panel on the right side.

## What you're looking at

- The **big map** shows where the drone is in the world.
- The drone is the **orange arrow** on the map. It points the way the drone is facing.
- The **right-side panel** shows numbers like the drone's height and battery.
- The **buttons** in the panel are how you tell the drone what to do.

## Move the map around

- **Slide the map**: click anywhere on the map and drag.
- **Zoom in**: pinch outward on a trackpad, or roll your scroll wheel up.
- **Zoom out**: pinch inward, or roll your scroll wheel down.

## Switch between map styles

There are 3 buttons in the right panel:

- **Hybrid** — shows real photos from above plus street names. This is the default.
- **Map** — shows a clean drawn map with roads. Best for seeing 3D buildings.
- **Satellite** — shows just the photo from above, no labels.

Click any of them to switch.

## See 3D buildings

- Click **Tilt 3D** in the right panel.
- The map will lean over and buildings will rise up like LEGO blocks.
- Click **Tilt 3D** again to flatten the map back down.

Tip: 3D buildings show up best in **Map** view, after you zoom in over a city like San Francisco or New York.

## Spin the map

- Hold the **Shift** key on your keyboard.
- Drag with **two fingers** on a trackpad (or right-click and drag with a mouse).
- The map rotates so you can see your area from any direction.

To put the map back facing north, look for the small compass arrow at the top-right of the map and click it.

## Walk around in Street View

- Look at the **top-right of the map** for a small **orange person icon**. That is "Pegman."
- Click and **drag Pegman** onto a road on the map. Roads glow blue when Pegman can stand there.
- The map turns into a street-level photo. You can look around like you are standing on that street.
- Use the arrows on the road to walk forward.
- Click the **X** in the top corner to come back to the map.

## Tell the drone where to fly

There are two ways: a **planned trip** that follows roads, or a **quick move** to dodge.

### Plan a trip (drone follows roads)

1. In the right panel find the **Navigate (roads)** box.
2. Type a starting address in **From**. As you type, suggestions appear — click one.
3. Type a destination address in **To** and pick a suggestion.
4. Click **Go**.
5. The drone instantly jumps to the From spot, a blue line appears showing the road route, and the drone follows it.
6. When the drone arrives, the blue line disappears.
7. Click **Cancel** at any time to stop.

### Quick move (dodge)

1. Check the box **Click map to move (dodge)** in the right panel.
2. Your mouse cursor turns into a crosshair.
3. Click anywhere on the map.
4. A box pops up asking how high to fly. Type a number like `20` and press OK.
5. The drone flies straight there fast — perfect for getting out of the way.

To stop the dodge mode, uncheck the box.

## Drone command buttons

Above the goto box, there are 4 main buttons:

- **Arm** — wake up the motors. You **must** press this before takeoff.
- **Takeoff (20 m)** — the drone lifts straight up to 20 meters.
- **Land** — the drone comes back down to the ground.
- **Disarm** — turn the motors off. Only works when the drone is on the ground.

Below those is a **Mode** dropdown with three choices:

- **MANUAL** — you tell the drone exactly what to do.
- **AUTO** — the drone follows the goto target you set.
- **RTL** — short for "Return to Launch." The drone flies back to where it took off and lands.

Pick a mode from the dropdown and press **Apply** to switch.

## What the numbers mean

In the right panel:

- **lat / lon** — where the drone is on Earth (its latitude and longitude).
- **alt (rel)** — how high the drone is, in meters above where it took off.
- **heading** — which way it is facing. 0 is north, 90 is east, 180 is south, 270 is west.
- **battery** — how much power is left, in percent.
- **gps** — how many GPS satellites the drone can see. More is better.
- **last cmd ack** — what the drone said about the last button you pressed. `ACCEPTED` means it worked.

## If something goes wrong

- **The map won't load.** Refresh the page (press Cmd-R on Mac or Ctrl-R on Windows).
- **The drone marker doesn't appear.** Wait a few seconds — the drone needs time to start sending its location. If it never shows up, the drone helper program might not be running; ask whoever set this up to check.
- **A button does nothing.** Look at the bottom of the panel for a small status message, or refresh the page.
- **The map is rotated and you're lost.** Hold Shift and drag two fingers to rotate it back, or click the small compass arrow in the top-right of the map.

Have fun flying.
