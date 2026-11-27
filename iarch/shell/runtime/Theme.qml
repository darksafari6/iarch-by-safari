// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Safe defaults. Validated projections replace the single token object.
pragma Singleton
import QtQuick
import "quality.js" as Quality

QtObject {
    id: root
    // Repository-relative sources; fall back to system fonts if assets are absent.
    property FontLoader bundledUi: FontLoader { source: "../assets/fonts/ui/regular.ttf" }
    property FontLoader bundledMono: FontLoader { source: "../assets/fonts/mono/regular.ttf" }
    property FontLoader bundledDisplay: FontLoader { source: "../assets/fonts/display/regular.ttf" }
    property FontLoader bundledRounded: FontLoader { source: "../assets/fonts/rounded/regular.ttf" }
    property var tokens: ({
        id: "safe-defaults",
        palette: {background: "#101211", surface: "#1b201d", text: "#edf3ee",
                  accent: "#8fcb6a", onAccent: "#10200c", secondary: "#c6e6a0",
                  error: "#e08a7a", outline: "#5c7456"},
        radius: {small: 8, medium: 12, large: 20},
        spacing: {small: 4, medium: 8, large: 16},
        fonts: {ui: "sans-serif", display: "sans-serif", mono: "monospace"},
        motion: {fast: 120, normal: 220, slow: 380},
        shape: {radius: {none: 0, xs: 4, sm: 8, md: 12, lg: 16, xl: 24, pill: 999},
                components: {window: "md", panel: "lg", card: "md", button: "sm", input: "sm", tooltip: "xs", chip: "pill", "osk-key": "sm"},
                chamfer: 0, border_width: 1, border_style: "solid"},
        easing: "InOutCubic", transition: "fade",
        surfaceMotion: {bar: {duration: "normal", style: "fade"}, overview: {duration: "normal", style: "fade"},
                        "sidebar-right": {duration: "normal", style: "fade"}, "sidebar-left": {duration: "normal", style: "fade"},
                        dock: {duration: "normal", style: "fade"}, osk: {duration: "normal", style: "fade"}},
        variants: {bar: "default", overview: "default", "sidebar-right": "default", "sidebar-left": "default", dock: "default", osk: "default"},
        sounds: {notification: {enabled: false, volume: 0}, volume: {enabled: false, volume: 0}, switch: {enabled: false, volume: 0}},
        surfaceStyle: "solid", quality: "balanced", reduceMotion: false
    })
    // Writable properties are required by QML Behavior; token bindings remain
    // the source of their targets. Callers should treat them as read-only.
    property color background: tokens.palette.background
    property color surface: tokens.palette.surface
    property color text: tokens.palette.text
    property color accent: tokens.palette.accent
    // A property named onAccent collides with QML's on<property> syntax when
    // accent also exists. Keep the public QML name distinct from the JSON key.
    property color accentForeground: tokens.palette.onAccent
    property color secondary: tokens.palette.secondary
    property color error: tokens.palette.error
    property color outline: tokens.palette.outline
    readonly property int colorTransitionDuration: animationsEnabled && !suppressTransitions ? 300 : 0
    Behavior on background { ColorAnimation { duration: root.colorTransitionDuration } }
    Behavior on surface { ColorAnimation { duration: root.colorTransitionDuration } }
    Behavior on text { ColorAnimation { duration: root.colorTransitionDuration } }
    Behavior on accent { ColorAnimation { duration: root.colorTransitionDuration } }
    Behavior on accentForeground { ColorAnimation { duration: root.colorTransitionDuration } }
    Behavior on secondary { ColorAnimation { duration: root.colorTransitionDuration } }
    Behavior on error { ColorAnimation { duration: root.colorTransitionDuration } }
    Behavior on outline { ColorAnimation { duration: root.colorTransitionDuration } }
    readonly property var shape: tokens.shape
    readonly property int chamfer: tokens.shape.chamfer
    readonly property int borderWidth: tokens.shape.border_width
    readonly property string borderStyle: tokens.shape.border_style
    readonly property var variants: tokens.variants
    readonly property var soundEvents: tokens.sounds
    readonly property var surfaceMotion: tokens.surfaceMotion
    readonly property string transition: tokens.transition
    readonly property int easing: tokens.easing === "Linear" ? Easing.Linear :
                                  tokens.easing === "OutCubic" ? Easing.OutCubic :
                                  tokens.easing === "InOutQuad" ? Easing.InOutQuad : Easing.InOutCubic
    readonly property int radiusSmall: tokens.radius.small
    readonly property int radiusMedium: tokens.radius.medium
    readonly property int radiusLarge: tokens.radius.large
    readonly property int spacingSmall: tokens.spacing.small
    readonly property int spacingMedium: tokens.spacing.medium
    readonly property int spacingLarge: tokens.spacing.large
    readonly property int durationFast: Math.round(tokens.motion.fast * animationScale)
    readonly property int durationNormal: Math.round(tokens.motion.normal * animationScale)
    // FontLoader registers bundled families for the process. Prefer an installed
    // requested family; use the bundled equivalent when it is unavailable.
    function fontFamily(preferred, loader, fallback) {
        if (typeof preferred === "string" && preferred &&
            ["sans-serif", "serif", "monospace"].indexOf(preferred.toLowerCase()) < 0 &&
            Qt.fontFamilies().some(function(family) { return family.toLowerCase() === preferred.toLowerCase() })) return preferred
        return loader.status === FontLoader.Ready && loader.name ? loader.name : fallback
    }
    readonly property string fontUi: fontFamily(tokens.fonts.ui, bundledUi, "sans-serif")
    readonly property string fontMono: fontFamily(tokens.fonts.mono, bundledMono, "monospace")
    readonly property string fontDisplay: fontFamily(tokens.fonts.display, bundledDisplay, "sans-serif")
    // Adapters own these live inputs; changing them never overwrites preference.
    property bool suppressTransitions: false
    property bool gameMode: false
    property bool lowBattery: false
    property bool systemReduceMotion: false
    readonly property var qualityPolicy: Quality.resolve(tokens.quality, gameMode, lowBattery)
    readonly property string quality: qualityPolicy.level
    readonly property bool blurEnabled: qualityPolicy.blur
    readonly property bool shadowsEnabled: qualityPolicy.shadows
    readonly property bool shadersEnabled: qualityPolicy.shaders
    readonly property int spectrumFps: qualityPolicy.spectrumFps
    readonly property real animationScale: qualityPolicy.animationScale
    // The accessibility preference always wins over a pack's setting.
    readonly property bool reduceMotion: tokens.reduceMotion || systemReduceMotion
    readonly property bool animationsEnabled: !reduceMotion && quality !== "low"
}
