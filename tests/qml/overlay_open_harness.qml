import QtQuick
import Quickshell

// Follow the shell panel loader's injection order before delivering open().
// Loading the real overlay catches host-contract failures that prevent its
// window from opening even though the bar widget is already visible.
ShellRoot {
  id: root

  property var log: []

  QtObject {
    id: service
    property var status: ({ review_songs: [], queue: [] })
    function run(args, callback) { callback({ songs: [] }) }
  }

  QtObject {
    id: shell
    function serviceFor(pluginId) { return service }
  }

  Loader {
    source: Quickshell.env("TUNERELAY_TEST_OVERLAY")
    onStatusChanged: {
      if (status === Loader.Error) {
        console.log("RESULT " + JSON.stringify(["overlay failed to load"]))
      }
    }
    onLoaded: {
      try {
        item.shell = shell
        item.manifest = { id: "dagd.tunerelay" }
        item.service = shell.serviceFor(item.manifest.id)
        item.open("{}")
        root.log.push("opened=" + item.opened)
        root.log.push("service injected=" + (item.service === service))
        item.command("tab-next")
        root.log.push("tab=" + item.tab)
        item.command("tab-previous")
        item.command("tab-previous")
        root.log.push("tab=" + item.tab)
        item.command("help")
        root.log.push("hints=" + item.showHints)
        item.command("song-next")
        item.command("discard")
        root.log.push("no song, no error")
        item.close()
        root.log.push("closed=" + item.opened)
      } catch (error) {
        root.log.push("error: " + error)
      }
      console.log("RESULT " + JSON.stringify(root.log))
    }
  }
}
