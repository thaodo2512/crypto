"""Composite Strategy — Freqtrade strategy base class.

Extends IStrategy with placeholder methods. Signal logic will be
added by subsequent sub-specs (SS-09 through SS-15).

See docs/sub-specs/SS-01.md
"""

import logging

from freqtrade.strategy import IStrategy
from pandas import DataFrame

logger = logging.getLogger(__name__)


class CompositeStrategy(IStrategy):
    """Main trading strategy integrating all 5 composite signals.

    See docs/sub-specs/SS-01.md
    """

    INTERFACE_VERSION = 3

    timeframe = "1h"
    can_short = False
    startup_candle_count = 200

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Add technical indicators to the dataframe.

        See docs/sub-specs/SS-01.md
        """
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define entry conditions.

        See docs/sub-specs/SS-01.md
        """
        dataframe.loc[:, "enter_long"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Define exit conditions.

        See docs/sub-specs/SS-01.md
        """
        dataframe.loc[:, "exit_long"] = 0
        return dataframe
