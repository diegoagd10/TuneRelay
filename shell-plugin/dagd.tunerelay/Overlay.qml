import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import qs.Ui
import "Strings.js" as Strings

// The floating TuneRelay window: Review / Queue / History tabs.
// Everything goes through the `tunerelay` CLI via the service's run queue.
Item {
  id: root

  property var shell: null
  property var manifest: null
  property bool opened: false

  readonly property string pluginId: (manifest && manifest.id) || "dagd.tunerelay"
  readonly property var service: shell ? shell.serviceFor(pluginId) : null
  readonly property var status: service ? service.status : ({ review_songs: [], queue: [] })

  property string tab: "review"
  readonly property int songId: session.songId
  readonly property var song: session.song
  property string message: ""
  property string historyQuery: ""
  property string historyState: ""
  property var historySongs: []

  property color background: Color.menu.background
  property color foreground: Color.menu.text
  property color accent: Color.menu.selectedText
  property color selectedBackground: Color.menu.selectedBackground
  property color scrim: Color.menu.scrim
  property color urgent: Color.urgent
  property string fontFamily: Style.font.menuFamily
  readonly property int gap: Style.spacing.md
  readonly property int radius: Style.cornerRadius

  function open(payloadJson) {
    root.opened = true
    root.message = ""
    root.refresh()
    Qt.callLater(function() { keys.forceActiveFocus() })
  }

  function close() { root.opened = false }

  // Start of every user action: clear the last error, then take focus away from any
  // TextInput so its editingFinished queues the pending edit before the action.
  function commitEditors() {
    root.message = ""
    keys.forceActiveFocus()
  }

  ReviewSession {
    id: session
    run: root.run
    onBlocked: if (!root.message) root.message = Strings.fixFieldsFirst
  }

  function dismiss() {
    root.opened = false
    if (root.shell) root.shell.hide(root.pluginId)
  }

  // Run a CLI command. Errors are shown until the user's next action (see
  // commitEditors), so an unrelated background refresh cannot hide them.
  function run(args, onSuccess, onFailure) {
    if (!root.service) return
    root.service.run(args, function(result) {
      if (!result || result.error) {
        root.message = Strings.errorPrefix + (result ? result.error : Strings.noAnswer)
        if (onFailure) onFailure(result)
        return
      }
      if (onSuccess) onSuccess(result)
    })
  }

  function refresh() {
    var waiting = root.status.review_songs || []
    var stillWaiting = false
    for (var i = 0; i < waiting.length; i++) if (waiting[i].id === root.songId) stillWaiting = true
    if (!stillWaiting) session.selectSong(waiting.length > 0 ? waiting[0].id : -1)
    session.load()
    if (root.tab === "history") root.loadHistory()
  }

  function loadHistory() {
    var args = ["history"]
    if (root.historyQuery) args = args.concat(["--q", root.historyQuery])
    if (root.historyState) args = args.concat(["--state", root.historyState])
    root.run(args, function(result) { root.historySongs = result.songs || [] })
  }

  // Confirm / Replace on the selected song, after the reviewed edits (see ReviewSession).
  function reviewedAction(command) {
    root.commitEditors()
    session.reviewed(command)
  }

  function edit(field, value) { session.edit(field, value) }

  function proposalLabel(proposal) {
    return proposal.origin === "codex" ? Strings.codexProposal(proposal.confidence) : Strings.defaultProposal
  }

  function sourcesLabel(proposal) {
    if (!proposal.sources || proposal.sources.length === 0) return Strings.noSources
    var hosts = []
    for (var i = 0; i < proposal.sources.length; i++) {
      var match = String(proposal.sources[i]).match(/^https?:\/\/(?:www\.)?([^\/]+)/)
      hosts.push(match ? match[1] : proposal.sources[i])
    }
    return hosts.join(", ")
  }

  function albumLabel(p) {
    return p.album + (p.year !== null && p.year !== undefined ? " (" + p.year + ")" : "")
  }

  function duration(seconds) {
    var s = Number(seconds || 0)
    return Math.floor(s / 60) + ":" + ("0" + (s % 60)).slice(-2)
  }

  Connections {
    target: root.service
    function onStatusChanged() { if (root.opened) root.refresh() }
  }

  component Label: Text {
    textFormat: Text.PlainText
    color: root.foreground
    font.family: root.fontFamily
    font.pixelSize: Style.font.body
    elide: Text.ElideRight
  }

  component Action: Rectangle {
    id: action
    property string label: ""
    property bool primary: false
    property bool danger: false
    signal clicked()
    implicitWidth: actionText.implicitWidth + root.gap * 2
    implicitHeight: actionText.implicitHeight + root.gap
    radius: root.radius
    color: primary ? root.selectedBackground : "transparent"
    border.width: 1
    border.color: danger ? root.urgent : (primary ? root.accent : root.foreground)
    Label {
      id: actionText
      anchors.centerIn: parent
      text: action.label
      color: action.danger ? root.urgent : (action.primary ? root.accent : root.foreground)
    }
    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      onClicked: {
        root.commitEditors()
        action.clicked()
      }
    }
  }

  component Field: Row {
    id: field
    property string name: ""
    property string label: ""
    property string value: ""
    property string placeholder: ""
    property int inputWidth: 200
    signal committed(string text)
    spacing: root.gap / 2
    // Typing breaks the text binding: follow the draft when it changes, and always show the
    // saved value again when the draft is replaced (even if that value compares equal).
    onValueChanged: input.text = field.value
    Connections {
      target: session.gate
      function onRestore() { input.text = field.value }
    }
    Label {
      width: 96
      anchors.verticalCenter: parent.verticalCenter
      text: field.label
      opacity: 0.7
    }
    Rectangle {
      width: field.inputWidth
      height: input.implicitHeight + root.gap / 2
      radius: root.radius
      color: "transparent"
      border.width: 1
      border.color: field.name && session.gate.isInvalid(field.name) ? root.urgent
        : (input.activeFocus ? root.accent : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.3))
      TextInput {
        id: input
        anchors.fill: parent
        anchors.margins: root.gap / 4
        verticalAlignment: TextInput.AlignVCenter
        text: field.value
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        clip: true
        selectByMouse: true
        onEditingFinished: field.committed(text)
        Label {
          anchors.fill: parent
          verticalAlignment: Text.AlignVCenter
          text: field.placeholder
          opacity: 0.4
          visible: !input.text && !input.activeFocus
        }
      }
    }
  }

  PanelWindow {
    id: panel
    visible: root.opened
    anchors { top: true; bottom: true; left: true; right: true }
    color: "transparent"
    WlrLayershell.namespace: "dagd-tunerelay"
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
    exclusionMode: ExclusionMode.Ignore

    Rectangle { anchors.fill: parent; color: root.scrim }
    MouseArea { anchors.fill: parent; onClicked: root.dismiss() }

    Rectangle {
      id: card
      width: Math.min(Style.space(1000), panel.width - Style.gapsOut * 4)
      height: Math.min(Style.space(720), panel.height - Style.gapsOut * 4)
      anchors.centerIn: parent
      radius: root.radius
      color: root.background
      border.width: 2
      border.color: Color.menu.border

      MouseArea { anchors.fill: parent; onClicked: keys.forceActiveFocus() }

      Item {
        id: keys
        anchors.fill: parent
        focus: true
        Keys.onPressed: function(event) {
          if (event.key === Qt.Key_Escape) {
            root.dismiss()
            event.accepted = true
          }
        }
      }

      Column {
        anchors.fill: parent
        anchors.margins: Style.spacing.panelPadding
        spacing: root.gap

        // Header: title and tabs.
        Row {
          width: parent.width
          spacing: root.gap
          Label {
            text: Strings.appName
            font.pixelSize: Style.font.heading
            width: parent.width - tabs.width - root.gap
          }
          Row {
            id: tabs
            spacing: root.gap
            Repeater {
              model: ["review", "queue", "history"]
              Label {
                id: tabLabel
                required property string modelData
                text: modelData === root.tab ? "[" + Strings.tabs[modelData] + "]" : Strings.tabs[modelData]
                color: modelData === root.tab ? root.accent : root.foreground
                font.pixelSize: Style.font.title
                MouseArea {
                  anchors.fill: parent
                  cursorShape: Qt.PointingHandCursor
                  onClicked: {
                    root.tab = tabLabel.modelData
                    root.refresh()
                  }
                }
              }
            }
          }
        }

        Label {
          width: parent.width
          visible: root.message !== ""
          text: root.message
          color: root.urgent
        }

        // ---------------------------------------------------------- Review
        Flickable {
          id: reviewTab
          visible: root.tab === "review"
          width: parent.width
          height: parent.height - y
          contentHeight: reviewColumn.implicitHeight
          clip: true

          Column {
            id: reviewColumn
            width: reviewTab.width
            spacing: root.gap

            Label {
              visible: !root.song
              text: Strings.nothingToReview
              opacity: 0.7
            }

            Row {
              visible: (root.status.review_songs || []).length > 0
              spacing: root.gap
              Label { text: Strings.waiting((root.status.review_songs || []).length) }
              Repeater {
                model: root.status.review_songs || []
                Label {
                  id: waitingLabel
                  required property var modelData
                  text: (modelData.id === root.songId ? "▸ " : "") + modelData.artist + " - " + modelData.title
                  color: modelData.id === root.songId ? root.accent : root.foreground
                  MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      root.commitEditors()
                      session.selectSong(waitingLabel.modelData.id)
                      root.refresh()
                    }
                  }
                }
              }
            }

            Label {
              visible: !!root.song && !!root.song.youtube
              width: parent.width
              text: root.song && root.song.youtube
                ? Strings.youtube + ": “" + root.song.youtube.title + "” · " + root.song.youtube.channel
                  + " · ▶ " + root.duration(root.song.youtube.duration)
                : ""
              MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: if (root.song && root.song.url) Qt.openUrlExternally(root.song.url)
              }
            }

            Rectangle {
              visible: !!root.song && root.song.state === "conflict"
              width: parent.width
              height: conflictColumn.implicitHeight + root.gap
              radius: root.radius
              color: "transparent"
              border.color: root.urgent
              border.width: 1
              Column {
                id: conflictColumn
                anchors.centerIn: parent
                Label { text: Strings.conflict + ": " + (root.song ? root.song.remote_path || "" : ""); color: root.urgent }
                Label { text: Strings.conflictHint; opacity: 0.7 }
              }
            }

            // Proposal cards; ● marks the selected one.
            Row {
              visible: !!root.song
              spacing: root.gap
              Repeater {
                model: root.song ? root.song.proposals : []
                Rectangle {
                  id: proposalCard
                  required property var modelData
                  required property int index
                  readonly property bool selected: root.song && root.song.selected === index
                  width: Style.space(190)
                  height: cardColumn.implicitHeight + root.gap
                  radius: root.radius
                  color: selected ? root.selectedBackground : "transparent"
                  border.width: 1
                  border.color: selected ? root.accent : Qt.rgba(root.foreground.r, root.foreground.g, root.foreground.b, 0.3)
                  Column {
                    id: cardColumn
                    x: root.gap / 2
                    y: root.gap / 2
                    width: parent.width - root.gap
                    spacing: 2
                    Label {
                      width: parent.width
                      text: (proposalCard.selected ? "● " : "○ ") + root.proposalLabel(proposalCard.modelData)
                      color: proposalCard.selected ? root.accent : root.foreground
                    }
                    Image {
                      width: parent.width
                      height: width
                      fillMode: Image.PreserveAspectCrop
                      source: proposalCard.modelData.cover ? "file://" + proposalCard.modelData.cover : ""
                      asynchronous: true
                    }
                    Label { width: parent.width; text: proposalCard.modelData.title; font.bold: true }
                    Label { width: parent.width; text: proposalCard.modelData.artists.join(", ") || proposalCard.modelData.artist }
                    Label { width: parent.width; text: root.albumLabel(proposalCard.modelData) }
                    Label { width: parent.width; text: Strings.fields.album_artist + ": " + proposalCard.modelData.album_artist; opacity: 0.7 }
                    Label {
                      width: parent.width
                      text: Strings.trackOf(proposalCard.modelData.track, proposalCard.modelData.track_total)
                        + " · " + Strings.fields.disc.toLowerCase() + " " + proposalCard.modelData.disc + "/" + proposalCard.modelData.disc_total
                    }
                    Label { width: parent.width; text: proposalCard.modelData.genre || ""; opacity: 0.7 }
                    Label { width: parent.width; text: root.sourcesLabel(proposalCard.modelData); opacity: 0.7 }
                  }
                  MouseArea {
                    anchors.fill: parent
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                      root.commitEditors()
                      session.selectProposal(proposalCard.index)
                    }
                  }
                }
              }
            }

            // Edit form for the draft.
            Column {
              id: editForm
              visible: !!root.song && !!root.song.draft
              spacing: root.gap / 2
              readonly property var draft: root.song && root.song.draft ? root.song.draft : ({})

              Row {
                spacing: root.gap * 2
                Field { name: "title"; label: Strings.fields.title; value: editForm.draft.title || ""; inputWidth: 280; onCommitted: function(t) { root.edit("title", t) } }
                Field { name: "artist"; label: Strings.fields.artist; value: editForm.draft.artist || ""; inputWidth: 280; onCommitted: function(t) { root.edit("artist", t) } }
              }
              Row {
                spacing: root.gap * 2
                Field { name: "album"; label: Strings.fields.album; value: editForm.draft.album || ""; inputWidth: 280; onCommitted: function(t) { root.edit("album", t) } }
                Field { name: "album_artist"; label: Strings.fields.album_artist; value: editForm.draft.album_artist || ""; inputWidth: 280; onCommitted: function(t) { root.edit("album_artist", t) } }
              }
              Field {
                name: "artists"
                label: Strings.fields.artists
                value: (editForm.draft.artists || []).join("; ")
                placeholder: Strings.artistsHint
                inputWidth: 668
                onCommitted: function(t) { root.edit("artists", t) }
              }
              Row {
                spacing: root.gap
                Field { name: "track"; label: Strings.fields.track; value: String(editForm.draft.track || ""); inputWidth: 40; onCommitted: function(t) { root.edit("track", t) } }
                Field { name: "track_total"; label: Strings.of; value: String(editForm.draft.track_total || ""); inputWidth: 40; onCommitted: function(t) { root.edit("track_total", t) } }
                Field { name: "disc"; label: Strings.fields.disc; value: String(editForm.draft.disc || ""); inputWidth: 40; onCommitted: function(t) { root.edit("disc", t) } }
                Field { name: "disc_total"; label: Strings.of; value: String(editForm.draft.disc_total || ""); inputWidth: 40; onCommitted: function(t) { root.edit("disc_total", t) } }
                Field { name: "year"; label: Strings.fields.year; value: editForm.draft.year === null || editForm.draft.year === undefined ? "" : String(editForm.draft.year); inputWidth: 60; onCommitted: function(t) { root.edit("year", t) } }
                Field { name: "genre"; label: Strings.fields.genre; value: editForm.draft.genre || ""; inputWidth: 140; onCommitted: function(t) { root.edit("genre", t) } }
              }
              Row {
                spacing: root.gap
                Field { name: "mbid_recording"; label: Strings.fields.mbid_recording; value: (editForm.draft.mbids || {}).recording || ""; inputWidth: 200; onCommitted: function(t) { root.edit("mbid_recording", t) } }
                Field { name: "mbid_release"; label: Strings.fields.mbid_release; value: (editForm.draft.mbids || {}).release || ""; inputWidth: 200; onCommitted: function(t) { root.edit("mbid_release", t) } }
                Field { name: "mbid_artist"; label: Strings.fields.mbid_artist; value: (editForm.draft.mbids || {}).artist || ""; inputWidth: 200; onCommitted: function(t) { root.edit("mbid_artist", t) } }
              }
              Row {
                spacing: root.gap
                Label { width: 96; text: Strings.fields.compilation; opacity: 0.7; anchors.verticalCenter: parent.verticalCenter }
                Action {
                  label: editForm.draft.compilation ? "☑" : "☐"
                  onClicked: root.edit("compilation", editForm.draft.compilation ? "false" : "true")
                }
              }

              // Cover picker.
              Row {
                spacing: root.gap
                Label { width: 96; text: Strings.cover; opacity: 0.7; anchors.verticalCenter: parent.verticalCenter }
                Image {
                  width: Style.space(48)
                  height: width
                  fillMode: Image.PreserveAspectCrop
                  source: editForm.draft.cover ? "file://" + editForm.draft.cover : ""
                  cache: false
                }
                Action {
                  label: Strings.coverThumbnail
                  onClicked: session.act(["cover", "--thumbnail"])
                }
                Field {
                  id: coverUrl
                  label: ""
                  placeholder: Strings.coverUrlPlaceholder
                  inputWidth: 200
                  onCommitted: function(t) { coverUrl.value = t }
                }
                Action {
                  label: Strings.coverUrl
                  onClicked: if (coverUrl.value) session.act(["cover", "--url", coverUrl.value])
                }
                Field {
                  id: coverFile
                  label: ""
                  placeholder: Strings.coverFilePlaceholder
                  inputWidth: 160
                  onCommitted: function(t) { coverFile.value = t }
                }
                Action {
                  label: Strings.coverFile
                  onClicked: if (coverFile.value) session.act(["cover", "--file", coverFile.value])
                }
              }
            }

            Row {
              visible: !!root.song
              spacing: root.gap
              Action {
                label: Strings.preview
                onClicked: session.preview()
              }
              Action {
                label: Strings.discard
                danger: true
                onClicked: session.act(["discard"])
              }
              Action {
                visible: !!root.song && root.song.state === "conflict"
                label: Strings.replace
                primary: true
                onClicked: root.reviewedAction("replace")
              }
              Action {
                label: Strings.confirm
                primary: true
                onClicked: root.reviewedAction("confirm")
              }
            }
          }
        }

        // ----------------------------------------------------------- Queue
        Column {
          visible: root.tab === "queue"
          width: parent.width
          spacing: root.gap / 2

          Label {
            visible: (root.status.queue || []).length === 0
            text: Strings.queueEmpty
            opacity: 0.7
          }

          Repeater {
            model: root.status.queue || []
            Label {
              required property var modelData
              width: parent.width
              text: (Strings.stateIcons[modelData.state] || "") + " " + Strings.states[modelData.state] + "   "
                + (modelData.title ? modelData.artist + " - " + modelData.title : modelData.youtube_title || modelData.url)
                + (modelData.state === "downloading" && modelData.progress !== null ? "   " + Strings.percent(modelData.progress) : "")
                + (modelData.state === "processing" ? "   " + Strings.codexLookup : "")
                + (modelData.state === "in_transit" && modelData.attempts > 0 ? "   " + Strings.attempt(modelData.attempts + 1, root.status.max_attempts || 3) : "")
            }
          }
        }

        // --------------------------------------------------------- History
        Column {
          visible: root.tab === "history"
          width: parent.width
          spacing: root.gap / 2

          Row {
            spacing: root.gap * 2
            Field {
              label: Strings.search
              value: root.historyQuery
              inputWidth: 240
              onCommitted: function(t) {
                root.historyQuery = t
                root.loadHistory()
              }
            }
            Action {
              label: Strings.stateFilter + " [" + Strings.states[root.historyState] + " ▾]"
              onClicked: {
                var order = Strings.historyStates
                root.historyState = order[(order.indexOf(root.historyState) + 1) % order.length]
                root.loadHistory()
              }
            }
          }

          Label {
            visible: root.historySongs.length === 0
            text: Strings.historyEmpty
            opacity: 0.7
          }

          Repeater {
            model: root.historySongs
            Row {
              id: historyRow
              required property var modelData
              spacing: root.gap
              Image {
                width: Style.space(40)
                height: width
                fillMode: Image.PreserveAspectCrop
                source: historyRow.modelData.cover ? "file://" + historyRow.modelData.cover : ""
              }
              Column {
                anchors.verticalCenter: parent.verticalCenter
                Label {
                  text: (Strings.stateIcons[historyRow.modelData.state] || "") + " " + Strings.states[historyRow.modelData.state]
                    + "   " + (historyRow.modelData.title
                      ? historyRow.modelData.artist + " - " + historyRow.modelData.title
                      : historyRow.modelData.youtube_title)
                    + (historyRow.modelData.album ? " · " + historyRow.modelData.album : "")
                    + "   " + String(historyRow.modelData.updated_at).slice(0, 10)
                }
                Label {
                  visible: !!historyRow.modelData.remote_path || !!historyRow.modelData.error
                  text: historyRow.modelData.remote_path || historyRow.modelData.error || ""
                  opacity: 0.7
                }
              }
              Action {
                visible: !!historyRow.modelData.url
                label: Strings.openYoutube
                onClicked: Qt.openUrlExternally(historyRow.modelData.url)
              }
              Action {
                visible: historyRow.modelData.state === "failed"
                label: Strings.retry
                primary: true
                onClicked: root.run(["retry", String(historyRow.modelData.id)], function() { root.loadHistory() })
              }
            }
          }
        }
      }
    }
  }
}
