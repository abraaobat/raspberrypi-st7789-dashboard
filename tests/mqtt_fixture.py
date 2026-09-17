"""Local fake MQTT broker. No production addresses, credentials or commands."""

import socketserver
import threading
import time


def packet(header, body):
    length, result = len(body), bytearray([header])
    while length >= 128:
        result.append(length % 128 | 128)
        length //= 128
    result.append(length)
    return bytes(result) + body


def receive(sock):
    def read(size):
        result = b""
        while len(result) < size:
            part = sock.recv(size - len(result))
            if not part:
                raise EOFError()
            result += part
        return result
    header = read(1)[0]
    length, shift = 0, 0
    for _ in range(4):
        digit = read(1)[0]
        length += (digit & 127) << shift
        if not digit & 128:
            return header, read(length)
        shift += 7
    raise ValueError()


class FakeMQTT:
    def __init__(self):
        self.calls = []
        self.connect_payloads = []  # Internal test-only; never returned by fixture/status.
        self.messages = {"casa/sala/temperatura": b"28.5", "casa/energia": b'{"sensor":{"power":123.4}}',
                         "casa/porta": b"false", "casa/status": b"online"}
        self.connack = b"\x00\x00"
        self.suback_codes = None
        self.raw_packets = None
        self.delay = 0
        self.slow_packet = None
        self.before_suback = False
        self.retained = True

    def __enter__(self):
        broker = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(5)
                try:
                    header, body = receive(self.request)
                    broker.calls.append({"type": header >> 4})
                    broker.connect_payloads.append(body)
                    time.sleep(broker.delay)
                    self.request.sendall(packet(0x20, broker.connack))
                    if broker.connack != b"\x00\x00":
                        return
                    header, body = receive(self.request)
                    offset, topics, qos = 2, [], []
                    while offset < len(body):
                        length = int.from_bytes(body[offset:offset + 2], "big")
                        topic = body[offset + 2:offset + 2 + length].decode()
                        offset += 2 + length
                        topics.append(topic)
                        qos.append(body[offset])
                        offset += 1
                    broker.calls.append({"type": header >> 4, "topics": topics, "qos": qos})
                    suback = packet(0x90, body[:2] + bytes(broker.suback_codes or [0] * len(topics)))
                    messages = []
                    for topic in topics:
                        if topic in broker.messages:
                            name = topic.encode()
                            messages.append(packet(0x31 if broker.retained else 0x30, len(name).to_bytes(2, "big") + name + broker.messages[topic]))
                    if broker.raw_packets is not None:
                        messages = broker.raw_packets
                    if not broker.before_suback:
                        self.request.sendall(suback)
                    if broker.slow_packet is not None:
                        for value in broker.slow_packet:
                            self.request.sendall(bytes([value]))
                            time.sleep(0.04)
                    for message in messages:
                        self.request.sendall(message)
                    if broker.before_suback:
                        self.request.sendall(suback)
                    while True:
                        header, _ = receive(self.request)
                        broker.calls.append({"type": header >> 4})
                        if header >> 4 == 14:
                            return
                except (OSError, EOFError, ValueError, IndexError):
                    pass

        class Server(socketserver.ThreadingTCPServer):
            daemon_threads = True
            block_on_close = False

        self.server = Server(("127.0.0.1", 0), Handler)
        self.url = f"mqtt://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=1)
