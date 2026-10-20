from startlive.core.pk.parameters import video_invite_fields
from startlive.core.pk.states.candidates import PkCandidate
from .pk_request import PkRequestWorker


class PkInviteWorker(PkRequestWorker):
    """Directed video PK, after a successful non-intercepted precheck."""
    operation = "start"

    def __init__(self, presenter, identity, /, candidate: PkCandidate):
        super().__init__(presenter, identity,
                         fields=video_invite_fields(candidate.uid,
                                                    invited_type_label=candidate.label_type))
