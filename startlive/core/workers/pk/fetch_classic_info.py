from .pk_request import PkRequestWorker


class PkClassicInfoWorker(PkRequestWorker):
    """Contract16 secret62ed0 variant, without pk_version or post-sign CSRF."""
    operation = "classic_info"

    def __init__(self, presenter, identity, /, pk_id: int):
        # The controller selects zero for current state or a positive round ID.
        super().__init__(presenter, identity,
                         fields={"is_anchor": "1", "pk_id": f"{pk_id:d}",
                                 "room_id": str(identity.room_id)})
