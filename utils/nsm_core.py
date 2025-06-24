import pandas as pd
import numpy as np
import os
from utils.helpers import extract_time_only, is_valid_number
from utils.nsm_logic import dynamic_nsm_adjust
from utils.excel_tools import save_excel

def run_nsm_recommendation(final_results, yesterday_str):
    query_ids = {
        "match_rate": 4821,
        "expiry_rate": 4823,
        "first_try_cater_rate": 4824,
        "book_search_ratio": 4825,
        "median_time_to_match": 4826,
        "median_eta": 4827,
        "pricing": 4836,
    }

    metrics_with_std = {
        4824: ["first_try_cater_rate"],
        4825: ["book_search_ratio"]
    }

    df_yesterday = extract_time_only(final_results[query_ids["match_rate"]].copy())
    df_yesterday = df_yesterday[df_yesterday["target_date"] == yesterday_str]
    top15_pairs = (
        df_yesterday.sort_values(["time_block", "unique_bookings"], ascending=[True, False])
        .groupby("time_block")
        .head(15)[["zone", "time_block"]]
        .drop_duplicates()
        .reset_index(drop=True)
    )
    comparison_df = top15_pairs.copy()

    for label, qid in query_ids.items():
        df = extract_time_only(final_results[qid].copy())
        df["target_date"] = pd.to_datetime(df["target_date"])
        df_hist = df[df["target_date"] != pd.to_datetime(yesterday_str)]
        df_yday = df[df["target_date"] == pd.to_datetime(yesterday_str)]

        metric_cols = [col for col in df.columns if col not in ["zone", "time_block", "target_date"]]
        numeric_cols = [col for col in metric_cols if df[col].dropna().apply(is_valid_number).all()]
        df[numeric_cols] = df[numeric_cols].apply(pd.to_numeric, errors="coerce")

        df_4wk = df_hist.groupby(["zone", "time_block"])[numeric_cols].mean().add_suffix("_4wk").reset_index()
        df_yday = df_yday.groupby(["zone", "time_block"])[numeric_cols].mean().add_suffix("_y").reset_index()

        if qid in metrics_with_std:
            std_metrics = metrics_with_std[qid]
            df_std = df_hist.groupby(["zone", "time_block"])[std_metrics].std().add_suffix("_4wk_std").reset_index()
            comparison_df = comparison_df.merge(df_std, on=["zone", "time_block"], how="left")

        comparison_df = comparison_df.merge(df_4wk, on=["zone", "time_block"], how="left")
        comparison_df = comparison_df.merge(df_yday, on=["zone", "time_block"], how="left")

    for col in comparison_df.columns:
        if "_4wk" in col:
            comparison_df[col] = comparison_df.groupby("time_block")[col].transform(lambda x: x.fillna(x.median()))
            comparison_df[col] = comparison_df[col].fillna(comparison_df[col].median())

    comparison_df["score_y"] = 0.6 * comparison_df["first_try_cater_rate_y"] + 0.4 * comparison_df["book_search_ratio_y"]
    comparison_df["score_4wk"] = 0.6 * comparison_df["first_try_cater_rate_4wk"] + 0.4 * comparison_df["book_search_ratio_4wk"]
    comparison_df["score_diff"] = comparison_df["score_y"] - comparison_df["score_4wk"]

    nsm_hist = extract_time_only(final_results[query_ids["pricing"]].copy())
    nsm_hist["target_date"] = pd.to_datetime(nsm_hist["target_date"])
    nsm_hist = nsm_hist[nsm_hist["target_date"] != pd.to_datetime(yesterday_str)]

    cater_hist = extract_time_only(final_results[4824].copy())
    bsr_hist = extract_time_only(final_results[4825].copy())
    for df in [cater_hist, bsr_hist]:
        df["target_date"] = pd.to_datetime(df["target_date"])

    hist_df = nsm_hist.merge(cater_hist, on=["zone", "time_block", "target_date"])
    hist_df = hist_df.merge(bsr_hist, on=["zone", "time_block", "target_date"])
    hist_df["nsm_bin"] = (hist_df["avg_nsm"] / 0.05).round() * 0.05

    nsm_perf = hist_df.groupby(["zone", "time_block", "nsm_bin"])[["first_try_cater_rate", "book_search_ratio"]].mean().reset_index()
    nsm_perf["score"] = 0.6 * nsm_perf["first_try_cater_rate"] + 0.4 * nsm_perf["book_search_ratio"]

    best_nsm_per_block = nsm_perf.sort_values("score", ascending=False).drop_duplicates(subset=["zone", "time_block"])
    best_nsm_per_block = best_nsm_per_block.rename(columns={"nsm_bin": "recommended_nsm"})[["zone", "time_block", "recommended_nsm"]]
    comparison_df = comparison_df.merge(best_nsm_per_block, on=["zone", "time_block"], how="left")

    comparison_df[["old_nsm", "recommended_nsm", "action", "reason_for_change"]] = comparison_df.apply(dynamic_nsm_adjust, axis=1)
    comparison_df["delta_nsm"] = comparison_df["recommended_nsm"] - comparison_df["old_nsm"]

    delta_threshold = 2
    filter_mask = (
        (comparison_df["action"].isin(["increase", "decrease"])) &
        (comparison_df["delta_nsm"].abs() < delta_threshold) &
        (~comparison_df["reason_for_change"].str.contains("z"))
    )
    final_df = comparison_df[~filter_mask].copy()

    summary_df = final_df[
        (final_df["action"].isin(["increase", "decrease"])) &
        (final_df["unique_bookings_y"] >= 50)
    ][[
        "zone", "time_block", "old_nsm", "recommended_nsm",
        "delta_nsm", "avg_dynamic_surge_level_y", "action"
    ]].sort_values(["zone", "time_block"]).reset_index(drop=True)

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, f"nsm_recommendations_{yesterday_str}.xlsx")
    
    save_excel(summary_df, final_df.sort_values(["zone", "time_block"]).reset_index(drop=True), output_path)

    return summary_df, final_df, output_path
