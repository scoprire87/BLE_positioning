import json
import os
import logging

_LOGGER = logging.getLogger(__name__)

class RadarStorage:
    def __init__(self, hass):
        self.path = hass.config.path("ble_radar_map.json")
        self.data = {"anchors": {}, "rooms": {}}
        self.load()

    def load(self):
        """Carica la mappa dal file JSON."""
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r') as f:
                    self.data = json.load(f)
            except Exception as e:
                _LOGGER.error(f"Errore nel caricamento della mappa radar: {e}")

    def save(self):
        """Salva la mappa su file JSON."""
        try:
            with open(self.path, 'w') as f:
                json.dump(self.data, f, indent=4)
        except Exception as e:
            _LOGGER.error(f"Errore nel salvataggio della mappa radar: {e}")

    def save_anchor(self, scanner_id, ref_rssi):
        """Salva la calibrazione di uno scanner (ancora)."""
        self.data["anchors"][scanner_id] = ref_rssi
        self.save()

    def save_room_point(self, room_name, fingerprint):
        """Aggiunge un'impronta digitale radio a una stanza."""
        if room_name not in self.data["rooms"]:
            self.data["rooms"][room_name] = []
        self.data["rooms"][room_name].append(fingerprint)
        self.save()

    def get_map(self):
        return self.data
