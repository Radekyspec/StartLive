from dataclasses import replace

from startlive.core.exceptions import PkError, PkProtocolError, TaskCancelled
from startlive.core.pk.candidates import parse_candidate_page
from startlive.core.pk.pk_info import queried_pk_info
from startlive.core.pk.parameters import connect_fields, cancel_connect_fields, \
    connection_pk_fields
from .pk_request import PkRequestWorker


class PkConnectWorker(PkRequestWorker):
    operation = "connect"

    def __init__(self, presenter, identity, /, candidate):
        super().__init__(presenter, identity, fields=connect_fields(
            candidate.uid, invited_type_label=candidate.label_type))

    def parse_result(self, data):
        value = data.get("biz_session_id") if isinstance(data, dict) else None
        if not isinstance(value, str) or not value:
            raise PkProtocolError("Connect 响应缺少连线会话 ID")
        return value


class PkCancelConnectWorker(PkRequestWorker):
    operation = "handle"

    def __init__(self, presenter, identity, /, peer_uid):
        super().__init__(presenter, identity,
                         fields=cancel_connect_fields(peer_uid))


class PkConnectionStartWorker(PkRequestWorker):
    operation = "start"

    def __init__(self, presenter, identity, /, biz_session_id):
        super().__init__(presenter, identity,
                         fields=connection_pk_fields(biz_session_id))

    def parse_result(self, data):
        info = queried_pk_info(data)
        if info.basic.pk_id <= 0 or info.basic.biz_session_id != self.fields["biz_session_id"]:
            raise PkProtocolError("转 PK 响应与当前连线不符")
        return info


class PkInteractListWorker(PkRequestWorker):
    operation = "interact_list"

    def __init__(self, presenter, identity, /):
        super().__init__(presenter, identity, fields={})


class PkLinkPanelWorker(PkRequestWorker):
    """Prepare the verified 1v1 panel using the shared request transport."""
    operation = "layout_data"

    def __init__(self, presenter, identity, /):
        super().__init__(presenter, identity, fields={})

    def run(self, report_progress, *args, **kwargs):
        self._request("layout_data", {})
        self._request("match_list", {}, after_sign={"type": "0", "last_id": "0"})
        self._request("get_match_select", {})
        self._request("in_conn_panel", {"room_id": str(self.identity.room_id)})
        return self._request("batch_recommend_list", {
            "label_map": '{"conn_random":"","universal_multi_conn_v2":""}'},
            parse_result=self.parse_result)

    def parse_result(self, data):
        if not isinstance(data, dict) or not isinstance(
                data.get("batch_data_map"), dict):
            raise PkProtocolError("连线推荐列表响应无效")
        group = data["batch_data_map"].get("universal_multi_conn_v2")
        if not isinstance(group, dict):
            raise PkProtocolError("响应缺少视频连线候选列表")
        # Pagination below is the existing view model, not request parameters.
        page = parse_candidate_page({"users": group.get("users"), "page": 1,
                                     "type": 1, "next": False})
        # The link panel can include the current anchor and occupied rooms.
        # Apply its invitation rules before presenting selectable candidates.
        return replace(page, users=tuple(
            candidate for candidate in page.users
            if candidate.uid != self.identity.uid and candidate.label_type
            and not candidate.biz_session_id
            and not candidate.raw.get("other_users_num", 0)))


class PkDisconnectLinkWorker(PkRequestWorker):
    """Order Exit before Quit on one existing HTTP session; no retries."""
    operation = "quit"

    def __init__(self, presenter, identity, /, biz_session_id, *, exit_pk):
        super().__init__(presenter, identity,
                         fields={"biz_session_id": biz_session_id})
        self.exit_pk = exit_pk

    def run(self, report_progress, *args, **kwargs):
        error = None
        if self.exit_pk:
            try:
                self._request("exit", {"stop_pk": "1"})
            except TaskCancelled:
                raise
            except Exception as caught:
                error = caught
        try:
            result = self._request("quit", self.fields)
        except TaskCancelled:
            raise
        except Exception as quit_error:
            if error is not None:
                raise PkError(
                    f"结束 PK 失败：{type(error).__name__}: {error}；"
                    f"退出连线也失败：{type(quit_error).__name__}: {quit_error}") from quit_error
            raise
        if error is not None:
            raise error
        return result
