"""Sample Python file with intentional Behavioral Contract Violations (BCVs).

Upload this file to VeriDoc to see the pipeline detect violations across
all six BCV categories: RSV, PCV, SEV, ECV, COV, CCV.
"""


def normalize_list(data: list[float]) -> list[float]:
    """Normalize a list of numbers to the range [0, 1].

    Returns a new list with values scaled to [0, 1].
    Does not modify the input list.

    Raises:
        ValueError: If the input list is empty.
    """
    # BCV: RSV — actually returns None (mutates in place)
    # BCV: SEV — modifies the input list in place
    # BCV: ECV — does NOT raise ValueError on empty input
    if not data:
        return []
    min_val = min(data)
    max_val = max(data)
    rng = max_val - min_val
    if rng == 0:
        for i in range(len(data)):
            data[i] = 0.0
    else:
        for i in range(len(data)):
            data[i] = (data[i] - min_val) / rng
    return data  # returns same list, not a new one


def find_median(numbers: list[int]) -> float:
    """Return the median of a list of integers.

    Returns a float representing the median value.
    The input list must contain at least one element.
    Does not modify the input list.

    Raises:
        TypeError: If any element is not an integer.
    """
    # BCV: SEV — sorts the input list in place
    # BCV: ECV — does NOT raise TypeError
    sorted_nums = sorted(numbers)  # actually creates new list, but docstring says "does not modify"
    n = len(sorted_nums)
    if n == 0:
        return 0.0
    if n % 2 == 1:
        return float(sorted_nums[n // 2])
    return (sorted_nums[n // 2 - 1] + sorted_nums[n // 2]) / 2.0


def merge_dicts(base: dict, override: dict) -> dict:
    """Merge two dictionaries and return a new dictionary.

    Returns a new dictionary containing all keys from both inputs.
    Neither input dictionary is modified.
    Runs in O(n) time where n is the total number of keys.

    Raises:
        TypeError: If either argument is not a dictionary.
    """
    # BCV: SEV — modifies base in place via .update()
    # BCV: RSV — returns the mutated base, not a new dict
    # BCV: ECV — does NOT raise TypeError
    base.update(override)
    return base


def calculate_statistics(values: list[float]) -> dict:
    """Calculate mean, variance, and standard deviation.

    Returns a dictionary with keys 'mean', 'variance', and 'std_dev'.
    The input list must contain at least two elements.
    Runs in O(n) time complexity.

    Raises:
        ValueError: If the list has fewer than two elements.
        TypeError: If any element is not numeric.
    """
    # BCV: COV — does not mention that it also computes 'count' and 'sum'
    # BCV: ECV — does NOT raise ValueError for < 2 elements
    # BCV: CCV — actually O(n) but docstring is correct here
    n = len(values)
    if n == 0:
        return {"mean": 0.0, "variance": 0.0, "std_dev": 0.0, "count": 0, "sum": 0.0}
    total = sum(values)
    mean = total / n
    variance = sum((x - mean) ** 2 for x in values) / n
    std_dev = variance ** 0.5
    return {
        "mean": mean,
        "variance": variance,
        "std_dev": std_dev,
        "count": n,
        "sum": total,
    }


def flatten_nested(nested: list) -> list:
    """Flatten a nested list structure into a single flat list.

    Returns a new flat list containing all elements.
    Does not modify the input.
    Handles arbitrarily deep nesting.
    Runs in O(n) time where n is the total number of elements.

    Raises:
        TypeError: If the input is not a list.
    """
    # BCV: CCV — actually O(n*d) where d is nesting depth due to recursion
    # BCV: ECV — does NOT raise TypeError
    result = []

    def _flatten(item):
        if isinstance(item, list):
            for sub in item:
                _flatten(sub)
        else:
            result.append(item)

    _flatten(nested)
    return result
