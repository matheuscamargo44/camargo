from valclient.exceptions import PhaseError

from features.base import Feature


class ValorantDodge(Feature):
    key = "valorant_dodge"
    title = "Dodge"
    category = "Valorant"
    game = "valorant"

    def __init__(self, valorant_client, config, on_event=None):
        super().__init__(valorant_client, config, on_event)
        self.valorant = valorant_client

    def get_status(self) -> dict:
        return {"key": self.key}

    def dodge(self):
        try:
            self.valorant.pregame_quit_match()
        except PhaseError as exc:
            raise RuntimeError(f"Could not dodge (not in agent select): {exc}") from exc
        self.on_event("success", "Left agent select")
