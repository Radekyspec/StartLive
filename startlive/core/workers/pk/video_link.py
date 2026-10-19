from startlive.core.exceptions import PkProtocolError
from startlive.core.pk.api import PkApi
from startlive.core.pk.candidates import parse_candidate_page
from startlive.core.pk.identity import require_current_identity
from startlive.core.pk.parameters import connect_fields, cancel_connect_fields, \
    connection_pk_fields
from .pk_request import PkRequestWorker


class PkConnectWorker(PkRequestWorker):
    operation = "connect"

    def __init__(self, presenter, identity, /, candidate):
        super().__init__(presenter, identity, fields=connect_fields(
            candidate.uid, invited_type_label=candidate.label_type))


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
        api = PkApi(self._session, self.identity,
                    logger_name=type(self).__name__)

        def request(operation, fields, **kwargs):
            return api.request(operation, fields,
                               before_send=lambda: require_current_identity(
                                   self.identity), **kwargs)

        request("layout_data", {})
        request("match_list", {}, after_sign={"type": "0", "last_id": "0"})
        request("get_match_select", {})
        request("in_conn_panel", {"room_id": str(self.identity.room_id)})
        result = request("batch_recommend_list", {
            "label_map": '{"conn_random":"","universal_multi_conn_v2":""}'})
        data = result.data
        if not isinstance(data, dict) or not isinstance(
                data.get("batch_data_map"), dict):
            raise PkProtocolError("连线推荐列表响应无效")
        group = data["batch_data_map"].get("universal_multi_conn_v2")
        if not isinstance(group, dict):
            raise PkProtocolError("响应缺少视频连线候选列表")
        # Pagination below is the existing view model, not request parameters.
        return parse_candidate_page({"users": group.get("users"), "page": 1,
                                     "type": 1, "next": False})


class PkDisconnectLinkWorker(PkRequestWorker):
    """Order Exit before Quit on one existing HTTP session; no retries."""
    operation = "quit"

    def __init__(self, presenter, identity, /, biz_session_id, *, exit_pk):
        super().__init__(presenter, identity,
                         fields={"biz_session_id": biz_session_id})
        self.exit_pk = exit_pk

    def run(self, report_progress, *args, **kwargs):
        api = PkApi(self._session, self.identity,
                    logger_name=type(self).__name__)
        guard = lambda: require_current_identity(self.identity)
        error = None
        if self.exit_pk:
            try:
                api.request("exit", {"stop_pk": "1"}, before_send=guard)
            except Exception as caught:
                error = caught
        result = api.request("quit", self.fields, before_send=guard)
        if error is not None:
            raise error
        return result
