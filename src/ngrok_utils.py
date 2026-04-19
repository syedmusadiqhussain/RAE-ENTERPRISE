import logging
import os
from typing import Any, Dict, Optional

from pyngrok import ngrok


logger = logging.getLogger(__name__)


class NgrokManager:
    def __init__(self, auth_token: str):
        self.auth_token = auth_token
        self.tunnel = None
        if self.auth_token:
            try:
                ngrok.set_auth_token(self.auth_token)
            except Exception as e:
                logger.error(f"Failed to set ngrok auth token: {e}")

    def start_tunnel(self, port: int = 8501) -> Optional[str]:
        try:
            self.tunnel = ngrok.connect(addr=port, bind_tls=True)
            url = self.tunnel.public_url
            base_dir = os.path.dirname(os.path.abspath(__file__))
            out_path = os.path.join(os.path.dirname(base_dir), "mobile_url.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(url)
            return url
        except Exception as e:
            logger.error(f"Failed to start ngrok tunnel: {e}")
            return None

    def stop_tunnel(self) -> None:
        try:
            if self.tunnel:
                ngrok.disconnect(self.tunnel.public_url)
            ngrok.kill()
        except Exception as e:
            logger.error(f"Failed to stop ngrok tunnel: {e}")

    def get_tunnel_info(self) -> Dict[str, Any]:
        if not self.tunnel:
            return {}
        return {"url": self.tunnel.public_url}

