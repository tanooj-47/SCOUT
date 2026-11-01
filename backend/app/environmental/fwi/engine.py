import math
from datetime import datetime
from typing import List, Optional, Tuple

from app.environmental.exceptions import FWITimeseriesGapError
from app.environmental.schemas import FWIDailyReading, FWIOutputRecord


class FWIEngine:
    """
    Standard Canadian Forest Fire Weather Index (CFS-FWI) System Engine.
    Implements mathematical equations documented in Van Wagner (1985, 1987).
    """

    # Day-length adjustments for DMC (effective day length in hours)
    DMC_DAYLENGTH_NORTH = [6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0]
    DMC_DAYLENGTH_SOUTH = [12.4, 10.9, 9.4, 8.0, 7.0, 6.0, 6.5, 7.5, 9.0, 12.8, 13.9, 13.9]

    # Day-length drying factors for DC (potential evapotranspiration adjustment)
    DC_DAYLENGTH_NORTH = [-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6]
    DC_DAYLENGTH_SOUTH = [6.4, 5.0, 2.4, 0.4, -1.6, -1.6, -1.6, -1.6, -1.6, 0.9, 3.8, 5.8]

    @classmethod
    def get_dmc_daylength(cls, lat: float, month: int) -> float:
        """Returns effective daylength (hours) for DMC based on latitude and month (1-12)."""
        idx = max(0, min(11, month - 1))
        if lat > 30.0:
            return cls.DMC_DAYLENGTH_NORTH[idx]
        elif lat < -30.0:
            return cls.DMC_DAYLENGTH_SOUTH[idx]
        return 9.0  # Equatorial / tropical approximation

    @classmethod
    def get_dc_daylength(cls, lat: float, month: int) -> float:
        """Returns daylength drying factor for DC based on latitude and month (1-12)."""
        idx = max(0, min(11, month - 1))
        if lat > 30.0:
            return cls.DC_DAYLENGTH_NORTH[idx]
        elif lat < -30.0:
            return cls.DC_DAYLENGTH_SOUTH[idx]
        return 1.39  # Equatorial / tropical approximation

    @classmethod
    def calculate_ffmc(
        cls,
        temp_c: float,
        rh_pct: float,
        wind_kmh: float,
        rain_mm: float,
        prev_ffmc: float,
    ) -> float:
        """
        Calculates Fine Fuel Moisture Code (FFMC).
        """
        # Moisture content of previous day's FFMC
        m0 = 147.2 * (101.0 - prev_ffmc) / (59.5 + prev_ffmc)

        # Rainfall wetting
        if rain_mm > 0.5:
            rf = rain_mm - 0.5
            if m0 > 150.0:
                mr = (
                    m0
                    + 42.5 * rf * math.exp(-100.0 / (251.0 - m0)) * (1.0 - math.exp(-6.93 / rf))
                    + 0.0015 * ((m0 - 150.0) ** 2) * math.sqrt(rf)
                )
            else:
                mr = m0 + 42.5 * rf * math.exp(-100.0 / (251.0 - m0)) * (1.0 - math.exp(-6.93 / rf))
            m0 = min(250.0, mr)

        # Equilibrium moisture contents
        ed = (
            0.942 * (rh_pct ** 0.679)
            + 11.0 * math.exp((rh_pct - 100.0) / 10.0)
            + 0.18 * (21.1 - temp_c) * (1.0 - math.exp(-0.115 * rh_pct))
        )
        ew = (
            0.618 * (rh_pct ** 0.753)
            + 10.0 * math.exp((rh_pct - 100.0) / 10.0)
            + 0.18 * (21.1 - temp_c) * (1.0 - math.exp(-0.115 * rh_pct))
        )

        # Drying or wetting
        if m0 > ed:
            k0 = 0.424 * (1.0 - (rh_pct / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind_kmh) * (1.0 - (rh_pct / 100.0) ** 8)
            kd = k0 * 0.581 * math.exp(0.0365 * temp_c)
            m = ed + (m0 - ed) * (10.0 ** (-kd))
        elif m0 < ew:
            k1 = 0.424 * (1.0 - ((100.0 - rh_pct) / 100.0) ** 1.7) + 0.0694 * math.sqrt(wind_kmh) * (
                1.0 - ((100.0 - rh_pct) / 100.0) ** 8
            )
            kw = k1 * 0.581 * math.exp(0.0365 * temp_c)
            m = ew - (ew - m0) * (10.0 ** (-kw))
        else:
            m = m0

        ffmc = 59.5 * (250.0 - m) / (147.2 + m)
        return max(0.0, min(101.0, ffmc))

    @classmethod
    def calculate_dmc(
        cls,
        temp_c: float,
        rh_pct: float,
        rain_mm: float,
        prev_dmc: float,
        lat: float,
        month: int,
    ) -> float:
        """
        Calculates Duff Moisture Code (DMC).
        """
        # Rainfall effect
        if rain_mm > 1.5:
            re = 0.92 * rain_mm - 1.27
            m_prev = 20.0 + math.exp(5.6348 - prev_dmc / 43.43)
            if prev_dmc <= 33.0:
                b = 100.0 / (0.5 + 0.3 * prev_dmc)
            elif prev_dmc <= 65.0:
                b = 14.0 - 1.3 * math.log(prev_dmc)
            else:
                b = 6.2 * math.log(prev_dmc) - 17.2
            mr = m_prev + (1000.0 * re) / (48.77 + b * re)
            p_prev = 244.72 - 43.43 * math.log(max(0.1, mr - 20.0))
            p = max(0.0, p_prev)
        else:
            p = prev_dmc

        # Drying effect
        le = cls.get_dmc_daylength(lat, month)
        if temp_c > -1.1:
            k = 1.894 * (temp_c + 1.1) * (100.0 - rh_pct) * le * 1e-4
        else:
            k = 0.0

        dmc = p + k
        return max(0.0, dmc)

    @classmethod
    def calculate_dc(
        cls,
        temp_c: float,
        rain_mm: float,
        prev_dc: float,
        lat: float,
        month: int,
    ) -> float:
        """
        Calculates Drought Code (DC).
        """
        # Rainfall effect
        if rain_mm > 2.8:
            rd = 0.83 * rain_mm - 1.27
            q_prev = 800.0 * math.exp(-prev_dc / 400.0)
            qr = q_prev + 3.937 * rd
            dr = 400.0 * math.log(800.0 / max(0.1, qr))
            d = max(0.0, dr)
        else:
            d = prev_dc

        # Drying factor
        lf = cls.get_dc_daylength(lat, month)
        if temp_c > -2.8:
            v = max(0.0, 0.36 * (temp_c + 2.8) + lf)
        else:
            v = 0.0

        dc = d + 0.5 * v
        return max(0.0, dc)

    @classmethod
    def calculate_isi(cls, wind_kmh: float, ffmc: float) -> float:
        """
        Calculates Initial Spread Index (ISI).
        """
        fw = math.exp(0.05039 * wind_kmh)
        m = 147.2 * (101.0 - ffmc) / (59.5 + ffmc)
        ff = 91.9 * math.exp(-0.1386 * m) * (1.0 + (m ** 5.31) / 4.93e7)
        return max(0.0, 0.208 * fw * ff)

    @classmethod
    def calculate_bui(cls, dmc: float, dc: float) -> float:
        """
        Calculates Buildup Index (BUI).
        """
        if dmc <= 0.4 * dc:
            bui = (0.8 * dmc * dc) / (dmc + 0.4 * dc) if (dmc + 0.4 * dc) > 0 else 0.0
        else:
            p = 1.0 - (0.8 * dc) / (dmc + 0.4 * dc)
            bui = dmc - p * (0.92 + (0.0114 * dmc) ** 1.7)
        return max(0.0, bui)

    @classmethod
    def calculate_fwi(cls, isi: float, bui: float) -> float:
        """
        Calculates Fire Weather Index (FWI).
        """
        if bui <= 80.0:
            fd = 0.626 * (bui ** 0.809) + 2.0
        else:
            fd = 1000.0 / (25.0 + 108.64 * math.exp(-0.023 * bui))

        b = 0.1 * isi * fd
        if b > 1.0:
            ln_s = 2.72 * ((0.434 * math.log(b)) ** 0.647)
            fwi = math.exp(ln_s)
        else:
            fwi = b
        return max(0.0, fwi)

    @classmethod
    def calculate_dsr(cls, fwi: float) -> float:
        """
        Calculates Daily Severity Rating (DSR).
        """
        return 0.0272 * (fwi ** 1.77)

    @classmethod
    def get_danger_rating(cls, fwi: float) -> str:
        """
        Classifies FWI into operational danger class.
        Standard Canadian thresholds:
        - Low: < 5.2
        - Moderate: 5.2 to < 11.2
        - High: 11.2 to < 21.3
        - Very High: 21.3 to < 38.0
        - Extreme: >= 38.0
        """
        if fwi < 5.2:
            return "Low"
        elif fwi < 11.2:
            return "Moderate"
        elif fwi < 21.3:
            return "High"
        elif fwi < 38.0:
            return "Very High"
        else:
            return "Extreme"

    @classmethod
    def calculate_series(
        cls,
        readings: List[FWIDailyReading],
        lat: float,
        initial_ffmc: float = 85.0,
        initial_dmc: float = 6.0,
        initial_dc: float = 15.0,
        strict_consecutive: bool = True,
    ) -> List[FWIOutputRecord]:
        """
        Executes sequential time-series calculation over daily noon readings.

        Gap Detection & Sequence Integrity:
        - If readings is empty: Returns an empty list [].
        - Validates that daily readings are in strict ascending calendar order.
        - Out-of-order dates: Raises FWITimeseriesGapError.
        - Duplicate dates: Raises FWITimeseriesGapError.
        - Missing calendar days:
            When strict_consecutive=True (default), raises FWITimeseriesGapError.
            When strict_consecutive=False, logs a warning and continues recursion without fabricating observations.
        """
        if not readings:
            return []

        # Validate sequence chronological integrity
        prev_date = None
        for i, reading in enumerate(readings):
            try:
                curr_date = datetime.strptime(reading.date[:10], "%Y-%m-%d").date()
            except (ValueError, TypeError) as exc:
                raise FWITimeseriesGapError(
                    f"Invalid date format in reading at index {i}: '{reading.date}'. Expected YYYY-MM-DD.",
                    details={"index": i, "date": reading.date},
                ) from exc

            if prev_date is not None:
                if curr_date < prev_date:
                    raise FWITimeseriesGapError(
                        f"Out-of-order date detected in FWI sequence: reading at index {i} has date {curr_date}, which precedes previous date {prev_date}.",
                        details={"index": i, "previous_date": str(prev_date), "current_date": str(curr_date)},
                    )
                if curr_date == prev_date:
                    raise FWITimeseriesGapError(
                        f"Duplicate date detected in FWI sequence: duplicate reading for date {curr_date} at index {i}.",
                        details={"index": i, "duplicate_date": str(curr_date)},
                    )
                gap_days = (curr_date - prev_date).days
                if gap_days > 1:
                    if strict_consecutive:
                        raise FWITimeseriesGapError(
                            f"Missing calendar day(s) detected in recursive FWI sequence: gap of {gap_days} days between {prev_date} and {curr_date} at index {i} (expected 1 day).",
                            details={
                                "index": i,
                                "previous_date": str(prev_date),
                                "current_date": str(curr_date),
                                "gap_days": gap_days,
                            },
                        )
            prev_date = curr_date

        records: List[FWIOutputRecord] = []
        curr_ffmc = initial_ffmc
        curr_dmc = initial_dmc
        curr_dc = initial_dc

        for reading in readings:
            # Parse month from ISO date string YYYY-MM-DD
            try:
                dt = datetime.strptime(reading.date[:10], "%Y-%m-%d")
                month = dt.month
            except ValueError:
                month = 7  # Default to July if parsing fails

            ffmc = cls.calculate_ffmc(
                temp_c=reading.temperature_celsius,
                rh_pct=reading.relative_humidity,
                wind_kmh=reading.wind_speed_kmh,
                rain_mm=reading.precipitation_mm,
                prev_ffmc=curr_ffmc,
            )
            dmc = cls.calculate_dmc(
                temp_c=reading.temperature_celsius,
                rh_pct=reading.relative_humidity,
                rain_mm=reading.precipitation_mm,
                prev_dmc=curr_dmc,
                lat=lat,
                month=month,
            )
            dc = cls.calculate_dc(
                temp_c=reading.temperature_celsius,
                rain_mm=reading.precipitation_mm,
                prev_dc=curr_dc,
                lat=lat,
                month=month,
            )
            isi = cls.calculate_isi(wind_kmh=reading.wind_speed_kmh, ffmc=ffmc)
            bui = cls.calculate_bui(dmc=dmc, dc=dc)
            fwi = cls.calculate_fwi(isi=isi, bui=bui)
            dsr = cls.calculate_dsr(fwi=fwi)
            danger = cls.get_danger_rating(fwi=fwi)

            records.append(
                FWIOutputRecord(
                    date=reading.date,
                    ffmc=round(ffmc, 1),
                    dmc=round(dmc, 1),
                    dc=round(dc, 1),
                    isi=round(isi, 1),
                    bui=round(bui, 1),
                    fwi=round(fwi, 1),
                    dsr=round(dsr, 2),
                    danger_rating=danger,
                )
            )

            # Update state for next day
            curr_ffmc = ffmc
            curr_dmc = dmc
            curr_dc = dc

        return records

    # Ergonomic alias for calculate_series
    calculate_timeseries = calculate_series
