"""Contract12 projection for directed video PK candidate mode8."""
from copy import deepcopy

from startlive.core.pk.states.candidates import PkCandidate, PkCandidatePage
from startlive.core.exceptions import PkProtocolError


def video_search_fields(search: str, *, page: int = 1):
    if not isinstance(search, str) or not search.strip():
        raise PkProtocolError("请输入要查找的主播 UID 或房间号")
    if type(page) is not int or page < 1:
        raise PkProtocolError("PK 搜索页码无效")
    return {"search": search, "type": "1", "page": str(page),
            "label": "invite_pk"}


def parse_candidate_page(data, *, requested_type=None) -> PkCandidatePage:
    if not isinstance(data, dict) or "users" not in data:
        raise PkProtocolError("PK 候选人响应无效")
    # Online Search returns users:null for no matches, and can omit type.
    # Use the captured request type only when absent; never override an
    # explicit response type. Keep the raw response unchanged for diagnostics.
    items = [] if data["users"] is None else data["users"]
    if not isinstance(items, list):
        raise PkProtocolError("PK 候选人响应无效")
    page, search_type, has_next = data.get("page"), data.get("type",
                                                             requested_type), data.get(
        "next")
    if type(page) is not int or page < 1 or type(
            search_type) is not int or type(has_next) is not bool:
        raise PkProtocolError("PK 候选人分页信息无效")

    def text(obj, name):
        value = obj.get(name)
        return value if isinstance(value, str) else ""

    users = []
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get("user"), dict):
            raise PkProtocolError("PK 候选人信息无效")
        user = item["user"]
        uid = user.get("uid")
        if type(uid) is not int or not 0 < uid < 1 << 64:
            raise PkProtocolError("PK 候选人的 UID 无效")
        # Missing or non-string label_type stays empty, as in the initialized
        # native item. Never substitute item.label or the request's invite_pk.
        users.append(PkCandidate(uid, text(user, "uname"), text(user, "face"),
                                 text(item, "label"), text(item, "label_type"),
                                 text(item, "biz_session_id"), deepcopy(item)))
    return PkCandidatePage(tuple(users), page, search_type, has_next,
                           deepcopy(data))
