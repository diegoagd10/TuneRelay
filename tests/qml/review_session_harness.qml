import QtQuick
import "../../shell-plugin/dagd.tunerelay"

// Drives the plugin's ReviewSession (the overlay's model) against a fake
// Service.run whose responses are held until `deliver()` releases the oldest,
// so a test controls exactly when late answers arrive. Like the real CLI, the
// fake applies each command to a saved draft per song when it is delivered.
// Prints: RESULT <json log>.
Item {
  id: root

  property var pending: []
  property var log: []
  property var saved: ({})
  property bool failNext: false

  function record(entry) { root.log = root.log.concat([entry]) }

  function run(args, ok, fail) {
    root.pending = root.pending.concat([{ args: args, ok: ok, fail: fail }])
  }

  function track(id) {
    return root.saved[id] === undefined ? "1" : root.saved[id]
  }

  // Apply a command to the saved draft and answer with the song, as the CLI does.
  function respond(args) {
    var id = Number(args[1])
    var next = JSON.parse(JSON.stringify(root.saved))
    if (args[0] === "select") next[id] = "proposal " + args[2]
    if (args[0] === "edit") next[id] = args[2].split("=")[1]
    root.saved = next
    var state = args[0] === "confirm" ? "in_transit" : "ready_for_review"
    return { id: id, state: state, draft: { track: root.track(id) } }
  }

  function deliver() {
    var job = root.pending[0]
    root.pending = root.pending.slice(1)
    if (job.args[0] !== "show") root.record("cli " + job.args.join(" "))
    if (root.failNext) {
      root.failNext = false
      if (job.fail) job.fail({ error: "rejected" })
      return
    }
    var result = root.respond(job.args)
    if (job.args[0] === "confirm") root.record("confirmed saved=" + root.track(result.id) + " shown=" + root.shownTrack)
    if (job.ok) job.ok(result)
  }

  property string shownTrack: session.song && session.song.draft ? session.song.draft.track : ""

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

  function scenarios() {
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
    root.record("---")

    // 6. Same song: an edit typed while a proposal selection is pending must not
    //    end up confirmed behind a form that shows something else.
    root.open(11)
    session.selectProposal(0)
    session.edit("track", "4")
    root.record("queued while selecting: " + root.pending.length)
    root.deliver()                                    // select 11 0
    session.reviewed("confirm")
    root.deliver()
    root.record("---")

    // 7. A failed proposal selection unlocks the form again.
    root.open(12)
    session.selectProposal(2)
    root.failNext = true
    root.deliver()
    session.edit("track", "6")
    root.deliver()
    session.reviewed("confirm")
    root.deliver()

  }

  // Always report and quit, so a script error fails the test instead of hanging it.
  Component.onCompleted: {
    try {
      root.scenarios()
    } catch (error) {
      root.record("ERROR " + error)
    }
    console.warn("RESULT " + JSON.stringify(root.log))
    Qt.quit()
  }
}
