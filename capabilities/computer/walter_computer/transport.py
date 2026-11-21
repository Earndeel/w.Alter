"""CuaDriver MCP port. No Hermes installation is required."""
from __future__ import annotations
import json
from typing import Any


def normalize_result(raw: dict[str, Any]) -> dict[str, Any]:
    texts, images, mimes = [], [], []
    for item in raw.get('content', []):
        if item.get('type') == 'text':
            texts.append(item.get('text', ''))
        elif item.get('type') == 'image':
            images.append(item.get('data'))
            mimes.append(item.get('mimeType'))
    data = '\n'.join(texts)
    try:
        data = json.loads(data)
    except (ValueError, TypeError):
        pass
    return {'data': data, 'images': images, 'image_mime_types': mimes,
            'structuredContent': raw.get('structuredContent', {}),
            'isError': bool(raw.get('isError', False))}


class DriverSession:
    """One serial, authenticated device-node connection with live schema discovery.

    Transport completion-unknown exceptions are never retried. A caller closes the
    operator and opens a new session before collecting fresh target evidence.
    """
    def __init__(self, command: list[str], *, transport=None):
        if transport is None:
            from walter_device_node.cua_transport import McpStdioSession
            transport = McpStdioSession(command=command)
        self.transport = transport
        self._started = False
        self.capabilities_discovered = False
        self.tools = {}

    def start(self):
        if self._started:
            return
        self.transport.start()
        # The pinned device-node transport serializes requests on its RLock.
        with self.transport._lock:
            result = self.transport._request('tools/list', {}, completion_can_be_unknown=False)
        self.tools = {row['name']: row for row in result.get('tools', [])}
        self.capabilities_discovered = True
        self._started = True

    def stop(self):
        self.transport.close()
        self._started = False

    def call_tool(self, name, args, *, timeout=30.0):
        self.start()
        if not self._has_tool(name):
            raise RuntimeError(f'driver does not advertise {name}')
        return normalize_result(self.transport.call_tool(name, args))

    def _has_tool(self, name):
        return name in self.tools

    def supports_input_property(self, tool, name):
        return name in self.tools.get(tool, {}).get('inputSchema', {}).get('properties', {})

    def supports_capability(self, name, *, tool):
        caps = self.tools.get(tool, {}).get('capabilities', [])
        return name in caps or (name == 'input.scroll.coordinates' and self.supports_input_property(tool, 'x'))

    @staticmethod
    def _logical_error_text(out):
        return str(out.get('data') or 'driver rejected the operation')

    def _call_tool_via_cli(self, *args):
        raise RuntimeError('independent port has no implicit second transport or replay')
