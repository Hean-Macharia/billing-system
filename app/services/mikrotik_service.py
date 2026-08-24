class MikroTikService:

    def __init__(
        self,
        host: str,
        username: str,
        password: str,
        port: int = 8728,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port

    async def connect(self):
        """
        MikroTik connection will be implemented here.
        """
        return {
            "status": "not_connected",
            "message": "MikroTik integration is not configured yet.",
        }

    async def create_hotspot_user(
        self,
        username: str,
        password: str,
        profile: str,
    ):
        return {
            "status": "not_implemented",
            "username": username,
            "profile": profile,
        }

    async def disable_user(
        self,
        username: str,
    ):
        return {
            "status": "not_implemented",
            "username": username,
        }