![BLE Radar Logo](img/logo_radar.png)

[![Apri la tua istanza Home Assistant e apri il repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=scoprire87&repository=BLE_positioning&category=Integration)

# BLE Radar

- Monitora i dispositivi Bluetooth per Area (Stanza) in [Home Assistant](https://home-assistant.io/), utilizzando [ESPHome](https://esphome.io/) [Bluetooth Proxies](https://esphome.io/components/bluetooth_proxy.html) e dispositivi Shelly Gen2 o successivi.

- (prossimamente) Triangolazione della posizione dei dispositivi su mappa!


[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)
[![HomeAssistant Minimum Version][haminverbadge]][haminver]
[![pre-commit][pre-commit-shield]][pre-commit]
[![Ruff][ruff-shield]][ruff]
[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]

## Cosa fa:

BLE Radar ti permette di tracciare qualsiasi dispositivo Bluetooth e far sì che Home Assistant ti dica in quale stanza della casa si trova. L'unico hardware extra necessario sono i dispositivi ESP32 con ESPHome che fungono da proxy Bluetooth o i dispositivi Shelly Plus.

- Localizzazione basata sull'Area (presenza in stanza a livello di dispositivo) funzionante.
- Crea sensori per Area e Distanza per i dispositivi scelti.
- Supporta i dispositivi iBeacon, inclusi quelli con indirizzi MAC casuali (come gli smartphone con l'app HA Companion).
- Supporta IRK (chiavi risolvibili) tramite il componente core [Private BLE Device](https://www.home-assistant.io/integrations/private_ble_device/). 
- Crea entità `device_tracker` per il monitoraggio Home/Not Home.
- Fornisce un dump completo dei dati tramite il servizio `ble_radar.dump_devices`.

## Di cosa hai bisogno:

- Home Assistant (versione minima richiesta: ![haminverbadge])
- Uno o più proxy Bluetooth (ESPHome, Shelly Plus o Bluetooth USB sull'host).
- Dispositivi BLE da tracciare (telefoni, smartwatch, beacon, ecc.).

## Installazione

Puoi installare BLE Radar aprendo HACS e cercando "BLE Radar".

[![Apri in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=scoprire87&repository=BLE_positioning&category=Integration)

Una volta aggiunta l'integrazione, riavvia Home Assistant e vai in `Impostazioni` -> `Dispositivi e Servizi` -> `Aggiungi Integrazione` cercandolo come `BLE Radar`.

---

## Contributi

Se vuoi contribuire, leggi le [Linee guida per la contribuzione](CONTRIBUTING.md)

---

[black]: https://github.com/psf/black
[ruff-shield]: https://img.shields.io/badge/code%20style-ruff-000000.svg?style=for-the-badge
[ruff]: https://github.com/astral-sh/ruff

[commits-shield]: https://img.shields.io/github/commit-activity/y/scoprire87/BLE_positioning.svg?style=for-the-badge
[commits]: https://github.com/scoprire87/BLE_positioning/commits/main

[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Default-green.svg?style=for-the-badge

[haminver]: https://github.com/scoprire87/BLE_positioning/commits/main/hacs.json
[haminverbadge]: https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fgithub.com%2Fscoprire87%2FBLE_positioning%2Fraw%2Fmain%2Fhacs.json&query=%24.homeassistant&style=for-the-badge&logo=homeassistant&logoColor=%2311BDF2&label=Minimum%20HA%20Version

[license-shield]: https://img.shields.io/github/license/scoprire87/BLE_positioning.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-%40scoprire87-blue.svg?style=for-the-badge

[pre-commit]: https://github.com/pre-commit/pre-commit
[pre-commit-shield]: https://img.shields.io/badge/pre--commit-enabled-brightgreen?style=for-the-badge

[releases-shield]: https://img.shields.io/github/release/scoprire87/BLE_positioning.svg?style=for-the-badge
[releases]: https://github.com/scoprire87/BLE_positioning/releases
[user_profile]: https://github.com/scoprire87
