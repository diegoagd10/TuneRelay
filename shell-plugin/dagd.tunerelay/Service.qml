import QtQuick
import Quickshell
import Quickshell.Io

// Holds TuneRelay's state for the bar widget and the overlay. It keeps one
// `tunerelay watch` process open (one JSON status line per change) and runs
// every other CLI command through a single queue.
Item {
  id: root
  visible: false

  property var shell: null
  property var settings: ({})

  readonly property string cli: (Quickshell.env("HOME") || "") + "/.local/bin/tunerelay"
  property var status: ({ version: 0, review: 0, busy: false, review_songs: [], queue: [], counts: {} })
  readonly property int reviewCount: status.review || 0
  readonly property bool busy: status.busy === true

  Process {
    id: watcher
    command: [root.cli, "watch"]
    running: true
    stdout: SplitParser {
      onRead: function(line) {
        try {
          root.status = JSON.parse(line)
        } catch (e) {
          console.warn("tunerelay watch: bad line", line)
        }
      }
    }
    onExited: restart.start()
  }

  // The CLI may be missing until install.sh runs; keep trying.
  Timer {
    id: restart
    interval: 5000
    onTriggered: watcher.running = true
  }

  property var jobs: []
  property var currentJob: null

  // Run `tunerelay <args>`; `callback(result)` gets the parsed JSON (with an
  // `error` key on failure) or null when the output was not JSON.
  function run(args, callback) {
    jobs.push({ args: args, callback: callback || null })
    if (!runner.running && currentJob === null) next()
  }

  function next() {
    if (jobs.length === 0) return
    currentJob = jobs.shift()
    runner.command = [root.cli].concat(currentJob.args)
    runner.running = true
  }

  function finish(text) {
    var job = currentJob
    currentJob = null
    var result = null
    try { result = JSON.parse(text) } catch (e) { result = null }
    if (job && job.callback) {
      try { job.callback(result) } catch (e) { console.warn("tunerelay callback threw:", e) }
    }
    next()
  }

  Process {
    id: runner
    running: false
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: root.finish(text)
    }
  }
}
