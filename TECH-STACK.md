# TuneRelay: initial technology plan

## Recommended stack

| Component | Technology | Role |
| --- | --- | --- |
| Omarchy desktop widget | QML with JavaScript | Native Quickshell interface for capturing links, reviewing metadata, and showing import status |
| Import service | Python | Authenticated HTTP API, metadata coordination, file validation, and library delivery |
| Service API | REST over HTTPS on the trusted home network | Narrow interface between the desktop widget and the server |
| Music library integration | Navidrome's Subsonic-compatible API or its scan command | Request a library scan after an authorized audio file is placed in the music folder |

## Component boundary

The desktop widget should remain small: it gathers the reference URL and user-approved metadata, submits an authorized audio file, and displays the result. The service on the music server owns validation, file naming, storage, and scan coordination. Credentials for the service must be kept out of the widget source and repository.

## First implementation milestones

1. Confirm the server's library path, network access, and authentication approach.
2. Define request/response fields for a track submission and its metadata.
3. Implement the service API and file validation.
4. Build the QML/JavaScript capture and review interface.
5. Connect Navidrome scanning and show success or failure in the widget.

## Open decisions

- Whether the widget imports a local audio file or a file provided through another authorized source.
- Which metadata provider or AI service to use, and how the user supplies any API key.
- Whether the server service will run as a Docker container or a system service.
