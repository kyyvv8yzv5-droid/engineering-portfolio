    def reserve(self, candidate: RiskReservation, equity: float) -> None:
        allowed, reason = self.evaluate(candidate, equity)
        if not allowed:
            raise ValueError(reason)
        self.reservations[candidate.opportunity_id] = candidate
