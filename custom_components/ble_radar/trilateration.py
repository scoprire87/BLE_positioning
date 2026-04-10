import numpy as np

def find_best_room_match(current_signals, saved_rooms):
    """
    Confronta il segnale attuale con la mappa registrata.
    current_signals: dict {scanner_id: rssi}
    saved_rooms: dict {nome_stanza: [lista_vettori_rssi]}
    """
    best_room = "Sconosciuta"
    min_distance = float('inf')

    # Se non abbiamo stanze mappate, non possiamo fare nulla
    if not saved_rooms:
        return "Nessuna Mappa"

    for room_name, fingerprints in saved_rooms.items():
        for fp in fingerprints:
            dist = 0
            # Prendiamo tutti gli scanner presenti nell'impronta o nel segnale attuale
            all_scanners = set(current_signals.keys()) | set(fp.keys())
            
            for s_id in all_scanners:
                # Se uno scanner non vede il dispositivo, assegniamo -100dBm
                val_curr = current_signals.get(s_id, -100)
                val_map = fp.get(s_id, -100)
                dist += (val_curr - val_map) ** 2
            
            # Distanza Euclidea (più è bassa, più sono simili)
            euclidean_dist = np.sqrt(dist)
            
            if euclidean_dist < min_distance:
                min_distance = euclidean_dist
                best_room = room_name
                
    return best_room
