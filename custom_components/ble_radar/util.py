"""General helper utilities for BLE Radar (Bermuda fork)."""

from __future__ import annotations

from functools import lru_cache


@lru_cache(64)
def mac_math_offset(mac, offset=0) -> str | None:
    """
    Perform addition/subtraction on a MAC address.

    With a MAC address in xx:xx:xx:xx:xx:xx format,
    add the offset (which may be negative) to the
    last octet, and return the full new MAC.
    If the resulting octet is outside of 00-FF then
    the function returns None.
    """
    if mac is None:
        return None
    octet = mac[-2:]
    try:
        octet_int = bytes.fromhex(octet)[0]
    except ValueError:
        return None
    if 0 <= (octet_new := octet_int + offset) <= 255:
        return f"{mac[:-3]}:{(octet_new):02x}"
    return None


@lru_cache(1024)
def mac_norm(mac: str) -> str:
    """
    Format the mac address string for entry into dev reg.

    What is returned is always lowercased, regardless of
    detected form.
    If mac is an identifiable MAC-address, it's returned
    in the xx:xx:xx:xx:xx:xx form.
    """
    to_test = mac

    if len(to_test) == 17:
        if to_test.count(":") == 5:
            return to_test.lower()
        if to_test.count("-") == 5:
            return to_test.replace("-", ":").lower()
        if to_test.count("_") == 5:
            return to_test.replace("_", ":").lower()

    elif len(to_test) == 14 and to_test.count(".") == 2:
        to_test = to_test.replace(".", "")

    if len(to_test) == 12:
        # no : included
        return ":".join(to_test.lower()[i : i + 2] for i in range(0, 12, 2))

    return mac.lower()


@lru_cache(2048)
def mac_explode_formats(mac: str) -> set[str]:
    """
    Take a formatted mac address and return the formats
    likely to be found in our device info, adverts etc
    by replacing ":" with each of "", "-", "_", ".".
    """
    altmacs = set()
    altmacs.add(mac)
    for newsep in ["", "-", "_", "."]:
        altmacs.add(mac.replace(":", newsep))
    return altmacs


def mac_redact(mac: str, tag: str | None = None) -> str:
    """Remove the centre octets of a MAC and optionally replace with a tag."""
    if tag is None:
        tag = ":"
    return f"{mac[:2]}::{tag}::{mac[-2:]}"


@lru_cache(1024)
def rssi_to_metres(rssi, ref_power=None, attenuation=None):
    """
    Convert instant rssi value to a distance in metres.
    Utilizzato dal BLE Radar come metodo di fallback per calcolare
    una stima quando l'algoritmo KNN non trova corrispondenze nella mappa.
    """
    if ref_power is None or attenuation is None:
        return False

    return 10 ** ((ref_power - rssi) / (10 * attenuation))


@lru_cache(256)
def clean_charbuf(instring: str | None) -> str:
    """
    Cleans a potentially dodgy charbuf from a bluetooth
    device of leading/trailing cruft and returns what's left.
    """
    if instring is not None:
        return instring.strip(" \t\r\n\x00").split("\0")[0]
    return ""
