"""Immutable account ownership key shared by asynchronous services."""
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    uid: int
    room_id: int
    cookies: tuple[tuple[str, str], ...] = field(repr=False)

    @classmethod
    def capture(cls, cookies, room_id):
        cookies = dict(cookies)
        return cls(int(cookies.get("DedeUserID", "0")), int(room_id or 0),
                   tuple(sorted(cookies.items())))

    def matches(self, identity):
        return (self.uid, self.room_id, self.cookies) == (
            identity.uid, identity.room_id, identity.cookies)
