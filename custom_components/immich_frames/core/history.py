"""Bounded slideshow navigation, independent of the host and image transport."""


class SlideHistory(list):
    limit = 20
    recent_limit = 10

    def append(self, slide):
        super().append(slide)
        del self[: -self.limit]

    @property
    def recent_ids(self):
        return {
            photo["id"] if isinstance(photo, dict) else photo.id
            for slide in self[-self.recent_limit :]
            for photo in slide.photos
        }

    def previous(self):
        if len(self) > 1:
            self.pop()
        return self[-1] if self else None
