"""
Canadian Forest Fire Weather Index (FWI) Subsystem.
Implements the recursive moisture and fire behavior equations from
Van Wagner & Pickett (1985, FTR 33) and Van Wagner (1987).
"""

from app.environmental.fwi.engine import FWIEngine

__all__ = ["FWIEngine"]
