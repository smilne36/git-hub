from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class Job:
    id: str
    source: str
    title: str
    company: str
    location: str
    url: str
    description: str = ""
    apply_url: str = ""


@dataclass
class Config:
    raw: dict

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        with open(path) as f:
            return cls(raw=yaml.safe_load(f))

    def get(self, *keys, default=None):
        node = self.raw
        for k in keys:
            if not isinstance(node, dict) or k not in node:
                return default
            node = node[k]
        return node
