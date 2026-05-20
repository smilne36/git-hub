from .greenhouse import GreenhouseApplier


def build_applier(source: str, profile: dict, dry_run: bool):
    if source == "greenhouse":
        return GreenhouseApplier(profile, dry_run=dry_run)
    return None
