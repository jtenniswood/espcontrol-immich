# Optional container compatibility

HACS is the primary installation path and creates native Home Assistant devices.
The optional container remains supported for existing HTTP/SQLite users. It now
has an explicit image-delivery path and uses the same slideshow runtime as the
native integration. It does not create native Home Assistant entities.

Open the add-on's ingress page, connect Immich, and create a frame. Its preview
and Previous/Pause/Next controls use the HTTP interface below. Relative browser
URLs keep requests within Home Assistant ingress. No API key is included in a
frame response or configuration export.

| Request | Result |
|---|---|
| `GET /api/frames` | Frame list |
| `GET /api/frames/{id}/state` | Complete current metadata, playback state, and a versioned image URL |
| `GET /api/frames/{id}/image` | Current rendered JPEG |
| `GET /api/frames/{id}/image?generation=N` | The JPEG for that retained generation, or 409 if it is no longer available |
| `POST /api/frames/{id}/commands/next` | Resume and advance |
| `POST /api/frames/{id}/commands/previous` | Return to the previous complete slide |
| `POST /api/frames/{id}/commands/pause` | Pause |
| `POST /api/frames/{id}/commands/resume` | Resume automatic playback |
| `POST /api/frames/{id}/commands/clear_cache` | Remove the disk cache |

A client needing matching metadata and image should fetch state, then use its
`image_url`. If the image returns 409, refetch state. Before the first available
image, state/image requests return 503; deleted or unknown frames return 404.
The browser page follows this interface. Ingress access is managed by Home
Assistant; the standalone HTTP service should remain on a trusted network.

Existing frame create/edit/delete, connection, catalog, import/export and refresh
endpoints remain. Old field names and saved dimensions retain their migration
behavior. New out-of-range values and non-boolean fallback flags now return 400
instead of being silently coerced. Next now resumes playback, matching the native
integration. Native identities, settings and credentials are not merged with
container records.

The previous code contained unconnected publisher hooks but no configured
publisher or image route. Those hooks have been replaced by the documented HTTP
path. The repository contains no other publisher consumers; external usage
cannot be measured from the checkout, so the container has not been retired.

`scripts/check_container.py` exercises an installed image against a local fake
Immich service: validate a connection, create a paired frame, retrieve matching
state/JPEG, and navigate. This runs inside both release candidates. It does not
claim live-server or physical-display acceptance; those remain in the device
acceptance checklist in the architecture guide.
