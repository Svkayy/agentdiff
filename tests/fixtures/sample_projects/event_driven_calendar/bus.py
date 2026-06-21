"""A tiny in-memory event bus for the event-driven fixture (no external deps)."""


class Bus:
    def __init__(self):
        self._handlers = {}
        self._collector = None

    def reset(self):
        self._handlers = {}
        self._collector = None

    def on(self, event_type, handler):
        self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, event_type, payload):
        for handler in self._handlers.get(event_type, []):
            handler(payload)

    def set_side_effect_collector(self, collected):
        self._collector = collected

    def record(self, channel, value):
        if self._collector is not None:
            self._collector.setdefault(channel, []).append(value)

    def wait_idle(self, idle_window_ms=500, timeout_s=5):
        # Synchronous bus — handlers run inline, so it's already idle.
        return


bus = Bus()
