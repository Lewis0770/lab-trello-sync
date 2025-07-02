from modules.funding_sync import parse_csv, filter_keywords, trello_writer

def main():
    csv_path = "data/funding_export.csv"  # <- update this as needed
    keyword_path = "modules/funding_sync/keywords.json"

    # Load data
    funding_entries = parse_csv.load_funding_csv(csv_path)
    lab_keywords = filter_keywords.load_keywords(keyword_path)

    # Track results
    semi_filtered = []
    dummy_filtered = []

    for entry in funding_entries:
        if not filter_keywords.is_future_entry(entry):
            continue  # Skip expired grants

        if filter_keywords.contains_keyword(entry, lab_keywords):
            semi_filtered.append(entry)
        else:
            dummy_filtered.append(entry)

    print(f"\n🔎 Semi-Filtered Matches: {len(semi_filtered)}")
    print(f"📄 Dummy (Unmatched): {len(dummy_filtered)}\n")

    for entry in semi_filtered:
        trello_writer.create_card(entry, list_name="Semi-Filtered")

    for entry in dummy_filtered:
        trello_writer.create_card(entry, list_name="Dummy List")

if __name__ == "__main__":
    main()
