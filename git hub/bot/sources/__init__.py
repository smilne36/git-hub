from .remoteok import RemoteOK
from .greenhouse import Greenhouse
from .lever import Lever
from .ashby import Ashby
from .adzuna import Adzuna


def build_sources(cfg: dict) -> list:
    sources = []
    s = cfg.get("sources", {})
    if s.get("remoteok", {}).get("enabled"):
        sources.append(RemoteOK())
    if s.get("greenhouse", {}).get("enabled"):
        sources.append(Greenhouse(s["greenhouse"].get("boards", [])))
    if s.get("lever", {}).get("enabled"):
        sources.append(Lever(s["lever"].get("companies", [])))
    if s.get("ashby", {}).get("enabled"):
        sources.append(Ashby(s["ashby"].get("companies", [])))
    if s.get("adzuna", {}).get("enabled"):
        a = s["adzuna"]
        sources.append(Adzuna(a["app_id"], a["app_key"], a.get("country", "us")))
    return sources
