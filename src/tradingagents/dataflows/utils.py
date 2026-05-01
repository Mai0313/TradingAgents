from typing import Annotated
import logging
from datetime import date, datetime, timedelta
from collections.abc import Callable

import pandas as pd

logger = logging.getLogger(__name__)

SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]


def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType | None = None) -> None:
    """Save output DataFrame to a CSV file.

    Args:
        data (pd.DataFrame): The data to save.
        tag (str): A tag or description of the data for logging purposes.
        save_path (SavePathType | None, optional): The file path to save data. Defaults to None.
    """
    if save_path:
        data.to_csv(save_path)
        logger.info("%s saved to %s", tag, save_path)


def get_current_date() -> str:
    """Get the current date as a string.

    Returns:
        str: Current date in YYYY-MM-DD format.
    """
    return date.today().strftime("%Y-%m-%d")


def decorate_all_methods(
    decorator: Callable[[Callable[..., object]], Callable[..., object]],
) -> Callable[[type], type]:
    """Class decorator that applies a given decorator to all callable methods.

    Args:
        decorator (Callable[[Callable[..., object]], Callable[..., object]]): The decorator to apply.

    Returns:
        Callable[[type], type]: A class decorator.
    """

    def class_decorator(cls: type) -> type:
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date_input: str | datetime) -> datetime:
    """Get the next weekday for a given date (skips weekends).

    Args:
        date_input (str | datetime): The starting date, either as a datetime object or a string in YYYY-MM-DD format.

    Returns:
        datetime: The next weekday as a datetime object.
    """
    if not isinstance(date_input, datetime):
        date_input = datetime.strptime(date_input, "%Y-%m-%d")

    if date_input.weekday() >= 5:
        days_to_add = 7 - date_input.weekday()
        return date_input + timedelta(days=days_to_add)
    return date_input
