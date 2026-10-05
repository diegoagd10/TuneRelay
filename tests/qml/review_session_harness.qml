import QtQuick
import "../../shell-plugin/dagd.tunerelay"

// Drives the plugin's ReviewSession (the overlay's model) against a fake
// Service.run whose responses are held until `deliver()` releases the oldest,
// so a test controls exactly when late answers arrive. Prints: RESULT <json log>.
Item {
  id: root

  property var pending: []
  property var log: []

  function record(entry) { root.log = root.log.concat([entry]) }

  function run(args, ok, fail) {
    root.pending = root.pending.concat([{ args: args, ok: ok }])
  }

  function respond(args) {
    var id = Number(args[1])
    if (args[0] === "show") return { id: id, state: "ready_for_review", draft: { track: "1" } }
    if (args[0] === "select") return { id: id, state: "ready_for_review", draft: { track: "proposal " + args[2] } }
    if (args[0] === "confirm") return { id: id, state: "in_transit", draft: { track: "1" } }
    if (args[0] === "cover") return { id: id, state: "ready_for_review", draft: { track: "1", cover: "new" } }
    if (args[0] === "edit") return { id: id, state: "ready_for_review", draft: { track: args[2].split("=")[1] } }
    return { id: id }
  }

  function deliver() {
    var job = root.pending[0]
    root.pending = root.pending.slice(1)
    if (job.args[0] !== "show") root.record("cli " + job.args.join(" "))
    if (job.ok) job.ok(root.respond(job.args))
  }

  function shown() {
    return "selected=" + session.songId + " form=" + (session.song ? session.song.id : "none")
  }

  ReviewSession {
    id: session
    run: root.run
  }

  function open(id) {
    session.selectSong(id)
    session.load()
    root.deliver()
  }

  Component.onCompleted: {
    // 1. A late `show` for the previous song must not take over the form.
    session.selectSong(3); session.load()
    session.selectSong(5); session.load()
    root.deliver()                                    // show 3 arrives while 5 is selected
    root.record("late show: " + root.shown())
    root.deliver()                                    // show 5
    session.reviewed("confirm"); root.deliver()
    root.record("---")

    // 2. A late proposal selection for the previous song is dropped too.
    root.open(5)
    session.selectProposal(1)
    session.selectSong(3); session.load()
    root.deliver()                                    // select 5 1 arrives while 3 is selected
    root.record("late select: " + root.shown())
    root.deliver()                                    // show 3
    session.reviewed("confirm"); root.deliver()
    root.record("---")

    // 3. Same for a late cover change.
    root.open(7)
    session.act(["cover", "--thumbnail"])
    session.selectSong(3); session.load()
    root.deliver()
    root.record("late cover: " + root.shown())
    root.deliver()
    root.record("---")

    // 4. Nothing can be confirmed before the selected song has loaded.
    session.selectSong(8); session.load()
    session.reviewed("confirm")
    root.record("queued before load: " + root.pending.length)
    root.deliver()
    root.record("---")

    // 5. A Confirm waiting on an edit is dropped when the user switches songs.
    root.open(9)
    session.edit("track", "4")
    session.reviewed("confirm")
    session.selectSong(3); session.load()
    root.deliver()                                    // the edit of song 9 is answered
    root.deliver()                                    // show 3
    root.record("pending after switch: " + root.pending.length + " " + root.shown())

    console.warn("RESULT " + JSON.stringify(root.log))
    Qt.quit()
  }
}
