import QtQuick

// Orders draft edits before the actions that depend on the reviewed draft
// (Confirm, Replace). An action waits until every pending edit has been
// answered, and only runs if none of them was rejected; a rejected field stays
// invalid until a later edit of that field succeeds or the draft is reset.
QtObject {
  id: gate

  // function(args, onSuccess(result), onFailure(result)) — the CLI runner.
  property var run: null
  property int pending: 0
  property var invalid: ({})
  property var waiting: []
  readonly property bool hasInvalid: Object.keys(invalid).length > 0

  signal edited(var song)
  signal blocked()

  function isInvalid(field) { return gate.invalid[field] === true }

  function setInvalid(field, value) {
    var next = ({})
    for (var key in gate.invalid) if (key !== field) next[key] = true
    if (value) next[field] = true
    gate.invalid = next
  }

  // The draft was replaced (another proposal or song): old field errors no longer apply.
  function reset() {
    gate.invalid = ({})
  }

  function edit(songId, field, value) {
    gate.pending += 1
    gate.run(["edit", String(songId), field + "=" + value],
      function(result) {
        gate.setInvalid(field, false)
        gate.edited(result)
        gate.settle()
      },
      function() {
        gate.setInvalid(field, true)
        gate.settle()
      })
  }

  function settle() {
    gate.pending -= 1
    if (gate.pending > 0) return
    var queued = gate.waiting
    gate.waiting = []
    if (queued.length === 0) return
    if (gate.hasInvalid) {
      gate.blocked()
      return
    }
    for (var i = 0; i < queued.length; i++) queued[i]()
  }

  // Run `action` once every pending edit is applied, and only if none was rejected.
  function afterEdits(action) {
    if (gate.pending > 0) {
      gate.waiting = gate.waiting.concat([action])
      return
    }
    if (gate.hasInvalid) {
      gate.blocked()
      return
    }
    action()
  }
}
