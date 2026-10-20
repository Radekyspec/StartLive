from startlive.core.pk.parameters import cancel_video_invite_fields
from .pk_request import PkRequestWorker


class PkCancelInvitationWorker(PkRequestWorker):
    """Cancel an ordinary directed invitation, not an active battle."""
    operation = "handle"

    def __init__(self, presenter, identity, /, peer_search, *, trace_id):
        super().__init__(presenter, identity,
                         fields=cancel_video_invite_fields(peer_search),
                         after_sign={
                             "client_traceid": trace_id} if trace_id else {})
