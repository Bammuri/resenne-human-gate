"""Local-network UNO R4 proxy, with optional legacy token and no retries."""
import http.client
import ipaddress
import json
import threading


class BoardWifi:
    def __init__(self):
        self.lock = threading.RLock()
        self.host = self.token = self.boot = ""
        self.cursor = 0

    def _request(self, method, path, body=None):
        connection = http.client.HTTPConnection(self.host, 80, timeout=3)
        try:
            headers = {"Content-Type": "text/plain; charset=utf-8"}
            if self.token:
                headers["X-Board-Token"] = self.token
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            raw = response.read(16385)
            if response.status != 200 or len(raw) > 16384:
                raise ValueError("보드 IP와 펌웨어를 확인해 주세요.")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("보드 응답 형식이 올바르지 않습니다.")
            return result
        except (OSError, http.client.HTTPException, json.JSONDecodeError) as error:
            raise ValueError("Wi-Fi 보드 연결이 끊겼습니다. 전송을 재시도하지 않았습니다.") from error
        finally:
            connection.close()

    def connect(self, host, token=""):
        try:
            address = ipaddress.IPv4Address(host)
            allowed = any(address in ipaddress.ip_network(net) for net in
                          ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
        except (ValueError, TypeError):
            allowed = False
        if not allowed or not isinstance(token, str) or (token and (not 16 <= len(token) <= 128 or not token.isascii() or any(ord(c) < 33 for c in token))):
            raise ValueError("보드의 올바른 사설 IPv4 주소를 입력해 주세요.")
        with self.lock:
            self.host, self.token = str(address), token
            try:
                status = self._request("GET", "/status")
                if status.get("board") != "UNO R4 WiFi" or status.get("protocol") != 3:
                    raise ValueError("호환되는 UNO R4 Wi-Fi 펌웨어가 아닙니다.")
                self.boot, self.cursor = status["boot"], int(status["cursor"])
                return status
            except Exception:
                self.disconnect()
                raise

    def disconnect(self):
        with self.lock:
            self.host = self.token = self.boot = ""
            self.cursor = 0

    def poll(self):
        with self.lock:
            if not self.host:
                raise ValueError("먼저 Wi-Fi 보드를 연결해 주세요.")
            result = self._request("GET", f"/events?after={self.cursor}")
            if result.get("reset") or result.get("boot") != self.boot:
                self.disconnect()
                raise ValueError("보드가 재시작됐거나 입력이 누락됐습니다. Wi-Fi 보드를 다시 연결해 주세요.")
            self.cursor = int(result["cursor"])
            return result

    def command(self, command):
        if not isinstance(command, str) or not 1 <= len(command) <= 255 or any(ord(c) < 32 for c in command):
            raise ValueError("올바른 한 줄 보드 명령이 필요합니다.")
        with self.lock:
            if not self.host:
                raise ValueError("먼저 Wi-Fi 보드를 연결해 주세요.")
            return self._request("POST", "/command", command.encode("utf-8"))
