# Pure QtQuick components

## Purpose

Reusable theme-aware controls for the planned dynamic shell.

## Inputs

The shared Theme defaults, caller-provided data and user interaction.

## Outputs

Controls and signals. They do not call shell services or fetch network data.
The gallery and live theme binding are not implemented yet.

`WorkspaceIndicator.qml` is a pure view of ten workspace states with dots,
bubbles and pill-group styles. It emits requests for the embedding adapter to
validate; it does not itself contact the compositor. Wheel and middle-click,
keyboard behavior and visuals remain UNTESTED-LIVE.
