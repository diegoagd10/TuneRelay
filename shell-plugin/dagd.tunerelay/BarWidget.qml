import QtQuick
import qs.Ui
import "Strings.js" as Strings

// Bar icon with the review count; ⟳ while anything is downloading,
// processing or in transit. Click toggles the TuneRelay window.
BarWidget {
  id: root
  moduleName: "dagd.tunerelay"

  readonly property var service: bar && bar.shell ? bar.shell.serviceFor(moduleName) : null
  readonly property int reviewCount: service ? service.reviewCount : 0
  readonly property bool busy: service ? service.busy : false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: Strings.barIcon
      + (root.reviewCount > 0 ? " " + root.reviewCount : "")
      + (root.busy ? " " + Strings.busyIcon : "")
    active: root.reviewCount > 0
    tooltipText: Strings.appName
    onPressed: function(mouseButton) {
      if (root.bar) root.bar.run("omarchy-shell shell toggle dagd.tunerelay")
    }
  }
}
