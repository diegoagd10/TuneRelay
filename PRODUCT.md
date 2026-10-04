# TuneRelay Product Brief

## Product in one sentence

TuneRelay helps a listener turn a music discovery into a correctly labeled item in their personal Navidrome library, with a quick review step on their Omarchy desktop.

## Problem to solve

When a listener discovers a song while browsing YouTube, saving it to a self-hosted music library takes several manual steps: finding or providing an authorized audio file, identifying the correct artist and track details, naming and organizing the file, transferring it to the server, and waiting for Navidrome to scan it. That friction makes it easy to lose the discovery or add poorly tagged music.

## Suggested solution

Provide a small Omarchy/Quickshell widget that captures the current YouTube link or a pasted link. The widget presents suggested metadata for the listener to review and correct, lets them select an audio file they are authorized to import, then securely sends the file and confirmed metadata to an import service on the music server. The service validates and organizes the submission in Navidrome's music library, requests a library scan, and reports the outcome to the widget.

The AI component may suggest metadata, but the listener confirms it before import. YouTube links are references for identifying discoveries; TuneRelay does not download audio from YouTube.

## Intended user

A self-hosting music listener who uses Omarchy on their desktop and Navidrome on a home server, and who wants a low-friction way to add music they own or are otherwise authorized to import.

## MVP workflow

1. Invoke the TuneRelay widget while viewing a song, or paste its YouTube URL.
2. Review suggested title, artist, album, year, and artwork; edit fields as needed.
3. Select an authorized local audio file.
4. Submit the reviewed metadata and file to the import service on the server.
5. See whether the file was accepted, added to the library, and scanned by Navidrome.

## MVP scope

- Omarchy/Quickshell widget for link capture, metadata review, file selection, and status.
- Authenticated import service on the Navidrome server.
- Metadata suggestions that remain editable and require user confirmation.
- Safe file validation, organization, duplicate handling, and Navidrome scan initiation.
- Clear success and failure feedback.

## Out of scope for the first version

- Downloading or ripping audio from YouTube.
- Automatically importing without user review.
- Replacing Navidrome or becoming a general-purpose music player.
- Supporting multiple server platforms or desktop environments before the first workflow works end to end.

## Product principles

- **User-approved:** metadata and the audio file are reviewed before import.
- **Convenient:** capture the discovery with as few context switches as practical.
- **Private by default:** transfer directly to the user's authenticated home service; never put server credentials in the widget or repository.
- **Recoverable:** show clear errors and allow a failed submission to be retried without creating accidental duplicates.
- **Rights-aware:** import only audio the user is authorized to add.

## Success criteria for the MVP

- A user can go from a YouTube reference link to a reviewed submission without manually logging into the server.
- The imported file has the confirmed metadata and appears in Navidrome after scanning.
- Invalid, duplicate, or failed submissions are explained clearly and do not silently corrupt the library.

## Open product decisions

- Which metadata sources or AI provider should produce suggestions?
- Should TuneRelay accept only local files at first, or support another authorized source?
- What file formats and maximum file sizes should the first version accept?
- How should the server service be installed and exposed securely on the home network?
