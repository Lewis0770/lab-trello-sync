#!/usr/bin/env python3
"""
Entry point for the Trello card mirroring script.
This file is called by GitHub Actions.
"""

import mirror_priority_cards

if __name__ == "__main__":
    mirror_priority_cards.main()
