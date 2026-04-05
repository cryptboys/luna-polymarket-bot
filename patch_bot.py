#!/usr/bin/env python3
"""Integrate Phase 6 Compounding Protocol into bot.py"""

from hermes_tools import read_file, patch, terminal
import os

os.chdir('/home/wawan/luna-polymarket-bot')

# Step 1: Add import for compounding module
r = read_file('src/bot.py', offset=36, limit=5)
print("IMPORTS SECTION:")
print(repr(r['content']))

# Patch: Import CompoundingEngine after EvolutionEngine
patch(path='src/bot.py',
old_string="    from src.news import NewsAnalyzer\n    from src.evolution import EvolutionEngine\n    from src.dashboard import start_dashboard",
new_string="    from src.news import NewsAnalyzer\n    from src.evolution import EvolutionEngine\n    from src.compounding import CompoundingEngine\n    from src.dashboard import start_dashboard")

# Step 2: Add CompoundingEngine init in __init__
r2 = read_file('src/bot.py', limit=150, offset=1)
content = r2['content']
# Find where EvolutionEngine is initialized
import re
match = re.search(r"self\.evolution = EvolutionEngine\(", content)
if match:
    # Find the end of the init block (next method def)
    start = match.start()
    context = content[start:start+300]
    print(f"\nEvolution init area: {repr(context[:200])}")
