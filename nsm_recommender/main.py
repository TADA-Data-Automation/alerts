from utils.helpers import Redash, Query, extract_time_only, is_valid_number
from utils.nsm_core import run_nsm_recommendation
from utils.slack import SlackBot
from dotenv import load_dotenv
from datetime import datetime, timedelta
import os
import pandas as pd

def main():
  
    # === Load environment ===
    load_dotenv()
    redash = Redash(key=os.getenv("REDASH_API_KEY"), base_url=os.getenv("REDASH_BASE_URL"))
    slack_channel = os.getenv("SLACK_CHANNEL")

    # === Dates ===
    today = datetime.today().date()
    yesterday = today - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")
    past_4_same_weekday = [(yesterday - timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(1, 5)]
    all_dates = past_4_same_weekday + [yesterday_str]

    # === Query IDs ===
    query_ids = {
        "match_rate": 4821,
        "expiry_rate": 4823,
        "first_try_cater_rate": 4824,
        "book_search_ratio": 4825,
        "median_time_to_match": 4826,
        "median_eta": 4827,
        "pricing": 4836,
    }

    # === Fetch all queries ===
    from collections import defaultdict
    def fetch_all_queries(query_ids, dates):
        results = defaultdict(list)
        for date in dates:
            queries = [Query(qid, params={"target_date": date}) for qid in query_ids.values()]
            redash.run_queries(queries)
            for q in queries:
                df = redash.get_result(q)
                df["target_date"] = date
                results[q.id].append(df)
        return {qid: pd.concat(dfs, ignore_index=True) for qid, dfs in results.items()}

    final_results = fetch_all_queries(query_ids, all_dates)

    # === Run core NSM logic ===
    summary_df, comparison_df, output_path = run_nsm_recommendation(final_results, yesterday_str)

    # === Slack summary ===
    total_blocks = len(comparison_df)
    included = len(summary_df)
    skipped = total_blocks - included

    summary_msg = (
        f"*📊 NSM Recommendations — {yesterday_str}*\n"
        f"> :increase: *Increase:* {(summary_df['action'] == 'increase').sum()}\n"
        f"> :decrease: *Decrease:* {(summary_df['action'] == 'decrease').sum()}\n"
        f"> 🚫 *Excluded (low volume or minimal change):* {skipped}\n"
        f"📎 Summary + details attached."
    )


    slack_bot = SlackBot()
    try:
        print(f"📄 Output path: {output_path}")
        print(f"📄 Type: {type(output_path)}")
        print(f"📦 File exists? {os.path.exists(output_path)}")

        slack_bot.uploadFilesWithComment(
            files=[output_path],
            channel=slack_channel,
            initial_comment=summary_msg
        )
        print("✅ Slack upload successful.")
    except Exception as e:
        print(f"❌ Slack upload failed: {e}")

# Run it
if __name__ == "__main__":
    main()
