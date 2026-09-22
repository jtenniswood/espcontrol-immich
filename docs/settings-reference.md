# Frame settings reference

Generated from `core/settings.py`. Run `python scripts/product_contract.py` after changing the contract.

| Control | Service values, in order | Default | Effect |
|---|---|---|---|
| Photo time range | `all_time` — All time; `1_month` — Last 1 month; `3_months` — Last 3 months; `6_months` — Last 6 months; `1_year` — Last 1 year; `2_years` — Last 2 years; `3_years` — Last 3 years; `4_years` — Last 4 years; `5_years` — Last 5 years; `10_years` — Last 10 years | `all_time` | selection |
| Screen shape | `landscape` — Landscape (1280 × 800); `portrait` — Portrait (800 × 1280); `square` — Square (720 × 720) | `landscape` | render |
| Photo fit | `crop` — Crop to fit; `show_full` — Show full image | `show_full` | render |
| Portrait images | `single` — Single portrait photos only; `pairs` — Single and Paired portrait photos; `pairs_only` — Paired portrait photos only | `single` | selection |
| Photo orientation | `any` — Mixed (landscapes and portraits); `portrait` — Portrait photos only; `landscape` — Landscape photos only | `any` | selection |
| Portrait image window | 0–7 | `2` | selection |
| Slideshow Timer | 10–86400 | `30` | timer |

Screen outputs are exactly Landscape 1280 × 800, Portrait 800 × 1280, and Square 720 × 720.

Square-only photo selection is retained for old saved configurations, but is not offered as a new native control choice. Square photos remain included in Mixed.

Setup and Configure edit the photo source; the device page owns these display and timing controls.

## Photo sources

| Source | Saved value | Fields |
|---|---|---|
| All photos | `all` | None |
| Albums | `album` | album_ids |
| Memories | `memories` | memory_window_days, fallback_to_all |
| Keywords | `smart` | smart_query, smart_reference_asset_id |
| Custom filter | `filter` | filter |

Timer changes reschedule playback without invalidating photos. Render and selection changes invalidate incompatible snapshots.
