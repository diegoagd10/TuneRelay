import QtQuick

// The song under review and its draft, independent of the view. The overlay
// renders `song` and calls these functions; everything goes through `run`.
//
// Ownership rule: CLI answers can arrive late (the service runs one command at
// a time), so a response may only replace the form if it is for the song that
// is selected *now*. Anything for a previously selected song is dropped, and
// actions always target the selected song, never a stale `song` object.
QtObject {
  id: session

  // function(args, onSuccess(result), onFailure(result)) — the CLI runner.
  property var run: null
  property int songId: -1
  property var song: null
  readonly property bool loaded: session.song !== null && session.song.id === session.songId

  signal blocked()

  property EditGate gate: EditGate {
    run: session.run
    onEdited: function(result) { session.accept(result) }
    onBlocked: session.blocked()
  }

  // Replace the form with `result` if it belongs to the selected song.
  function accept(result) {
    if (!result || result.id !== session.songId) return false
    var replaced = !session.loaded
    session.song = result
    if (replaced) session.gate.draftReplaced(result.id)
    return true
  }

  function selectSong(id) {
    if (id === session.songId) return
    session.songId = id
    session.song = null
    session.gate.draftReplaced(id)
  }

  function load() {
    if (session.songId < 0) {
      session.song = null
      return
    }
    session.run(["show", String(session.songId)], session.accept)
  }

  // A proposal becomes the draft: always restore the editors, even if values are equal.
  function selectProposal(index) {
    if (!session.loaded) return
    session.run(["select", String(session.songId), String(index)], function(result) {
      if (result.id !== session.songId) return
      session.song = result
      session.gate.draftReplaced(result.id)
    })
  }

  function preview() {
    if (session.loaded) session.run(["preview", String(session.songId)])
  }

  // An action on the selected song whose answer is that song (cover, discard).
  function act(args) {
    if (!session.loaded) return
    session.run([args[0], String(session.songId)].concat(args.slice(1)), session.accept)
  }

  // Confirm / Replace: only once the reviewed edits are applied and none was rejected,
  // and only for the song that was selected when the user asked.
  function reviewed(command) {
    if (!session.loaded) return
    var id = session.songId
    session.gate.afterEdits(function() {
      if (session.songId !== id) return
      session.run([command, String(id)], session.accept)
    })
  }

  function edit(field, value) {
    if (!session.loaded || !session.song.draft) return
    var draft = session.song.draft
    var current = draft[field]
    if (field === "artists") current = (current || []).join("; ")
    if (field.indexOf("mbid_") === 0) current = (draft.mbids || {})[field.slice(5)]
    var same = String(current === null || current === undefined ? "" : current) === String(value)
    if (same && !session.gate.isInvalid(field)) return
    session.gate.edit(session.songId, field, value)
  }
}
