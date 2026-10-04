// Every user-facing string of the TuneRelay plugin, in English.
.pragma library

var appName = "TuneRelay"
var barIcon = "󰎆"
var busyIcon = "⟳"

var tabs = { review: "Review", queue: "Queue", history: "History" }

var waiting = function(count) { return "Waiting (" + count + ")" }
var nothingToReview = "Nothing waiting for review."
var queueEmpty = "Nothing in flight."
var historyEmpty = "No songs match."
var youtube = "YouTube"
var defaultProposal = "YouTube (default)"
var codexProposal = function(confidence) { return "Codex " + Number(confidence).toFixed(2) }
var noSources = "—"
var conflict = "Already exists in Navidrome"
var conflictHint = "Replace the file on the server, or discard this song."

var fields = {
  title: "Title",
  artist: "Artist",
  artists: "Artists",
  album: "Album",
  album_artist: "Album artist",
  track: "Track",
  disc: "Disc",
  year: "Year",
  genre: "Genre",
  compilation: "Compilation"
}
var of = "/"
var artistsHint = "Separate artists with ;"

var cover = "Cover"
var coverThumbnail = "Thumbnail"
var coverUrl = "Use URL"
var coverFile = "Use file"
var coverUrlPlaceholder = "https://…"
var coverFilePlaceholder = "/path/to/image.jpg"

var preview = "▶ Preview"
var discard = "Discard"
var confirm = "Confirm"
var replace = "Replace"
var retry = "Retry"
var openYoutube = "↗ YouTube"
var search = "Search"
var stateFilter = "State"

var states = {
  "": "All",
  downloading: "downloading",
  download_failed: "download failed",
  queued: "queued",
  processing: "processing",
  ready_for_review: "ready for review",
  in_transit: "in transit",
  sent: "sent",
  failed: "failed",
  conflict: "conflict",
  discarded: "discarded"
}
var stateIcons = {
  downloading: "⬇",
  queued: "⏳",
  processing: "⚙",
  in_transit: "⇡",
  sent: "✔",
  failed: "✖",
  discarded: "–",
  download_failed: "✖"
}
var historyStates = ["", "sent", "discarded", "failed"]

var attempt = function(n, max) { return "attempt " + n + "/" + max }
var percent = function(n) { return n + "%" }
var codexLookup = "(Codex lookup)"
var trackOf = function(n, total) { return "track " + n + "/" + total }
var errorPrefix = "Error: "
