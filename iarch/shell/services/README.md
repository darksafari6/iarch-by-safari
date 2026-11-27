# Dynamic shell services

## Purpose

Adapters expose session data and guarded requests to the dynamic shell.

## Inputs

Local system tools, validated state and Quickshell service models.

## Outputs

Live properties, bounded persistent state and explicit request signals.
Most adapters are active only when a consumer needs them. See
`docs/SHELL-SERVICES.md` for dependencies, failure behavior and verification.
No live integration is claimed; the dynamic session remains guarded.
