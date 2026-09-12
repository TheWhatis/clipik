from .utils import get_skipped_required_utils
from .exception import InitializationError


def main() -> None:
    skipped_utils: list[str] = get_skipped_required_utils()

    if skipped_utils:
        skipped_utils_str: str = ', '.join(skipped_utils)
        raise InitializationError(f'Utils [{skipped_utils_str}] is required, install it')

    print("Hello from clipik!")
