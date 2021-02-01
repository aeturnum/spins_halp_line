from typing import Dict, Protocol


class Restoreable(Protocol):
    def get_snapshot(self) -> dict:
        pass

    def get_snapshot_name(self) -> str:
        pass

class Restoreer(Protocol):
    async def restore_states(self, name: str, shared_state: dict, sub_states: Dict[str, dict]):
        pass
