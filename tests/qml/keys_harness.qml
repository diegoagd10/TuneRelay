import QtQuick
import "../../shell-plugin/dagd.tunerelay/Keys.js" as KeyMap

// Feeds key presses to the plugin's keyboard map (Keys.js) and prints the
// command for each one. Prints: RESULT <json log>.
Item {
  function press(key, modifiers) { return { key: key, modifiers: modifiers || 0 } }

  Component.onCompleted: {
    var log = []
    var navigate = [
      ["review", Qt.Key_Escape, 0],
      ["review", Qt.Key_J, 0],
      ["review", Qt.Key_Down, 0],
      ["review", Qt.Key_K, 0],
      ["review", Qt.Key_2, 0],
      ["review", Qt.Key_5, 0],
      ["review", Qt.Key_E, 0],
      ["review", Qt.Key_D, 0],
      ["review", Qt.Key_D, Qt.ShiftModifier],
      ["review", Qt.Key_Return, Qt.ControlModifier],
      ["review", Qt.Key_Enter, Qt.ControlModifier | Qt.KeypadModifier],
      ["review", Qt.Key_Return, Qt.ControlModifier | Qt.ShiftModifier],
      ["review", Qt.Key_Return, 0],
      ["review", Qt.Key_J, Qt.ControlModifier],
      ["review", Qt.Key_J, Qt.MetaModifier],
      ["review", Qt.Key_3, Qt.AltModifier],
      ["review", Qt.Key_4, Qt.AltModifier],
      ["review", Qt.Key_Tab, Qt.ControlModifier],
      ["review", Qt.Key_Backtab, Qt.ControlModifier | Qt.ShiftModifier],
      ["review", Qt.Key_Question, Qt.ShiftModifier],
      ["review", Qt.Key_PageDown, 0],
      ["queue", Qt.Key_J, 0],
      ["queue", Qt.Key_D, Qt.ShiftModifier],
      ["history", Qt.Key_J, 0],
      ["history", Qt.Key_Slash, 0],
      ["history", Qt.Key_F, 0],
      ["history", Qt.Key_Return, 0],
      ["history", Qt.Key_R, 0]
    ]
    for (var i = 0; i < navigate.length; i++) {
      var n = navigate[i]
      log.push(n[0] + " " + i + "=" + KeyMap.navigate(n[0], press(n[1], n[2])))
    }
    log.push("edit esc=" + KeyMap.editing(press(Qt.Key_Escape)))
    log.push("edit ctrl+enter=" + KeyMap.editing(press(Qt.Key_Return, Qt.ControlModifier)))
    log.push("edit j=" + KeyMap.editing(press(Qt.Key_J)))
    log.push("edit enter=" + KeyMap.editing(press(Qt.Key_Return)))
    console.log("RESULT " + JSON.stringify(log))
    Qt.quit()
  }
}
