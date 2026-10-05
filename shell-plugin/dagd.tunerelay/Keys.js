// The TuneRelay window's keyboard map. A key press becomes a command name and
// the overlay runs it, so the map can be tested without the window.
//
// Navigate mode: no text field has focus, single keys are commands.
// Edit mode: a field has focus and gets every key except the few in `editing`.
// No binding uses Super: Hyprland's global bindings live there and win anyway.
.pragma library

var tabs = ["review", "queue", "history"]

// Only these modifiers change a binding (keypad Enter carries KeypadModifier).
function modifiers(event) {
  return event.modifiers & (Qt.ShiftModifier | Qt.ControlModifier | Qt.AltModifier | Qt.MetaModifier)
}

function isEnter(key) { return key === Qt.Key_Return || key === Qt.Key_Enter }

// Keys that work in both modes.
function common(key, mods) {
  if (isEnter(key) && mods === Qt.ControlModifier) return "confirm"
  if (isEnter(key) && mods === (Qt.ControlModifier | Qt.ShiftModifier)) return "replace"
  return ""
}

function editing(event) {
  var mods = modifiers(event)
  if (event.key === Qt.Key_Escape && mods === 0) return "leave"
  return common(event.key, mods)
}

var reviewKeys = {}
reviewKeys[Qt.Key_J] = "song-next"
reviewKeys[Qt.Key_Down] = "song-next"
reviewKeys[Qt.Key_K] = "song-previous"
reviewKeys[Qt.Key_Up] = "song-previous"
reviewKeys[Qt.Key_1] = "proposal-0"
reviewKeys[Qt.Key_2] = "proposal-1"
reviewKeys[Qt.Key_3] = "proposal-2"
reviewKeys[Qt.Key_4] = "proposal-3"
reviewKeys[Qt.Key_E] = "edit"
reviewKeys[Qt.Key_I] = "edit"
reviewKeys[Qt.Key_C] = "compilation"
reviewKeys[Qt.Key_T] = "thumbnail"
reviewKeys[Qt.Key_P] = "preview"
reviewKeys[Qt.Key_O] = "youtube"

var queueKeys = {}
queueKeys[Qt.Key_J] = "line-down"
queueKeys[Qt.Key_Down] = "line-down"
queueKeys[Qt.Key_K] = "line-up"
queueKeys[Qt.Key_Up] = "line-up"

var historyKeys = {}
historyKeys[Qt.Key_J] = "row-next"
historyKeys[Qt.Key_Down] = "row-next"
historyKeys[Qt.Key_K] = "row-previous"
historyKeys[Qt.Key_Up] = "row-previous"
historyKeys[Qt.Key_Slash] = "search"
historyKeys[Qt.Key_F] = "filter"
historyKeys[Qt.Key_O] = "youtube"
historyKeys[Qt.Key_Return] = "youtube"
historyKeys[Qt.Key_Enter] = "youtube"
historyKeys[Qt.Key_R] = "retry"

var plainKeys = { review: reviewKeys, queue: queueKeys, history: historyKeys }

// The command for a key press in navigate mode on `tab`, or "" if the key is not bound.
function navigate(tab, event) {
  var key = event.key
  var mods = modifiers(event)
  var shared = common(key, mods)
  if (shared) return shared
  if (key === Qt.Key_Escape && mods === 0) return "close"
  if (key === Qt.Key_Question && (mods === 0 || mods === Qt.ShiftModifier)) return "help"
  if (mods === Qt.AltModifier && key >= Qt.Key_1 && key < Qt.Key_1 + tabs.length) return "tab-" + tabs[key - Qt.Key_1]
  if (key === Qt.Key_Tab && mods === Qt.ControlModifier) return "tab-next"
  if ((key === Qt.Key_Backtab || key === Qt.Key_Tab) && mods === (Qt.ControlModifier | Qt.ShiftModifier)) return "tab-previous"
  if (key === Qt.Key_PageDown && mods === 0) return "page-down"
  if (key === Qt.Key_PageUp && mods === 0) return "page-up"
  if (tab === "review" && key === Qt.Key_D && mods === Qt.ShiftModifier) return "discard"
  if (mods !== 0) return ""
  return plainKeys[tab][key] || ""
}
