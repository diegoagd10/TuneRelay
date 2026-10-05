import QtQuick
import "../../shell-plugin/dagd.tunerelay"

// Drives the plugin's EditGate the way Overlay.qml does, against an asynchronous
// FIFO fake of Service.run + `tunerelay edit` (non-numeric tracks are rejected).
// Prints one line: RESULT <json log>.
Item {
  id: root

  property var drafts: ({ "1": { track: "1" }, "2": { track: "2" } })
  property int songId: 1
  readonly property string savedTrack: root.drafts[String(root.songId)].track
  property var log: []
  property var queue: []

  function record(entry) { root.log = root.log.concat([entry]) }

  function run(args, ok, fail) {
    root.queue = root.queue.concat([{ args: args, ok: ok, fail: fail }])
    if (!pump.running) pump.start()
  }

  Timer {
    id: pump
    interval: 10
    onTriggered: {
      var job = root.queue[0]
      root.queue = root.queue.slice(1)
      var kv = job.args[2].split("=")
      if (/^[0-9]+$/.test(kv[1])) {
        var next = JSON.parse(JSON.stringify(root.drafts))
        next[job.args[1]][kv[0]] = kv[1]
        root.drafts = next
        job.ok({ id: Number(job.args[1]) })
      } else {
        job.fail({ error: "track must be a whole number" })
      }
      if (root.queue.length > 0) pump.start()
    }
  }

  EditGate {
    id: gate
    run: root.run
    onBlocked: root.record("blocked " + root.songId)
  }

  // Same wiring as Overlay.qml's Field: typing breaks the binding; restore on replacement.
  TextInput {
    id: track
    text: root.savedTrack
    Connections {
      target: gate
      function onRestore() { track.text = root.savedTrack }
    }
  }

  function typeAndCommit(value) {
    track.text = value
    gate.edit(root.songId, "track", value)
  }

  function confirm() {
    var id = root.songId
    gate.afterEdits(function() {
      root.record("confirm " + id + " saved=" + root.drafts[String(id)].track + " shown=" + track.text)
    })
  }

  // Overlay.selectSong + showSong, and a proposal (re)selection.
  function switchSong(id) {
    root.songId = id
    gate.draftReplaced(id)
  }

  function reselectProposal() { gate.draftReplaced(root.songId) }

  property int step: 0
  property var steps: [
    function() { root.typeAndCommit("n"); root.confirm() },          // rejected -> blocked
    function() { root.switchSong(2); root.confirm() },               // other song is not blocked
    function() { root.switchSong(1); root.typeAndCommit("n"); root.confirm() },
    function() { root.reselectProposal(); root.record("after reselect shown=" + track.text); root.confirm() },
    function() { root.typeAndCommit("x"); root.switchSong(2) },      // answer arrives after the switch
    function() { root.confirm() },                                   // stale rejection must not block song 2
    function() { console.warn("RESULT " + JSON.stringify(root.log)); Qt.quit() }
  ]

  Timer {
    interval: 80
    repeat: true
    running: true
    onTriggered: {
      root.steps[root.step]()
      root.step += 1
    }
  }
}
