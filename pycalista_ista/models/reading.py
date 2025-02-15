"""Reading model for Ista Calista meter readings.

This module provides the Reading class that represents a single meter
reading at a specific point in time. It supports comparison operations
for chronological ordering and arithmetic operations for consumption
calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Reading:
    """A single meter reading at a specific point in time.
    
    This class represents a meter reading value along with its timestamp.
    It supports comparison operations based on the timestamp and arithmetic
    operations for calculating consumption between readings.
    
    Attributes:
        date: Timestamp of when the reading was taken
        reading: The meter reading value
        
    Example:
        ```python
        reading = Reading(datetime.now(), 100.5)
        next_reading = Reading(datetime.now(), 120.5)
        consumption = next_reading - reading  # 20.0
        ```
    """

    date: datetime
    reading: float

    def __post_init__(self) -> None:
        """Validate the reading value after initialization.
        
        Raises:
            ValueError: If reading is negative
        """
        if self.reading < 0:
            raise ValueError(f"Reading value cannot be negative: {self.reading}")

    def __sub__(self, other: Reading) -> float:
        """Calculate consumption between two readings.
        
        Args:
            other: The previous reading to subtract
            
        Returns:
            The consumption value between the two readings
            
        Raises:
            TypeError: If other is not a Reading instance
        """
        if not isinstance(other, Reading):
            raise TypeError(f"Cannot subtract {type(other)} from Reading")
        return self.reading - other.reading

    def __lt__(self, other: Reading) -> bool:
        """Compare readings chronologically.
        
        Args:
            other: Another reading to compare with
            
        Returns:
            True if this reading is earlier than other
            
        Raises:
            TypeError: If other is not a Reading instance
        """
        if not isinstance(other, Reading):
            raise TypeError(f"Cannot compare Reading with {type(other)}")
        return self.date < other.date

    def __str__(self) -> str:
        """Get string representation of the reading.
        
        Returns:
            String with reading value and formatted date
        """
        return f"{self.reading:.2f} @ {self.date.isoformat()}"
