
import json
from macro_crunch.macros import compute_macros, check_fit
from macro_crunch.llm import propose


table = json.load(open("data/ingredients.json"))
remaining = {"cal": 600, "protein": 45, "carbs": 60, "fat": 15}

meal = propose(["chicken_breast", "white_rice_cooked", "broccoli"], remaining)
computed = compute_macros(meal, table)
passes, deltas = check_fit(computed, remaining)

print(meal)
print(computed)
print(passes, deltas)