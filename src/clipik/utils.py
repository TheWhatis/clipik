import shutil
import os
from clipik.variables import REQUIRED_UTILS


def get_skipped_required_utils() -> list[str]:
    skipped_utils: list[str] = []

    for util in REQUIRED_UTILS:
        if shutil.which(util) is None:
            skipped_utils.append(util)

    return skipped_utils
