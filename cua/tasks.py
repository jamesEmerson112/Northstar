"""Pre-canned demo task strings for the drone dashboard.

The more explicit the instruction, the more reliable the run. The dashboard's
button/input labels are referenced verbatim so Northstar can grep for them.
"""

DEMO_TAKEOFF_LAND = (
    "Click the button labelled 'Arm'. Then click the button labelled "
    "'Takeoff (20 m)'. Wait until the altitude indicator in the right panel "
    "shows about 20 meters. Then click 'Land'. When the panel says "
    "'armed: no' and the drone has landed, call the done function."
)

DEMO_SF_TOUR = (
    "Click 'Arm' then 'Takeoff (20 m)' to get the drone airborne. "
    "In the 'Navigate (roads)' section, click the input labelled "
    "'From address' and type '1 Dr Carlton B Goodlett Place San Francisco'. "
    "Pick the first autocomplete suggestion. Then click the input labelled "
    "'To address' and type 'Pier 39 San Francisco'. Pick the first suggestion. "
    "Click 'Go'. Watch the blue route appear and the drone follow the streets. "
    "When the drone has arrived (the blue line disappears), call the done "
    "function."
)

DEMO_STREET_VIEW = (
    "Look at the top right of the map for a small orange person icon called "
    "Pegman. Drag Pegman onto a road in the city. The map will switch to "
    "Street View. Look around using the on-screen arrows for about 5 seconds. "
    "Then click the X button in the top corner to exit Street View. Call the "
    "done function once the map is back."
)


ALL = {
    "takeoff-land": DEMO_TAKEOFF_LAND,
    "sf-tour": DEMO_SF_TOUR,
    "street-view": DEMO_STREET_VIEW,
}
