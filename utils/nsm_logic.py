import pandas as pd
import numpy as np

def calc_z(y, mean, std):
    if pd.isna(y) or pd.isna(mean) or pd.isna(std):
        return np.nan
    if std == 0:
        return 0
    return (y - mean) / std

def dynamic_nsm_adjust(row, z_max=0.7, score_diff_threshold=0.03, adjust_factor=0.5, min_volume=50):
    current_nsm = row.get("avg_nsm_y")
    best_nsm = row.get("recommended_nsm")
    volume = row.get("unique_bookings_y", 0)

    if pd.isna(current_nsm) or pd.isna(best_nsm):
        return pd.Series([None, None, "no_data", "missing_nsm"])
    if volume < min_volume:
        return pd.Series([current_nsm, current_nsm, "no_change_low_volume", "low_volume"])

    z_cater = calc_z(row.get("first_try_cater_rate_y"), row.get("first_try_cater_rate_4wk"), row.get("first_try_cater_rate_4wk_std"))
    z_bsr = calc_z(row.get("book_search_ratio_y"), row.get("book_search_ratio_4wk"), row.get("book_search_ratio_4wk_std"))

    if pd.isna(z_cater) or pd.isna(z_bsr):
        return pd.Series([current_nsm, current_nsm, "no_data", "missing_z"])

    score_y = 0.6 * row.get("first_try_cater_rate_y", 0) + 0.4 * row.get("book_search_ratio_y", 0)
    score_4wk = 0.6 * row.get("first_try_cater_rate_4wk", 0) + 0.4 * row.get("book_search_ratio_4wk", 0)
    score_diff = score_y - score_4wk

    if z_cater < -z_max and z_bsr < -z_max:
        new_nsm = current_nsm + adjust_factor * (best_nsm - current_nsm)
        direction = "increase" if new_nsm > current_nsm else "decrease"
        return pd.Series([current_nsm, new_nsm, direction, "underperforming_z"])
    elif z_cater > z_max and z_bsr > z_max:
        new_nsm = current_nsm + adjust_factor * (best_nsm - current_nsm)
        direction = "increase" if new_nsm > current_nsm else "decrease"
        return pd.Series([current_nsm, new_nsm, direction, "overperforming_z"])
    elif abs(score_diff) > score_diff_threshold:
        new_nsm = current_nsm + adjust_factor * (best_nsm - current_nsm)
        direction = "increase" if new_nsm > current_nsm else "decrease"
        reason = f"{direction}_score_only"
        return pd.Series([current_nsm, new_nsm, direction, reason])
    else:
        return pd.Series([current_nsm, current_nsm, "no_change", "stable"])
