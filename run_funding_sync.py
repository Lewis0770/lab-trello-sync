from modules.funding_sync import parse_csv, filter_keywords, trello_writer

def main():
    csv_path = "CSV/grants-gov-opp-search--20250702135040.csv"
    keyword_path = "modules/funding_sync/keywords.json"

    print("🚀 Starting Funding Sync Process...")

    # Load keywords for cleanup
    lab_keywords = filter_keywords.load_keywords(keyword_path)
    
    # Clean up existing incorrectly categorized cards
    trello_writer.cleanup_existing_cards(lab_keywords)

    # Load data
    funding_entries = parse_csv.load_funding_csv(csv_path)
    
    if not funding_entries:
        print("❌ No funding entries loaded. Exiting.")
        return

    # Track results
    semi_filtered = []
    dummy_filtered = []

    for entry in funding_entries:
        if not filter_keywords.is_future_entry(entry):
            continue  

        if filter_keywords.contains_keyword(entry, lab_keywords):
            semi_filtered.append(entry)
        else:
            dummy_filtered.append(entry)

    print(f"\n🔎 Semi-Filtered Matches: {len(semi_filtered)}")
    print(f"📄 Dummy (Unmatched): {len(dummy_filtered)}\n")

    # Create Trello cards
    print("📝 Creating Trello cards...")
    created_semi = 0
    created_dummy = 0

    for entry in semi_filtered:
        trello_writer.create_card(entry, list_name="Semi-Filtered")
        created_semi += 1

    for entry in dummy_filtered:
        trello_writer.create_card(entry, list_name="Dummy List")
        created_dummy += 1

    print(f"\n🎉 Process Complete!")
    print(f"✅ Created {created_semi} cards in Semi-Filtered list")
    print(f"✅ Created {created_dummy} cards in Dummy List")

if __name__ == "__main__":
    main()