# Reset implementation and acceptance

HACS remains the primary installation path. The optional container is retained
as an HTTP/SQLite compatibility adapter with a tested image-delivery interface;
there is no evidence in the repository that would justify removing existing
external consumers.

| Plan requirement | Implementation | Verification |
|---|---|---|
| Preserve HACS and stable native identities | Self-contained integration packaging, unchanged entity keys and frame ownership | Isolated HACS installation, Hassfest, native upgrade and reauthentication tests |
| One validated settings model | `core/settings.py` supplies canonical `FrameSettings`, source descriptions and control effects | Historical fixture expectations, boundary rejection tests, existing settings/flow tests |
| Separate historical migration rules | Native `settings.py`; container `compatibility.py` | Native preset/album/fit/filter fixtures; container cover/contain/dimension fixtures |
| One slideshow runtime | `core/session.py`; thin coordinator and HTTP adapters | The same playback, source-race, Previous-race and offline-restart scenarios through both hosts |
| Complete images and metadata stay together | Existing `FrameSnapshot` and verified atomic snapshot store | Pixel/cache tests; versioned HTTP image delivery; native image-link tests |
| Explicit authentication recovery | Native reauthentication flow updates only this frame's API key | Invalid-key retry, cached-image retention, unchanged entry/entity identities |
| Preserve the lightweight UI | Native forms retained; container source choices use the registry and its preview uses the frame API | Native setup/options tests, generated-page checks, JavaScript syntax check and HTTP delivery tests |
| Publish tested artifacts | Candidate archives are accepted once, recorded, verified and promoted by immutable image/configuration identity | Candidate smoke checks, substitution-rejection tests, localhost-only registry promotion and multi-architecture manifest rehearsal |
| Record source and resolved dependencies | Archive/configuration digests, commit, architecture, Python and OS package versions in provenance | Artifact record/verify commands; provenance attached before draft release becomes public |
| Preserve compatibility and release gates | Generated references, installation checks, native/core suites, Hassfest and HACS workflow retained | Product-contract/version checks, actionlint and supported Python test matrix |

## Behavior deliberately retained

Native source editing remains separate from display/timer controls. Legacy
screen presets, album selections, fit preferences, square-only orientation and
frame identities retain their existing translations. The renderer, JPEG quality,
full-size fallback, paired-portrait layout and background sampling are unchanged.
Connections are not merged across native frames.

Pause and Previous now invalidate older in-flight refreshes. Next resumes
playback in both hosts. Previous does not rewrite the last-generated-slide cache;
restart restores that compatible generated slide and starts unpaused, preserving
the native restart contract. Container imports and HTTP aliases remain supported,
while invalid new numeric ranges and boolean values are rejected consistently.

## Verification boundaries

Automated tests use controlled Immich responses. Container acceptance runs the
installed package and real local HTTP endpoints against a temporary fake Immich
service. Release promotion is rehearsed against a temporary localhost-only
registry; it does not publish a GitHub release or a GHCR image.

Live Immich and physical-display acceptance remain the documented release
checklist in `architecture.md`. These require the user's test installation and
hardware. No production installation, public release, or saved frame data was
changed during implementation.
