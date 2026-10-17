from .pk_request import PkRequestWorker
from startlive.core.pk.candidates import parse_candidate_page, \
    video_search_fields
from startlive.core.exceptions import PkProtocolError


class PkSearchCandidatesWorker(PkRequestWorker):
    operation = "search_candidates"

    def __init__(self, presenter, identity, /, search, *, page=1):
        super().__init__(presenter, identity,
                         fields=video_search_fields(search, page=page))

    def parse_result(self, result):
        page = parse_candidate_page(result.data,
                                    requested_type=int(self.fields["type"]))
        if page.search_type != 1:
            raise PkProtocolError("返回的候选人不属于指定视频 PK 搜索")
        return page
