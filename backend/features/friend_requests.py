import logging
from features.base import Feature

logger = logging.getLogger(__name__)


class FriendRequestsManager(Feature):
    key = "friend_requests"
    title = "Friend Requests"
    category = "Social"

    def _fetch_requests(self):
        # Try V2 first (puuid-based)
        try:
            res_v2 = self.lcu.lcu_request("GET", "/lol-chat/v2/friend-requests")
            if res_v2.status_code == 200:
                return res_v2.json() or []
        except Exception:
            pass

        # Fallback to V1
        try:
            res_v1 = self.lcu.lcu_request("GET", "/lol-chat/v1/friend-requests")
            if res_v1.status_code == 200:
                return res_v1.json() or []
        except Exception:
            pass

        return []

    def get_status(self) -> dict:
        pending_count = 0
        if self.lcu.is_league_connected():
            try:
                reqs = self._fetch_requests()
                incoming = [r for r in reqs if r.get("direction") in ("in", "BOTH", "INCOMING")]
                pending_count = len(incoming) if incoming else len(reqs)
            except Exception as e:
                logger.debug(f"Could not fetch friend requests: {e}")

        return {
            "key": self.key,
            "pending_count": pending_count,
        }

    def accept_all(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        reqs = self._fetch_requests()
        accepted = 0

        for r in reqs:
            puuid = r.get("puuid")
            req_id = r.get("id") or r.get("summonerId")

            handled = False
            if puuid:
                try:
                    accept_res = self.lcu.lcu_request(
                        "PUT", f"/lol-chat/v2/friend-requests/{puuid}", {"direction": "BOTH"}
                    )
                    if accept_res.status_code in (200, 201, 204):
                        accepted += 1
                        handled = True
                except Exception:
                    pass

            if not handled and req_id:
                try:
                    accept_res = self.lcu.lcu_request(
                        "PUT", f"/lol-chat/v1/friend-requests/{req_id}", {"direction": "BOTH"}
                    )
                    if accept_res.status_code in (200, 201, 204):
                        accepted += 1
                except Exception:
                    pass

        self.on_event("success", f"Accepted {accepted} friend request(s)")
        return {"accepted": accepted}

    def reject_all(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        reqs = self._fetch_requests()
        rejected = 0

        for r in reqs:
            puuid = r.get("puuid")
            req_id = r.get("id") or r.get("summonerId")

            handled = False
            if puuid:
                try:
                    del_res = self.lcu.lcu_request("DELETE", f"/lol-chat/v2/friend-requests/{puuid}")
                    if del_res.status_code in (200, 201, 204):
                        rejected += 1
                        handled = True
                except Exception:
                    pass

            if not handled and req_id:
                try:
                    del_res = self.lcu.lcu_request("DELETE", f"/lol-chat/v1/friend-requests/{req_id}")
                    if del_res.status_code in (200, 201, 204):
                        rejected += 1
                except Exception:
                    pass

        self.on_event("success", f"Rejected {rejected} friend request(s)")
        return {"rejected": rejected}
