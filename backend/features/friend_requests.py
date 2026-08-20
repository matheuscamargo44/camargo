import logging
from features.base import Feature

logger = logging.getLogger(__name__)


class FriendRequestsManager(Feature):
    key = "friend_requests"
    title = "Friend Requests"
    category = "Social"

    def get_status(self) -> dict:
        pending_count = 0
        if self.lcu.is_league_connected():
            try:
                res = self.lcu.lcu_request("GET", "/lol-chat/v1/friend-requests")
                if res.status_code == 200:
                    reqs = res.json()
                    # Filter incoming requests
                    incoming = [r for r in reqs if r.get("direction") == "in" or r.get("direction") == "BOTH"]
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

        res = self.lcu.lcu_request("GET", "/lol-chat/v1/friend-requests")
        if res.status_code != 200:
            raise RuntimeError(f"Could not fetch friend requests (HTTP {res.status_code})")

        reqs = res.json()
        accepted = 0

        for r in reqs:
            req_id = r.get("id") or r.get("summonerId")
            if req_id:
                accept_res = self.lcu.lcu_request("PUT", f"/lol-chat/v1/friend-requests/{req_id}", {"direction": "in"})
                if accept_res.status_code in (200, 201, 204):
                    accepted += 1

        self.on_event("success", f"Accepted {accepted} friend request(s)")
        return {"accepted": accepted}

    def reject_all(self):
        if not self.lcu.is_league_connected():
            raise RuntimeError("League client is not connected")

        res = self.lcu.lcu_request("GET", "/lol-chat/v1/friend-requests")
        if res.status_code != 200:
            raise RuntimeError(f"Could not fetch friend requests (HTTP {res.status_code})")

        reqs = res.json()
        rejected = 0

        for r in reqs:
            req_id = r.get("id") or r.get("summonerId")
            if req_id:
                del_res = self.lcu.lcu_request("DELETE", f"/lol-chat/v1/friend-requests/{req_id}")
                if del_res.status_code in (200, 201, 204):
                    rejected += 1

        self.on_event("success", f"Rejected {rejected} friend request(s)")
        return {"rejected": rejected}
