from .pk_request import PkRequestWorker
from startlive.core.pk.states.candidates import PkCandidate
from startlive.core.pk.parameters import video_invite_fields


class PkInviteWorker(PkRequestWorker):
    """Directed video PK, after a successful non-intercepted precheck."""
    operation = "start"

    def __init__(self, presenter, identity, /, candidate: PkCandidate):
        super().__init__(presenter, identity,
                         fields=video_invite_fields(candidate.uid,
                                                    invited_type_label=candidate.label_type))
