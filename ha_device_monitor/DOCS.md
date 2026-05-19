# HA Device Monitor

Dashboard zobrazující všechna zařízení a jejich aktuální stav v reálném čase.

## Funkce

- **Dashboard** – mřížka karet pro každou entitu v HA (světla, spínače, senzory, klima, binární senzory…)
- **Filtrování** – filtr podle domény a fulltextové hledání
- **Live update** – stavy se aktualizují okamžitě přes WebSocket bez obnovení stránky
- **Log změn** – plovoucí panel se záznamy všech změn stavů (tlačítko 📋 vpravo dole)
- **Logování** – každá změna stavu se zapíše do logu add-onu jako JSON

## Formát logu

```json
{
  "timestamp": "2024-01-15T10:30:00+00:00",
  "entity_id": "light.obyvak",
  "friendly_name": "Světlo obývák",
  "old_state": "off",
  "new_state": "on",
  "attributes": { "brightness": 255, "color_temp": 370 },
  "context": { "id": "...", "user_id": "..." }
}
```

## Instalace

1. Zkopírujte složku `LLMbasedHA` do `/addons/` na svém HA hostu
2. V HA přejděte na **Nastavení → Doplňky → Obchod s doplňky → ⋮ → Zkontrolovat aktualizace**
3. Doplněk `HA Device Monitor` se objeví v sekci Local add-ons
4. Nainstalujte a spusťte

Dashboard je dostupný přes záložku **Device Monitor** v postranním menu.
