class KalmanFilter:
    def __init__(self, q=0.1, r=2.0):
        """
        q: Varianza del processo (quanto è veloce il movimento reale)
        r: Varianza della misura (quanto è rumoroso il segnale Bluetooth)
        """
        self.q = q
        self.r = r
        self.x = None  # Valore stimato
        self.p = 1.0   # Errore stimato

    def update(self, measurement):
        """Aggiorna il filtro con una nuova misura RSSI o coordinata."""
        if self.x is None:
            self.x = measurement
            return measurement
        
        # Fase di predizione
        self.p = self.p + self.q
        
        # Guadagno di Kalman
        k = self.p / (self.p + self.r)
        
        # Aggiornamento dello stato
        self.x = self.x + k * (measurement - self.x)
        self.p = (1 - k) * self.p
        
        return self.x
