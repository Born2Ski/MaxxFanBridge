# Touchscreen UI (gui-v2)

## Approach: native switch pane, no GUI modification

Venus OS 3.70+ has a switch pane in the new UI. Any D-Bus service named
`com.victronenergy.switch.*` that exposes `/SwitchableOutput/...` paths gets a card there
automatically, with a control per output chosen by its `Settings/Type`. The driver in
`venus/` publishes one such service per fan, plus one for the presets, so:

- nothing in gui-v2 is patched, and Venus OS updates do not break the UI,
- the same cards appear on the touchscreen, in Remote Console and in VRM,
- names, grouping and visibility can be edited from the GUI and are remembered,
- the values are also reachable from Node-RED, MQTT and Modbus-TCP for automation.

Interactive design at the official display's 800×480:
[MaxxFan switch pane](https://claude.ai/artifact/URemBE8xJgGaqg2khCpj6J) (local copy in
`docs/gui-mockup/project/`; keep both in step).

## Language

`language = nl` under `[gui]` in `config.ini` puts every text the driver supplies in Dutch;
`en` gives English. gui-v2 draws the rest (Aan/Uit on the toggles, menus, the edit mode) in the
language chosen in Venus OS, so set that to Nederlands too. Fan and preset names are whatever
`config.ini` says.

## One card per fan

Open the switch pane with the switch icon in the top bar of the touchscreen.

```
┌──────────────── Keuken ────────────────────┐  ┌────────────────── Bed ─────────────────────┐
│ Ventilator                         [ Aan ] │  │ Ventilator                         [ Uit ] │
│ Snelheid         ───────●────────    60 %  │  │ Snelheid         ──●─────────────    20 %  │
│ Richting                    [ Afzuigen ▾ ] │  │ Richting                    [ Inblazen ▾ ] │
│ Klep open                          [ Aan ] │  │ Klep open                          [ Uit ] │
│ Modus                      [ Handmatig ▾ ] │  │ Modus                    [ Automatisch ▾ ] │
└────────────────────────────────────────────┘  └────────────────────────────────────────────┘
```

| Control (nl / en) | Output key | gui-v2 type | D-Bus value |
|---|---|---|---|
| Ventilator / Fan | `fan` | 1 toggle | `State` 0 / 1 |
| Snelheid / Speed | `speed` | 7 basic slider, 10–100 step 10, unit % | `Dimming` |
| Richting / Direction: Inblazen, Afzuigen | `direction` | 6 dropdown | `Dimming` 0 intake / 1 exhaust |
| Klep open / Lid | `lid` | 1 toggle (Aan = open) | `State` 0 / 1 |
| Modus / Mode: Handmatig, Automatisch | `mode` | 6 dropdown | `Dimming` 0 / 1 |

There is no setpoint control: the controller's keys can nudge the fan's thermostat setpoint
but not set it to a value, so it is left to the fan's own keypad.

How the cards behave:

- **Right after a touch** the card shows the new value. It stays there until the controller
  reports the fan got there; commands go out one at a time, after the controller has been
  quiet for 2 seconds.
- **Not confirmed**: on/off, speed and mode are sent once more after 10 s (direction and lid
  are toggles and never repeated). After 20 s the card shows the controller's last report again.
- **Keypad or remote used**: Ventilator, Snelheid and Modus follow within a second, because the
  controller reports them. Richting is the controller's guess. Klep stays as the driver
  believes it.
- **Klep dicht switches the fan off.** Closing the lid first sends "fan off", then closes it,
  so the fan never runs against a closed lid. "Off" is sent even when the card already shows
  the fan off, in case the keypad started it. **Klep open only opens**: the fan stays as it is.
- **Klep the wrong way round**: press Open/Close on the ceiling keypad or the remote once, so
  the fan matches the card. Tapping the card does not help: it sends a toggle.
- Touching Ventilator, Snelheid, Richting or Klep while the fan is in Automatisch switches it to
  Handmatig first.
- **Disconnected** (greyed out, touches refused) when the controller has sent nothing for
  150 s, or when the driver loses the broker. The fans keep working from their keypads and
  remotes.
- Card title = the fan's name from `config.ini`, changeable in the GUI.

## Presets card: Snelkeuze

A third card sets both fans with one tap. Its buttons and their contents come from the
`[preset …]` sections in `config.ini`:

```
┌───────── Snelkeuze ─────────┐
│ Koken                [ Uit ]│
│ Slapen               [ Uit ]│
│ Rijden               [ Aan ]│     ← lit: the fans are as Rijden set them
│ Standaard            [ Uit ]│
│ Opslaan als         [ — ▾ ] │
└─────────────────────────────┘
```

| Preset | Keuken (fan1) | Bed (fan2) | Idea |
|---|---|---|---|
| Koken | exhaust 80 %, lid open | intake 30 %, lid open | Steam out over the stove, fresh air in at the other end |
| Slapen | exhaust 20 %, lid open | off, lid open | Quiet, slow air change; no motor over the bed |
| Rijden | off, lid closed | off, lid closed | Closed up for the road |
| Standaard | exhaust 40 %, lid open | intake 40 %, lid open | Everyday through-flow |

These are starting points; change them in `config.ini`, or on the screen with *Opslaan als*.

- **One tap** on a preset sends its values to each fan it names, exactly as touching the fan
  cards would, and lights that preset; the others go dark. The fan cards change at once.
- A preset goes **dark again** when someone touches a control of one of its fans, or when, a
  minute after the tap, its fans no longer show its values (keypad, remote, thermostat).
  Tapping a lit preset only darkens it; tap it again to re-apply.
- **Opslaan als** stores what the fan cards show now into the chosen preset, and lights it. The
  menu then goes back to "—". Saved presets live in `presets.json` and win over `config.ini`.
- A fan that is disconnected is left alone; a preset with no reachable fan is refused.
- Rename a preset, or hide *Opslaan als*, in the switch pane's edit mode like any other
  control. Where gui-v2 places the card among the others is up to gui-v2.

Each fan line in a preset is one of: `off` (lid left as it is), `off open`, `off closed`,
`intake 30` / `exhaust 70` (running, lid opens), `auto`, or `keep` (fan not touched; also when
the line is missing). There is no running fan with a closed lid: `exhaust 70 closed` is refused.
These words stay English in `config.ini`.

## Known wrinkles in gui-v2 (from other people's drivers)

- The *stepped switch* (type 4) reports the step index, not the value. That is why speed is a
  basic slider. If the slider misbehaves on your version, set speed to type 2 (dimmer).
- A toggle reads Aan/Uit, not Open/Dicht. That is why the lid control is called "Klep open".

## Optional later: a dedicated fan page

gui-v2 (3.70~45 and later) can load extra QML pages from `/data/apps/`, attached to a device
under Settings → Devices. That would allow a purpose-made page: big direction arrows, a lid
graphic, the ceiling temperature. Reasons it is not in v1:

- Victron marks the plugin mechanism as not officially released, and the API may change.
- Plugin pages load on the local touchscreen only, not in Remote Console or VRM.
- It sits several taps deep in Settings, while the switch pane is one tap from anywhere.

The page would only read and write the same D-Bus paths, so it can be added later without
changing the driver.

## Automation ideas that come for free

- Node-RED on the Venus device: close both lids when the vehicle moves or when a rain sensor trips.
- Run a fan on exhaust while the battery is above a state of charge and the inside is warm.
- Tie the Keuken fan to an induction hob's load.
