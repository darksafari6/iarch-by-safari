// Copyright (C) 2026 Safari — GPL-3.0-or-later
// Accepts a validated token projection from the guarded theme bridge.
import QtQuick
import "." as Runtime
import "projection.js" as Projection
import "registry.js" as Registry

QtObject {
    id: root
    property bool ready: false
    property string error: ""
    property string activeId: ""
    property var surfaceRegistry: null
    signal transitionRequested(string style, color previousBackground)

    function acceptProjection(candidate, noTransition) {
        if (!Projection.validate(candidate)) {
            error = "invalid theme projection"
            return false
        }
        // The entire object changes together; external callers cannot mutate it.
        let copied = JSON.parse(JSON.stringify(candidate))
        let previous = Runtime.Theme.background
        let wasReady = ready
        Runtime.Theme.suppressTransitions = noTransition === true
        Runtime.Theme.tokens = copied
        Runtime.Theme.suppressTransitions = false
        activeId = copied.id
        ready = true
        error = ""
        if (wasReady && noTransition !== true && copied.transition !== "none" && Runtime.Theme.animationsEnabled)
            transitionRequested(copied.transition, previous)
        return true
    }

    // Check both parts before either object is modified. A bundle is produced by
    // shell_projection.py; this is not a substitute for pack validation.
    function validBundle(bundle) {
        if (!bundle || typeof bundle !== "object" || Array.isArray(bundle) ||
                Object.keys(bundle).length !== 3 || bundle.schema_version !== 1 ||
                !Object.prototype.hasOwnProperty.call(bundle, "theme") ||
                !Object.prototype.hasOwnProperty.call(bundle, "surfaces") ||
                !surfaceRegistry || !Projection.validate(bundle.theme) ||
                Registry.configure(bundle.surfaces) === null) {
            return false
        }
        return true
    }

    function acceptBundle(bundle, noTransition) {
        if (!validBundle(bundle)) {
            error = "invalid theme bundle"
            return false
        }
        let copied = JSON.parse(JSON.stringify(bundle))
        surfaceRegistry.configure(copied.surfaces)
        return acceptProjection(copied.theme, noTransition)
    }

}
