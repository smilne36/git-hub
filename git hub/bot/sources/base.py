from ..config import Job


class Source:
    name: str = "base"

    def fetch(self) -> list[Job]:
        raise NotImplementedError
