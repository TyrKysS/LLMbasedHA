import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timezone

import aiohttp
import aiohttp_jinja2
import jinja2
from aiohttp import web

logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
logger = logging.getLogger("ha_monitor")

HA_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_URL = "http://supervisor/core"
WS_URL = "ws://supervisor/core/api/websocket"

states_cache: dict[str, dict] = {}
ws_clients: set[web.WebSocketResponse] = set()


def classify_entity(entity_id: str, state: str, attributes: dict) -> dict:
    domain = entity_id.split(".")[0]
    result = {"domain": domain, "state_raw": state, "display": {}}

    if domain in ("light", "switch", "input_boolean", "fan", "automation", "script"):
        result["display"] = {"type": "toggle", "value": state == "on", "label": "Zapnuto" if state == "on" else "Vypnuto"}
    elif domain in ("binary_sensor",):
        device_class = attributes.get("device_class", "")
        labels = {
            "motion": ("Detekován", "Nedetekován"),
            "door": ("Otevřeno", "Zavřeno"),
            "window": ("Otevřeno", "Zavřeno"),
            "presence": ("Přítomen", "Nepřítomen"),
            "occupancy": ("Obsazeno", "Prázdno"),
            "smoke": ("Kouř detekován", "OK"),
            "moisture": ("Vlhkost detekována", "Suché"),
            "contact": ("Otevřeno", "Zavřeno"),
        }
        on_label, off_label = labels.get(device_class, ("Aktivní", "Neaktivní"))
        result["display"] = {"type": "binary", "value": state == "on", "label": on_label if state == "on" else off_label}
    elif domain == "sensor":
        device_class = attributes.get("device_class", "")
        unit = attributes.get("unit_of_measurement", "")
        result["display"] = {"type": "value", "value": state, "unit": unit, "device_class": device_class}
    elif domain == "climate":
        result["display"] = {
            "type": "climate",
            "value": state,
            "current_temp": attributes.get("current_temperature"),
            "target_temp": attributes.get("temperature"),
            "humidity": attributes.get("current_humidity"),
        }
    elif domain in ("media_player",):
        result["display"] = {"type": "media", "value": state, "label": state}
    elif domain in ("cover",):
        result["display"] = {"type": "cover", "value": state, "position": attributes.get("current_position")}
    elif domain == "person":
        result["display"] = {"type": "person", "value": state, "label": state}
    elif domain == "weather":
        result["display"] = {
            "type": "weather",
            "value": state,
            "temperature": attributes.get("temperature"),
            "humidity": attributes.get("humidity"),
        }
    else:
        result["display"] = {"type": "generic", "value": state}

    result["friendly_name"] = attributes.get("friendly_name", entity_id)
    result["icon"] = attributes.get("icon", "")
    return result


async def fetch_all_states(session: aiohttp.ClientSession) -> list[dict]:
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    async with session.get(f"{HA_URL}/api/states", headers=headers) as resp:
        resp.raise_for_status()
        return await resp.json()


async def broadcast(message: dict) -> None:
    dead = set()
    for ws in ws_clients:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    ws_clients.difference_update(dead)


async def listen_ha_events(app: web.Application) -> None:
    headers = {"Authorization": f"Bearer {HA_TOKEN}"}
    msg_id = 1

    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(WS_URL) as ws:
                    auth_req = await ws.receive_json()
                    if auth_req.get("type") == "auth_required":
                        await ws.send_json({"type": "auth", "access_token": HA_TOKEN})
                        auth_resp = await ws.receive_json()
                        if auth_resp.get("type") != "auth_ok":
                            logger.error("WebSocket auth failed: %s", auth_resp)
                            await asyncio.sleep(10)
                            continue

                    await ws.send_json({"id": msg_id, "type": "subscribe_events", "event_type": "state_changed"})
                    msg_id += 1
                    await ws.receive_json()  # subscription ACK

                    logger.info("WebSocket připojen, poslouchám state_changed události")

                    async for msg in ws:
                        if msg.type != aiohttp.WSMsgType.TEXT:
                            continue
                        data = json.loads(msg.data)
                        if data.get("type") != "event":
                            continue

                        event = data["event"]
                        event_data = event.get("data", {})
                        entity_id = event_data.get("entity_id", "")
                        new_state_obj = event_data.get("new_state") or {}
                        old_state_obj = event_data.get("old_state") or {}

                        new_state = new_state_obj.get("state", "unavailable")
                        old_state = old_state_obj.get("state", "unavailable")
                        attributes = new_state_obj.get("attributes", {})

                        change_log = {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "entity_id": entity_id,
                            "friendly_name": attributes.get("friendly_name", entity_id),
                            "old_state": old_state,
                            "new_state": new_state,
                            "attributes": attributes,
                            "context": new_state_obj.get("context", {}),
                        }
                        logger.info("STATE_CHANGE %s", json.dumps(change_log, ensure_ascii=False))

                        classified = classify_entity(entity_id, new_state, attributes)
                        states_cache[entity_id] = classified

                        await broadcast({"type": "state_changed", "entity_id": entity_id, "data": classified})

        except Exception as exc:
            logger.warning("WebSocket chyba: %s — opakuji za 10s", exc)
            await asyncio.sleep(10)


@aiohttp_jinja2.template("dashboard.html")
async def dashboard(request: web.Request) -> dict:
    return {"states": states_cache}


async def api_states(request: web.Request) -> web.Response:
    return web.json_response(states_cache)


async def websocket_handler(request: web.Request) -> web.WebSocketResponse:
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    ws_clients.add(ws)
    try:
        await ws.send_json({"type": "init", "states": states_cache})
        async for _ in ws:
            pass
    finally:
        ws_clients.discard(ws)
    return ws


async def on_startup(app: web.Application) -> None:
    async with aiohttp.ClientSession() as session:
        try:
            raw_states = await fetch_all_states(session)
            for entity in raw_states:
                eid = entity["entity_id"]
                state = entity["state"]
                attrs = entity.get("attributes", {})
                states_cache[eid] = classify_entity(eid, state, attrs)
            logger.info("Načteno %d entit z Home Assistant", len(states_cache))
        except Exception as exc:
            logger.error("Chyba při načítání stavů: %s", exc)

    asyncio.create_task(listen_ha_events(app))


def build_app() -> web.Application:
    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader("/app/templates"))
    app.router.add_get("/", dashboard)
    app.router.add_get("/api/states", api_states)
    app.router.add_get("/ws", websocket_handler)
    app.on_startup.append(on_startup)
    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8099))
    app = build_app()
    web.run_app(app, host="0.0.0.0", port=port, access_log=None)
