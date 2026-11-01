import pytest

from app.environmental.exceptions import FWITimeseriesGapError
from app.environmental.fwi.benchmark import VAN_WAGNER_BENCHMARK_DAYS, run_benchmark_validation
from app.environmental.fwi.engine import FWIEngine
from app.environmental.schemas import FWIDailyReading


class TestFWIEngine:

    def test_day_one_mathematical_consistency(self):
        # Day 1 of Van Wagner & Pickett (1985) / NOR-X-424
        reading = FWIDailyReading(
            date="1985-04-13",
            temperature_celsius=17.0,
            relative_humidity=42.0,
            wind_speed_kmh=25.0,
            precipitation_mm=0.0,
        )

        records = FWIEngine.calculate_series(
            readings=[reading],
            lat=40.0,
            initial_ffmc=85.0,
            initial_dmc=6.0,
            initial_dc=15.0,
        )

        assert len(records) == 1
        rec = records[0]

        # Assert published outputs within 0.1 tolerance
        assert abs(rec.ffmc - 87.7) <= 0.1
        assert abs(rec.dmc - 8.5) <= 0.1
        assert abs(rec.dc - 19.0) <= 0.1
        assert abs(rec.isi - 10.9) <= 0.1
        assert abs(rec.bui - 8.5) <= 0.1
        assert abs(rec.fwi - 10.1) <= 0.1
        assert rec.danger_rating == "Moderate"

    def test_rain_suppression_effect(self):
        # Heavy rain should dramatically reduce FFMC and DMC
        reading_dry = FWIDailyReading(
            date="2026-06-01",
            temperature_celsius=30.0,
            relative_humidity=20.0,
            wind_speed_kmh=20.0,
            precipitation_mm=0.0,
        )
        reading_rain = FWIDailyReading(
            date="2026-06-02",
            temperature_celsius=18.0,
            relative_humidity=95.0,
            wind_speed_kmh=10.0,
            precipitation_mm=25.0,
        )

        records = FWIEngine.calculate_series([reading_dry, reading_rain], lat=30.0)
        assert len(records) == 2
        rec_dry, rec_rain = records[0], records[1]

        assert rec_dry.ffmc > 88.0
        assert rec_rain.ffmc < 50.0  # Heavy rain saturates fine fuel
        assert rec_rain.fwi < 1.0
        assert rec_rain.danger_rating == "Low"

    def test_danger_rating_scale(self):
        assert FWIEngine.get_danger_rating(3.0) == "Low"
        assert FWIEngine.get_danger_rating(8.0) == "Moderate"
        assert FWIEngine.get_danger_rating(15.0) == "High"
        assert FWIEngine.get_danger_rating(30.0) == "Very High"
        assert FWIEngine.get_danger_rating(45.0) == "Extreme"

    def test_benchmark_validation_suite(self):
        passed, details = run_benchmark_validation(tolerance=0.2)
        for d in details:
            assert d["passed"] is True, f"Benchmark failed on {d['date']}: max_diff={d['max_diff']}"
        assert passed is True

    def test_unrounded_numerical_differences_against_nor_x_424(self):
        """
        Verifies unrounded numerical precision against NOR-X-424 Table 7 published ground truth.
        Asserts that absolute differences do not exceed 0.05 for any variable across all 5 benchmark days.
        """
        curr_ffmc, curr_dmc, curr_dc = 85.0, 6.0, 15.0
        for row in VAN_WAGNER_BENCHMARK_DAYS:
            date_str, temp, rh, wind, rain = row[0], row[1], row[2], row[3], row[4]
            exp_ffmc, exp_dmc, exp_dc, exp_isi, exp_bui, exp_fwi = row[5], row[6], row[7], row[8], row[9], row[10]
            exp_dsr = round(0.0272 * (exp_fwi ** 1.77), 2)
            month = int(date_str[5:7])

            ffmc = FWIEngine.calculate_ffmc(temp, rh, wind, rain, curr_ffmc)
            dmc = FWIEngine.calculate_dmc(temp, rh, rain, curr_dmc, lat=40.0, month=month)
            dc = FWIEngine.calculate_dc(temp, rain, curr_dc, lat=40.0, month=month)
            isi = FWIEngine.calculate_isi(wind, ffmc)
            bui = FWIEngine.calculate_bui(dmc, dc)
            fwi = FWIEngine.calculate_fwi(isi, bui)
            dsr = FWIEngine.calculate_dsr(fwi)

            # Assert unrounded differences are <= 0.05
            assert abs(ffmc - exp_ffmc) <= 0.05, f"FFMC diff {abs(ffmc - exp_ffmc)} on {date_str}"
            assert abs(dmc - exp_dmc) <= 0.05, f"DMC diff {abs(dmc - exp_dmc)} on {date_str}"
            assert abs(dc - exp_dc) <= 0.05, f"DC diff {abs(dc - exp_dc)} on {date_str}"
            assert abs(isi - exp_isi) <= 0.05, f"ISI diff {abs(isi - exp_isi)} on {date_str}"
            assert abs(bui - exp_bui) <= 0.05, f"BUI diff {abs(bui - exp_bui)} on {date_str}"
            assert abs(fwi - exp_fwi) <= 0.05, f"FWI diff {abs(fwi - exp_fwi)} on {date_str}"
            assert abs(dsr - exp_dsr) <= 0.02, f"DSR diff {abs(dsr - exp_dsr)} on {date_str}"

            curr_ffmc, curr_dmc, curr_dc = ffmc, dmc, dc

    def test_timeseries_gap_detection_consecutive(self):
        """Verifies that strictly consecutive daily readings calculate successfully."""
        r1 = FWIDailyReading(date="2026-05-01", temperature_celsius=25.0, relative_humidity=40.0, wind_speed_kmh=15.0, precipitation_mm=0.0)
        r2 = FWIDailyReading(date="2026-05-02", temperature_celsius=26.0, relative_humidity=38.0, wind_speed_kmh=18.0, precipitation_mm=0.0)
        r3 = FWIDailyReading(date="2026-05-03", temperature_celsius=27.0, relative_humidity=35.0, wind_speed_kmh=12.0, precipitation_mm=0.0)

        results = FWIEngine.calculate_series([r1, r2, r3], lat=28.0)
        assert len(results) == 3
        assert results[0].date == "2026-05-01"
        assert results[2].date == "2026-05-03"

    def test_timeseries_gap_detection_one_missing_day(self):
        """Verifies that a gap of one calendar day raises FWITimeseriesGapError."""
        r1 = FWIDailyReading(date="2026-05-01", temperature_celsius=25.0, relative_humidity=40.0, wind_speed_kmh=15.0, precipitation_mm=0.0)
        # Missing 2026-05-02
        r2 = FWIDailyReading(date="2026-05-03", temperature_celsius=27.0, relative_humidity=35.0, wind_speed_kmh=12.0, precipitation_mm=0.0)

        with pytest.raises(FWITimeseriesGapError) as exc_info:
            FWIEngine.calculate_series([r1, r2], lat=28.0)
        assert "gap of 2 days" in str(exc_info.value)
        assert exc_info.value.details["gap_days"] == 2

    def test_timeseries_gap_detection_multiple_missing_days(self):
        """Verifies that a gap of multiple calendar days raises FWITimeseriesGapError."""
        r1 = FWIDailyReading(date="2026-05-01", temperature_celsius=25.0, relative_humidity=40.0, wind_speed_kmh=15.0, precipitation_mm=0.0)
        # Gap from May 1 to May 10 (9 days)
        r2 = FWIDailyReading(date="2026-05-10", temperature_celsius=28.0, relative_humidity=30.0, wind_speed_kmh=20.0, precipitation_mm=0.0)

        with pytest.raises(FWITimeseriesGapError) as exc_info:
            FWIEngine.calculate_series([r1, r2], lat=28.0)
        assert exc_info.value.details["gap_days"] == 9

    def test_timeseries_gap_detection_duplicate_dates(self):
        """Verifies that duplicate dates raise FWITimeseriesGapError."""
        r1 = FWIDailyReading(date="2026-05-01", temperature_celsius=25.0, relative_humidity=40.0, wind_speed_kmh=15.0, precipitation_mm=0.0)
        r2 = FWIDailyReading(date="2026-05-01", temperature_celsius=26.0, relative_humidity=38.0, wind_speed_kmh=18.0, precipitation_mm=0.0)

        with pytest.raises(FWITimeseriesGapError) as exc_info:
            FWIEngine.calculate_series([r1, r2], lat=28.0)
        assert "Duplicate date detected" in str(exc_info.value)
        assert exc_info.value.details["duplicate_date"] == "2026-05-01"

    def test_timeseries_gap_detection_out_of_order_dates(self):
        """Verifies that chronologically inverted readings raise FWITimeseriesGapError."""
        r1 = FWIDailyReading(date="2026-05-02", temperature_celsius=26.0, relative_humidity=38.0, wind_speed_kmh=18.0, precipitation_mm=0.0)
        r2 = FWIDailyReading(date="2026-05-01", temperature_celsius=25.0, relative_humidity=40.0, wind_speed_kmh=15.0, precipitation_mm=0.0)

        with pytest.raises(FWITimeseriesGapError) as exc_info:
            FWIEngine.calculate_series([r1, r2], lat=28.0)
        assert "Out-of-order date detected" in str(exc_info.value)

    def test_timeseries_gap_detection_empty_input(self):
        """Verifies that empty readings input returns empty list []."""
        results = FWIEngine.calculate_series([], lat=28.0)
        assert results == []

    def test_timeseries_allow_gaps_policy(self):
        """Verifies that strict_consecutive=False allows non-consecutive series without exception."""
        r1 = FWIDailyReading(date="2026-05-01", temperature_celsius=25.0, relative_humidity=40.0, wind_speed_kmh=15.0, precipitation_mm=0.0)
        r2 = FWIDailyReading(date="2026-05-05", temperature_celsius=28.0, relative_humidity=30.0, wind_speed_kmh=20.0, precipitation_mm=0.0)

        results = FWIEngine.calculate_series([r1, r2], lat=28.0, strict_consecutive=False)
        assert len(results) == 2
        assert results[1].date == "2026-05-05"

    def test_calculate_timeseries_alias(self):
        """Verifies that calculate_timeseries is an exact functional alias to calculate_series."""
        r1 = FWIDailyReading(date="2026-05-01", temperature_celsius=25.0, relative_humidity=40.0, wind_speed_kmh=15.0, precipitation_mm=0.0)
        res_series = FWIEngine.calculate_series([r1], lat=28.0)
        res_timeseries = FWIEngine.calculate_timeseries([r1], lat=28.0)
        assert len(res_series) == len(res_timeseries) == 1
        assert res_series[0].fwi == res_timeseries[0].fwi
